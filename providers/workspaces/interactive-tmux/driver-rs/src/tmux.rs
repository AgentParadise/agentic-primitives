//! Thin wrappers around `docker exec <container> tmux <subcmd>`.
//!
//! Everything that talks to the container goes through this module. Keeping
//! the shell-out localised here means the rest of the crate can be tested
//! without a docker daemon (the per-agent readiness logic lives in
//! `adapter` and only needs strings).

use std::io::{Error, Result};
use std::process::{Command, Output};

pub const TMUX_SESSION: &str = "agents";

fn check_output(out: Output, what: &str) -> Result<Output> {
    if out.status.success() {
        Ok(out)
    } else {
        let stderr = String::from_utf8_lossy(&out.stderr);
        Err(Error::other(format!(
            "{what} failed (exit {}): {stderr}",
            out.status
        )))
    }
}

/// Run `docker exec <container> <args...>` and return its `Output`.
pub fn docker_exec(container: &str, args: &[&str]) -> Result<Output> {
    let mut cmd = Command::new("docker");
    cmd.arg("exec").arg(container);
    cmd.args(args);
    let out = cmd.output()?;
    check_output(out, &format!("docker exec {container} {}", args.join(" ")))
}

/// `docker exec <container> tmux send-keys -t <session>:<window> <keys...>`.
/// Each `key` is one tmux send-keys argument (special-key names like
/// `Enter`, `C-j`, or `Escape` are honoured by tmux).
pub fn send_keys(container: &str, window: &str, keys: &[&str]) -> Result<()> {
    let target = format!("{TMUX_SESSION}:{window}");
    let mut args: Vec<&str> = vec!["tmux", "send-keys", "-t", &target];
    args.extend_from_slice(keys);
    docker_exec(container, &args)?;
    Ok(())
}

/// `docker exec <container> tmux send-keys -l -t <session>:<window> <text>`.
///
/// The `-l` flag tells tmux to deliver the bytes literally (no special-key
/// interpretation) — the canonical pattern for the body of a user message.
pub fn send_literal(container: &str, window: &str, text: &str) -> Result<()> {
    let target = format!("{TMUX_SESSION}:{window}");
    docker_exec(container, &["tmux", "send-keys", "-t", &target, "-l", text])?;
    Ok(())
}

/// `docker exec <container> tmux capture-pane -p -t <session>:<window>`.
pub fn capture_pane(container: &str, window: &str) -> Result<String> {
    let target = format!("{TMUX_SESSION}:{window}");
    let out = docker_exec(container, &["tmux", "capture-pane", "-p", "-t", &target])?;
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

/// Bootstrap a new tmux session inside `container` whose first window is
/// named `first_window`, sized `cols`x`rows`. Mirrors the Python driver's
/// `tmux new-session -d -s agents -n <first> -x cols -y rows`.
pub fn new_session(container: &str, first_window: &str, cols: u32, rows: u32) -> Result<()> {
    docker_exec(
        container,
        &[
            "tmux",
            "new-session",
            "-d",
            "-s",
            TMUX_SESSION,
            "-n",
            first_window,
            "-x",
            &cols.to_string(),
            "-y",
            &rows.to_string(),
        ],
    )?;
    Ok(())
}

pub fn new_window(container: &str, name: &str) -> Result<()> {
    docker_exec(
        container,
        &["tmux", "new-window", "-t", TMUX_SESSION, "-n", name],
    )?;
    Ok(())
}
