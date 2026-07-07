//! Two-tier cancellation escalation logic (Plan B Task 6).
//!
//! These test the `CancelEscalator` -> `CancelToken` level transitions WITHOUT
//! raising real OS signals (real signal delivery is inherently hard to unit
//! test and is covered by the live run, Task 8). The CLI wires SIGINT/SIGTERM
//! to this exact logic via a self-pipe watcher thread in `main.rs`.

use itmux::run::orchestrator::{CancelEscalator, CancelLevel, CancelToken, SignalKind};

#[test]
fn first_interrupt_is_graceful_second_is_hard() {
    let token = CancelToken::new();
    let mut escalator = CancelEscalator::new();

    assert_eq!(token.level(), CancelLevel::None);

    escalator.on_signal(SignalKind::Interrupt, &token);
    assert_eq!(
        token.level(),
        CancelLevel::Graceful,
        "first Ctrl-C requests a graceful cancel"
    );

    escalator.on_signal(SignalKind::Interrupt, &token);
    assert_eq!(
        token.level(),
        CancelLevel::Hard,
        "second Ctrl-C escalates to hard"
    );
}

#[test]
fn terminate_goes_straight_to_hard() {
    let token = CancelToken::new();
    let mut escalator = CancelEscalator::new();

    escalator.on_signal(SignalKind::Terminate, &token);
    assert_eq!(
        token.level(),
        CancelLevel::Hard,
        "SIGTERM is an immediate hard cancel"
    );
}

#[test]
fn hard_is_never_downgraded_by_a_later_interrupt() {
    let token = CancelToken::new();
    let mut escalator = CancelEscalator::new();

    escalator.on_signal(SignalKind::Terminate, &token);
    // A stray interrupt after a hard cancel must not drop it back to graceful.
    escalator.on_signal(SignalKind::Interrupt, &token);
    assert_eq!(token.level(), CancelLevel::Hard);
}

#[test]
fn three_interrupts_stay_hard() {
    let token = CancelToken::new();
    let mut escalator = CancelEscalator::new();

    for _ in 0..3 {
        escalator.on_signal(SignalKind::Interrupt, &token);
    }
    assert_eq!(token.level(), CancelLevel::Hard);
}
