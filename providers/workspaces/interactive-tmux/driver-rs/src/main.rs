//! `itmux` — CLI entry point with the same subcommand surface as the Python
//! driver's `python -m interactive_tmux`. Each subcommand emits JSON on
//! stdout in the exact shape the Python equivalent emits, so `smoke-rs.sh`
//! can mirror `smoke.sh` line-for-line.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode, Stdio};
use std::time::Duration;

use clap::{Parser, Subcommand, ValueEnum};
use serde::Serialize;
use serde_json::{json, Value};

use itmux::adapter::{Agent, AGENTS};
use itmux::registry;
use itmux::run::contract::{
    AgentRunEvent, AgentRunEventPayload, AgentRunLimits, AgentRunOutcome, AgentRunResult,
    AgentRunSpec, ObservabilityExporter,
};
use itmux::run::harness_observer::{
    ClaudeTranscriptObserver, CodexExecJsonObserver, HarnessObserver,
};
use itmux::run::observability::{
    langfuse_api_base_url, langfuse_basic_auth_header, langfuse_trace_id_for_run,
    ObservabilityFanout,
};
use itmux::run::orchestrator::CancelToken;
#[cfg(unix)]
use itmux::run::orchestrator::{CancelEscalator, SignalKind};
use itmux::run::workspace_executor::{generate_run_id, now_rfc3339};
use itmux::workspace::{
    StartOptions, Workspace, DEFAULT_IMAGE, DEFAULT_STARTUP_TIMEOUT_S, DEFAULT_TMUX_COLS,
    DEFAULT_TMUX_ROWS, DEFAULT_WORKDIR,
};

const LANGFUSE_TRACE_QUERY_TIMEOUT: Duration = Duration::from_secs(10);
const DEFAULT_LANGFUSE_QUERY_FROM_START_TIME: &str = "2020-01-01T00:00:00Z";
const DEFAULT_LANGFUSE_QUERY_TO_START_TIME: &str = "2100-01-01T00:00:00Z";

#[derive(Parser, Debug)]
#[command(
    name = "itmux",
    about = "Rust port of the interactive-tmux workspace driver.",
    version
)]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
enum CodexRunMode {
    /// Launch the interactive Codex TUI in the Docker workspace.
    Tui,
    /// Run `codex exec --json` and normalize its structured event stream.
    Exec,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RunDispatch {
    WorkspaceTui,
    CodexExec,
    AgentMismatch,
}

#[derive(Subcommand, Debug)]
enum Cmd {
    /// Start a workspace.
    Start {
        #[arg(long)]
        name: String,
        #[arg(long, default_value = DEFAULT_IMAGE)]
        image: String,
        #[arg(long, default_value = DEFAULT_WORKDIR)]
        workdir: String,
        /// Comma-separated list of agents to enable. Default: all three.
        #[arg(long, default_value = "claude,codex,gemini")]
        agents: String,
        #[arg(long, default_value_t = DEFAULT_TMUX_COLS)]
        cols: u32,
        #[arg(long, default_value_t = DEFAULT_TMUX_ROWS)]
        rows: u32,
        #[arg(long, default_value_t = DEFAULT_STARTUP_TIMEOUT_S)]
        startup_timeout: f64,
        /// Raise on any agent's startup readiness miss (default: lax, like the Python CLI).
        #[arg(long, default_value_t = false)]
        strict_startup: bool,
    },
    /// Send a message to an agent.
    Send {
        #[arg(long)]
        name: String,
        #[arg(long)]
        agent: String,
        #[arg(long)]
        text: String,
    },
    /// Block until agent is ready, or timeout.
    #[command(name = "await")]
    Await {
        #[arg(long)]
        name: String,
        #[arg(long)]
        agent: String,
        #[arg(long, default_value_t = 60.0)]
        timeout: f64,
        #[arg(long, default_value_t = 4)]
        stable_polls: u32,
        #[arg(long, default_value_t = 0.5)]
        poll_interval: f64,
        #[arg(long, default_value_t = 2.0)]
        warmup: f64,
    },
    /// Print captured pane contents.
    Capture {
        #[arg(long)]
        name: String,
        #[arg(long)]
        agent: String,
    },
    /// Run an arbitrary command via `docker exec` inside the workspace
    /// container — bypasses tmux; useful for liveness checks.
    Exec {
        #[arg(long)]
        name: String,
        /// Command and args (after `--`).
        #[arg(last = true, required = true)]
        argv: Vec<String>,
    },
    /// Stop a workspace and remove its throwaway credential dir.
    Stop {
        #[arg(long)]
        name: String,
    },
    /// Run a recipe end-to-end: provision -> submit -> await -> capture ->
    /// stop, streaming R6 event JSONL on stdout and emitting a final result.
    Run {
        /// Path to a recipe directory (EXP-0005 shape).
        #[arg(long)]
        recipe: PathBuf,
        /// The task text handed to the recipe's default agent.
        #[arg(long)]
        task: String,
        /// Container image. Defaults to the interactive-tmux workspace image.
        #[arg(long, default_value = DEFAULT_IMAGE)]
        image: String,
        /// How Codex recipes execute. `tui` preserves the current interactive
        /// workspace behavior; `exec` uses structured `codex exec --json`
        /// telemetry for rich tool/token/cost observability.
        #[arg(long, default_value = "tui")]
        codex_mode: CodexRunMode,
        /// Codex binary used when `--codex-mode exec`.
        #[arg(long, default_value = "codex")]
        codex_bin: String,
        /// Sandbox policy passed to `codex exec` when `--codex-mode exec`.
        #[arg(long, default_value = "read-only")]
        codex_sandbox: String,
        /// Emit event JSONL on stdout (on by default). `--json false`
        /// suppresses the event stream and prints only a human result summary.
        #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
        json: bool,
        /// Write the final `AgentRunResult` JSON to this file instead of a
        /// `type:"result"` line on stdout.
        #[arg(long)]
        result_file: Option<PathBuf>,
        /// Wall-clock timeout, in seconds, for the whole run. Maps to
        /// `AgentRunSpec.limits.timeout_s`. When omitted, the orchestrator's
        /// default await bound applies (behaviour unchanged from before this
        /// flag existed). Must be a finite, strictly-positive number - a
        /// non-finite or non-positive value is rejected with a clean CLI error
        /// (never a downstream `Duration::from_secs_f64` panic).
        #[arg(long, value_parser = parse_positive_timeout)]
        timeout: Option<f64>,
        /// Path to a `.env` file supplying run credentials. Secret values are
        /// loaded from the file and never appear in command arguments.
        #[arg(long)]
        env_file: Option<PathBuf>,
        #[arg(long, default_value_t = false)]
        allow_host_auth_fallback: bool,
        /// Append normalized run events to this JSONL file as an observability
        /// artifact. Relative paths resolve in the driver process.
        #[arg(long)]
        observability_file: Option<PathBuf>,
        /// Enable fallback/collector LangFuse OTLP export using LANGFUSE_*
        /// credentials. Prefer official LangFuse Claude/Codex plugins for
        /// rich Claude/Codex trace UX.
        #[arg(long)]
        observability_langfuse: bool,
        /// Force fallback LangFuse OTLP export even when TRACE_TO_LANGFUSE
        /// indicates an official LangFuse plugin is already tracing.
        #[arg(long)]
        observability_langfuse_force: bool,
        /// LangFuse origin or OTLP endpoint. Defaults to LANGFUSE_BASE_URL.
        #[arg(long)]
        langfuse_base_url: Option<String>,
        /// LangFuse project id used to report UI trace links. Defaults to
        /// LANGFUSE_PROJECT_ID when set.
        #[arg(long)]
        langfuse_project_id: Option<String>,
        /// Label for the LangFuse observability link in AgentRunResult.
        #[arg(long)]
        langfuse_label: Option<String>,
    },
    /// Run `codex exec --json`, normalize its event stream, and fan it out to
    /// observability exporters. This is the first runnable harness-observer
    /// path for Codex token/usage events.
    #[command(name = "codex-exec")]
    CodexExec {
        /// Prompt handed to `codex exec`.
        #[arg(long)]
        prompt: String,
        /// Codex binary to execute.
        #[arg(long, default_value = "codex")]
        codex_bin: String,
        /// Optional model override passed as `--model`.
        #[arg(long)]
        model: Option<String>,
        /// Sandbox policy passed to `codex exec`.
        #[arg(long, default_value = "read-only")]
        sandbox: String,
        /// Emit normalized AgentRunEvent JSONL on stdout.
        #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
        json: bool,
        /// Write the final `AgentRunResult` JSON to this file. If omitted and
        /// `--json true`, the result is emitted as a final `type:"result"`
        /// event on stdout.
        #[arg(long)]
        result_file: Option<PathBuf>,
        /// Append normalized observer events to this JSONL file.
        #[arg(long)]
        observability_file: Option<PathBuf>,
        /// Enable fallback/collector LangFuse OTLP export using LANGFUSE_*
        /// credentials. Prefer official LangFuse Claude/Codex plugins for
        /// rich Claude/Codex trace UX.
        #[arg(long)]
        observability_langfuse: bool,
        /// Force fallback LangFuse OTLP export even when TRACE_TO_LANGFUSE
        /// indicates an official LangFuse plugin is already tracing.
        #[arg(long)]
        observability_langfuse_force: bool,
        /// LangFuse origin or OTLP endpoint. Defaults to LANGFUSE_BASE_URL.
        #[arg(long)]
        langfuse_base_url: Option<String>,
        /// LangFuse project id used to report UI trace links. Defaults to
        /// LANGFUSE_PROJECT_ID when set.
        #[arg(long)]
        langfuse_project_id: Option<String>,
        /// Label for the LangFuse observability link in AgentRunResult.
        #[arg(long)]
        langfuse_label: Option<String>,
    },
    /// Read Claude Code transcript JSONL, normalize tool/usage events, and fan
    /// them out to observability exporters.
    #[command(name = "claude-transcript")]
    ClaudeTranscript {
        /// Claude transcript JSONL file. Use `-` to read stdin.
        #[arg(long)]
        transcript: PathBuf,
        /// Optional run id. Defaults to a generated `itmux` run id.
        #[arg(long)]
        run_id: Option<String>,
        /// Emit normalized AgentRunEvent JSONL on stdout.
        #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
        json: bool,
        /// Write the final `AgentRunResult` JSON to this file. If omitted and
        /// `--json true`, the result is emitted as a final `type:"result"`
        /// event on stdout.
        #[arg(long)]
        result_file: Option<PathBuf>,
        /// Append normalized observer events to this JSONL file.
        #[arg(long)]
        observability_file: Option<PathBuf>,
        /// Enable fallback/collector LangFuse OTLP export using LANGFUSE_*
        /// credentials. Prefer official LangFuse Claude/Codex plugins for
        /// rich Claude/Codex trace UX.
        #[arg(long)]
        observability_langfuse: bool,
        /// Force fallback LangFuse OTLP export even when TRACE_TO_LANGFUSE
        /// indicates an official LangFuse plugin is already tracing.
        #[arg(long)]
        observability_langfuse_force: bool,
        /// LangFuse origin or OTLP endpoint. Defaults to LANGFUSE_BASE_URL.
        #[arg(long)]
        langfuse_base_url: Option<String>,
        /// LangFuse project id used to report UI trace links. Defaults to
        /// LANGFUSE_PROJECT_ID when set.
        #[arg(long)]
        langfuse_project_id: Option<String>,
        /// Label for the LangFuse observability link in AgentRunResult.
        #[arg(long)]
        langfuse_label: Option<String>,
    },
    /// Query LangFuse observations for an exported trace. This is the first
    /// agent-facing read path for inspecting traces after export.
    #[command(name = "langfuse-trace")]
    LangFuseTrace {
        /// Existing 32-hex LangFuse/OpenTelemetry trace id.
        #[arg(long, conflicts_with = "run_id")]
        trace_id: Option<String>,
        /// `itmux` run id; the command derives the deterministic trace id used
        /// by the exporter.
        #[arg(long, conflicts_with = "trace_id")]
        run_id: Option<String>,
        /// LangFuse origin or OTLP endpoint. Defaults to LANGFUSE_BASE_URL.
        #[arg(long)]
        langfuse_base_url: Option<String>,
        /// Env var containing the LangFuse public key.
        #[arg(long, default_value = "LANGFUSE_PUBLIC_KEY")]
        public_key_env: String,
        /// Env var containing the LangFuse secret key.
        #[arg(long, default_value = "LANGFUSE_SECRET_KEY")]
        secret_key_env: String,
        /// Lower bound for observation start time. Keep this bounded.
        #[arg(long, default_value = DEFAULT_LANGFUSE_QUERY_FROM_START_TIME)]
        from_start_time: String,
        /// Upper bound for observation start time. Keep this bounded.
        #[arg(long, default_value = DEFAULT_LANGFUSE_QUERY_TO_START_TIME)]
        to_start_time: String,
        /// LangFuse observation field groups to request.
        #[arg(long, default_value = "core,basic,usage,trace_context")]
        fields: String,
        /// Maximum observation rows to request.
        #[arg(long, default_value_t = 100)]
        limit: u32,
        /// Include trace-scoped LangFuse scores in the summary.
        #[arg(long, default_value_t = false)]
        include_scores: bool,
        /// Maximum score rows to request when --include-scores is set.
        #[arg(long, default_value_t = 20)]
        score_limit: u32,
        /// LangFuse read API to use.
        #[arg(long, value_enum, default_value = "observations-v2")]
        api: LangFuseTraceApi,
        /// Response shape for agents: compact summary or full backend response.
        #[arg(long, value_enum, default_value = "full")]
        output: LangFuseTraceOutput,
    },
    /// List recent LangFuse traces so agents can discover runs to inspect.
    #[command(name = "langfuse-traces")]
    LangFuseTraces {
        /// LangFuse origin or OTLP endpoint. Defaults to LANGFUSE_BASE_URL.
        #[arg(long)]
        langfuse_base_url: Option<String>,
        /// Env var containing the LangFuse public key.
        #[arg(long, default_value = "LANGFUSE_PUBLIC_KEY")]
        public_key_env: String,
        /// Env var containing the LangFuse secret key.
        #[arg(long, default_value = "LANGFUSE_SECRET_KEY")]
        secret_key_env: String,
        /// Maximum trace rows to request.
        #[arg(long, default_value_t = 20)]
        limit: u32,
        /// 1-based LangFuse page number.
        #[arg(long, default_value_t = 1)]
        page: u32,
        /// Keep only traces for this harness, for example codex or claude.
        #[arg(long)]
        harness: Option<String>,
        /// Keep only traces for this provider, for example openai or anthropic.
        #[arg(long)]
        provider: Option<String>,
        /// Keep only traces for this model.
        #[arg(long)]
        model: Option<String>,
        /// Keep only traces for this LangFuse environment.
        #[arg(long)]
        environment: Option<String>,
        /// Response shape for agents: compact summary or full backend response.
        #[arg(long, value_enum, default_value = "summary")]
        output: LangFuseTraceOutput,
    },
    /// Create a LangFuse score for an exported trace so agents can write
    /// learning-loop feedback next to the telemetry they inspect.
    #[command(name = "langfuse-score")]
    LangFuseScore {
        /// Existing 32-hex LangFuse/OpenTelemetry trace id.
        #[arg(long, conflicts_with = "run_id")]
        trace_id: Option<String>,
        /// `itmux` run id; the command derives the deterministic trace id used
        /// by the exporter.
        #[arg(long, conflicts_with = "trace_id")]
        run_id: Option<String>,
        /// LangFuse origin or OTLP endpoint. Defaults to LANGFUSE_BASE_URL.
        #[arg(long)]
        langfuse_base_url: Option<String>,
        /// Env var containing the LangFuse public key.
        #[arg(long, default_value = "LANGFUSE_PUBLIC_KEY")]
        public_key_env: String,
        /// Env var containing the LangFuse secret key.
        #[arg(long, default_value = "LANGFUSE_SECRET_KEY")]
        secret_key_env: String,
        /// Score name, for example agentic.learning_loop_probe.
        #[arg(long)]
        name: String,
        /// Score value. Numeric/boolean values must parse as numbers; text and
        /// categorical values are sent as strings.
        #[arg(long)]
        value: String,
        /// LangFuse score data type.
        #[arg(long, value_enum, default_value = "numeric")]
        data_type: LangFuseScoreDataType,
        /// Optional score comment.
        #[arg(long)]
        comment: Option<String>,
        /// Optional JSON metadata object.
        #[arg(long)]
        metadata_json: Option<String>,
        /// Optional LangFuse score id. Supplying one makes retries idempotent.
        #[arg(long)]
        score_id: Option<String>,
        /// Optional LangFuse environment label for the score.
        #[arg(long)]
        environment: Option<String>,
        /// Response shape for agents: compact summary or full backend response.
        #[arg(long, value_enum, default_value = "summary")]
        output: LangFuseTraceOutput,
    },
    /// List LangFuse scores so agents can read learning-loop feedback.
    #[command(name = "langfuse-scores")]
    LangFuseScores {
        /// Existing 32-hex LangFuse/OpenTelemetry trace id.
        #[arg(long, conflicts_with = "run_id")]
        trace_id: Option<String>,
        /// `itmux` run id; the command derives the deterministic trace id used
        /// by the exporter.
        #[arg(long, conflicts_with = "trace_id")]
        run_id: Option<String>,
        /// LangFuse origin or OTLP endpoint. Defaults to LANGFUSE_BASE_URL.
        #[arg(long)]
        langfuse_base_url: Option<String>,
        /// Env var containing the LangFuse public key.
        #[arg(long, default_value = "LANGFUSE_PUBLIC_KEY")]
        public_key_env: String,
        /// Env var containing the LangFuse secret key.
        #[arg(long, default_value = "LANGFUSE_SECRET_KEY")]
        secret_key_env: String,
        /// Optional score id filter. Comma-separate multiple ids.
        #[arg(long)]
        score_ids: Option<String>,
        /// Optional score name filter.
        #[arg(long)]
        name: Option<String>,
        /// Optional data type filter.
        #[arg(long, value_enum)]
        data_type: Option<LangFuseScoreDataType>,
        /// Maximum score rows to request.
        #[arg(long, default_value_t = 20)]
        limit: u32,
        /// 1-based LangFuse page number.
        #[arg(long, default_value_t = 1)]
        page: u32,
        /// Response shape for agents: compact summary or full backend response.
        #[arg(long, value_enum, default_value = "summary")]
        output: LangFuseTraceOutput,
    },
}

/// Clap value parser for `--timeout`: accept only a finite, strictly-positive
/// number of seconds. Rejects `<= 0.0` (an instant/zero timeout is meaningless)
/// and non-finite values (`NaN`, `inf`) with a message clap renders as a clean
/// CLI error - this is what keeps `Duration::from_secs_f64` from ever seeing a
/// value that would panic.
fn parse_positive_timeout(raw: &str) -> Result<f64, String> {
    let value: f64 = raw
        .parse()
        .map_err(|_| format!("'{raw}' is not a number"))?;
    if !value.is_finite() {
        return Err(format!("timeout must be a finite number, got '{raw}'"));
    }
    if value <= 0.0 {
        return Err(format!("timeout must be greater than 0, got '{raw}'"));
    }
    Ok(value)
}

/// Build the `AgentRunSpec` for `itmux run` from the CLI inputs. Pure so the
/// `--timeout -> limits.timeout_s` mapping is unit-testable without spawning a
/// run. When `timeout` is `None`, `limits` stays `None` so the default await
/// bound is unchanged (R6: additive, no behaviour change when omitted).
fn build_run_spec(recipe: PathBuf, task: String, timeout: Option<f64>) -> AgentRunSpec {
    AgentRunSpec {
        recipe,
        task,
        input_artifacts: Vec::new(),
        credentials: Default::default(),
        observability: Vec::new(),
        limits: timeout.map(|timeout_s| AgentRunLimits {
            timeout_s: Some(timeout_s),
            token_budget: None,
        }),
    }
}

fn parse_agent(s: &str) -> Result<Agent, String> {
    Agent::parse(s).ok_or_else(|| format!("unknown agent: {s} (one of claude/codex/gemini)"))
}

/// Resolve per-agent host credential directories, honoring `ITMUX_{AGENT}_HOME`
/// env vars first and `$HOME/.{agent}` second.
///
/// This is the fix for the docker-out-of-docker (DooD) bug Syntropic137's
/// integration e2e surfaced on PR #202: when this driver runs inside another
/// container, `$HOME` is the container's home (e.g. `/root`), not the
/// operator's, so every agent slot defaults to `None` and `start_workspace`
/// fails with `no enabled agents (host_auth empty)`. The env-var overrides
/// let the calling environment point at the real mounted credentials.
fn default_host_auth(wanted: &[Agent]) -> HashMap<Agent, Option<PathBuf>> {
    let home = std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/root"));
    let mut out = HashMap::new();
    for agent in AGENTS {
        let override_env = match agent {
            Agent::Claude => "ITMUX_CLAUDE_HOME",
            Agent::Codex => "ITMUX_CODEX_HOME",
            Agent::Gemini => "ITMUX_GEMINI_HOME",
        };
        let path = std::env::var_os(override_env)
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                home.join(match agent {
                    Agent::Claude => ".claude",
                    Agent::Codex => ".codex",
                    Agent::Gemini => ".gemini",
                })
            });
        let enabled = wanted.contains(&agent) && path.is_dir();
        out.insert(agent, if enabled { Some(path) } else { None });
    }
    out
}

