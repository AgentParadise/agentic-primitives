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
}

fn parse_agent(s: &str) -> Result<Agent, String> {
    Agent::parse(s).ok_or_else(|| format!("unknown agent: {s} (one of claude/codex/gemini)"))
}

fn default_host_auth(wanted: &[Agent]) -> HashMap<Agent, Option<PathBuf>> {
    let home = std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/root"));
    let mut out = HashMap::new();
    for agent in AGENTS {
        let path = match agent {
            Agent::Claude => home.join(".claude"),
            Agent::Codex => home.join(".codex"),
            Agent::Gemini => home.join(".gemini"),
        };
        let enabled = wanted.contains(&agent) && path.is_dir();
        out.insert(agent, if enabled { Some(path) } else { None });
    }
    out
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
    }
}
