//! Readiness-parser unit tests.
//!
//! Each test loads a captured pane fixture (real smoke output with smoke
//! tokens scrubbed) and asserts the per-agent `is_ready` / `is_started`
//! predicate matches Python parity.

use itmux::adapter::{
    claude_is_ready, claude_is_started, codex_is_ready, codex_is_started, gemini_is_ready,
    gemini_is_started,
};

const CLAUDE_READY: &str = include_str!("fixtures/claude/ready_post_turn.txt");
const CLAUDE_GENERATING: &str = include_str!("fixtures/claude/generating.txt");
const CLAUDE_WELCOME: &str = include_str!("fixtures/claude/welcome_started.txt");

const CODEX_READY: &str = include_str!("fixtures/codex/ready_post_turn.txt");
const CODEX_WORKING: &str = include_str!("fixtures/codex/working.txt");
const CODEX_IDLE_HINT: &str = include_str!("fixtures/codex/idle_hint_only.txt");

const GEMINI_READY: &str = include_str!("fixtures/gemini/ready_post_turn.txt");
const GEMINI_THINKING: &str = include_str!("fixtures/gemini/thinking.txt");
const GEMINI_COLD: &str = include_str!("fixtures/gemini/cold_no_prompt.txt");

// ---------------------------------------------------------------------------
// Claude

#[test]
fn claude_post_turn_pane_is_ready() {
    assert!(
        claude_is_ready(CLAUDE_READY),
        "expected post-turn capture to satisfy all three signals"
    );
}

#[test]
fn claude_generating_pane_is_not_ready() {
    assert!(
        !claude_is_ready(CLAUDE_GENERATING),
        "presence of `esc to interrupt` must veto readiness"
    );
}

#[test]
fn claude_welcome_pane_is_started_but_not_ready() {
    // The welcome screen shows `❯ Try …` (placeholder); is_started must
    // pass, but the strict post-turn is_ready must NOT — the prompt line
    // isn't empty.
    assert!(claude_is_started(CLAUDE_WELCOME));
    assert!(!claude_is_ready(CLAUDE_WELCOME));
}

#[test]
fn claude_missing_footer_is_not_ready() {
    let pane = "❯ \n\n some random text without the footer";
    assert!(!claude_is_ready(pane));
    assert!(!claude_is_started(pane));
}

#[test]
fn claude_empty_prompt_regex_tolerates_trailing_whitespace() {
    // The Python regex `^❯\s*$` (multiline) tolerates trailing whitespace.
    let pane = "  ? for shortcuts\n❯   \nfooter";
    assert!(claude_is_ready(pane));
}

// ---------------------------------------------------------------------------
// Codex

#[test]
fn codex_post_turn_pane_is_ready() {
    assert!(codex_is_ready(CODEX_READY));
    assert!(codex_is_started(CODEX_READY));
}

#[test]
fn codex_working_pane_is_not_ready() {
    assert!(
        !codex_is_ready(CODEX_WORKING),
        "presence of `• Working` must veto readiness"
    );
}

#[test]
fn codex_idle_with_hint_only_is_ready() {
    // The `Write tests for @…` hint alone is enough idle signal.
    assert!(codex_is_ready(CODEX_IDLE_HINT));
}

#[test]
fn codex_empty_pane_is_not_ready() {
    assert!(!codex_is_ready(""));
}

#[test]
fn codex_tip_only_satisfies_readiness() {
    // Even if `› ` is missing, a `Tip:` line alone is OR'd into the check
    // (mirrors the Python adapter's three-way OR).
    let pane = "Tip: Use /feedback to send logs to the maintainers.\n";
    assert!(codex_is_ready(pane));
}

// ---------------------------------------------------------------------------
// Gemini

#[test]
fn gemini_post_turn_pane_is_ready() {
    assert!(gemini_is_ready(GEMINI_READY));
    assert!(gemini_is_started(GEMINI_READY));
}

#[test]
fn gemini_thinking_pane_is_not_ready() {
    // Both `Thinking...` and `esc to cancel` must veto readiness even
    // when the prompt-hint line is still visible at the bottom.
    assert!(!gemini_is_ready(GEMINI_THINKING));
}

#[test]
fn gemini_cold_no_prompt_is_not_ready() {
    assert!(!gemini_is_ready(GEMINI_COLD));
    assert!(!gemini_is_started(GEMINI_COLD));
}

#[test]
fn gemini_esc_to_cancel_alone_vetoes_readiness() {
    // Test the second guard arm independently — `esc to cancel` even
    // without `Thinking...`.
    let pane = "Type your message\nesc to cancel\n";
    assert!(!gemini_is_ready(pane));
}