/// Parse `ITMUX_CLAUDE_PLUGIN_DIRS` (colon-separated, like `$PATH`).
///
/// Returns an empty vec when the env var is unset or empty. The driver
/// translates each entry to a `claude --plugin-dir <path>` flag at
/// launch. Paths are NOT existence-checked here — they point at
/// container-side paths that may not exist in the calling process's
/// filesystem (typical layout: the integrator bind-mounts a host
/// directory into the container at the same path, sets the env var to
/// that container path).
///
/// Surfaced by Syntropic137's workflow-skills bridge experiment
/// (`docs/plans/workflow-skills.md` §9): settings.json injection of
/// `installedPlugins` is silently ignored by the TUI; only the
/// `--plugin-dir` CLI flag actually loads plugins.
fn default_claude_plugin_dirs() -> Vec<PathBuf> {
    match std::env::var("ITMUX_CLAUDE_PLUGIN_DIRS") {
        Ok(raw) if !raw.is_empty() => raw
            .split(':')
            .filter(|s| !s.is_empty())
            .map(PathBuf::from)
            .collect(),
        _ => Vec::new(),
    }
}

/// Resolve `~/.claude.json`, honoring `ITMUX_CLAUDE_JSON` first, then
/// `$HOME/.claude.json`. Returns `None` if neither resolves to an existing
/// file — `prepare_claude` synthesises a fresh dotjson in that case
/// (acceptable per EXP-05a; just no `oauthAccount` passthrough).
fn default_host_claude_dotjson() -> Option<PathBuf> {
    if let Some(p) = std::env::var_os("ITMUX_CLAUDE_JSON") {
        let path = PathBuf::from(p);
        return if path.is_file() { Some(path) } else { None };
    }
    let home = std::env::var_os("HOME").map(PathBuf::from)?;
    let path = home.join(".claude.json");
    if path.is_file() {
        Some(path)
    } else {
        None
    }
}

#[derive(Serialize)]
struct StartReport {
    name: String,
    container: String,
    agents: Vec<String>,
    startup_status: HashMap<String, Value>,
}

#[allow(clippy::too_many_arguments)]
fn handle_start(
    name: String,
    image: String,
    workdir: String,
    agents: String,
    cols: u32,
    rows: u32,
    startup_timeout: f64,
    strict_startup: bool,
) -> ExitCode {
    let wanted: Vec<Agent> = match agents
        .split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(parse_agent)
        .collect::<Result<_, _>>()
    {
        Ok(v) => v,
        Err(e) => {
            eprintln!("{e}");
            return ExitCode::from(2);
        }
    };

    let mut opts = StartOptions::new(&name);
    opts.image = image;
    opts.workdir = workdir;
    opts.tmux_size = (cols, rows);
    opts.startup_timeout_s = startup_timeout;
    opts.strict_startup = strict_startup;
    opts.host_auth = default_host_auth(&wanted);
    opts.host_claude_dotjson = default_host_claude_dotjson();
    opts.claude_plugin_dirs = default_claude_plugin_dirs();

    match Workspace::start(opts) {
        Ok(ws) => {
            if let Err(e) = ws.save_to_registry() {
                eprintln!("warning: save workspace record: {e}");
            }
            let startup_status: HashMap<String, Value> = ws
                .startup_status
                .iter()
                .map(|(a, r)| {
                    (
                        a.as_str().to_string(),
                        serde_json::to_value(r).unwrap_or(Value::Null),
                    )
                })
                .collect();
            let all_failed =
                !ws.startup_status.is_empty() && ws.startup_status.values().all(|r| !r.ready);
            let report = StartReport {
                name: ws.name.clone(),
                container: ws.container.clone(),
                agents: ws
                    .enabled_agents
                    .iter()
                    .map(|a| a.as_str().to_string())
                    .collect(),
                startup_status,
            };
            println!("{}", serde_json::to_string(&report).unwrap());
            if all_failed {
                ExitCode::from(3)
            } else {
                ExitCode::SUCCESS
            }
        }
        Err(e) => {
            // Match Python: emit JSON error with the failure shape so the
            // smoke harness can parse it (and use exit 3 for startup
            // readiness errors, exit 1 for other errors).
            if e.kind() == std::io::ErrorKind::TimedOut {
                println!(
                    "{}",
                    json!({
                        "error": "startup_readiness",
                        "message": e.to_string(),
                    })
                );
                ExitCode::from(3)
            } else {
                eprintln!("error: {e}");
                ExitCode::from(1)
            }
        }
    }
}

fn handle_send(name: String, agent: String, text: String) -> ExitCode {
    let agent = match parse_agent(&agent) {
        Ok(a) => a,
        Err(e) => {
            eprintln!("{e}");
            return ExitCode::from(2);
        }
    };
    let Ok(ws) = Workspace::load_from_registry(&name) else {
        eprintln!("no registered workspace: {name}");
        return ExitCode::from(1);
    };
    match ws.send_message(agent, &text) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("send_message failed: {e}");
            ExitCode::from(1)
        }
    }
}

fn handle_await(
    name: String,
    agent: String,
    timeout: f64,
    stable_polls: u32,
    poll_interval: f64,
    warmup: f64,
) -> ExitCode {
    let agent = match parse_agent(&agent) {
        Ok(a) => a,
        Err(e) => {
            eprintln!("{e}");
            return ExitCode::from(2);
        }
    };
    let Ok(ws) = Workspace::load_from_registry(&name) else {
        eprintln!("no registered workspace: {name}");
        return ExitCode::from(1);
    };
    match ws.await_completion(agent, timeout, stable_polls, poll_interval, warmup) {
        Ok(result) => {
            // Mirror Python `await`: drop `pane` from the printed JSON so
            // shell harnesses don't get a wall of text.
            let mut v = serde_json::to_value(&result).unwrap_or(Value::Null);
            if let Some(obj) = v.as_object_mut() {
                obj.remove("pane");
            }
            println!("{}", serde_json::to_string(&v).unwrap());
            ExitCode::from(result.cli_exit_code() as u8)
        }
        Err(e) => {
            eprintln!("await_completion failed: {e}");
            ExitCode::from(1)
        }
    }
}

fn handle_capture(name: String, agent: String) -> ExitCode {
    let agent = match parse_agent(&agent) {
        Ok(a) => a,
        Err(e) => {
            eprintln!("{e}");
            return ExitCode::from(2);
        }
    };
    let Ok(ws) = Workspace::load_from_registry(&name) else {
        eprintln!("no registered workspace: {name}");
        return ExitCode::from(1);
    };
    match ws.capture_response(agent) {
        Ok(text) => {
            let mut stdout = std::io::stdout().lock();
            let _ = stdout.write_all(text.as_bytes());
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("capture failed: {e}");
            ExitCode::from(1)
        }
    }
}

fn handle_exec(name: String, argv: Vec<String>) -> ExitCode {
    let Ok(ws) = Workspace::load_from_registry(&name) else {
        eprintln!("no registered workspace: {name}");
        return ExitCode::from(1);
    };
    let argv_refs: Vec<&str> = argv.iter().map(String::as_str).collect();
    match ws.exec(&argv_refs) {
        Ok(out) => {
            let mut stdout = std::io::stdout().lock();
            let _ = stdout.write_all(&out.stdout);
            let mut stderr = std::io::stderr().lock();
            let _ = stderr.write_all(&out.stderr);
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("exec failed: {e}");
            ExitCode::from(1)
        }
    }
}

fn handle_stop(name: String) -> ExitCode {
    match Workspace::load_from_registry(&name) {
        Ok(ws) => {
            let _ = ws.stop();
            let _ = registry::forget(&name);
            ExitCode::SUCCESS
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("stop failed to load workspace {name}: {e}");
            ExitCode::from(1)
        }
    }
}

/// Install a SIGINT/SIGTERM watcher that folds signals into `cancel` via the
/// two-tier [`CancelEscalator`]. Returns the signal handle + the watcher thread
/// so the caller can stop and join it after the run.
///
/// Signal safety: `signal_hook::iterator::Signals` registers an
/// async-signal-safe handler (a self-pipe write) inside the crate; the closure
/// below runs on an ORDINARY thread draining that pipe, so it may safely call
/// into the `CancelToken`. No `unsafe` and no work in handler context.
#[cfg(unix)]
fn install_signal_watcher(
    cancel: CancelToken,
) -> Option<(signal_hook::iterator::Handle, std::thread::JoinHandle<()>)> {
    use signal_hook::consts::{SIGINT, SIGTERM};
    use signal_hook::iterator::Signals;

    let mut signals = match Signals::new([SIGINT, SIGTERM]) {
        Ok(signals) => signals,
        Err(err) => {
            eprintln!("[itmux run] could not install signal handler (run is uncancellable): {err}");
            return None;
        }
    };
    let handle = signals.handle();
    let join = std::thread::spawn(move || {
        let mut escalator = CancelEscalator::new();
        for signal in signals.forever() {
            let kind = if signal == SIGTERM {
                SignalKind::Terminate
            } else {
                SignalKind::Interrupt
            };
            escalator.on_signal(kind, &cancel);
        }
    });
    Some((handle, join))
}

#[derive(Debug, Clone, Default)]
struct LangFuseCliOptions {
    enabled: bool,
    force: bool,
    official_plugin_tracing_active: bool,
    base_url: Option<String>,
    project_id: Option<String>,
    label: Option<String>,
}

fn build_observability_exporters(
    observability_file: Option<PathBuf>,
    file_label: &str,
    langfuse: LangFuseCliOptions,
) -> Vec<ObservabilityExporter> {
    let mut exporters: Vec<_> = observability_file
        .map(|path| ObservabilityExporter::File {
            path,
            label: Some(file_label.to_string()),
        })
        .into_iter()
        .collect();

    if langfuse.enabled && (!langfuse.official_plugin_tracing_active || langfuse.force) {
        exporters.push(ObservabilityExporter::LangFuseOtlp {
            base_url: langfuse.base_url,
            public_key_env: "LANGFUSE_PUBLIC_KEY".to_string(),
            secret_key_env: "LANGFUSE_SECRET_KEY".to_string(),
            environment_env: "LANGFUSE_TRACING_ENVIRONMENT".to_string(),
            project_id: langfuse.project_id,
            project_id_env: "LANGFUSE_PROJECT_ID".to_string(),
            service_name: "agentic-primitives".to_string(),
            label: langfuse
                .label
                .or_else(|| Some("LangFuse trace".to_string())),
        });
    }

    exporters
}

fn official_langfuse_plugin_tracing_active() -> bool {
    truthy_env("TRACE_TO_LANGFUSE")
}

