//! Thin wrappers around `docker exec <container> tmux <subcmd>`.
//!
//! Everything that talks to the container goes through this module. Keeping
//! the shell-out localised here means the rest of the crate can be tested
//! without a docker daemon (the per-agent readiness logic lives in
//! `adapter` and only needs strings).

use std::io::{Error, ErrorKind, Result, Write};
use std::process::{Child, Command, Output, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc;
use std::time::Duration;

pub const TMUX_SESSION: &str = "agents";

/// Bound for one `docker exec` / `tmux` operation. Mirrors the Python
/// driver's `DEFAULT_EXEC_TIMEOUT_S` (PY:86): a single wedged exec must not
/// be able to hang the workflow forever.
pub const DEFAULT_EXEC_TIMEOUT_S: f64 = 15.0;

/// Bound for `docker run` / `docker rm -f`. Mirrors the Python driver's
/// `DEFAULT_RUN_TIMEOUT_S` (PY:87).
pub const DEFAULT_RUN_TIMEOUT_S: f64 = 30.0;

/// Run `cmd`, bounding its execution to `timeout`.
///
/// std-only, no `unsafe`: spawns the child (stdout/stderr always piped, so
/// the returned `Output` is populated the same way `Command::output()`
/// would populate it), then waits for it on a dedicated thread and races
/// that wait against `timeout` via `mpsc::recv_timeout`. On timeout the
/// child is best-effort killed and an `ErrorKind::TimedOut` error is
/// returned. Mirrors Python's `subprocess.run(..., timeout=...)` bound
/// (PY:222-280, PY:576-626) without pulling in an async runtime or a new
/// dependency.
pub fn run_bounded(mut cmd: Command, timeout: Duration) -> Result<Output> {
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());
    let child = cmd.spawn()?;
    wait_bounded(child, timeout)
}

/// Wait on an already-spawned `child`, bounded by `timeout`.
///
/// Shared by `run_bounded` and the stdin-writer path
/// (`docker_exec_with_stdin`), which needs to feed the child's stdin from
/// its own thread before this bound takes over waiting on exit.
///
/// On timeout, the child is killed (best-effort - `Child::kill` is a plain
/// signal send, not a guarantee the process has fully exited by the time
/// this function returns) and the waiter thread is left to finish and drop
/// its result on the floor; we do not block joining it; the timeout error
/// is returned immediately so a wedged process can never make this
/// function itself hang.
pub fn wait_bounded(child: Child, timeout: Duration) -> Result<Output> {
    let pid = child.id();
    let (tx, rx) = mpsc::channel();
    std::thread::spawn(move || {
        let result = child.wait_with_output();
        let _ = tx.send(result);
    });
    match rx.recv_timeout(timeout) {
        Ok(result) => result,
        Err(_) => {
            // Best-effort: ask the process (and, since docker/tmux
            // children are frequently themselves a fork/exec wrapper,
            // just its own pid - not a process group) to die. We do not
            // have a `Child` handle here anymore (it was moved into the
            // waiter thread so that thread can drain stdout/stderr without
            // deadlocking on a full pipe buffer), so killing by pid via
            // the `kill` utility is the only std-only, `unsafe`-free way
            // to reach it from this side.
            let _ = Command::new("kill")
                .args(["-9", &pid.to_string()])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn();
            Err(Error::new(
                ErrorKind::TimedOut,
                format!("command timed out after {timeout:?}"),
            ))
        }
    }
}

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

/// Run `docker exec <container> <args...>` and return its `Output`, bounded
/// by `DEFAULT_EXEC_TIMEOUT_S` (PY:86) so a wedged exec can't hang forever.
pub fn docker_exec_timeout(container: &str, args: &[&str], timeout: Duration) -> Result<Output> {
    let mut cmd = Command::new("docker");
    cmd.arg("exec").arg(container);
    cmd.args(args);
    let out = run_bounded(cmd, timeout)?;
    check_output(
        out,
        &format!("docker exec {container} {}", redact_args(args)),
    )
}

