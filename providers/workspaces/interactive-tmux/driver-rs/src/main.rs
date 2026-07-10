//! `itmux` — CLI entry point with the same subcommand surface as the Python
//! driver's `python -m interactive_tmux`. Each subcommand emits JSON on
//! stdout in the exact shape the Python equivalent emits, so `smoke-rs.sh`
//! can mirror `smoke.sh` line-for-line.

use std::collections::HashMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode, Stdio};

use clap::{Parser, Subcommand, ValueEnum};
use serde::Serialize;
use serde_json::{json, Value};

mod langfuse;

use crate::langfuse::{
    handle_langfuse_score, handle_langfuse_scores, handle_langfuse_trace, handle_langfuse_traces,
    LangFuseScoreDataType, LangFuseTraceApi, LangFuseTraceOutput,
    DEFAULT_LANGFUSE_QUERY_FROM_START_TIME, DEFAULT_LANGFUSE_QUERY_TO_START_TIME,
};
use itmux::adapter::{Agent, AGENTS};
use itmux::registry;
use itmux::run::contract::{
    AgentRunEvent, AgentRunEventPayload, AgentRunLimits, AgentRunOutcome, AgentRunResult,
    AgentRunSpec, ObservabilityExporter,
};
use itmux::run::harness_observer::{
    ClaudeTranscriptObserver, CodexExecJsonObserver, HarnessObserver,
};
use itmux::run::observability::ObservabilityFanout;
use itmux::run::orchestrator::CancelToken;
#[cfg(unix)]
use itmux::run::orchestrator::{CancelEscalator, SignalKind};
use itmux::run::workspace_executor::{generate_run_id, now_rfc3339};
use itmux::workspace::{
    StartOptions, Workspace, DEFAULT_IMAGE, DEFAULT_STARTUP_TIMEOUT_S, DEFAULT_TMUX_COLS,
    DEFAULT_TMUX_ROWS, DEFAULT_WORKDIR,
};

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
        /// Append Syntropic137 HookWatcher-compatible JSONL to this file.
        #[arg(long)]
        observability_syntropic_file: Option<PathBuf>,
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
        /// Append Syntropic137 HookWatcher-compatible JSONL to this file.
        #[arg(long)]
        observability_syntropic_file: Option<PathBuf>,
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
        /// Append Syntropic137 HookWatcher-compatible JSONL to this file.
        #[arg(long)]
        observability_syntropic_file: Option<PathBuf>,
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

fn build_observability_exporters(
    observability_file: Option<PathBuf>,
    observability_syntropic_file: Option<PathBuf>,
    file_label: &str,
) -> Vec<ObservabilityExporter> {
    let mut exporters: Vec<_> = observability_file
        .map(|path| ObservabilityExporter::File {
            path,
            label: Some(file_label.to_string()),
        })
        .into_iter()
        .collect();

    if let Some(path) = observability_syntropic_file {
        exporters.push(ObservabilityExporter::SyntropicJsonl {
            path,
            label: Some("Syntropic137 events".to_string()),
        });
    }

    exporters
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

fn non_empty_env(key: &str) -> Option<String> {
    std::env::var(key)
        .ok()
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
    observability_syntropic_file: Option<PathBuf>,
) -> ExitCode {
    let credentials = match itmux::run::secret_env::load_credentials(env_file.as_deref()) {
        Ok(credentials) => credentials,
        Err(err) => {
            eprintln!("[itmux run] {err}");
            return ExitCode::from(2);
        }
    };
    let observability = build_observability_exporters(
        observability_file,
        observability_syntropic_file,
        "itmux run events",
    );
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
    observability_syntropic_file: Option<PathBuf>,
) -> ExitCode {
    let exporters = build_observability_exporters(
        observability_file,
        observability_syntropic_file,
        "codex exec events",
    );
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
    observability_syntropic_file: Option<PathBuf>,
) -> ExitCode {
    let exporters = build_observability_exporters(
        observability_file,
        observability_syntropic_file,
        "claude transcript events",
    );
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
            observability_syntropic_file,
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
            observability_syntropic_file,
        ),
        Cmd::CodexExec {
            prompt,
            codex_bin,
            model,
            sandbox,
            json,
            result_file,
            observability_file,
            observability_syntropic_file,
        } => handle_codex_exec(
            prompt,
            codex_bin,
            model,
            sandbox,
            json,
            result_file,
            observability_file,
            observability_syntropic_file,
        ),
        Cmd::ClaudeTranscript {
            transcript,
            run_id,
            json,
            result_file,
            observability_file,
            observability_syntropic_file,
        } => handle_claude_transcript(
            transcript,
            run_id,
            json,
            result_file,
            observability_file,
            observability_syntropic_file,
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
    fn cli_exporters_include_file_when_configured() {
        let exporters = build_observability_exporters(
            Some(PathBuf::from("/tmp/events.jsonl")),
            None,
            "local events",
        );

        assert_eq!(exporters.len(), 1);
        assert!(matches!(exporters[0], ObservabilityExporter::File { .. }));
    }

    #[test]
    fn cli_exporters_include_syntropic_jsonl_when_configured() {
        let exporters = build_observability_exporters(
            Some(PathBuf::from("/tmp/events.jsonl")),
            Some(PathBuf::from("/tmp/syntropic-events.jsonl")),
            "local events",
        );

        assert_eq!(exporters.len(), 2);
        assert!(matches!(exporters[0], ObservabilityExporter::File { .. }));
        match &exporters[1] {
            ObservabilityExporter::SyntropicJsonl { path, label } => {
                assert_eq!(path, &PathBuf::from("/tmp/syntropic-events.jsonl"));
                assert_eq!(label.as_deref(), Some("Syntropic137 events"));
            }
            ObservabilityExporter::File { .. } => panic!("expected Syntropic137 exporter"),
        }
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
}