fn truthy_env(name: &str) -> bool {
    std::env::var(name)
        .ok()
        .map(|value| {
            matches!(
                value.trim().to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
        .unwrap_or(false)
}

fn resolve_codex_exec_model(explicit_model: Option<String>) -> Option<String> {
    if let Some(model) = non_empty_string(explicit_model) {
        return Some(model);
    }
    if let Some(model) = non_empty_env("CODEX_MODEL") {
        return Some(model);
    }
    codex_config_path().and_then(|path| read_codex_config_model(&path))
}

fn codex_config_path() -> Option<PathBuf> {
    if let Some(codex_home) = std::env::var_os("CODEX_HOME") {
        return Some(PathBuf::from(codex_home).join("config.toml"));
    }
    let home = std::env::var_os("HOME")?;
    Some(PathBuf::from(home).join(".codex/config.toml"))
}

fn read_codex_config_model(path: &Path) -> Option<String> {
    let raw = std::fs::read_to_string(path).ok()?;
    parse_codex_config_model(&raw)
}

fn parse_codex_config_model(raw: &str) -> Option<String> {
    for line in raw.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('[') {
            break;
        }
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let Some((key, value)) = trimmed.split_once('=') else {
            continue;
        };
        if key.trim() != "model" {
            continue;
        }
        return parse_toml_string_literal(value.trim())
            .and_then(|value| non_empty_string(Some(value)));
    }
    None
}

fn parse_toml_string_literal(value: &str) -> Option<String> {
    let value = value.split('#').next().unwrap_or(value).trim();
    if value.len() >= 2 && value.starts_with('"') && value.ends_with('"') {
        return Some(value[1..value.len() - 1].to_string());
    }
    if value.len() >= 2 && value.starts_with('\'') && value.ends_with('\'') {
        return Some(value[1..value.len() - 1].to_string());
    }
    None
}

fn non_empty_string(value: Option<String>) -> Option<String> {
    value
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn codex_model_for_exec(recipe_model: &str) -> Option<String> {
    let model = recipe_model
        .trim()
        .strip_prefix("openai/")
        .unwrap_or_else(|| recipe_model.trim());
    non_empty_string(Some(model.to_string()))
}

fn select_run_dispatch(agent: Agent, codex_mode: CodexRunMode) -> RunDispatch {
    match (agent, codex_mode) {
        (Agent::Codex, CodexRunMode::Exec) => RunDispatch::CodexExec,
        (Agent::Codex, CodexRunMode::Tui) => RunDispatch::WorkspaceTui,
        (_, CodexRunMode::Exec) => RunDispatch::AgentMismatch,
        (_, CodexRunMode::Tui) => RunDispatch::WorkspaceTui,
    }
}

#[allow(clippy::too_many_arguments)]
fn handle_run(
    recipe: PathBuf,
    task: String,
    image: String,
    codex_mode: CodexRunMode,
    codex_bin: String,
    codex_sandbox: String,
    json: bool,
    result_file: Option<PathBuf>,
    timeout: Option<f64>,
    env_file: Option<PathBuf>,
    allow_host_auth_fallback: bool,
    observability_file: Option<PathBuf>,
    langfuse: LangFuseCliOptions,
) -> ExitCode {
    let credentials = match itmux::run::secret_env::load_credentials(env_file.as_deref()) {
        Ok(credentials) => credentials,
        Err(err) => {
            eprintln!("[itmux run] {err}");
            return ExitCode::from(2);
        }
    };
    let observability =
        build_observability_exporters(observability_file, "itmux run events", langfuse);
    let spec_recipe = recipe.clone();
    let mut spec = build_run_spec(recipe, task, timeout);
    spec.credentials = credentials;
    spec.observability = observability;
    let run_id = generate_run_id();
    let plan = match itmux::run::recipe_loader::load_execution_plan(&spec) {
        Ok(plan) => plan,
        Err(err) => {
            eprintln!("[itmux run] failed to load recipe: {err}");
            return ExitCode::from(1);
        }
    };
    match select_run_dispatch(plan.agent, codex_mode) {
        RunDispatch::CodexExec => {
            let model =
                codex_model_for_exec(&plan.model_name).or_else(|| resolve_codex_exec_model(None));
            return handle_codex_exec_with_exporters(CodexExecRunOptions {
                prompt: plan.submit_text,
                codex_bin,
                model,
                sandbox: codex_sandbox,
                json,
                result_file,
                exporters: spec.observability,
                run_id,
                log_prefix: "itmux run codex-exec",
                human_label: "run codex-exec",
            });
        }
        RunDispatch::AgentMismatch => {
            eprintln!(
                "[itmux run] --codex-mode exec was requested, but recipe {} default agent is {}",
                spec_recipe.display(),
                plan.agent.as_str()
            );
            return ExitCode::from(64);
        }
        RunDispatch::WorkspaceTui => {}
    }
    let cancel = CancelToken::new();

    // Wire OS signals to the two-tier cancellation (Task 6): first Ctrl-C ->
    // graceful, second Ctrl-C or SIGTERM -> hard. On any signal path the
    // orchestrator's single terminalization still tears the workspace down
    // exactly once, so there is no orphaned container even on Ctrl-C. The
    // watcher runs on a normal thread (unix only); non-unix builds skip it.
    #[cfg(unix)]
    let signal_watcher = install_signal_watcher(cancel.clone());

    // Emit each event as one JSON line on stdout (R6: stdout is PURE
    // AgentRunEvent JSONL; stderr stays human-only). Count events so the final
    // result event (below) continues the monotonic `seq`.
    let event_seq = std::cell::Cell::new(0u64);
    let mut emit = |event: &AgentRunEvent| {
        event_seq.set(event_seq.get().max(event.seq + 1));
        if json {
            match serde_json::to_string(event) {
                Ok(line) => println!("{line}"),
                Err(err) => eprintln!("[itmux run] failed to serialize event: {err}"),
            }
        }
    };

    let run_result = itmux::run::workspace_executor::run_with_plan(
        &spec,
        &plan,
        &image,
        &run_id,
        &cancel,
        allow_host_auth_fallback,
        &mut emit,
    );

    // Stop the signal watcher before handling the result (best-effort).
    #[cfg(unix)]
    if let Some((handle, join)) = signal_watcher {
        handle.close();
        let _ = join.join();
    }

    let result = match run_result {
        Ok(result) => result,
        Err(err) => {
            // Precondition failure (e.g. the recipe failed to load) before any
            // workspace was provisioned - nothing to tear down.
            eprintln!("[itmux run] {err}");
            return ExitCode::from(1);
        }
    };

    let success = result.result.success;

    // Deliver the final result. When a result file is given, write it THERE and
    // keep stdout as pure event JSONL. Otherwise, in JSON mode, emit the result
    // as a real AgentRunEvent (`type:"result"`) so EVERY stdout line still
    // parses as an AgentRunEvent (Fix 4 / R6 stdout purity).
    match result_file {
        Some(path) => match serde_json::to_vec_pretty(&result) {
            Ok(bytes) => {
                if let Err(err) = std::fs::write(&path, bytes) {
                    eprintln!(
                        "[itmux run] failed to write result file {}: {err}",
                        path.display()
                    );
                    return ExitCode::from(1);
                }
            }
            Err(err) => {
                eprintln!("[itmux run] failed to serialize result: {err}");
                return ExitCode::from(1);
            }
        },
        None => {
            if json {
                let event = AgentRunEvent::result(&run_id, event_seq.get(), now_rfc3339(), result);
                match serde_json::to_string(&event) {
                    Ok(line) => println!("{line}"),
                    Err(err) => eprintln!("[itmux run] failed to serialize result: {err}"),
                }
            } else {
                println!(
                    "run {}: success={} - {}",
                    run_id, result.result.success, result.result.summary
                );
            }
        }
    }

    if success {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(3)
    }
}

struct CodexExecRunOptions<'a> {
    prompt: String,
    codex_bin: String,
    model: Option<String>,
    sandbox: String,
    json: bool,
    result_file: Option<PathBuf>,
    exporters: Vec<ObservabilityExporter>,
    run_id: String,
    log_prefix: &'a str,
    human_label: &'a str,
}

#[allow(clippy::too_many_arguments)]
fn handle_codex_exec(
    prompt: String,
    codex_bin: String,
    model: Option<String>,
    sandbox: String,
    json: bool,
    result_file: Option<PathBuf>,
    observability_file: Option<PathBuf>,
    langfuse: LangFuseCliOptions,
) -> ExitCode {
    let exporters =
        build_observability_exporters(observability_file, "codex exec events", langfuse);
    handle_codex_exec_with_exporters(CodexExecRunOptions {
        prompt,
        codex_bin,
        model,
        sandbox,
        json,
        result_file,
        exporters,
        run_id: generate_run_id(),
        log_prefix: "itmux codex-exec",
        human_label: "codex exec",
    })
}

fn handle_codex_exec_with_exporters(options: CodexExecRunOptions<'_>) -> ExitCode {
    let CodexExecRunOptions {
        prompt,
        codex_bin,
        model,
        sandbox,
        json,
        result_file,
        exporters,
        run_id,
        log_prefix,
        human_label,
    } = options;
    let mut fanout = ObservabilityFanout::new(&exporters);
    let requested_model = non_empty_string(model.clone());
    let telemetry_model = resolve_codex_exec_model(model.clone());
    let mut observer = CodexExecJsonObserver::with_model(telemetry_model);
    let mut seq = 0u64;
    let mut session_log = String::new();
    let mut parse_error: Option<String> = None;

    let mut emit_payload = |payload: AgentRunEventPayload, fanout: &mut ObservabilityFanout| {
        let event = AgentRunEvent {
            run_id: run_id.clone(),
            seq,
            ts: now_rfc3339(),
            payload,
        };
        seq += 1;
        fanout.emit(&event);
        if json {
            match serde_json::to_string(&event) {
                Ok(line) => println!("{line}"),
                Err(err) => eprintln!("[{log_prefix}] failed to serialize event: {err}"),
            }
        }
    };

    let mut cmd = Command::new(&codex_bin);
    cmd.arg("exec")
        .arg("--json")
        .arg("--sandbox")
        .arg(&sandbox)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(model) = requested_model {
        cmd.arg("--model").arg(model);
    }
    cmd.arg(prompt);

    let mut child = match cmd.spawn() {
        Ok(child) => child,
        Err(err) => {
            eprintln!("[{log_prefix}] failed to spawn {codex_bin}: {err}");
            return ExitCode::from(1);
        }
    };

    let stderr = child.stderr.take();
    let stderr_join = stderr.map(|mut stderr| {
        std::thread::spawn(move || {
            let mut buf = String::new();
            let _ = stderr.read_to_string(&mut buf);
            buf
        })
    });

    if let Some(stdout) = child.stdout.take() {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            match line {
                Ok(line) => {
                    session_log.push_str(&line);
                    session_log.push('\n');
                    match observer.observe_jsonl_line(&line) {
                        Ok(events) => {
                            for observed in events {
                                emit_payload(observed.payload, &mut fanout);
                            }
                        }
                        Err(err) => {
                            let message = err.to_string();
                            parse_error.get_or_insert_with(|| message.clone());
                            emit_payload(
                                AgentRunEventPayload::ToolEnd {
                                    tool_name: "codex_exec.parse".to_string(),
                                    success: false,
                                    output_summary: Some(message),
                                },
                                &mut fanout,
                            );
                        }
                    }
                }
                Err(err) => {
                    let message = format!("failed reading codex stdout: {err}");
                    parse_error.get_or_insert_with(|| message.clone());
                    emit_payload(
                        AgentRunEventPayload::ToolEnd {
                            tool_name: "codex_exec.read".to_string(),
                            success: false,
                            output_summary: Some(message),
                        },
                        &mut fanout,
                    );
                    break;
                }
            }
        }
    }

    let status = match child.wait() {
        Ok(status) => status,
        Err(err) => {
            eprintln!("[{log_prefix}] failed waiting for codex process: {err}");
            return ExitCode::from(1);
        }
    };

    let stderr = stderr_join
        .and_then(|join| join.join().ok())
        .unwrap_or_default();
    if !stderr.is_empty() {
        session_log.push_str("\n[stderr]\n");
        session_log.push_str(&stderr);
        let mut stderr_out = std::io::stderr().lock();
        let _ = stderr_out.write_all(stderr.as_bytes());
    }

    let success = status.success() && parse_error.is_none();
    let summary = if let Some(err) = parse_error {
        format!("codex exec observer parse/read failure: {err}")
    } else if success {
        "codex exec completed successfully".to_string()
    } else {
        format!(
            "codex exec exited with status {}",
            status
                .code()
                .map_or_else(|| "signal".to_string(), |code| code.to_string())
        )
    };
    let outcome = AgentRunOutcome { success, summary };
    emit_payload(
        AgentRunEventPayload::SessionEnd {
            outcome: outcome.clone(),
        },
        &mut fanout,
    );

    let result = AgentRunResult {
        result: outcome,
        output_artifacts: Vec::new(),
        session_log,
        observability: fanout.finish(),
    };

    match result_file {
        Some(path) => match serde_json::to_vec_pretty(&result) {
            Ok(bytes) => {
                if let Err(err) = std::fs::write(&path, bytes) {
                    eprintln!(
                        "[{log_prefix}] failed to write result file {}: {err}",
                        path.display()
                    );
                    return ExitCode::from(1);
                }
            }
            Err(err) => {
                eprintln!("[{log_prefix}] failed to serialize result: {err}");
                return ExitCode::from(1);
            }
        },
        None => {
            if json {
                let event = AgentRunEvent::result(&run_id, seq, now_rfc3339(), result);
                match serde_json::to_string(&event) {
                    Ok(line) => println!("{line}"),
                    Err(err) => eprintln!("[{log_prefix}] failed to serialize result: {err}"),
                }
            } else {
                println!(
                    "{human_label} {}: success={}",
                    run_id,
                    if success { "true" } else { "false" }
                );
            }
        }
    }

    if success {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(3)
    }
}

#[allow(clippy::too_many_arguments)]
fn handle_claude_transcript(
    transcript: PathBuf,
    run_id: Option<String>,
    json: bool,
    result_file: Option<PathBuf>,
    observability_file: Option<PathBuf>,
    langfuse: LangFuseCliOptions,
) -> ExitCode {
    let exporters =
        build_observability_exporters(observability_file, "claude transcript events", langfuse);
    let mut fanout = ObservabilityFanout::new(&exporters);
    let mut observer = ClaudeTranscriptObserver::new();
    let run_id = run_id.unwrap_or_else(generate_run_id);
    let mut seq = 0u64;
    let mut parse_error: Option<String> = None;
    let mut input_lines = 0usize;
    let mut observed_payloads = 0usize;

    let input = if transcript.as_os_str() == "-" {
        let mut input = String::new();
        if let Err(err) = std::io::stdin().read_to_string(&mut input) {
            eprintln!("[itmux claude-transcript] failed to read stdin: {err}");
            return ExitCode::from(1);
        }
        input
    } else {
        match std::fs::read_to_string(&transcript) {
            Ok(input) => input,
            Err(err) => {
                eprintln!(
                    "[itmux claude-transcript] failed to read transcript {}: {err}",
                    transcript.display()
                );
                return ExitCode::from(1);
            }
        }
    };

    let mut emit_payload = |payload: AgentRunEventPayload, fanout: &mut ObservabilityFanout| {
        let event = AgentRunEvent {
            run_id: run_id.clone(),
            seq,
            ts: now_rfc3339(),
            payload,
        };
        seq += 1;
        fanout.emit(&event);
        if json {
            match serde_json::to_string(&event) {
                Ok(line) => println!("{line}"),
                Err(err) => {
                    eprintln!("[itmux claude-transcript] failed to serialize event: {err}");
                }
            }
        }
    };

    for line in input.lines() {
        input_lines += 1;
        match observer.observe_jsonl_line(line) {
            Ok(events) => {
                for observed in events {
                    observed_payloads += 1;
                    emit_payload(observed.payload, &mut fanout);
                }
            }
            Err(err) => {
                let message = "invalid claude transcript JSONL line".to_string();
                eprintln!("[itmux claude-transcript] {err}");
                parse_error.get_or_insert_with(|| message.clone());
                emit_payload(
                    AgentRunEventPayload::ToolEnd {
                        tool_name: "claude_transcript.parse".to_string(),
                        success: false,
                        output_summary: Some(message),
                    },
                    &mut fanout,
                );
            }
        }
    }

    let success = parse_error.is_none();
    let summary = parse_error
        .map(|err| format!("claude transcript observer parse failure: {err}"))
        .unwrap_or_else(|| "claude transcript normalized successfully".to_string());
    let outcome = AgentRunOutcome { success, summary };
    emit_payload(
        AgentRunEventPayload::SessionEnd {
            outcome: outcome.clone(),
        },
        &mut fanout,
    );

    let result = AgentRunResult {
        result: outcome,
        output_artifacts: Vec::new(),
        session_log: format!(
            "claude transcript omitted from result; normalized {observed_payloads} events from {input_lines} input lines"
        ),
        observability: fanout.finish(),
    };

    match result_file {
        Some(path) => match serde_json::to_vec_pretty(&result) {
            Ok(bytes) => {
                if let Err(err) = std::fs::write(&path, bytes) {
                    eprintln!(
                        "[itmux claude-transcript] failed to write result file {}: {err}",
                        path.display()
                    );
                    return ExitCode::from(1);
                }
            }
            Err(err) => {
                eprintln!("[itmux claude-transcript] failed to serialize result: {err}");
                return ExitCode::from(1);
            }
        },
        None => {
            if json {
                let event = AgentRunEvent::result(&run_id, seq, now_rfc3339(), result);
                match serde_json::to_string(&event) {
                    Ok(line) => println!("{line}"),
                    Err(err) => {
                        eprintln!("[itmux claude-transcript] failed to serialize result: {err}");
                    }
                }
            } else {
                println!(
                    "claude transcript {}: success={}",
                    run_id,
                    if success { "true" } else { "false" }
                );
            }
        }
    }

    if success {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(3)
    }
}

#[derive(Debug, Clone, Copy, ValueEnum)]
enum LangFuseTraceApi {
    /// Recommended row-level API for current LangFuse Cloud/newer deployments.
    ObservationsV2,
    /// Compatibility path for self-hosted deployments that do not expose v2.
    LegacyTrace,
}

impl LangFuseTraceApi {
    fn as_str(self) -> &'static str {
        match self {
            Self::ObservationsV2 => "observations_v2",
            Self::LegacyTrace => "legacy_trace",
        }
    }
}