pub fn docker_exec(container: &str, args: &[&str]) -> Result<Output> {
    docker_exec_timeout(
        container,
        args,
        Duration::from_secs_f64(DEFAULT_EXEC_TIMEOUT_S),
    )
}

/// `docker exec -i <container> <args...>`, feeding `stdin_data` to the
/// process's stdin and returning its `Output`.
///
/// Used by credential transfer (`auth::stage_into_container`) to push file
/// bytes / base64 payloads into the container without ever putting them in
/// argv (PY:1506-1517) - argv is world-readable via `ps` /
/// `/proc/<pid>/cmdline` for the lifetime of the exec; stdin is not.
pub fn docker_exec_with_stdin_timeout(
    container: &str,
    args: &[&str],
    stdin_data: &[u8],
    timeout: Duration,
) -> Result<Output> {
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
    // Bounded wait (PY:86 `DEFAULT_EXEC_TIMEOUT_S`): if this times out, `?`
    // returns immediately and the writer thread is left detached - once the
    // killed child's stdin pipe closes its `write_all` fails fast and the
    // thread exits on its own; there is nothing useful left to join.
    let out = wait_bounded(child, timeout)?;
    writer
        .join()
        .map_err(|_| Error::other("stdin-writer thread panicked"))??;
    check_output(
        out,
        &format!("docker exec -i {container} {}", redact_args(args)),
    )
}

