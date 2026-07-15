//! Gap 1 tests: the per-harness submit input-readiness gate (the claude
//! send-race). Keystroke landing is auth-independent, so these are pure
//! fixture/unit tests - no docker, no live token.
//!
//! Harness-neutrality (plan R8): the retry path is exercised for claude and
//! the one-shot path is asserted for codex through the SAME
//! `run_submit_protocol` interface; the per-harness specifics
//! (`needs_submit_verification`, `input_reflects_submission`) live in
//! `adapter.rs`, and `run_submit_protocol` itself has no harness-name
//! branches (the full generic-run guard lands with the orchestrator in
//! Task 3).

use std::cell::Cell;
use std::time::Duration;

use itmux::adapter::{
    input_reflects_submission, needs_submit_verification, run_submit_protocol, submit_fragment,
    Agent, SubmitOutcome,
};

// --- pane fixtures ---------------------------------------------------------

const CLAUDE_TASK: &str = "Write a haiku about the sea";

/// The send-race failure: claude launched, keystrokes dropped, prompt empty.
fn claude_dropped_pane() -> String {
    "\n❯\n\n  ? for shortcuts\n".to_string()
}

/// The healthy case: the typed prompt is echoed in claude's input line.
fn claude_landed_pane() -> String {
    format!("\n❯ {CLAUDE_TASK}\n\n  ? for shortcuts\n")
}

/// Codex, after its launch dance, with the prompt typed into its input line.
fn codex_landed_pane() -> String {
    format!("\n› {CLAUDE_TASK}\n\n  Tip: press Enter to send\n")
}

// --- pure predicate --------------------------------------------------------

#[test]
fn submit_fragment_uses_first_line_normalised_and_capped() {
    assert_eq!(submit_fragment("  hello   world  "), "hello world");
    assert_eq!(
        submit_fragment("first line\nsecond line"),
        "first line",
        "multi-line prompt yields a stable single-line needle"
    );
    let long = "x".repeat(200);
    assert_eq!(submit_fragment(&long).chars().count(), 60, "capped at 60");
}

#[test]
fn claude_empty_prompt_pane_does_not_reflect_submission() {
    assert!(!input_reflects_submission(
        Agent::Claude,
        &claude_dropped_pane(),
        CLAUDE_TASK
    ));
}

#[test]
fn claude_landed_pane_reflects_submission() {
    assert!(input_reflects_submission(
        Agent::Claude,
        &claude_landed_pane(),
        CLAUDE_TASK
    ));
}

#[test]
fn claude_reflects_submission_survives_wrapped_prompt() {
    // TUI wraps the echoed prompt across lines and pads with spaces; the
    // whitespace-normalised match must still find it.
    let wrapped = "❯ Write a haiku\n  about the sea\n  ? for shortcuts";
    assert!(input_reflects_submission(
        Agent::Claude,
        wrapped,
        CLAUDE_TASK
    ));
}

#[test]
fn codex_landed_pane_reflects_submission() {
    // Codex still works: its predicate accepts a normally-typed prompt.
    assert!(input_reflects_submission(
        Agent::Codex,
        &codex_landed_pane(),
        CLAUDE_TASK
    ));
}

// --- per-harness verification flags ----------------------------------------

#[test]
fn only_claude_needs_submit_verification() {
    // The per-harness seam: claude opts into the gate; codex/gemini do not.
    assert!(needs_submit_verification(Agent::Claude));
    assert!(!needs_submit_verification(Agent::Codex));
    assert!(!needs_submit_verification(Agent::Gemini));
}

// --- protocol runner: claude retry path ------------------------------------

#[test]
fn claude_submit_retries_until_prompt_lands_then_submits_once() {
    let sends = Cell::new(0u32);
    let captures = Cell::new(0u32);
    let finalizes = Cell::new(0u32);
    let sleeps = Cell::new(0u32);
    let retype_clears = Cell::new(0u32);

    let outcome: SubmitOutcome = run_submit_protocol(
        Agent::Claude,
        CLAUDE_TASK,
        3,
        Duration::from_millis(0),
        |attempt| {
            sends.set(sends.get() + 1);
            if attempt > 0 {
                retype_clears.set(retype_clears.get() + 1);
            }
            Ok(())
        },
        || {
            captures.set(captures.get() + 1);
            // First capture: keystrokes dropped. Second: landed.
            if captures.get() == 1 {
                Ok(claude_dropped_pane())
            } else {
                Ok(claude_landed_pane())
            }
        },
        || {
            finalizes.set(finalizes.get() + 1);
            Ok(())
        },
        |_d| {
            sleeps.set(sleeps.get() + 1);
        },
    )
    .expect("protocol runs");

    assert_eq!(
        outcome,
        SubmitOutcome {
            attempts: 2,
            verified: true
        }
    );
    assert_eq!(sends.get(), 2, "typed twice: initial + one retry");
    assert_eq!(
        retype_clears.get(),
        1,
        "retry clears input before re-typing"
    );
    assert_eq!(captures.get(), 2, "captured after each type");
    assert_eq!(
        finalizes.get(),
        1,
        "submit key pressed exactly once, after landing"
    );
    assert_eq!(sleeps.get(), 2, "settle pause before each capture");
}

#[test]
fn claude_submit_gives_up_after_max_attempts_but_still_submits() {
    let sends = Cell::new(0u32);
    let finalizes = Cell::new(0u32);

    let outcome = run_submit_protocol(
        Agent::Claude,
        CLAUDE_TASK,
        3,
        Duration::from_millis(0),
        |_attempt| {
            sends.set(sends.get() + 1);
            Ok(())
        },
        // Prompt never lands (pathological): every capture shows it dropped.
        || Ok(claude_dropped_pane()),
        || {
            finalizes.set(finalizes.get() + 1);
            Ok(())
        },
        |_d| {},
    )
    .expect("protocol runs");

    assert_eq!(
        outcome,
        SubmitOutcome {
            attempts: 3,
            verified: false
        },
        "exhausts the bounded retries and reports unverified"
    );
    assert_eq!(sends.get(), 3, "typed once per bounded attempt");
    assert_eq!(
        finalizes.get(),
        1,
        "still presses submit so a real launch is never wedged forever"
    );
}

// --- protocol runner: codex one-shot path (still works) --------------------

#[test]
fn codex_submit_sends_once_without_verification() {
    let sends = Cell::new(0u32);
    let finalizes = Cell::new(0u32);

    let outcome = run_submit_protocol(
        Agent::Codex,
        CLAUDE_TASK,
        3,
        Duration::from_millis(0),
        |attempt| {
            assert_eq!(attempt, 0, "one-shot: only the first attempt is ever sent");
            sends.set(sends.get() + 1);
            Ok(())
        },
        // A one-shot harness must never do the verify capture round-trip.
        || panic!("codex submit must not capture the pane"),
        || {
            finalizes.set(finalizes.get() + 1);
            Ok(())
        },
        |_d| panic!("codex submit must not sleep to verify"),
    )
    .expect("protocol runs");

    assert_eq!(
        outcome,
        SubmitOutcome {
            attempts: 1,
            verified: true
        }
    );
    assert_eq!(sends.get(), 1, "codex types exactly once");
    assert_eq!(finalizes.get(), 1, "codex submits exactly once");
}
