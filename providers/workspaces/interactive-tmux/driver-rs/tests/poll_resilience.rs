//! Poll-resilience parity tests (Plan 1a, Task 4).
//!
//! Exercises the pure `itmux::workspace::classify_poll` step function that
//! `await_completion`/`wait_for_started` use to decide, per poll, whether to
//! keep waiting, treat the pane as captured, or bail out because the
//! workspace target itself is dead. No docker daemon involved - every case
//! feeds a synthetic `std::io::Result<String>` (the same shape
//! `tmux::capture_pane` returns) straight into `classify_poll`.
//!
//! Parity source: `driver/interactive_tmux.py` `_wait_for_started`
//! (PY:1962-1987), `await_completion` (PY:2110-2138), and
//! `_container_death_reason` / `_CONTAINER_DEAD_STDERR_MARKERS`
//! (PY:1637-1666).

use std::io::{Error, ErrorKind, Result};

use itmux::workspace::{classify_poll, PollStep};

fn transient_timeout() -> Result<String> {
    Err(Error::new(
        ErrorKind::TimedOut,
        "command timed out after 15s",
    ))
}

fn transient_exec_failure() -> Result<String> {
    // A generic docker exec failure whose stderr does not name a dead
    // container/session - e.g. a one-off wedge. Must be retried, not fatal.
    Err(Error::other(
        "docker exec c1 tmux capture-pane failed (exit 1): unexpected error",
    ))
}

fn ready_pane(text: &str) -> Result<String> {
    Ok(text.to_string())
}

#[test]
fn poll_sequence_transient_transient_ready_does_not_abort_on_first_error() {
    // (a) capture sequence [transient_err, transient_err, ready_pane] ->
    // classification never returns Dead, and the final capture is surfaced
    // for the readiness predicate to evaluate. This is the resilience gap:
    // a naive `?`-on-first-error loop would have aborted after step 1.
    let sequence = [
        transient_timeout(),
        transient_exec_failure(),
        ready_pane("agent is idle"),
    ];

    let mut captured: Option<String> = None;
    for capture in sequence {
        match classify_poll(capture) {
            PollStep::Retry => continue,
            PollStep::Captured(pane) => {
                captured = Some(pane);
            }
            PollStep::Dead(reason) => panic!("unexpectedly classified as dead: {reason}"),
        }
    }

    assert_eq!(captured.as_deref(), Some("agent is idle"));
}

#[test]
fn timed_out_capture_is_always_transient() {
    assert_eq!(classify_poll(transient_timeout()), PollStep::Retry);
}

#[test]
fn generic_capture_failure_is_transient() {
    assert_eq!(classify_poll(transient_exec_failure()), PollStep::Retry);
}

#[test]
fn real_container_dead_markers_are_classified_as_dead() {
    let cases = [
        "docker exec c1 tmux capture-pane failed (exit 1): Error: No such container: c1",
        "docker exec c1 tmux capture-pane failed (exit 1): container c1 is not running",
        "docker exec c1 tmux capture-pane failed (exit 1): no server running on /tmp/tmux-0/default",
        "docker exec c1 tmux capture-pane failed (exit 1): no such session: agents",
        "docker exec c1 tmux capture-pane failed (exit 1): can't find session agents",
    ];

    for case in cases {
        let step = classify_poll(Err(Error::other(case)));
        match step {
            PollStep::Dead(reason) => assert!(!reason.is_empty(), "empty reason for: {case}"),
            other => panic!("expected Dead for {case:?}, got {other:?}"),
        }
    }
}

#[test]
fn docker_daemon_outage_strings_are_not_classified_as_container_dead() {
    // (c) "cannot connect to the Docker daemon" must NOT be treated as
    // container death - it is a transient daemon/socket outage, and the
    // container is very likely still running once the daemon recovers.
    // Treating it as death would abort a live workspace on a blip.
    let daemon_outage_cases = [
        "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?",
        "error connecting to docker socket: dial unix /var/run/docker.sock: connect: no such file or directory",
    ];

    for case in daemon_outage_cases {
        let step = classify_poll(Err(Error::other(case)));
        assert_eq!(
            step,
            PollStep::Retry,
            "daemon-outage string wrongly classified as dead: {case}"
        );
    }
}

#[test]
fn timeout_is_never_classified_as_dead_even_with_a_death_marker_in_the_message() {
    // A `TimedOut` kind must short-circuit to transient regardless of
    // message content - mirrors Python's `isinstance(exc, TimeoutExpired)`
    // check running before any string matching (PY:1657-1658).
    let step = classify_poll(Err(Error::new(
        ErrorKind::TimedOut,
        "no such container: timed out waiting for capture",
    )));
    assert_eq!(step, PollStep::Retry);
}