pub fn docker_exec_with_stdin(container: &str, args: &[&str], stdin_data: &[u8]) -> Result<Output> {
    docker_exec_with_stdin_timeout(
        container,
        args,
        stdin_data,
        Duration::from_secs_f64(DEFAULT_EXEC_TIMEOUT_S),
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

/// Bound above which `send-keys -l` is skipped in favour of the
/// load-buffer/paste-buffer path. Mirrors the Python driver's
/// `TMUX_SEND_KEYS_MAX_BYTES` (PY:91): tmux's `send-keys -l` has a ~16KB
/// cap and silently truncates larger payloads, so anything bigger is
/// staged through a tmux paste buffer instead (PY:645-707).
pub const TMUX_SEND_KEYS_MAX_BYTES: usize = 12_000;

/// Monotonic per-process counter feeding the unique paste-buffer name.
/// Combined with the process id it makes each large-payload send use its
/// own named tmux buffer, so concurrent sends never race on the shared
/// default buffer (Python uses a `uuid4` token for the same reason,
/// PY:684-686). `std`-only, no `unsafe`, no new deps.
static PASTE_BUFFER_SEQ: AtomicU64 = AtomicU64::new(0);

/// The command plan `send_literal` will execute for a given payload,
/// factored out as a pure, assertable value so tests can cover the
/// threshold logic without a docker daemon.
#[derive(Debug, PartialEq, Eq)]
pub enum SendLiteralPlan {
    /// `tmux send-keys -t <pane> -l -- <text>` - payload at or under
    /// `TMUX_SEND_KEYS_MAX_BYTES` (PY:666 uses `<=` for this path).
    SendKeys { pane: String, text: String },
    /// `tmux load-buffer -b <buffer> -` (fed `payload` via stdin) followed
    /// by `tmux paste-buffer -p -b <buffer> -d -t <pane>` - payload over
    /// the threshold (PY:683-702). `-p` sends a bracketed paste so a
    /// multiline prompt is delivered atomically instead of each newline
    /// submitting early; `-b <buffer>` uses a unique named buffer to avoid
    /// racing the shared default buffer; `-d` deletes that buffer after
    /// pasting, covering Python's `finally` cleanup.
    PasteBuffer {
        pane: String,
        buffer: String,
        payload: Vec<u8>,
    },
}

impl SendLiteralPlan {
    /// `tmux load-buffer` argv for the large path (stdin carries the
    /// payload). Empty for the `SendKeys` variant.
    pub fn load_buffer_args(&self) -> Vec<String> {
        match self {
            SendLiteralPlan::SendKeys { .. } => Vec::new(),
            SendLiteralPlan::PasteBuffer { buffer, .. } => {
                vec![
                    "tmux".into(),
                    "load-buffer".into(),
                    "-b".into(),
                    buffer.clone(),
                    "-".into(),
                ]
            }
        }
    }

    /// `tmux paste-buffer` argv for the large path. Empty for the
    /// `SendKeys` variant.
    pub fn paste_buffer_args(&self) -> Vec<String> {
        match self {
            SendLiteralPlan::SendKeys { .. } => Vec::new(),
            SendLiteralPlan::PasteBuffer { pane, buffer, .. } => {
                vec![
                    "tmux".into(),
                    "paste-buffer".into(),
                    "-p".into(),
                    "-b".into(),
                    buffer.clone(),
                    "-d".into(),
                    "-t".into(),
                    pane.clone(),
                ]
            }
        }
    }
}

/// Derive a unique-per-call tmux buffer name. `std`-only: process id plus a
/// monotonic counter, prefixed to mirror the Python driver's `itmux-<hex>`
/// naming (PY:686). Two sends from the same process get distinct counter
/// values; two sends from different processes get distinct pids.
fn next_paste_buffer_name() -> String {
    let seq = PASTE_BUFFER_SEQ.fetch_add(1, Ordering::Relaxed);
    format!("itmux-{}-{seq}", std::process::id())
}

/// Decide how `text` should be delivered into `pane`, without touching
/// docker or tmux. Mirrors the Python driver's byte-length branch
/// (PY:665-666): the threshold is measured against the UTF-8 byte length
/// of the payload, not its character count. The large path mints a unique
/// buffer name so concurrent callers never collide.
pub fn plan_send_literal(pane: &str, text: &str) -> SendLiteralPlan {
    let payload = text.as_bytes();
    if payload.len() <= TMUX_SEND_KEYS_MAX_BYTES {
        SendLiteralPlan::SendKeys {
            pane: pane.to_string(),
            text: text.to_string(),
        }
    } else {
        SendLiteralPlan::PasteBuffer {
            pane: pane.to_string(),
            buffer: next_paste_buffer_name(),
            payload: payload.to_vec(),
        }
    }
}

/// `docker exec <container> tmux send-keys -l -t <session>:<window> <text>`,
/// or - for payloads over `TMUX_SEND_KEYS_MAX_BYTES` - a
/// `load-buffer`/`paste-buffer` round trip that avoids tmux's ~16KB
/// `send-keys -l` truncation cap (PY:645-707).
///
/// The `-l` flag tells tmux to deliver the bytes literally (no special-key
/// interpretation) - the canonical pattern for the body of a user message.
pub fn send_literal(container: &str, window: &str, text: &str) -> Result<()> {
    let target = format!("{TMUX_SESSION}:{window}");
    let plan = plan_send_literal(&target, text);
    match &plan {
        SendLiteralPlan::SendKeys { pane, text } => {
            // `--` ends option parsing so a prompt beginning with `-` (e.g.
            // "-R", "--help") is treated as literal text, not a tmux
            // send-keys flag.
            docker_exec(
                container,
                &["tmux", "send-keys", "-t", pane, "-l", "--", text],
            )?;
        }
        SendLiteralPlan::PasteBuffer {
            pane,
            buffer,
            payload,
        } => {
            // `load-buffer -b <name> -` reads the buffer contents from
            // stdin (which `docker_exec_with_stdin` already pipes in - no
            // container-side temp file needed) into a unique named buffer.
            docker_exec_with_stdin(
                container,
                &["tmux", "load-buffer", "-b", buffer, "-"],
                payload,
            )?;
            // `-p` = bracketed paste (atomic multiline); `-d` deletes the
            // named buffer afterwards so large sends don't accumulate stale
            // buffers and can't leak payload bytes into a later paste.
            if let Err(error) = docker_exec(
                container,
                &["tmux", "paste-buffer", "-p", "-b", buffer, "-d", "-t", pane],
            ) {
                // `-d` only cleans up after a successful paste. If the paste
                // command itself fails, remove the named buffer best-effort so
                // its prompt payload cannot remain readable in the container.
                let _ = docker_exec(container, &["tmux", "delete-buffer", "-b", buffer]);
                return Err(error);
            }
        }
    }
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