#[derive(Debug, Clone, Copy, ValueEnum)]
enum LangFuseTraceOutput {
    /// Emit only the agent-facing learning-loop summary.
    Summary,
    /// Emit the summary plus the raw LangFuse response.
    Full,
}

#[derive(Debug, Clone, Copy, ValueEnum)]
enum LangFuseScoreDataType {
    Numeric,
    Boolean,
    Categorical,
    Text,
}

impl LangFuseScoreDataType {
    fn as_langfuse(self) -> &'static str {
        match self {
            Self::Numeric => "NUMERIC",
            Self::Boolean => "BOOLEAN",
            Self::Categorical => "CATEGORICAL",
            Self::Text => "TEXT",
        }
    }

    fn parse_value(self, value: &str) -> Result<Value, String> {
        match self {
            Self::Numeric => {
                let number = value
                    .parse::<f64>()
                    .map_err(|_| "NUMERIC scores require a finite JSON number".to_string())?;
                if !number.is_finite() {
                    return Err("NUMERIC scores require a finite JSON number".to_string());
                }
                serde_json::Number::from_f64(number)
                    .map(Value::Number)
                    .ok_or_else(|| "NUMERIC scores require a finite JSON number".to_string())
            }
            Self::Boolean => match value {
                "1" | "true" | "TRUE" | "True" => Ok(Value::Number(1.into())),
                "0" | "false" | "FALSE" | "False" => Ok(Value::Number(0.into())),
                _ => Err("BOOLEAN scores require one of true, false, 1, or 0".to_string()),
            },
            Self::Categorical | Self::Text => Ok(Value::String(value.to_string())),
        }
    }
}

#[derive(Serialize)]
struct LangFuseTraceQueryRequest {
    api: &'static str,
    endpoint: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    scores_endpoint: Option<String>,
    trace_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    run_id: Option<String>,
    fields: String,
    limit: u32,
    include_scores: bool,
    score_limit: u32,
    from_start_time: String,
    to_start_time: String,
}

#[derive(Serialize)]
struct LangFuseTracesListRequest {
    endpoint: String,
    limit: u32,
    page: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    harness: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    provider: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    model: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    environment: Option<String>,
}

#[derive(Serialize)]
struct LangFuseScoreCreateRequest {
    endpoint: String,
    trace_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    run_id: Option<String>,
    name: String,
    data_type: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    score_id: Option<String>,
}

#[derive(Serialize)]
struct LangFuseScoresListRequest {
    endpoint: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    trace_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    run_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    score_ids: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    data_type: Option<&'static str>,
    limit: u32,
    page: u32,
}

