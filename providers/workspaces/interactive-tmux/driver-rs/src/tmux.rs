//! Thin wrappers around `docker exec <container> tmux <subcmd>`.
//!
//! Everything that talks to the container goes through this module. Keeping
//! the shell-out localised here means the rest of the crate can be tested
//! without a docker daemon (the per-agent readiness logic lives in
//! `adapter` and only needs strings).

use std::io::{Error, Result, Write};
use std::process::{Command, Output, Stdio};

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

/// Render args for an error label with literal `send-keys` payloads
/// redacted. Prompt bodies often carry secrets, tokens, or user data; the
/// arg following `-l` (skipping a `--` terminator) is replaced with its
/// length so a failed send doesn't leak content into error messages.
fn redact_args(args: &[&str]) -> String {
    let mut parts: Vec<String> = Vec::with_capacity(args.len());
    let mut redact_next = false;
    for &tok in args {
        if redact_next && tok != "--" {
            parts.push(format!("<redacted {} chars>", tok.len()));
            redact_next = false;
        } else {
            parts.push(tok.to_string());
            if tok == "-l" {
                redact_next = true;
            }
        }
    }
    parts.join(" ")
}

/// Run `docker exec <container> <args...>` and return its `Output`.
pub fn docker_exec(container: &str, args: &[&str]) -> Result<Output> {
    let mut cmd = Command::new("docker");
    cmd.arg("exec").arg(container);
    cmd.args(args);
    let out = cmd.output()?;
    check_output(
        out,
        &format!("docker exec {container} {}", redact_args(args)),
    )
}

/// `docker exec -i <container> <args...>`, feeding `stdin_data` to the
/// process's stdin and returning its `Output`.
///
/// Used by credential transfer (`auth::stage_into_container`) to push file
/// bytes / base64 payloads into the container without ever putting them in
/// argv (PY:1506-1517) - argv is world-readable via `ps` /
/// `/proc/<pid>/cmdline` for the lifetime of the exec; stdin is not.
pub fn docker_exec_with_stdin(container: &str, args: &[&str], stdin_data: &[u8]) -> Result<Output> {
    let mut cmd = Command::new("docker");
    cmd.arg("exec").arg("-i").arg(container);
    cmd.args(args);
    cmd.stdin(Stdio::piped());
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());
    let mut child = cmd.spawn()?;
    // Feed stdin from a dedicated thread so a payload larger than the pipe
    // buffer can't deadlock against `wait_with_output` reading stdout/stderr
    // (classic "write blocks because the child is blocked writing its own
    // full stdout pipe, which we haven't started draining yet" deadlock).
    let mut stdin = child
        .stdin
        .take()
        .expect("stdin piped above via Stdio::piped()");
    let payload = stdin_data.to_vec();
    let writer = std::thread::spawn(move || stdin.write_all(&payload));
    let out = child.wait_with_output()?;
    writer
        .join()
        .map_err(|_| Error::other("stdin-writer thread panicked"))??;
    check_output(
        out,
        &format!("docker exec -i {container} {}", redact_args(args)),
    )
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
/// interpretation) - the canonical pattern for the body of a user message.
pub fn send_literal(container: &str, window: &str, text: &str) -> Result<()> {
    let target = format!("{TMUX_SESSION}:{window}");
    // `--` ends option parsing so a prompt beginning with `-` (e.g. "-R",
    // "--help") is treated as literal text, not a tmux send-keys flag.
    docker_exec(
        container,
        &["tmux", "send-keys", "-t", &target, "-l", "--", text],
    )?;
    Ok(())
}

/// Capture the full pane buffer including scrollback.
///
/// `-S -` = start at the top of the history; `-E -` = end at the bottom
/// of the visible pane. Together they return EVERYTHING the TUI has
/// written, not just the rows the terminal happens to render right now.
/// Without these flags, a multi-paragraph model reply that overflows
/// the visible window (default 200x50) is silently truncated. EXP-03
/// documented this from the start; the driver shipped without it
/// (D-block-3 from the Syntropic137 stress run,
/// experiments/stress/STRESS-REPORT.md).
pub fn capture_pane(container: &str, window: &str) -> Result<String> {
    let target = format!("{TMUX_SESSION}:{window}");
    let out = docker_exec(
        container,
        &[
            "tmux",
            "capture-pane",
            "-p",
            "-t",
            &target,
            "-S",
            "-",
            "-E",
            "-",
        ],
    )?;
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

/// Return the bottom `n_lines` lines of a captured pane.
///
/// Mirrors the Python driver's `_pane_tail`: with the full-scrollback
/// capture above, the buffer contains every prompt and every prior
/// generation. The per-agent `is_started` / `is_ready` predicates would
/// be fooled by old text - `"esc to interrupt" not in pane` flips false
/// after the first generation, and Claude's empty-chevron regex matches
/// against ancient prompts. Evaluating against the tail preserves the
/// pre-fix "check the visible window" semantics on a full-history capture.
/// Surfaced by Syntropic137 stress D-block-2.
pub fn pane_tail(pane_text: &str, n_lines: usize) -> String {
    if pane_text.is_empty() {
        return String::new();
    }
    let lines: Vec<&str> = pane_text.split('\n').collect();
    if lines.len() <= n_lines {
        return pane_text.to_string();
    }
    let start = lines.len() - n_lines;
    lines[start..].join("\n")
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn redact_args_hides_literal_payload_after_dash_l() {
        let args = [
            "tmux",
            "send-keys",
            "-t",
            "agents:claude",
            "-l",
            "--",
            "secret-token",
        ];
        let s = redact_args(&args);
        assert!(!s.contains("secret-token"), "payload leaked: {s}");
        assert!(s.contains("<redacted 12 chars>"), "got: {s}");
        assert!(s.contains("send-keys"));
    }

    #[test]
    fn redact_args_leaves_non_literal_commands_intact() {
        let args = ["tmux", "capture-pane", "-p", "-t", "agents:claude"];
        assert_eq!(redact_args(&args), "tmux capture-pane -p -t agents:claude");
    }
}
