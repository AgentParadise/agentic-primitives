//! Regression tests for the paste-buffer fallback in `send_literal`.
//!
//! Mirrors the Python driver's `_tmux_send_literal` (PY:645-707): tmux's
//! `send-keys -l` has a ~16KB cap and silently truncates larger payloads.
//! Above `TMUX_SEND_KEYS_MAX_BYTES` (PY:91, `12_000`) the driver instead
//! stages the payload into a tmux buffer via `load-buffer -` (stdin) and
//! dispatches it with `paste-buffer`.
//!
//! These tests exercise the pure planning function only - no docker
//! daemon involved - so they run in any environment.

use itmux::tmux::{plan_send_literal, SendLiteralPlan, TMUX_SEND_KEYS_MAX_BYTES};

const PANE: &str = "agents:0";

#[test]
fn small_payload_uses_send_keys() {
    let text = "x".repeat(100);
    match plan_send_literal(PANE, &text) {
        SendLiteralPlan::SendKeys { pane, text: t } => {
            assert_eq!(pane, PANE);
            assert_eq!(t, text);
        }
        SendLiteralPlan::PasteBuffer { .. } => panic!("100-byte payload must use send-keys -l"),
    }
}

#[test]
fn large_payload_uses_paste_buffer() {
    let text = "y".repeat(20 * 1024);
    match plan_send_literal(PANE, &text) {
        SendLiteralPlan::PasteBuffer {
            pane,
            buffer,
            payload,
        } => {
            assert_eq!(pane, PANE);
            assert_eq!(payload, text.as_bytes());
            assert!(!buffer.is_empty(), "large path must mint a buffer name");
        }
        SendLiteralPlan::SendKeys { .. } => panic!("20KB payload must use paste-buffer"),
    }
}

#[test]
fn large_payload_plan_uses_bracketed_paste_and_named_buffer() {
    let text = "y".repeat(20 * 1024);
    let plan = plan_send_literal(PANE, &text);
    let buffer = match &plan {
        SendLiteralPlan::PasteBuffer { buffer, .. } => buffer.clone(),
        SendLiteralPlan::SendKeys { .. } => panic!("20KB payload must use paste-buffer"),
    };

    // load-buffer stages the payload into the NAMED buffer via stdin (`-`).
    let load = plan.load_buffer_args();
    assert_eq!(
        load,
        vec![
            "tmux".to_string(),
            "load-buffer".to_string(),
            "-b".to_string(),
            buffer.clone(),
            "-".to_string(),
        ],
    );

    // paste-buffer MUST carry `-p` (bracketed paste) and `-b <name>`
    // (named buffer), plus `-d` to delete it after paste. PY:698-702.
    let paste = plan.paste_buffer_args();
    assert!(
        paste.iter().any(|a| a == "-p"),
        "paste-buffer plan must include -p (bracketed paste): {paste:?}"
    );
    let b_pos = paste
        .iter()
        .position(|a| a == "-b")
        .expect("paste-buffer plan must include -b");
    assert_eq!(
        paste.get(b_pos + 1),
        Some(&buffer),
        "-b must be followed by the minted buffer name"
    );
    assert!(
        paste.iter().any(|a| a == "-d"),
        "paste-buffer plan must include -d (delete buffer after paste): {paste:?}"
    );
    assert_eq!(
        paste,
        vec![
            "tmux".to_string(),
            "paste-buffer".to_string(),
            "-p".to_string(),
            "-b".to_string(),
            buffer.clone(),
            "-d".to_string(),
            "-t".to_string(),
            PANE.to_string(),
        ],
    );
}

#[test]
fn buffer_names_are_unique_per_call() {
    let text = "y".repeat(20 * 1024);
    let a = match plan_send_literal(PANE, &text) {
        SendLiteralPlan::PasteBuffer { buffer, .. } => buffer,
        SendLiteralPlan::SendKeys { .. } => unreachable!(),
    };
    let b = match plan_send_literal(PANE, &text) {
        SendLiteralPlan::PasteBuffer { buffer, .. } => buffer,
        SendLiteralPlan::SendKeys { .. } => unreachable!(),
    };
    assert_ne!(a, b, "each large send must mint a distinct buffer name");
}

#[test]
fn small_payload_plan_has_no_paste_buffer_args() {
    let plan = plan_send_literal(PANE, "small");
    assert!(plan.load_buffer_args().is_empty());
    assert!(plan.paste_buffer_args().is_empty());
}

#[test]
fn boundary_exactly_at_threshold_uses_send_keys() {
    // PY:666 uses `<=` for the small-path check, so a payload of exactly
    // `TMUX_SEND_KEYS_MAX_BYTES` bytes still takes the send-keys path.
    let text = "z".repeat(TMUX_SEND_KEYS_MAX_BYTES);
    match plan_send_literal(PANE, &text) {
        SendLiteralPlan::SendKeys { .. } => {}
        SendLiteralPlan::PasteBuffer { .. } => {
            panic!("payload of exactly the threshold must use send-keys -l")
        }
    }
}

#[test]
fn boundary_one_byte_over_threshold_uses_paste_buffer() {
    let text = "z".repeat(TMUX_SEND_KEYS_MAX_BYTES + 1);
    match plan_send_literal(PANE, &text) {
        SendLiteralPlan::PasteBuffer { .. } => {}
        SendLiteralPlan::SendKeys { .. } => {
            panic!("payload one byte over the threshold must use paste-buffer")
        }
    }
}

#[test]
fn threshold_constant_matches_python_parity() {
    // PY:91 `TMUX_SEND_KEYS_MAX_BYTES = 12_000`.
    assert_eq!(TMUX_SEND_KEYS_MAX_BYTES, 12_000);
}