#[allow(clippy::too_many_arguments)]
fn handle_langfuse_trace(
    trace_id: Option<String>,
    run_id: Option<String>,
    base_url: Option<String>,
    public_key_env: String,
    secret_key_env: String,
    from_start_time: String,
    to_start_time: String,
    fields: String,
    limit: u32,
    include_scores: bool,
    score_limit: u32,
    api: LangFuseTraceApi,
    output: LangFuseTraceOutput,
) -> ExitCode {
    let Some(trace_id) = trace_id.or_else(|| run_id.as_deref().map(langfuse_trace_id_for_run))
    else {
        println!(
            "{}",
            json!({
                "ok": false,
                "error": "provide exactly one of --trace-id or --run-id"
            })
        );
        return ExitCode::from(2);
    };

    let mut missing = Vec::new();
    let base_url = base_url
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .or_else(|| non_empty_env("LANGFUSE_BASE_URL"))
        .unwrap_or_else(|| {
            missing.push("LANGFUSE_BASE_URL".to_string());
            String::new()
        });
    let public_key = non_empty_env(&public_key_env).unwrap_or_else(|| {
        missing.push(public_key_env.clone());
        String::new()
    });
    let secret_key = non_empty_env(&secret_key_env).unwrap_or_else(|| {
        missing.push(secret_key_env.clone());
        String::new()
    });

    if !missing.is_empty() {
        println!(
            "{}",
            json!({
                "ok": false,
                "error": "missing required LangFuse query configuration",
                "missing": missing,
            })
        );
        return ExitCode::from(78);
    }

    let endpoint = build_langfuse_trace_query_url(
        api,
        &base_url,
        &trace_id,
        &from_start_time,
        &to_start_time,
        &fields,
        limit,
    );
    let scores_endpoint = include_scores.then(|| {
        build_langfuse_scores_list_url(&base_url, Some(&trace_id), None, None, None, score_limit, 1)
    });
    let request = LangFuseTraceQueryRequest {
        api: api.as_str(),
        endpoint: endpoint.clone(),
        scores_endpoint: scores_endpoint.clone(),
        trace_id: trace_id.clone(),
        run_id: run_id.clone(),
        fields,
        limit,
        include_scores,
        score_limit,
        from_start_time,
        to_start_time,
    };

    let response = ureq::get(&endpoint)
        .timeout(LANGFUSE_TRACE_QUERY_TIMEOUT)
        .set(
            "Authorization",
            &langfuse_basic_auth_header(&public_key, &secret_key),
        )
        .call();

    match response {
        Ok(response) if (200..300).contains(&response.status()) => {
            let body = response.into_string().unwrap_or_default();
            let parsed = match serde_json::from_str::<Value>(&body) {
                Ok(parsed) => parsed,
                Err(err) => {
                    println!(
                        "{}",
                        serde_json::to_string_pretty(&json!({
                            "ok": false,
                            "request": request,
                            "error": "invalid LangFuse trace JSON response",
                            "parse_error": err.to_string(),
                            "body": body,
                        }))
                        .unwrap()
                    );
                    return ExitCode::from(1);
                }
            };
            let mut summary = summarize_langfuse_trace_response(&parsed);
            let mut scores_response = None;
            if let Some(scores_endpoint) = scores_endpoint {
                match query_langfuse_json(&scores_endpoint, &public_key, &secret_key) {
                    Ok(score_payload) => {
                        let scores_request = LangFuseScoresListRequest {
                            endpoint: scores_endpoint,
                            trace_id: Some(trace_id),
                            run_id,
                            score_ids: None,
                            name: None,
                            data_type: None,
                            limit: score_limit,
                            page: 1,
                        };
                        let score_summary =
                            summarize_langfuse_scores_response(&score_payload, &scores_request);
                        if let Some(summary) = summary.as_object_mut() {
                            summary.insert("scores".to_string(), score_summary);
                        }
                        scores_response = Some(score_payload);
                    }
                    Err(error) => {
                        if let Some(summary) = summary.as_object_mut() {
                            summary.insert("scores_error".to_string(), error);
                        }
                    }
                }
            }
            let output = match output {
                LangFuseTraceOutput::Summary => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                }),
                LangFuseTraceOutput::Full => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                    "response": parsed,
                    "scores_response": scores_response,
                }),
            };
            println!("{}", serde_json::to_string_pretty(&output).unwrap());
            ExitCode::SUCCESS
        }
        Ok(response) => {
            let status = response.status();
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(ureq::Error::Status(status, response)) => {
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(err) => {
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "error": err.to_string(),
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn handle_langfuse_traces(
    base_url: Option<String>,
    public_key_env: String,
    secret_key_env: String,
    limit: u32,
    page: u32,
    harness: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    environment: Option<String>,
    output: LangFuseTraceOutput,
) -> ExitCode {
    let mut missing = Vec::new();
    let base_url = base_url
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .or_else(|| non_empty_env("LANGFUSE_BASE_URL"))
        .unwrap_or_else(|| {
            missing.push("LANGFUSE_BASE_URL".to_string());
            String::new()
        });
    let public_key = non_empty_env(&public_key_env).unwrap_or_else(|| {
        missing.push(public_key_env.clone());
        String::new()
    });
    let secret_key = non_empty_env(&secret_key_env).unwrap_or_else(|| {
        missing.push(secret_key_env.clone());
        String::new()
    });

    if !missing.is_empty() {
        println!(
            "{}",
            json!({
                "ok": false,
                "error": "missing required LangFuse query configuration",
                "missing": missing,
            })
        );
        return ExitCode::from(78);
    }

    let endpoint = build_langfuse_traces_list_url(&base_url, limit, page);
    let request = LangFuseTracesListRequest {
        endpoint: endpoint.clone(),
        limit,
        page,
        harness: non_empty_string(harness),
        provider: non_empty_string(provider),
        model: non_empty_string(model),
        environment: non_empty_string(environment),
    };

    let response = ureq::get(&endpoint)
        .timeout(LANGFUSE_TRACE_QUERY_TIMEOUT)
        .set(
            "Authorization",
            &langfuse_basic_auth_header(&public_key, &secret_key),
        )
        .call();

    match response {
        Ok(response) if (200..300).contains(&response.status()) => {
            let body = response.into_string().unwrap_or_default();
            let parsed = serde_json::from_str::<Value>(&body).unwrap_or_else(|err| {
                json!({
                    "parse_error": err.to_string(),
                    "body": body,
                })
            });
            let summary = summarize_langfuse_traces_response(&parsed, &request);
            let output = match output {
                LangFuseTraceOutput::Summary => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                }),
                LangFuseTraceOutput::Full => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                    "response": parsed,
                }),
            };
            println!("{}", serde_json::to_string_pretty(&output).unwrap());
            ExitCode::SUCCESS
        }
        Ok(response) => {
            let status = response.status();
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(ureq::Error::Status(status, response)) => {
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(err) => {
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "error": err.to_string(),
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn handle_langfuse_score(
    trace_id: Option<String>,
    run_id: Option<String>,
    base_url: Option<String>,
    public_key_env: String,
    secret_key_env: String,
    name: String,
    value: String,
    data_type: LangFuseScoreDataType,
    comment: Option<String>,
    metadata_json: Option<String>,
    score_id: Option<String>,
    environment: Option<String>,
    output: LangFuseTraceOutput,
) -> ExitCode {
    let Some(trace_id) = trace_id.or_else(|| run_id.as_deref().map(langfuse_trace_id_for_run))
    else {
        println!(
            "{}",
            json!({
                "ok": false,
                "error": "provide exactly one of --trace-id or --run-id"
            })
        );
        return ExitCode::from(2);
    };

    let score_value = match data_type.parse_value(&value) {
        Ok(value) => value,
        Err(error) => {
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "error": error,
                }))
                .unwrap()
            );
            return ExitCode::from(2);
        }
    };

    let metadata = match metadata_json {
        Some(raw) => match serde_json::from_str::<Value>(&raw) {
            Ok(value @ Value::Object(_)) => Some(value),
            Ok(_) => {
                println!(
                    "{}",
                    serde_json::to_string_pretty(&json!({
                        "ok": false,
                        "error": "--metadata-json must be a JSON object",
                    }))
                    .unwrap()
                );
                return ExitCode::from(2);
            }
            Err(err) => {
                println!(
                    "{}",
                    serde_json::to_string_pretty(&json!({
                        "ok": false,
                        "error": format!("invalid --metadata-json: {err}"),
                    }))
                    .unwrap()
                );
                return ExitCode::from(2);
            }
        },
        None => None,
    };

    let mut missing = Vec::new();
    let base_url = base_url
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .or_else(|| non_empty_env("LANGFUSE_BASE_URL"))
        .unwrap_or_else(|| {
            missing.push("LANGFUSE_BASE_URL".to_string());
            String::new()
        });
    let public_key = non_empty_env(&public_key_env).unwrap_or_else(|| {
        missing.push(public_key_env.clone());
        String::new()
    });
    let secret_key = non_empty_env(&secret_key_env).unwrap_or_else(|| {
        missing.push(secret_key_env.clone());
        String::new()
    });

    if !missing.is_empty() {
        println!(
            "{}",
            json!({
                "ok": false,
                "error": "missing required LangFuse query configuration",
                "missing": missing,
            })
        );
        return ExitCode::from(78);
    }

    let endpoint = build_langfuse_score_create_url(&base_url);
    let request = LangFuseScoreCreateRequest {
        endpoint: endpoint.clone(),
        trace_id: trace_id.clone(),
        run_id,
        name: name.clone(),
        data_type: data_type.as_langfuse(),
        score_id: non_empty_string(score_id.clone()),
    };

    let mut body = json!({
        "traceId": trace_id,
        "name": name,
        "value": score_value,
        "dataType": data_type.as_langfuse(),
    });
    if let Some(body) = body.as_object_mut() {
        if let Some(score_id) = non_empty_string(score_id) {
            body.insert("id".to_string(), Value::String(score_id));
        }
        if let Some(comment) = non_empty_string(comment) {
            body.insert("comment".to_string(), Value::String(comment));
        }
        if let Some(metadata) = metadata {
            body.insert("metadata".to_string(), metadata);
        }
        if let Some(environment) = non_empty_string(environment) {
            body.insert("environment".to_string(), Value::String(environment));
        }
    }

    let body = serde_json::to_string(&body).unwrap();
    let response = ureq::post(&endpoint)
        .timeout(LANGFUSE_TRACE_QUERY_TIMEOUT)
        .set("Content-Type", "application/json")
        .set(
            "Authorization",
            &langfuse_basic_auth_header(&public_key, &secret_key),
        )
        .send_string(&body);

    match response {
        Ok(response) if (200..300).contains(&response.status()) => {
            let body = response.into_string().unwrap_or_default();
            let parsed = serde_json::from_str::<Value>(&body).unwrap_or_else(|err| {
                json!({
                    "parse_error": err.to_string(),
                    "body": body,
                })
            });
            let summary = summarize_langfuse_score_response(&parsed, &request);
            let output = match output {
                LangFuseTraceOutput::Summary => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                }),
                LangFuseTraceOutput::Full => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                    "response": parsed,
                }),
            };
            println!("{}", serde_json::to_string_pretty(&output).unwrap());
            ExitCode::SUCCESS
        }
        Ok(response) => {
            let status = response.status();
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(ureq::Error::Status(status, response)) => {
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(err) => {
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "error": err.to_string(),
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn handle_langfuse_scores(
    trace_id: Option<String>,
    run_id: Option<String>,
    base_url: Option<String>,
    public_key_env: String,
    secret_key_env: String,
    score_ids: Option<String>,
    name: Option<String>,
    data_type: Option<LangFuseScoreDataType>,
    limit: u32,
    page: u32,
    output: LangFuseTraceOutput,
) -> ExitCode {
    let trace_id = trace_id.or_else(|| run_id.as_deref().map(langfuse_trace_id_for_run));

    let mut missing = Vec::new();
    let base_url = base_url
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .or_else(|| non_empty_env("LANGFUSE_BASE_URL"))
        .unwrap_or_else(|| {
            missing.push("LANGFUSE_BASE_URL".to_string());
            String::new()
        });
    let public_key = non_empty_env(&public_key_env).unwrap_or_else(|| {
        missing.push(public_key_env.clone());
        String::new()
    });
    let secret_key = non_empty_env(&secret_key_env).unwrap_or_else(|| {
        missing.push(secret_key_env.clone());
        String::new()
    });

    if !missing.is_empty() {
        println!(
            "{}",
            json!({
                "ok": false,
                "error": "missing required LangFuse query configuration",
                "missing": missing,
            })
        );
        return ExitCode::from(78);
    }

    let endpoint = build_langfuse_scores_list_url(
        &base_url,
        trace_id.as_deref(),
        score_ids.as_deref(),
        name.as_deref(),
        data_type.map(LangFuseScoreDataType::as_langfuse),
        limit,
        page,
    );
    let request = LangFuseScoresListRequest {
        endpoint: endpoint.clone(),
        trace_id,
        run_id,
        score_ids: non_empty_string(score_ids),
        name: non_empty_string(name),
        data_type: data_type.map(LangFuseScoreDataType::as_langfuse),
        limit,
        page,
    };

    let response = ureq::get(&endpoint)
        .timeout(LANGFUSE_TRACE_QUERY_TIMEOUT)
        .set(
            "Authorization",
            &langfuse_basic_auth_header(&public_key, &secret_key),
        )
        .call();

    match response {
        Ok(response) if (200..300).contains(&response.status()) => {
            let body = response.into_string().unwrap_or_default();
            let parsed = serde_json::from_str::<Value>(&body).unwrap_or_else(|err| {
                json!({
                    "parse_error": err.to_string(),
                    "body": body,
                })
            });
            let summary = summarize_langfuse_scores_response(&parsed, &request);
            let output = match output {
                LangFuseTraceOutput::Summary => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                }),
                LangFuseTraceOutput::Full => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                    "response": parsed,
                }),
            };
            println!("{}", serde_json::to_string_pretty(&output).unwrap());
            ExitCode::SUCCESS
        }
        Ok(response) => {
            let status = response.status();
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(ureq::Error::Status(status, response)) => {
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(err) => {
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "error": err.to_string(),
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
    }
}

fn non_empty_env(key: &str) -> Option<String> {
    std::env::var(key)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn query_langfuse_json(endpoint: &str, public_key: &str, secret_key: &str) -> Result<Value, Value> {
    let response = ureq::get(endpoint)
        .timeout(LANGFUSE_TRACE_QUERY_TIMEOUT)
        .set(
            "Authorization",
            &langfuse_basic_auth_header(public_key, secret_key),
        )
        .call();

    match response {
        Ok(response) if (200..300).contains(&response.status()) => {
            let body = response.into_string().unwrap_or_default();
            Ok(serde_json::from_str::<Value>(&body).unwrap_or_else(|err| {
                json!({
                    "parse_error": err.to_string(),
                    "body": body,
                })
            }))
        }
        Ok(response) => {
            let status = response.status();
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            Err(json!({
                "status": status,
                "status_text": status_text,
                "body": body,
            }))
        }
        Err(ureq::Error::Status(status, response)) => {
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            Err(json!({
                "status": status,
                "status_text": status_text,
                "body": body,
            }))
        }
        Err(err) => Err(json!({
            "error": err.to_string(),
        })),
    }
}

fn summarize_langfuse_trace_response(response: &Value) -> Value {
    let trace = response
        .get("response")
        .and_then(Value::as_object)
        .map(|_| response.get("response").unwrap())
        .unwrap_or(response);
    let observations = trace
        .get("observations")
        .and_then(Value::as_array)
        .cloned()
        .or_else(|| trace.get("data").and_then(Value::as_array).cloned())
        .unwrap_or_default();

    let mut names = BTreeSet::new();
    let mut types = BTreeSet::new();
    let mut environments = BTreeSet::new();
    let mut models = BTreeSet::new();
    let mut model_ids = BTreeSet::new();
    let mut harnesses = BTreeSet::new();
    let mut providers = BTreeSet::new();
    let mut total_tokens = 0_u64;
    let mut input_tokens = 0_u64;
    let mut output_tokens = 0_u64;
    let mut calculated_total_cost = 0.0_f64;
    let mut has_cost = false;
    let mut tool_stats: BTreeMap<String, ToolTraceStats> = BTreeMap::new();
    let mut tool_events = Vec::new();
    let mut operation_stats: BTreeMap<String, ToolTraceStats> = BTreeMap::new();
    let mut operation_events = Vec::new();
    let mut agent_tool_stats: BTreeMap<String, ToolTraceStats> = BTreeMap::new();
    let mut agent_tool_events = Vec::new();
    let mut harness_tool_stats: BTreeMap<String, ToolTraceStats> = BTreeMap::new();
    let mut harness_tool_events = Vec::new();
    let mut category_counts: BTreeMap<String, u64> = BTreeMap::new();
    let mut trace_events = Vec::new();
    let mut generation_stats: BTreeMap<String, GenerationTraceStats> = BTreeMap::new();
    let mut generation_events = Vec::new();

    for observation in &observations {
        insert_string(&mut names, observation.get("name"));
        insert_string(&mut types, observation.get("type"));
        insert_string(&mut environments, observation.get("environment"));
        insert_string(&mut models, observation.get("model"));
        insert_string(&mut model_ids, observation.get("modelId"));

        let observation_input_tokens = usage_number(observation, "input")
            .or_else(|| Some(number_u64(observation.get("promptTokens"))))
            .unwrap_or(0);
        let observation_output_tokens = usage_number(observation, "output")
            .or_else(|| Some(number_u64(observation.get("completionTokens"))))
            .unwrap_or(0);
        let observation_total_tokens = usage_number(observation, "total")
            .or_else(|| Some(number_u64(observation.get("totalTokens"))))
            .unwrap_or(0);
        let is_generation = is_generation_observation(observation, observation_total_tokens);
        if is_generation {
            input_tokens = input_tokens.saturating_add(observation_input_tokens);
            output_tokens = output_tokens.saturating_add(observation_output_tokens);
            total_tokens = total_tokens.saturating_add(observation_total_tokens);
        }

        if is_generation {
            if let Some(cost) = total_cost_number(observation) {
                calculated_total_cost += cost;
                has_cost = true;
            }
        }

        let attrs = observation
            .get("metadata")
            .and_then(|metadata| metadata.get("attributes"));
        let event_seq = attr_u64(attrs, "agentic.event.seq");
        insert_string(
            &mut harnesses,
            attrs.and_then(|attrs| attrs.get("agentic.harness")),
        );
        insert_string(
            &mut providers,
            attrs.and_then(|attrs| attrs.get("agentic.provider")),
        );
        insert_string(
            &mut models,
            attrs.and_then(|attrs| attrs.get("agentic.model")),
        );

        let event_type = attr_string(attrs, "agentic.event.type").or_else(|| {
            observation
                .get("name")
                .and_then(Value::as_str)
                .map(str::to_string)
        });
        let tool_name = attr_string(attrs, "agentic.tool.name");
        let category = classify_trace_event(event_type.as_deref(), tool_name.as_deref());
        *category_counts.entry(category.to_string()).or_default() += 1;
        if let Some(event_type) = event_type.clone() {
            trace_events.push(TraceEvent {
                seq: event_seq,
                sort_time: observation
                    .get("startTime")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                sort_id: observation
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                event: event_type,
                name: observation
                    .get("name")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                category: category.to_string(),
                tool_name: tool_name.clone(),
                harness: attr_string(attrs, "agentic.harness"),
                provider: attr_string(attrs, "agentic.provider"),
                model: attr_string(attrs, "agentic.model").or_else(|| {
                    observation
                        .get("model")
                        .and_then(Value::as_str)
                        .map(str::to_string)
                }),
                success: attr_bool(attrs, "agentic.tool.success")
                    .or_else(|| attr_bool(attrs, "agentic.outcome.success")),
                total_tokens: number_u64(observation.get("totalTokens")),
                calculated_total_cost: number_f64(observation.get("calculatedTotalCost")),
            });
        }
        if is_generation {
            let model = observation
                .get("model")
                .and_then(Value::as_str)
                .map(str::to_string)
                .or_else(|| attr_string(attrs, "agentic.model"))
                .unwrap_or_else(|| "unknown".to_string());
            let model_id = observation
                .get("modelId")
                .and_then(Value::as_str)
                .map(str::to_string);
            let harness = attr_string(attrs, "agentic.harness");
            let provider = attr_string(attrs, "agentic.provider");
            let input_cost = cost_number(observation, "input")
                .or_else(|| number_f64(observation.get("calculatedInputCost")));
            let output_cost = cost_number(observation, "output")
                .or_else(|| number_f64(observation.get("calculatedOutputCost")));
            let total_cost =
                cost_number(observation, "total").or_else(|| total_cost_number(observation));
            let stats = generation_stats.entry(model.clone()).or_default();
            stats.count = stats.count.saturating_add(1);
            stats.input_tokens = stats.input_tokens.saturating_add(observation_input_tokens);
            stats.output_tokens = stats
                .output_tokens
                .saturating_add(observation_output_tokens);
            stats.total_tokens = stats.total_tokens.saturating_add(observation_total_tokens);
            if let Some(cost) = total_cost {
                stats.calculated_total_usd += cost;
                stats.has_cost = true;
            }
            if let Some(provider) = provider.as_ref() {
                stats.providers.insert(provider.clone());
            }
            if let Some(harness) = harness.as_ref() {
                stats.harnesses.insert(harness.clone());
            }
            if let Some(model_id) = model_id.as_ref() {
                stats.model_ids.insert(model_id.clone());
            }
            generation_events.push(GenerationTraceEvent {
                seq: event_seq,
                sort_time: observation
                    .get("startTime")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                sort_id: observation
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                observation_id: observation
                    .get("id")
                    .and_then(Value::as_str)
                    .map(str::to_string),
                name: observation
                    .get("name")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                model,
                model_id,
                harness,
                provider,
                input_tokens: observation_input_tokens,
                output_tokens: observation_output_tokens,
                total_tokens: observation_total_tokens,
                cached_input_tokens: usage_number(observation, "cached_prompt_tokens")
                    .or_else(|| usage_number(observation, "cachedInput"))
                    .or_else(|| usage_number(observation, "cached_input_tokens")),
                reasoning_output_tokens: usage_number(observation, "reasoning_completion_tokens")
                    .or_else(|| usage_number(observation, "reasoningOutput"))
                    .or_else(|| usage_number(observation, "reasoning_output_tokens")),
                calculated_input_cost_usd: input_cost,
                calculated_output_cost_usd: output_cost,
                calculated_total_cost_usd: total_cost,
                pricing_tier: observation
                    .get("usagePricingTierName")
                    .and_then(Value::as_str)
                    .map(str::to_string),
                unit: observation
                    .get("unit")
                    .and_then(Value::as_str)
                    .map(str::to_string),
            });
        }
        if matches!(event_type.as_deref(), Some("tool_start" | "tool_end")) {
            let event_type_value = event_type.clone().unwrap_or_else(|| "unknown".to_string());
            let tool_name = tool_name.unwrap_or_else(|| "unknown".to_string());
            let success = attr_bool(attrs, "agentic.tool.success");
            let stats = tool_stats.entry(tool_name.clone()).or_default();
            update_tool_trace_stats(stats, event_type.as_deref(), success);
            tool_events.push(ToolTraceEvent {
                seq: event_seq,
                sort_time: observation
                    .get("startTime")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                sort_id: observation
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                event: event_type_value.clone(),
                tool_name: tool_name.clone(),
                success,
            });
            let category_group = match category {
                "operation" => Some((&mut operation_stats, &mut operation_events)),
                "agent_tool" => Some((&mut agent_tool_stats, &mut agent_tool_events)),
                "harness_tool" => Some((&mut harness_tool_stats, &mut harness_tool_events)),
                _ => None,
            };
            if let Some((stats_by_name, events)) = category_group {
                let stats = stats_by_name.entry(tool_name.clone()).or_default();
                update_tool_trace_stats(stats, event_type.as_deref(), success);
                events.push(ToolTraceEvent {
                    seq: event_seq,
                    sort_time: observation
                        .get("startTime")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string(),
                    sort_id: observation
                        .get("id")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string(),
                    event: event_type_value,
                    tool_name,
                    success,
                });
            }
        }
    }

    let category_counts = category_counts
        .into_iter()
        .map(|(category, count)| {
            json!({
                "category": category,
                "count": count,
            })
        })
        .collect::<Vec<_>>();
    let event_sequence_source = if trace_events.iter().any(|event| event.seq.is_some()) {
        Some("agentic.event.seq")
    } else {
        None
    };
    trace_events.sort_by(|a, b| {
        a.seq
            .unwrap_or(u64::MAX)
            .cmp(&b.seq.unwrap_or(u64::MAX))
            .then_with(|| a.sort_time.cmp(&b.sort_time))
            .then_with(|| a.sort_id.cmp(&b.sort_id))
    });
    let event_sequence_truncated = trace_events.len() > 200;
    let event_sequence = trace_events
        .into_iter()
        .take(200)
        .map(|event| {
            json!({
                "seq": event.seq,
                "event": event.event,
                "name": event.name,
                "category": event.category,
                "tool_name": event.tool_name,
                "harness": event.harness,
                "provider": event.provider,
                "model": event.model,
                "success": event.success,
                "total_tokens": event.total_tokens,
                "calculated_total_cost": event.calculated_total_cost,
            })
        })
        .collect::<Vec<_>>();
    let tools = summarize_tool_trace_group(tool_stats, tool_events, 100);
    let operations = summarize_tool_trace_group(operation_stats, operation_events, 100);
    let agent_tools = summarize_tool_trace_group(agent_tool_stats, agent_tool_events, 100);
    let harness_tools = summarize_tool_trace_group(harness_tool_stats, harness_tool_events, 100);
    let generations = summarize_generation_trace_group(generation_stats, generation_events, 100);

    json!({
        "trace_id": trace.get("id").and_then(Value::as_str),
        "trace_name": trace.get("name").and_then(Value::as_str),
        "session_id": trace.get("sessionId").and_then(Value::as_str),
        "environment": trace.get("environment").and_then(Value::as_str),
        "observation_count": observations.len(),
        "observation_names": names.into_iter().collect::<Vec<_>>(),
        "observation_types": types.into_iter().collect::<Vec<_>>(),
        "environments": environments.into_iter().collect::<Vec<_>>(),
        "harnesses": harnesses.into_iter().collect::<Vec<_>>(),
        "providers": providers.into_iter().collect::<Vec<_>>(),
        "models": models.into_iter().collect::<Vec<_>>(),
        "model_ids": model_ids.into_iter().collect::<Vec<_>>(),
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
        "cost": {
            "calculated_total_usd": if has_cost { Some(calculated_total_cost) } else { None },
        },
        "events": {
            "sequence_source": event_sequence_source,
            "category_counts": category_counts,
            "sequence": event_sequence,
            "sequence_truncated": event_sequence_truncated,
        },
        "tools": tools,
        "operations": operations,
        "agent_tools": agent_tools,
        "harness_tools": harness_tools,
        "generations": generations,
    })
}

fn summarize_langfuse_score_response(
    response: &Value,
    request: &LangFuseScoreCreateRequest,
) -> Value {
    json!({
        "score_id": response.get("id").and_then(Value::as_str),
        "trace_id": request.trace_id,
        "run_id": request.run_id,
        "name": request.name,
        "data_type": request.data_type,
        "created": response.get("id").and_then(Value::as_str).is_some(),
    })
}

fn summarize_langfuse_scores_response(
    response: &Value,
    request: &LangFuseScoresListRequest,
) -> Value {
    let rows = response
        .get("data")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let scores = rows
        .iter()
        .filter(|score| score_matches_scores_request(score, request))
        .map(|score| {
            let trace = score.get("trace");
            json!({
                "score_id": score.get("id").and_then(Value::as_str),
                "trace_id": score.get("traceId").and_then(Value::as_str),
                "observation_id": score.get("observationId").and_then(Value::as_str),
                "name": score.get("name").and_then(Value::as_str),
                "data_type": score.get("dataType").and_then(Value::as_str),
                "value": score.get("value"),
                "string_value": score.get("stringValue").and_then(Value::as_str),
                "source": score.get("source").and_then(Value::as_str),
                "environment": score.get("environment").and_then(Value::as_str),
                "comment": score.get("comment").and_then(Value::as_str),
                "metadata": score.get("metadata"),
                "created_at": score.get("createdAt").and_then(Value::as_str),
                "updated_at": score.get("updatedAt").and_then(Value::as_str),
                "trace_environment": trace
                    .and_then(|trace| trace.get("environment"))
                    .and_then(Value::as_str),
                "trace_tags": trace
                    .and_then(|trace| trace.get("tags"))
                    .and_then(Value::as_array),
            })
        })
        .collect::<Vec<_>>();

    json!({
        "requested_trace_id": request.trace_id,
        "requested_run_id": request.run_id,
        "requested_name": request.name,
        "requested_score_ids": request.score_ids,
        "returned_count": scores.len(),
        "total_items": response
            .get("meta")
            .and_then(|meta| meta.get("totalItems"))
            .and_then(Value::as_u64),
        "scores": scores,
    })
}

fn score_matches_scores_request(score: &Value, request: &LangFuseScoresListRequest) -> bool {
    if let Some(expected) = request
        .trace_id
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        if score
            .get("traceId")
            .and_then(Value::as_str)
            .map(|actual| actual != expected)
            .unwrap_or(true)
        {
            return false;
        }
    }
    if let Some(expected_ids) = request
        .score_ids
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        let score_id = score.get("id").and_then(Value::as_str);
        let expected = expected_ids
            .split(',')
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .collect::<Vec<_>>();
        if !expected.is_empty() && !score_id.is_some_and(|actual| expected.contains(&actual)) {
            return false;
        }
    }
    if let Some(expected) = request
        .name
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        if score
            .get("name")
            .and_then(Value::as_str)
            .map(|actual| actual != expected)
            .unwrap_or(true)
        {
            return false;
        }
    }
    if let Some(expected) = request
        .data_type
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        if score
            .get("dataType")
            .and_then(Value::as_str)
            .map(|actual| !actual.eq_ignore_ascii_case(expected))
            .unwrap_or(true)
        {
            return false;
        }
    }
    true
}

