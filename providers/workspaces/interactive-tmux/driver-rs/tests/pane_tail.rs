//! Regression tests for the full-scrollback capture + tail-based
//! readiness, mirroring the Python `test_interactive_tmux_pane_tail.py`.
//!
//! Covers the two stress blockers from Syntropic137's stress run
//! (syntropic137 repo, `origin/exp/interactive-tmux-stress`,
//! `experiments/stress/STRESS-REPORT.md`):
//!
//! - D-block-3: `tmux capture-pane` previously shipped without
//!   `-S - -E -`, returning only the visible 50 rows. The
//!   `capture_pane` wrapper in `src/tmux.rs` now includes those flags;
//!   this test file does not shell out to docker, so it covers the
//!   helper that consumers (workspace::await_completion etc.) layer on
//!   top: `pane_tail`.
//! - D-block-2: `is_ready` / `is_started` predicates fooled by stale
//!   text in the now-included scrollback (an old "esc to interrupt"
//!   forever vetoes Claude readiness). Predicates are now evaluated
//!   against the bottom-of-pane tail; this file asserts the tail
//!   predicate matches the live idle state while the whole-buffer
//!   predicate does not.

use itmux::adapter::{claude_is_ready, codex_is_ready, gemini_is_ready};
use itmux::tmux::pane_tail;

/// Build a pane buffer with EXACT line accounting.
///
/// Each line is non-empty so `pane.split('\n')` round-trips the input,
/// which keeps the tail predictable regardless of trailing-newline
/// semantics.
fn build_pane(history_substring: &str, history_lines: usize, idle_tail: &[String]) -> String {
    let mut lines: Vec<String> = (0..history_lines)
        .map(|i| format!("  history-{i} {history_substring} END"))
        .collect();
    lines.extend(idle_tail.iter().cloned());
    lines.join("\n")
}

fn claude_idle_tail(n: usize) -> Vec<String> {
    let mut lines = vec!["  visible-filler-A".to_string(); n / 2 - 2];
    lines.push("\u{276f} ".to_string()); // empty `❯ ` chevron line
    lines.push("─".repeat(80));
    lines.push("  ? for shortcuts".to_string());
    while lines.len() < n {
        lines.push("  visible-filler-B".to_string());
    }
    lines
}

fn codex_idle_tail(n: usize) -> Vec<String> {
    let mut lines = vec!["  visible-filler-A".to_string(); n - 4];
    lines.push("\u{203a} ".to_string()); // `› ` idle marker
    lines.push("  Tip: drive the model with /commands".to_string());
    lines.push("  visible-filler-B".to_string());
    lines.push("  visible-filler-C".to_string());
    lines
}

fn gemini_idle_tail(n: usize) -> Vec<String> {
    let mut lines = vec!["  visible-filler-A".to_string(); n - 3];
    lines.push(" >   Type your message or @path/to/file".to_string());
    lines.push("  visible-filler-B".to_string());
    lines.push("  visible-filler-C".to_string());
    lines
}

// ---------------------------------------------------------------------------
// pane_tail helper

#[test]
fn pane_tail_short_returns_pane_verbatim() {
    let pane = "line0\nline1\nline2";
    assert_eq!(pane_tail(pane, 50), pane);
}

#[test]
fn pane_tail_long_truncates_to_last_n_lines() {
    let pane: String = (0..200).map(|i| format!("row{i}")).collect::<Vec<_>>().join("\n");
    let tail = pane_tail(&pane, 50);
    let lines: Vec<&str> = tail.split('\n').collect();
    assert_eq!(lines.len(), 50);
    assert_eq!(lines[0], "row150");
    assert_eq!(lines[49], "row199");
}

#[test]
fn pane_tail_empty_yields_empty() {
    assert_eq!(pane_tail("", 50), "");
}

// ---------------------------------------------------------------------------
// Claude

#[test]
fn claude_full_buffer_with_stale_generation_breaks_predicate() {
    let full = build_pane("esc to interrupt", 200, &claude_idle_tail(50));
    // Predicate over the WHOLE scrollback sees stale "esc to interrupt"
    // → reports not ready.
    assert!(!claude_is_ready(&full));
}

#[test]
fn claude_tail_correctly_reports_ready_on_multi_paragraph_history() {
    let full = build_pane("esc to interrupt", 200, &claude_idle_tail(50));
    let tail = pane_tail(&full, 50);
    assert!(
        claude_is_ready(&tail),
        "tail should match idle predicate; tail starts with: {:?}",
        tail.split('\n').next().unwrap_or_default()
    );
}

#[test]
fn claude_full_pane_taller_than_one_screen() {
    // STRESS-REPORT.md ratio (5716/1834 ~= 3x) — pane 3x the visible height.
    let full = build_pane("esc to interrupt + filler text", 300, &claude_idle_tail(50));
    assert!(!claude_is_ready(&full));
    let tail = pane_tail(&full, 50);
    assert!(claude_is_ready(&tail));
}

// ---------------------------------------------------------------------------
// Codex

#[test]
fn codex_full_buffer_with_stale_working_breaks_predicate() {
    let full = build_pane("• Working (esc to interrupt)", 200, &codex_idle_tail(50));
    assert!(!codex_is_ready(&full));
}

#[test]
fn codex_tail_correctly_reports_ready() {
    let full = build_pane("• Working (esc to interrupt)", 200, &codex_idle_tail(50));
    let tail = pane_tail(&full, 50);
    assert!(codex_is_ready(&tail));
}

// ---------------------------------------------------------------------------
// Gemini

#[test]
fn gemini_full_buffer_with_stale_thinking_breaks_predicate() {
    let full = build_pane("Thinking... esc to cancel", 200, &gemini_idle_tail(50));
    assert!(!gemini_is_ready(&full));
}

#[test]
fn gemini_tail_correctly_reports_ready() {
    let full = build_pane("Thinking... esc to cancel", 200, &gemini_idle_tail(50));
    let tail = pane_tail(&full, 50);
    assert!(gemini_is_ready(&tail));
}
