//! `itmux` — CLI entry point with the same subcommand surface as the Python
//! driver's `python -m interactive_tmux`. Each subcommand emits JSON on
//! stdout in the exact shape the Python equivalent emits, so `smoke-rs.sh`
//! can mirror `smoke.sh` line-for-line.

use std::collections::HashMap;
use std::io::Write;
use std::path::PathBuf;
use std::process::ExitCode;

use clap::{Parser, Subcommand};
use serde::Serialize;
use serde_json::{json, Value};

use itmux::adapter::{Agent, AGENTS};
use itmux::registry;
use itmux::run::contract::{AgentRunEvent, AgentRunLimits, AgentRunSpec};
use itmux::run::orchestrator::CancelToken;
#[cfg(unix)]
use itmux::run::orchestrator::{CancelEscalator, SignalKind};
use itmux::run::workspace_executor::{generate_run_id, now_rfc3339, run as run_orchestrated};
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

fn handle_run(
    recipe: PathBuf,
    task: String,
    image: String,
    json: bool,
    result_file: Option<PathBuf>,
    timeout: Option<f64>,
) -> ExitCode {
    let spec = build_run_spec(recipe, task, timeout);
    let run_id = generate_run_id();
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

    let run_result = run_orchestrated(&spec, &image, &run_id, &cancel, &mut emit);

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
            json,
            result_file,
            timeout,
        } => handle_run(recipe, task, image, json, result_file, timeout),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_run_spec_maps_timeout_to_limits_timeout_s() {
        let spec = build_run_spec(
            PathBuf::from("/recipes/hello"),
            "do the thing".to_string(),
            Some(12.5),
        );
        let limits = spec.limits.expect("timeout should populate limits");
        assert_eq!(limits.timeout_s, Some(12.5));
        // Only the timeout is set; the token budget stays unset.
        assert_eq!(limits.token_budget, None);
    }

    #[test]
    fn parse_positive_timeout_accepts_a_finite_positive_value() {
        assert_eq!(parse_positive_timeout("2.5"), Ok(2.5));
    }

    #[test]
    fn parse_positive_timeout_rejects_non_positive_and_non_finite() {
        // Each of these would reach Duration::from_secs_f64 and panic if it
        // slipped through - the parser must reject them cleanly instead.
        for bad in ["-1", "0", "NaN", "inf", "-inf", "not-a-number"] {
            assert!(
                parse_positive_timeout(bad).is_err(),
                "expected {bad:?} to be rejected"
            );
        }
    }

    #[test]
    fn build_run_spec_without_timeout_leaves_limits_none() {
        // Omitting --timeout must not change existing behaviour: no limits, so
        // the orchestrator's default await bound applies.
        let spec = build_run_spec(
            PathBuf::from("/recipes/hello"),
            "do the thing".to_string(),
            None,
        );
        assert!(spec.limits.is_none());
    }
}