fn summarize_langfuse_traces_response(
    response: &Value,
    request: &LangFuseTracesListRequest,
) -> Value {
    let rows = response
        .get("data")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut traces = Vec::new();
    let mut harnesses = BTreeSet::new();
    let mut providers = BTreeSet::new();
    let mut models = BTreeSet::new();
    let mut environments = BTreeSet::new();
    let mut total_cost = 0.0_f64;
    let mut has_cost = false;

    for trace in rows {
        let metadata = trace.get("metadata");
        let harness = metadata_string(metadata, "harness").or_else(|| {
            trace
                .get("tags")
                .and_then(Value::as_array)
                .and_then(|tags| {
                    tags.iter().find_map(|tag| {
                        tag.as_str()
                            .and_then(|tag| tag.strip_prefix("harness:"))
                            .map(ToOwned::to_owned)
                    })
                })
        });
        let provider = metadata_string(metadata, "provider");
        let model = metadata_string(metadata, "model");
        let environment = trace
            .get("environment")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned)
            .or_else(|| metadata_string(metadata, "langfuse.environment"));

        if !filter_matches(&harness, request.harness.as_deref())
            || !filter_matches(&provider, request.provider.as_deref())
            || !filter_matches(&model, request.model.as_deref())
            || !filter_matches(&environment, request.environment.as_deref())
        {
            continue;
        }

        if let Some(value) = harness.as_ref() {
            harnesses.insert(value.clone());
        }
        if let Some(value) = provider.as_ref() {
            providers.insert(value.clone());
        }
        if let Some(value) = model.as_ref() {
            models.insert(value.clone());
        }
        if let Some(value) = environment.as_ref() {
            environments.insert(value.clone());
        }
        if let Some(cost) = number_f64(trace.get("totalCost")) {
            total_cost += cost;
            has_cost = true;
        }

        let observation_count = trace
            .get("observations")
            .and_then(Value::as_array)
            .map(|observations| observations.len())
            .unwrap_or(0);
        traces.push(json!({
            "trace_id": trace.get("id").and_then(Value::as_str),
            "run_id": metadata_string(metadata, "run_id")
                .or_else(|| trace.get("sessionId").and_then(Value::as_str).map(ToOwned::to_owned)),
            "session_id": trace.get("sessionId").and_then(Value::as_str),
            "name": trace.get("name").and_then(Value::as_str),
            "timestamp": trace.get("timestamp").and_then(Value::as_str),
            "created_at": trace.get("createdAt").and_then(Value::as_str),
            "updated_at": trace.get("updatedAt").and_then(Value::as_str),
            "environment": environment,
            "harness": harness,
            "provider": provider,
            "model": model,
            "total_cost": number_f64(trace.get("totalCost")),
            "latency_s": number_f64(trace.get("latency")),
            "observation_count": observation_count,
            "html_path": trace.get("htmlPath").and_then(Value::as_str),
        }));
    }

    json!({
        "page": request.page,
        "limit": request.limit,
        "returned_count": traces.len(),
        "backend_total_items": response.pointer("/meta/totalItems").and_then(Value::as_u64),
        "backend_total_pages": response.pointer("/meta/totalPages").and_then(Value::as_u64),
        "filters": {
            "harness": request.harness,
            "provider": request.provider,
            "model": request.model,
            "environment": request.environment,
        },
        "harnesses": harnesses.into_iter().collect::<Vec<_>>(),
        "providers": providers.into_iter().collect::<Vec<_>>(),
        "models": models.into_iter().collect::<Vec<_>>(),
        "environments": environments.into_iter().collect::<Vec<_>>(),
        "total_cost": if has_cost { Some(total_cost) } else { None },
        "traces": traces,
    })
}

#[derive(Debug, Default)]
struct ToolTraceStats {
    starts: u64,
    ends: u64,
    successes: u64,
    failures: u64,
}

#[derive(Debug, Default)]
struct GenerationTraceStats {
    count: u64,
    input_tokens: u64,
    output_tokens: u64,
    total_tokens: u64,
    calculated_total_usd: f64,
    has_cost: bool,
    providers: BTreeSet<String>,
    harnesses: BTreeSet<String>,
    model_ids: BTreeSet<String>,
}

#[derive(Debug)]
struct ToolTraceEvent {
    seq: Option<u64>,
    sort_time: String,
    sort_id: String,
    event: String,
    tool_name: String,
    success: Option<bool>,
}

#[derive(Debug)]
struct GenerationTraceEvent {
    seq: Option<u64>,
    sort_time: String,
    sort_id: String,
    observation_id: Option<String>,
    name: String,
    model: String,
    model_id: Option<String>,
    harness: Option<String>,
    provider: Option<String>,
    input_tokens: u64,
    output_tokens: u64,
    total_tokens: u64,
    cached_input_tokens: Option<u64>,
    reasoning_output_tokens: Option<u64>,
    calculated_input_cost_usd: Option<f64>,
    calculated_output_cost_usd: Option<f64>,
    calculated_total_cost_usd: Option<f64>,
    pricing_tier: Option<String>,
    unit: Option<String>,
}

#[derive(Debug)]
struct TraceEvent {
    seq: Option<u64>,
    sort_time: String,
    sort_id: String,
    event: String,
    name: String,
    category: String,
    tool_name: Option<String>,
    harness: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    success: Option<bool>,
    total_tokens: u64,
    calculated_total_cost: Option<f64>,
}

fn update_tool_trace_stats(
    stats: &mut ToolTraceStats,
    event_type: Option<&str>,
    success: Option<bool>,
) {
    match event_type {
        Some("tool_start") => stats.starts = stats.starts.saturating_add(1),
        Some("tool_end") => {
            stats.ends = stats.ends.saturating_add(1);
            match success {
                Some(true) => stats.successes = stats.successes.saturating_add(1),
                Some(false) => stats.failures = stats.failures.saturating_add(1),
                None => {}
            }
        }
        _ => {}
    }
}

fn summarize_tool_trace_group(
    stats: BTreeMap<String, ToolTraceStats>,
    mut events: Vec<ToolTraceEvent>,
    limit: usize,
) -> Value {
    let start_count = stats.values().map(|stats| stats.starts).sum::<u64>();
    let end_count = stats.values().map(|stats| stats.ends).sum::<u64>();
    let success_count = stats.values().map(|stats| stats.successes).sum::<u64>();
    let failure_count = stats.values().map(|stats| stats.failures).sum::<u64>();
    let names = stats.keys().cloned().collect::<Vec<_>>();
    let by_name = stats
        .into_iter()
        .map(|(name, stats)| {
            json!({
                "name": name,
                "starts": stats.starts,
                "ends": stats.ends,
                "successes": stats.successes,
                "failures": stats.failures,
            })
        })
        .collect::<Vec<_>>();
    let sequence_source = if events.iter().any(|event| event.seq.is_some()) {
        Some("agentic.event.seq")
    } else {
        None
    };
    events.sort_by(|a, b| {
        a.seq
            .unwrap_or(u64::MAX)
            .cmp(&b.seq.unwrap_or(u64::MAX))
            .then_with(|| a.sort_time.cmp(&b.sort_time))
            .then_with(|| a.sort_id.cmp(&b.sort_id))
    });
    let sequence_truncated = events.len() > limit;
    let sequence = events
        .into_iter()
        .take(limit)
        .map(|event| {
            json!({
                "seq": event.seq,
                "event": event.event,
                "tool_name": event.tool_name,
                "success": event.success,
            })
        })
        .collect::<Vec<_>>();

    json!({
        "start_count": start_count,
        "end_count": end_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "names": names,
        "by_name": by_name,
        "sequence_source": sequence_source,
        "sequence": sequence,
        "sequence_truncated": sequence_truncated,
    })
}

fn summarize_generation_trace_group(
    stats: BTreeMap<String, GenerationTraceStats>,
    mut events: Vec<GenerationTraceEvent>,
    max_sequence: usize,
) -> Value {
    let mut total_count = 0_u64;
    let mut input_tokens = 0_u64;
    let mut output_tokens = 0_u64;
    let mut total_tokens = 0_u64;
    let mut calculated_total_usd = 0.0_f64;
    let mut has_cost = false;
    let by_model = stats
        .into_iter()
        .map(|(model, stats)| {
            total_count = total_count.saturating_add(stats.count);
            input_tokens = input_tokens.saturating_add(stats.input_tokens);
            output_tokens = output_tokens.saturating_add(stats.output_tokens);
            total_tokens = total_tokens.saturating_add(stats.total_tokens);
            if stats.has_cost {
                calculated_total_usd += stats.calculated_total_usd;
                has_cost = true;
            }
            json!({
                "model": model,
                "model_ids": stats.model_ids.into_iter().collect::<Vec<_>>(),
                "providers": stats.providers.into_iter().collect::<Vec<_>>(),
                "harnesses": stats.harnesses.into_iter().collect::<Vec<_>>(),
                "count": stats.count,
                "input_tokens": stats.input_tokens,
                "output_tokens": stats.output_tokens,
                "total_tokens": stats.total_tokens,
                "calculated_total_usd": if stats.has_cost {
                    Some(stats.calculated_total_usd)
                } else {
                    None
                },
            })
        })
        .collect::<Vec<_>>();

    let sequence_source = if events.iter().any(|event| event.seq.is_some()) {
        Some("agentic.event.seq")
    } else {
        None
    };
    events.sort_by(|a, b| {
        a.seq
            .unwrap_or(u64::MAX)
            .cmp(&b.seq.unwrap_or(u64::MAX))
            .then_with(|| a.sort_time.cmp(&b.sort_time))
            .then_with(|| a.sort_id.cmp(&b.sort_id))
    });
    let sequence_truncated = events.len() > max_sequence;
    let sequence = events
        .into_iter()
        .take(max_sequence)
        .map(|event| {
            json!({
                "seq": event.seq,
                "observation_id": event.observation_id,
                "name": event.name,
                "model": event.model,
                "model_id": event.model_id,
                "harness": event.harness,
                "provider": event.provider,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "total_tokens": event.total_tokens,
                "cached_input_tokens": event.cached_input_tokens,
                "reasoning_output_tokens": event.reasoning_output_tokens,
                "calculated_input_cost_usd": event.calculated_input_cost_usd,
                "calculated_output_cost_usd": event.calculated_output_cost_usd,
                "calculated_total_cost_usd": event.calculated_total_cost_usd,
                "pricing_tier": event.pricing_tier,
                "unit": event.unit,
            })
        })
        .collect::<Vec<_>>();

    json!({
        "count": total_count,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "calculated_total_usd": if has_cost {
            Some(calculated_total_usd)
        } else {
            None
        },
        "by_model": by_model,
        "sequence_source": sequence_source,
        "sequence": sequence,
        "sequence_truncated": sequence_truncated,
    })
}

fn classify_trace_event(event_type: Option<&str>, tool_name: Option<&str>) -> &'static str {
    match event_type {
        Some("tool_start" | "tool_end") => classify_tool_event(tool_name),
        Some("token_usage") => "usage",
        Some("hook_event") => "hook",
        Some("session_end") => "session",
        Some("agentic_primitives.run") => "root",
        Some(_) | None => "other",
    }
}

fn classify_tool_event(tool_name: Option<&str>) -> &'static str {
    match tool_name.unwrap_or_default() {
        "provision" | "launch" | "submit" | "await" | "capture" => "operation",
        name if name.starts_with("codex_exec.thread")
            || name.starts_with("codex_exec.turn")
            || name.starts_with("codex_exec.error")
            || name.starts_with("claude_transcript.") =>
        {
            "harness_tool"
        }
        name if name.starts_with("codex_exec.item.") => "agent_tool",
        "" | "unknown" => "other",
        _ => "agent_tool",
    }
}

fn insert_string(out: &mut BTreeSet<String>, value: Option<&Value>) {
    if let Some(value) = value.and_then(Value::as_str) {
        if !value.trim().is_empty() {
            out.insert(value.to_string());
        }
    }
}

fn attr_string(attrs: Option<&Value>, key: &str) -> Option<String> {
    attrs
        .and_then(|attrs| attrs.get(key))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn attr_bool(attrs: Option<&Value>, key: &str) -> Option<bool> {
    attrs.and_then(|attrs| attrs.get(key)).and_then(|value| {
        value.as_bool().or_else(|| match value.as_str()?.trim() {
            "true" => Some(true),
            "false" => Some(false),
            _ => None,
        })
    })
}

fn attr_u64(attrs: Option<&Value>, key: &str) -> Option<u64> {
    attrs.and_then(|attrs| attrs.get(key)).and_then(|value| {
        value
            .as_u64()
            .or_else(|| value.as_str()?.trim().parse().ok())
    })
}

fn metadata_string(metadata: Option<&Value>, key: &str) -> Option<String> {
    metadata
        .and_then(|metadata| metadata.get(key))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn filter_matches(value: &Option<String>, expected: Option<&str>) -> bool {
    let Some(expected) = expected.map(str::trim).filter(|value| !value.is_empty()) else {
        return true;
    };
    value
        .as_deref()
        .is_some_and(|value| value.eq_ignore_ascii_case(expected))
}

fn number_u64(value: Option<&Value>) -> u64 {
    value
        .and_then(|value| {
            value
                .as_u64()
                .or_else(|| value.as_f64().map(|v| v.max(0.0) as u64))
        })
        .unwrap_or(0)
}

fn number_f64(value: Option<&Value>) -> Option<f64> {
    value.and_then(|value| value.as_f64().or_else(|| value.as_u64().map(|v| v as f64)))
}

fn usage_number(observation: &Value, key: &str) -> Option<u64> {
    observation
        .get("usageDetails")
        .and_then(|details| details.get(key))
        .map(Some)
        .map(number_u64)
        .filter(|value| *value > 0)
        .or_else(|| {
            observation
                .get("usage")
                .and_then(|usage| usage.get(key))
                .map(Some)
                .map(number_u64)
                .filter(|value| *value > 0)
        })
}

fn cost_number(observation: &Value, key: &str) -> Option<f64> {
    observation
        .get("costDetails")
        .and_then(|details| details.get(key))
        .and_then(|value| number_f64(Some(value)))
}

fn total_cost_number(observation: &Value) -> Option<f64> {
    cost_number(observation, "total")
        .or_else(|| number_f64(observation.get("calculatedTotalCost")))
        .or_else(|| number_f64(observation.get("totalCost")))
}

fn is_generation_observation(observation: &Value, total_tokens: u64) -> bool {
    match observation.get("type").and_then(Value::as_str) {
        Some("GENERATION") => true,
        Some(_) => false,
        None => total_tokens > 0,
    }
}

fn build_langfuse_observations_v2_url(
    base_url: &str,
    trace_id: &str,
    from_start_time: &str,
    to_start_time: &str,
    fields: &str,
    limit: u32,
) -> String {
    let base = langfuse_api_base_url(base_url);
    format!(
        "{}/api/public/v2/observations?traceId={}&fromStartTime={}&toStartTime={}&fields={}&limit={}",
        base.trim_end_matches('/'),
        url_query_encode(trace_id),
        url_query_encode(from_start_time),
        url_query_encode(to_start_time),
        url_query_encode(fields),
        limit
    )
}

fn build_langfuse_trace_query_url(
    api: LangFuseTraceApi,
    base_url: &str,
    trace_id: &str,
    from_start_time: &str,
    to_start_time: &str,
    fields: &str,
    limit: u32,
) -> String {
    match api {
        LangFuseTraceApi::ObservationsV2 => build_langfuse_observations_v2_url(
            base_url,
            trace_id,
            from_start_time,
            to_start_time,
            fields,
            limit,
        ),
        LangFuseTraceApi::LegacyTrace => {
            let base = langfuse_api_base_url(base_url);
            format!(
                "{}/api/public/traces/{}",
                base.trim_end_matches('/'),
                url_path_encode(trace_id)
            )
        }
    }
}

fn build_langfuse_traces_list_url(base_url: &str, limit: u32, page: u32) -> String {
    let base = langfuse_api_base_url(base_url);
    format!(
        "{}/api/public/traces?limit={}&page={}",
        base.trim_end_matches('/'),
        limit,
        page
    )
}

fn build_langfuse_score_create_url(base_url: &str) -> String {
    let base = langfuse_api_base_url(base_url);
    format!("{}/api/public/scores", base.trim_end_matches('/'))
}

fn build_langfuse_scores_list_url(
    base_url: &str,
    trace_id: Option<&str>,
    score_ids: Option<&str>,
    name: Option<&str>,
    data_type: Option<&str>,
    limit: u32,
    page: u32,
) -> String {
    let base = langfuse_api_base_url(base_url);
    let mut params = vec![format!("limit={limit}"), format!("page={page}")];
    if let Some(trace_id) = non_empty_str(trace_id) {
        params.push(format!("traceId={}", url_query_encode(trace_id)));
    }
    if let Some(score_ids) = non_empty_str(score_ids) {
        params.push(format!("scoreIds={}", url_query_encode(score_ids)));
    }
    if let Some(name) = non_empty_str(name) {
        params.push(format!("name={}", url_query_encode(name)));
    }
    if let Some(data_type) = non_empty_str(data_type) {
        params.push(format!("dataType={}", url_query_encode(data_type)));
    }
    format!(
        "{}/api/public/scores?{}",
        base.trim_end_matches('/'),
        params.join("&")
    )
}

fn non_empty_str(value: Option<&str>) -> Option<&str> {
    value.map(str::trim).filter(|value| !value.is_empty())
}

fn url_path_encode(value: &str) -> String {
    let mut out = String::new();
    for byte in value.bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'.' | b'_' | b'~') {
            out.push(byte as char);
        } else {
            out.push('%');
            out.push(char::from(b"0123456789ABCDEF"[(byte >> 4) as usize]));
            out.push(char::from(b"0123456789ABCDEF"[(byte & 0x0f) as usize]));
        }
    }
    out
}

