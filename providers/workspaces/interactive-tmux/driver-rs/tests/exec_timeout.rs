//! Parity: every docker/tmux shell-out is bounded by a timeout
//! (PY:86-87 `DEFAULT_EXEC_TIMEOUT_S` / `DEFAULT_RUN_TIMEOUT_S`), so a
//! wedged child process can never hang the driver forever.
//!
//! These tests exercise `itmux::tmux::run_bounded` directly against real
//! `sh` subprocesses - no docker daemon required.

use std::process::Command;
use std::time::{Duration, Instant};

use itmux::tmux::run_bounded;

#[test]
fn run_bounded_kills_and_errors_on_timeout_without_blocking() {
    let mut cmd = Command::new("sh");
    cmd.args(["-c", "sleep 5"]);

    let start = Instant::now();
    let result = run_bounded(cmd, Duration::from_millis(200));
    let elapsed = start.elapsed();

    assert!(result.is_err(), "expected a timeout error, got: {result:?}");
    let err = result.unwrap_err();
    assert_eq!(
        err.kind(),
        std::io::ErrorKind::TimedOut,
        "expected ErrorKind::TimedOut, got: {:?} ({err})",
        err.kind()
    );

    // The whole point: we must NOT have waited out the 5s sleep. Give a
    // generous scheduler margin, but this must stay well under 1s. Timeout
    // cleanup dispatches `kill -9` without waiting for that subprocess.
    assert!(
        elapsed < Duration::from_secs(1),
        "run_bounded blocked for {elapsed:?}, expected well under 1s (child should have been killed)"
    );
}

#[test]
fn run_bounded_returns_output_for_a_fast_command() {
    let mut cmd = Command::new("sh");
    cmd.args(["-c", "echo hi"]);

    let out = run_bounded(cmd, Duration::from_secs(5)).expect("fast command should not time out");

    assert!(
        out.status.success(),
        "expected success, got: {:?}",
        out.status
    );
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains("hi"),
        "expected stdout to contain 'hi', got: {stdout:?}"
    );
}

#[test]
fn run_bounded_does_not_leak_a_hung_child_process() {
    // Best-effort leak check: run_bounded on a long sleeper with a short
    // timeout must return promptly. If the child were not killed, this
    // test process would still exit fine (children don't block process
    // exit on unix), but the *call* itself hanging would be the real bug -
    // already covered above. Here we additionally check that issuing the
    // call twice in a row is still fast, which would not be true if kills
    // were failing to fire and something was accumulating wait time.
    let start = Instant::now();
    for _ in 0..2 {
        let mut cmd = Command::new("sh");
        cmd.args(["-c", "sleep 5"]);
        let result = run_bounded(cmd, Duration::from_millis(150));
        assert!(result.is_err());
    }
    let elapsed = start.elapsed();
    assert!(
        elapsed < Duration::from_secs(2),
        "two bounded calls took {elapsed:?}, expected well under 2s"
    );
}