fn url_query_encode(value: &str) -> String {
    let mut out = String::new();
    for byte in value.bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'.' | b'_' | b'~') {
            out.push(byte as char);
        } else {
            out.push('%');
            out.push(char::from(b"0123456789ABCDEF"[(byte >> 4) as usize]));
            out.push(char::from(b"0123456789ABCDEF"[(byte & 0x0f) as usize]));
        }
    }
    out
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    match cli.cmd {
        Cmd::Start {
            name,
            image,
            workdir,
            agents,
            cols,
            rows,
            startup_timeout,
            strict_startup,
        } => handle_start(
            name,
            image,
            workdir,
            agents,
            cols,
            rows,
            startup_timeout,
            strict_startup,
        ),
        Cmd::Send { name, agent, text } => handle_send(name, agent, text),
        Cmd::Await {
            name,
            agent,
            timeout,
            stable_polls,
            poll_interval,
            warmup,
        } => handle_await(name, agent, timeout, stable_polls, poll_interval, warmup),
        Cmd::Capture { name, agent } => handle_capture(name, agent),
        Cmd::Exec { name, argv } => handle_exec(name, argv),
        Cmd::Stop { name } => handle_stop(name),
        Cmd::Run {
            recipe,
            task,
            image,
            codex_mode,
            codex_bin,
            codex_sandbox,
            json,
            result_file,
            timeout,
            env_file,
            allow_host_auth_fallback,
            observability_file,
            observability_langfuse,
            observability_langfuse_force,
            langfuse_base_url,
            langfuse_project_id,
            langfuse_label,
        } => handle_run(
            recipe,
            task,
            image,
            codex_mode,
            codex_bin,
            codex_sandbox,
            json,
            result_file,
            timeout,
            env_file,
            allow_host_auth_fallback,
            observability_file,
            LangFuseCliOptions {
                enabled: observability_langfuse,
                force: observability_langfuse_force,
                official_plugin_tracing_active: official_langfuse_plugin_tracing_active(),
                base_url: langfuse_base_url,
                project_id: langfuse_project_id,
                label: langfuse_label,
            },
        ),
        Cmd::CodexExec {
            prompt,
            codex_bin,
            model,
            sandbox,
            json,
            result_file,
            observability_file,
            observability_langfuse,
            observability_langfuse_force,
            langfuse_base_url,
            langfuse_project_id,
            langfuse_label,
        } => handle_codex_exec(
            prompt,
            codex_bin,
            model,
            sandbox,
            json,
            result_file,
            observability_file,
            LangFuseCliOptions {
                enabled: observability_langfuse,
                force: observability_langfuse_force,
                official_plugin_tracing_active: official_langfuse_plugin_tracing_active(),
                base_url: langfuse_base_url,
                project_id: langfuse_project_id,
                label: langfuse_label,
            },
        ),
        Cmd::ClaudeTranscript {
            transcript,
            run_id,
            json,
            result_file,
            observability_file,
            observability_langfuse,
            observability_langfuse_force,
            langfuse_base_url,
            langfuse_project_id,
            langfuse_label,
        } => handle_claude_transcript(
            transcript,
            run_id,
            json,
            result_file,
            observability_file,
            LangFuseCliOptions {
                enabled: observability_langfuse,
                force: observability_langfuse_force,
                official_plugin_tracing_active: official_langfuse_plugin_tracing_active(),
                base_url: langfuse_base_url,
                project_id: langfuse_project_id,
                label: langfuse_label,
            },
        ),
        Cmd::LangFuseTrace {
            trace_id,
            run_id,
            langfuse_base_url,
            public_key_env,
            secret_key_env,
            from_start_time,
            to_start_time,
            fields,
            limit,
            include_scores,
            score_limit,
            api,
            output,
        } => handle_langfuse_trace(
            trace_id,
            run_id,
            langfuse_base_url,
            public_key_env,
            secret_key_env,
            from_start_time,
            to_start_time,
            fields,
            limit,
            include_scores,
            score_limit,
            api,
            output,
        ),
        Cmd::LangFuseTraces {
            langfuse_base_url,
            public_key_env,
            secret_key_env,
            limit,
            page,
            harness,
            provider,
            model,
            environment,
            output,
        } => handle_langfuse_traces(
            langfuse_base_url,
            public_key_env,
            secret_key_env,
            limit,
            page,
            harness,
            provider,
            model,
            environment,
            output,
        ),
        Cmd::LangFuseScore {
            trace_id,
            run_id,
            langfuse_base_url,
            public_key_env,
            secret_key_env,
            name,
            value,
            data_type,
            comment,
            metadata_json,
            score_id,
            environment,
            output,
        } => handle_langfuse_score(
            trace_id,
            run_id,
            langfuse_base_url,
            public_key_env,
            secret_key_env,
            name,
            value,
            data_type,
            comment,
            metadata_json,
            score_id,
            environment,
            output,
        ),
        Cmd::LangFuseScores {
            trace_id,
            run_id,
            langfuse_base_url,
            public_key_env,
            secret_key_env,
            score_ids,
            name,
            data_type,
            limit,
            page,
            output,
        } => handle_langfuse_scores(
            trace_id,
            run_id,
            langfuse_base_url,
            public_key_env,
            secret_key_env,
            score_ids,
            name,
            data_type,
            limit,
            page,
            output,
        ),
    }
}

#[cfg(test)]
mod cli_tests {
    use super::*;

    #[test]
    fn cli_exporters_include_file_and_langfuse_when_enabled() {
        let exporters = build_observability_exporters(
            Some(PathBuf::from("/tmp/events.jsonl")),
            "local events",
            LangFuseCliOptions {
                enabled: true,
                force: false,
                official_plugin_tracing_active: false,
                base_url: Some("https://cloud.langfuse.com".to_string()),
                project_id: Some("project-123".to_string()),
                label: Some("trace view".to_string()),
            },
        );

        assert_eq!(exporters.len(), 2);
        assert!(matches!(exporters[0], ObservabilityExporter::File { .. }));
        match &exporters[1] {
            ObservabilityExporter::LangFuseOtlp {
                base_url,
                public_key_env,
                secret_key_env,
                environment_env,
                project_id,
                project_id_env,
                service_name,
                label,
            } => {
                assert_eq!(base_url.as_deref(), Some("https://cloud.langfuse.com"));
                assert_eq!(public_key_env, "LANGFUSE_PUBLIC_KEY");
                assert_eq!(secret_key_env, "LANGFUSE_SECRET_KEY");
                assert_eq!(environment_env, "LANGFUSE_TRACING_ENVIRONMENT");
                assert_eq!(project_id.as_deref(), Some("project-123"));
                assert_eq!(project_id_env, "LANGFUSE_PROJECT_ID");
                assert_eq!(service_name, "agentic-primitives");
                assert_eq!(label.as_deref(), Some("trace view"));
            }
            ObservabilityExporter::File { .. } => panic!("expected LangFuse exporter"),
        }
    }

    #[test]
    fn cli_exporters_do_not_require_langfuse_project_id() {
        let exporters = build_observability_exporters(
            None,
            "local events",
            LangFuseCliOptions {
                enabled: true,
                force: false,
                official_plugin_tracing_active: false,
                base_url: None,
                project_id: None,
                label: None,
            },
        );

        assert_eq!(exporters.len(), 1);
        match &exporters[0] {
            ObservabilityExporter::LangFuseOtlp {
                base_url,
                project_id,
                project_id_env,
                label,
                ..
            } => {
                assert!(base_url.is_none());
                assert!(project_id.is_none());
                assert_eq!(project_id_env, "LANGFUSE_PROJECT_ID");
                assert_eq!(label.as_deref(), Some("LangFuse trace"));
            }
            ObservabilityExporter::File { .. } => panic!("expected LangFuse exporter"),
        }
    }

    #[test]
    fn cli_exporters_suppress_langfuse_when_official_plugin_tracing_is_active() {
        let exporters = build_observability_exporters(
            Some(PathBuf::from("/tmp/events.jsonl")),
            "local events",
            LangFuseCliOptions {
                enabled: true,
                force: false,
                official_plugin_tracing_active: true,
                base_url: Some("http://localhost:3000".to_string()),
                project_id: None,
                label: None,
            },
        );

        assert_eq!(exporters.len(), 1);
        assert!(matches!(exporters[0], ObservabilityExporter::File { .. }));
    }

    #[test]
    fn cli_exporters_can_force_langfuse_when_official_plugin_tracing_is_active() {
        let exporters = build_observability_exporters(
            Some(PathBuf::from("/tmp/events.jsonl")),
            "local events",
            LangFuseCliOptions {
                enabled: true,
                force: true,
                official_plugin_tracing_active: true,
                base_url: Some("http://localhost:3000".to_string()),
                project_id: None,
                label: None,
            },
        );

        assert_eq!(exporters.len(), 2);
        assert!(matches!(exporters[0], ObservabilityExporter::File { .. }));
        assert!(matches!(
            exporters[1],
            ObservabilityExporter::LangFuseOtlp { .. }
        ));
    }

    #[test]
    fn codex_exec_model_prefers_explicit_model() {
        assert_eq!(
            resolve_codex_exec_model(Some(" gpt-explicit ".to_string())).as_deref(),
            Some("gpt-explicit")
        );
    }

    #[test]
    fn codex_config_model_reads_top_level_model_only() {
        let raw = r#"
            # Codex account default
            model = "gpt-5.5"

            [profiles.fast]
            model = "gpt-4.1"
        "#;

        assert_eq!(parse_codex_config_model(raw).as_deref(), Some("gpt-5.5"));
    }

    #[test]
    fn codex_config_model_ignores_profile_only_model() {
        let raw = r#"
            [profiles.fast]
            model = "gpt-4.1"
        "#;

        assert_eq!(parse_codex_config_model(raw), None);
    }

    #[test]
    fn codex_exec_model_strips_openai_recipe_prefix() {
        assert_eq!(
            codex_model_for_exec("openai/gpt-5.5").as_deref(),
            Some("gpt-5.5")
        );
        assert_eq!(
            codex_model_for_exec(" gpt-5.5 ").as_deref(),
            Some("gpt-5.5")
        );
        assert_eq!(codex_model_for_exec("  "), None);
    }

    #[test]
    fn run_cli_accepts_codex_exec_mode() {
        let cli = Cli::parse_from([
            "itmux",
            "run",
            "--recipe",
            "/tmp/recipe",
            "--task",
            "hello",
            "--codex-mode",
            "exec",
            "--codex-bin",
            "codex-dev",
            "--codex-sandbox",
            "workspace-write",
        ]);
        match cli.cmd {
            Cmd::Run {
                codex_mode,
                codex_bin,
                codex_sandbox,
                ..
            } => {
                assert_eq!(codex_mode, CodexRunMode::Exec);
                assert_eq!(codex_bin, "codex-dev");
                assert_eq!(codex_sandbox, "workspace-write");
            }
            other => panic!("expected run command, got {other:?}"),
        }
    }

    #[test]
    fn run_dispatch_only_uses_exec_for_codex_recipes() {
        assert_eq!(
            select_run_dispatch(Agent::Codex, CodexRunMode::Exec),
            RunDispatch::CodexExec
        );
        assert_eq!(
            select_run_dispatch(Agent::Codex, CodexRunMode::Tui),
            RunDispatch::WorkspaceTui
        );
        assert_eq!(
            select_run_dispatch(Agent::Claude, CodexRunMode::Exec),
            RunDispatch::AgentMismatch
        );
        assert_eq!(
            select_run_dispatch(Agent::Claude, CodexRunMode::Tui),
            RunDispatch::WorkspaceTui
        );
    }

    #[test]
    fn langfuse_trace_query_url_is_bounded_and_encoded() {
        let url = build_langfuse_trace_query_url(
            LangFuseTraceApi::ObservationsV2,
            "https://langfuse.example.com/api/public/otel/v1/traces",
            "abc123",
            "2026-07-07T20:00:00Z",
            "2026-07-07T20:30:00Z",
            "core,basic,usage,trace_context",
            25,
        );

        assert_eq!(
            url,
            "https://langfuse.example.com/api/public/v2/observations?traceId=abc123&fromStartTime=2026-07-07T20%3A00%3A00Z&toStartTime=2026-07-07T20%3A30%3A00Z&fields=core%2Cbasic%2Cusage%2Ctrace_context&limit=25"
        );
    }

    #[test]
    fn langfuse_trace_query_supports_legacy_self_host_trace_api() {
        let url = build_langfuse_trace_query_url(
            LangFuseTraceApi::LegacyTrace,
            "https://langfuse.example.com/api/public/otel",
            "trace id/with spaces",
            "2026-07-07T20:00:00Z",
            "2026-07-07T20:30:00Z",
            "core,basic",
            25,
        );

        assert_eq!(
            url,
            "https://langfuse.example.com/api/public/traces/trace%20id%2Fwith%20spaces"
        );
    }

    #[test]
    fn langfuse_trace_cli_defaults_are_agent_friendly() {
        let cli = Cli::try_parse_from([
            "itmux",
            "langfuse-trace",
            "--run-id",
            "run-query",
            "--api",
            "legacy-trace",
            "--output",
            "summary",
        ])
        .unwrap();

        let Cmd::LangFuseTrace {
            run_id,
            from_start_time,
            to_start_time,
            output,
            ..
        } = cli.cmd
        else {
            panic!("expected langfuse-trace command");
        };

        assert_eq!(run_id.as_deref(), Some("run-query"));
        assert_eq!(from_start_time, DEFAULT_LANGFUSE_QUERY_FROM_START_TIME);
        assert_eq!(to_start_time, DEFAULT_LANGFUSE_QUERY_TO_START_TIME);
        assert!(matches!(output, LangFuseTraceOutput::Summary));
    }

    #[test]
    fn langfuse_trace_cli_can_include_scores() {
        let cli = Cli::try_parse_from([
            "itmux",
            "langfuse-trace",
            "--run-id",
            "run-query",
            "--include-scores",
            "--score-limit",
            "7",
            "--output",
            "summary",
        ])
        .unwrap();

        let Cmd::LangFuseTrace {
            include_scores,
            score_limit,
            output,
            ..
        } = cli.cmd
        else {
            panic!("expected langfuse-trace command");
        };

        assert!(include_scores);
        assert_eq!(score_limit, 7);
        assert!(matches!(output, LangFuseTraceOutput::Summary));
    }

    #[test]
    fn langfuse_traces_list_url_uses_public_traces_endpoint() {
        let url = build_langfuse_traces_list_url(
            "https://langfuse.example.com/api/public/otel/v1/traces",
            25,
            2,
        );

        assert_eq!(
            url,
            "https://langfuse.example.com/api/public/traces?limit=25&page=2"
        );
    }

    #[test]
    fn langfuse_traces_cli_defaults_to_summary_output() {
        let cli = Cli::try_parse_from([
            "itmux",
            "langfuse-traces",
            "--limit",
            "5",
            "--harness",
            "claude",
        ])
        .unwrap();

        let Cmd::LangFuseTraces {
            limit,
            page,
            harness,
            output,
            ..
        } = cli.cmd
        else {
            panic!("expected langfuse-traces command");
        };

        assert_eq!(limit, 5);
        assert_eq!(page, 1);
        assert_eq!(harness.as_deref(), Some("claude"));
        assert!(matches!(output, LangFuseTraceOutput::Summary));
    }

    #[test]
    fn langfuse_score_create_url_uses_public_scores_endpoint() {
        let url = build_langfuse_score_create_url(
            "https://langfuse.example.com/api/public/otel/v1/traces",
        );

        assert_eq!(url, "https://langfuse.example.com/api/public/scores");
    }

    #[test]
    fn langfuse_score_value_parser_matches_public_api_contract() {
        assert_eq!(
            LangFuseScoreDataType::Numeric.parse_value("0.75").unwrap(),
            json!(0.75)
        );
        assert_eq!(
            LangFuseScoreDataType::Boolean.parse_value("true").unwrap(),
            json!(1)
        );
        assert_eq!(
            LangFuseScoreDataType::Categorical
                .parse_value("useful")
                .unwrap(),
            json!("useful")
        );
        assert!(LangFuseScoreDataType::Numeric
            .parse_value("useful")
            .is_err());
    }

    #[test]
    fn langfuse_score_cli_defaults_to_summary_output() {
        let cli = Cli::try_parse_from([
            "itmux",
            "langfuse-score",
            "--run-id",
            "run-query",
            "--name",
            "agentic.learning_loop_probe",
            "--value",
            "1",
        ])
        .unwrap();

        let Cmd::LangFuseScore {
            run_id,
            name,
            data_type,
            output,
            ..
        } = cli.cmd
        else {
            panic!("expected langfuse-score command");
        };

        assert_eq!(run_id.as_deref(), Some("run-query"));
        assert_eq!(name, "agentic.learning_loop_probe");
        assert!(matches!(data_type, LangFuseScoreDataType::Numeric));
        assert!(matches!(output, LangFuseTraceOutput::Summary));
    }

    #[test]
    fn langfuse_scores_list_url_filters_feedback_fields() {
        let url = build_langfuse_scores_list_url(
            "https://langfuse.example.com/api/public/otel/v1/traces",
            Some("trace id/with spaces"),
            Some("score-a,score-b"),
            Some("agentic.learning_loop_probe"),
            Some("BOOLEAN"),
            10,
            2,
        );

        assert_eq!(
            url,
            "https://langfuse.example.com/api/public/scores?limit=10&page=2&traceId=trace%20id%2Fwith%20spaces&scoreIds=score-a%2Cscore-b&name=agentic.learning_loop_probe&dataType=BOOLEAN"
        );
    }

    #[test]
    fn langfuse_scores_cli_defaults_to_summary_output() {
        let cli = Cli::try_parse_from([
            "itmux",
            "langfuse-scores",
            "--run-id",
            "run-query",
            "--score-ids",
            "score-a",
            "--name",
            "agentic.learning_loop_probe",
        ])
        .unwrap();

        let Cmd::LangFuseScores {
            run_id,
            score_ids,
            name,
            limit,
            page,
            output,
            ..
        } = cli.cmd
        else {
            panic!("expected langfuse-scores command");
        };

        assert_eq!(run_id.as_deref(), Some("run-query"));
        assert_eq!(score_ids.as_deref(), Some("score-a"));
        assert_eq!(name.as_deref(), Some("agentic.learning_loop_probe"));
        assert_eq!(limit, 20);
        assert_eq!(page, 1);
        assert!(matches!(output, LangFuseTraceOutput::Summary));
    }

    #[test]
    fn langfuse_scores_summary_filters_backend_rows_client_side() {
        let response = json!({
            "meta": {"totalItems": 3},
            "data": [
                {
                    "id": "score-good",
                    "traceId": "trace-wanted",
                    "name": "agentic.learning_loop_probe",
                    "dataType": "BOOLEAN",
                    "value": 1
                },
                {
                    "id": "score-other-trace",
                    "traceId": "trace-other",
                    "name": "agentic.learning_loop_probe",
                    "dataType": "BOOLEAN",
                    "value": 1
                },
                {
                    "id": "score-other-name",
                    "traceId": "trace-wanted",
                    "name": "agentic.other",
                    "dataType": "BOOLEAN",
                    "value": 1
                }
            ]
        });
        let request = LangFuseScoresListRequest {
            endpoint: "https://langfuse.example.com/api/public/scores".to_string(),
            trace_id: Some("trace-wanted".to_string()),
            run_id: Some("run-wanted".to_string()),
            score_ids: Some("score-good,missing-score".to_string()),
            name: Some("agentic.learning_loop_probe".to_string()),
            data_type: Some("BOOLEAN"),
            limit: 20,
            page: 1,
        };

        let summary = summarize_langfuse_scores_response(&response, &request);

        assert_eq!(summary["returned_count"], 1);
        assert_eq!(summary["total_items"], 3);
        assert_eq!(summary["scores"][0]["score_id"], "score-good");
        assert_eq!(summary["scores"][0]["trace_id"], "trace-wanted");
    }

    #[test]
    fn langfuse_traces_summary_filters_and_extracts_learning_loop_fields() {
        let response = json!({
            "data": [
                {
                    "id": "trace-codex",
                    "name": "agentic_primitives.run",
                    "timestamp": "2026-07-08T03:26:12.000Z",
                    "createdAt": "2026-07-08T03:26:14.571Z",
                    "updatedAt": "2026-07-08T03:26:14.584Z",
                    "environment": "local-macbook",
                    "sessionId": "run-codex",
                    "metadata": {
                        "run_id": "run-codex",
                        "harness": "codex",
                        "provider": "openai",
                        "model": "gpt-5.5"
                    },
                    "observations": ["obs-1", "obs-2"],
                    "totalCost": 0.25,
                    "latency": 2.0,
                    "htmlPath": "/project/p/traces/trace-codex"
                },
                {
                    "id": "trace-claude",
                    "name": "agentic_primitives.run",
                    "timestamp": "2026-07-08T03:15:34.000Z",
                    "environment": "local-macbook",
                    "sessionId": "run-claude",
                    "metadata": {
                        "run_id": "run-claude",
                        "harness": "claude",
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-6"
                    },
                    "observations": ["obs-1"],
                    "totalCost": 0.5,
                    "latency": 6.0,
                    "htmlPath": "/project/p/traces/trace-claude"
                }
            ],
            "meta": {
                "page": 1,
                "limit": 2,
                "totalItems": 2,
                "totalPages": 1
            }
        });
        let request = LangFuseTracesListRequest {
            endpoint: "https://langfuse.example.com/api/public/traces?limit=2&page=1".to_string(),
            limit: 2,
            page: 1,
            harness: Some("claude".to_string()),
            provider: None,
            model: None,
            environment: None,
        };

        let summary = summarize_langfuse_traces_response(&response, &request);

        assert_eq!(summary["returned_count"], 1);
        assert_eq!(summary["backend_total_items"], 2);
        assert_eq!(summary["harnesses"], json!(["claude"]));
        assert_eq!(summary["providers"], json!(["anthropic"]));
        assert_eq!(summary["models"], json!(["claude-sonnet-4-6"]));
        assert_eq!(summary["total_cost"], json!(0.5));
        assert_eq!(summary["traces"][0]["trace_id"], "trace-claude");
        assert_eq!(summary["traces"][0]["run_id"], "run-claude");
        assert_eq!(summary["traces"][0]["observation_count"], 1);
        assert_eq!(
            summary["traces"][0]["html_path"],
            "/project/p/traces/trace-claude"
        );
    }

    #[test]
    fn langfuse_trace_summary_extracts_learning_loop_fields() {
        let response = json!({
            "id": "trace-1",
            "name": "agentic_primitives.run",
            "sessionId": "run-1",
            "environment": "local-test",
            "observations": [
                {
                    "name": "token_usage",
                    "type": "GENERATION",
                    "environment": "local-test",
                    "model": "gpt-4o-mini",
                    "modelId": "model-row-id",
                    "promptTokens": 10,
                    "completionTokens": 3,
                    "totalTokens": 13,
                    "usage": {"input": 10, "output": 3, "total": 13, "cached_prompt_tokens": 4},
                    "costDetails": {"input": 0.000002, "output": 0.0000013, "total": 0.0000033},
                    "calculatedTotalCost": 0.0000033,
                    "totalCost": 99.0,
                    "metadata": {
                        "attributes": {
                            "agentic.event.seq": "2",
                            "agentic.harness": "codex",
                            "agentic.provider": "openai",
                            "agentic.model": "gpt-4o-mini"
                        }
                    }
                },
                {
                    "name": "aggregate_span",
                    "type": "SPAN",
                    "totalTokens": 999,
                    "calculatedTotalCost": 99.0
                },
                {
                    "name": "tool_start",
                    "id": "obs-0",
                    "startTime": "2026-07-07T23:59:59.000Z",
                    "type": "SPAN",
                    "metadata": {
                        "attributes": {
                            "agentic.event.type": "tool_start",
                            "agentic.event.seq": "0",
                            "agentic.tool.name": "provision"
                        }
                    }
                },
                {
                    "name": "tool_end",
                    "id": "obs-1",
                    "startTime": "2026-07-07T23:59:59.000Z",
                    "type": "SPAN",
                    "metadata": {
                        "attributes": {
                            "agentic.event.type": "tool_end",
                            "agentic.event.seq": "1",
                            "agentic.tool.name": "provision",
                            "agentic.tool.success": "true"
                        }
                    }
                },
                {
                    "name": "tool_start",
                    "id": "obs-3",
                    "startTime": "2026-07-08T00:00:00.000Z",
                    "type": "SPAN",
                    "metadata": {
                        "attributes": {
                            "agentic.event.type": "tool_start",
                            "agentic.event.seq": "3",
                            "agentic.tool.name": "Bash",
                            "agentic.tool.input_redacted": "true"
                        }
                    }
                },
                {
                    "name": "tool_end",
                    "id": "obs-5",
                    "startTime": "2026-07-08T00:00:00.000Z",
                    "type": "SPAN",
                    "metadata": {
                        "attributes": {
                            "agentic.event.type": "tool_end",
                            "agentic.event.seq": "5",
                            "agentic.tool.name": "TodoWrite",
                            "agentic.tool.success": "false"
                        }
                    }
                },
                {
                    "name": "tool_end",
                    "id": "obs-4",
                    "startTime": "2026-07-08T00:00:00.000Z",
                    "type": "SPAN",
                    "metadata": {
                        "attributes": {
                            "agentic.event.type": "tool_end",
                            "agentic.event.seq": 4,
                            "agentic.tool.name": "Bash",
                            "agentic.tool.success": "true"
                        }
                    }
                }
            ]
        });

        let summary = summarize_langfuse_trace_response(&response);

        assert_eq!(summary["trace_id"], "trace-1");
        assert_eq!(summary["observation_count"], 7);
        assert_eq!(summary["harnesses"], json!(["codex"]));
        assert_eq!(summary["providers"], json!(["openai"]));
        assert_eq!(summary["models"], json!(["gpt-4o-mini"]));
        assert_eq!(summary["model_ids"], json!(["model-row-id"]));
        assert_eq!(summary["usage"]["input_tokens"], 10);
        assert_eq!(summary["usage"]["output_tokens"], 3);
        assert_eq!(summary["usage"]["total_tokens"], 13);
        assert_eq!(summary["cost"]["calculated_total_usd"], 0.0000033);
        assert_eq!(summary["generations"]["count"], 1);
        assert_eq!(summary["generations"]["input_tokens"], 10);
        assert_eq!(summary["generations"]["output_tokens"], 3);
        assert_eq!(summary["generations"]["total_tokens"], 13);
        assert_eq!(
            summary["generations"]["calculated_total_usd"],
            json!(0.0000033)
        );
        assert_eq!(
            summary["generations"]["by_model"],
            json!([
                {
                    "model": "gpt-4o-mini",
                    "model_ids": ["model-row-id"],
                    "providers": ["openai"],
                    "harnesses": ["codex"],
                    "count": 1,
                    "input_tokens": 10,
                    "output_tokens": 3,
                    "total_tokens": 13,
                    "calculated_total_usd": 0.0000033
                }
            ])
        );
        assert_eq!(
            summary["generations"]["sequence_source"],
            "agentic.event.seq"
        );
        assert_eq!(summary["generations"]["sequence"][0]["seq"], 2);
        assert_eq!(
            summary["generations"]["sequence"][0]["observation_id"],
            json!(null)
        );
        assert_eq!(
            summary["generations"]["sequence"][0]["model"],
            "gpt-4o-mini"
        );
        assert_eq!(
            summary["generations"]["sequence"][0]["cached_input_tokens"],
            4
        );
        assert_eq!(
            summary["generations"]["sequence"][0]["calculated_input_cost_usd"],
            0.000002
        );
        assert_eq!(
            summary["generations"]["sequence"][0]["calculated_output_cost_usd"],
            0.0000013
        );
        assert_eq!(
            summary["generations"]["sequence"][0]["calculated_total_cost_usd"],
            0.0000033
        );
        assert_eq!(summary["generations"]["sequence_truncated"], false);
        assert_eq!(summary["events"]["sequence_source"], "agentic.event.seq");
        assert_eq!(summary["events"]["sequence"][0]["seq"], 0);
        assert_eq!(summary["events"]["sequence"][0]["category"], "operation");
        assert_eq!(summary["events"]["sequence"][2]["event"], "token_usage");
        assert_eq!(summary["events"]["sequence"][2]["category"], "usage");
        assert_eq!(summary["events"]["sequence"][2]["total_tokens"], json!(13));
        assert_eq!(
            summary["events"]["sequence"][2]["calculated_total_cost"],
            json!(0.0000033)
        );
        assert_eq!(summary["events"]["sequence"][3]["seq"], 3);
        assert_eq!(summary["events"]["sequence"][3]["category"], "agent_tool");
        assert_eq!(
            summary["events"]["category_counts"],
            json!([
                {"category": "agent_tool", "count": 3},
                {"category": "operation", "count": 2},
                {"category": "other", "count": 1},
                {"category": "usage", "count": 1}
            ])
        );
        assert_eq!(summary["events"]["sequence_truncated"], false);
        assert_eq!(summary["tools"]["start_count"], 2);
        assert_eq!(summary["tools"]["end_count"], 3);
        assert_eq!(summary["tools"]["success_count"], 2);
        assert_eq!(summary["tools"]["failure_count"], 1);
        assert_eq!(
            summary["tools"]["names"],
            json!(["Bash", "TodoWrite", "provision"])
        );
        assert_eq!(
            summary["tools"]["by_name"],
            json!([
                {"name": "Bash", "starts": 1, "ends": 1, "successes": 1, "failures": 0},
                {"name": "TodoWrite", "starts": 0, "ends": 1, "successes": 0, "failures": 1},
                {"name": "provision", "starts": 1, "ends": 1, "successes": 1, "failures": 0}
            ])
        );
        assert_eq!(summary["tools"]["sequence_source"], "agentic.event.seq");
        assert_eq!(summary["tools"]["sequence"][0]["seq"], 0);
        assert_eq!(summary["tools"]["sequence"][2]["seq"], 3);
        assert_eq!(summary["tools"]["sequence"][3]["seq"], 4);
        assert_eq!(summary["tools"]["sequence"][4]["seq"], 5);
        assert_eq!(summary["tools"]["sequence"][2]["tool_name"], "Bash");
        assert_eq!(summary["tools"]["sequence"][3]["success"], true);
        assert_eq!(summary["tools"]["sequence"][4]["success"], false);
        assert_eq!(summary["tools"]["sequence_truncated"], false);
        assert_eq!(summary["operations"]["names"], json!(["provision"]));
        assert_eq!(summary["operations"]["start_count"], 1);
        assert_eq!(summary["operations"]["end_count"], 1);
        assert_eq!(summary["operations"]["success_count"], 1);
        assert_eq!(
            summary["agent_tools"]["names"],
            json!(["Bash", "TodoWrite"])
        );
        assert_eq!(summary["agent_tools"]["start_count"], 1);
        assert_eq!(summary["agent_tools"]["end_count"], 2);
        assert_eq!(summary["agent_tools"]["success_count"], 1);
        assert_eq!(summary["agent_tools"]["failure_count"], 1);
        assert_eq!(summary["harness_tools"]["names"], json!([]));
    }

    #[test]
    fn non_empty_env_rejects_blank_values() {
        std::env::set_var("ITMUX_TEST_BLANK_ENV", "  ");
        std::env::set_var("ITMUX_TEST_VALUE_ENV", " value ");

        assert_eq!(non_empty_env("ITMUX_TEST_BLANK_ENV"), None);
        assert_eq!(
            non_empty_env("ITMUX_TEST_VALUE_ENV").as_deref(),
            Some("value")
        );
        assert_eq!(non_empty_env("ITMUX_TEST_MISSING_ENV"), None);

        std::env::remove_var("ITMUX_TEST_BLANK_ENV");
        std::env::remove_var("ITMUX_TEST_VALUE_ENV");
    }
}
