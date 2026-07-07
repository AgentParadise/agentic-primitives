//! Gap 2 tests: per-harness `detect_outcome` (Plan B Task 5).
//!
//! Auth-independent fixture/unit tests - no docker, no token. A clean ready
//! pane yields success; a pane carrying a harness hard-error marker yields
//! failure with the marker in the reason. Harness specifics live in
//! `adapter.rs` (per R8); these tests exercise claude AND codex.

use itmux::adapter::{detect_outcome, error_markers, Agent, RunOutcomeSignal};

// Real ready-pane captures (smoke output with tokens scrubbed) - reused from
// the readiness fixtures so "clean ready pane -> success" is tested against
// panes the readiness predicate actually accepts.
const CLAUDE_READY: &str = include_str!("fixtures/claude/ready_post_turn.txt");
const CLAUDE_GENERATING: &str = include_str!("fixtures/claude/generating.txt");
const CODEX_READY: &str = include_str!("fixtures/codex/ready_post_turn.txt");

fn assert_failure_mentions(signal: &RunOutcomeSignal, needle: &str) {
    assert!(!signal.success, "expected failure, got: {signal:?}");
    assert!(
        signal.reason.contains(needle),
        "reason should mention {needle:?}, got: {}",
        signal.reason
    );
}

// --- claude ----------------------------------------------------------------

#[test]
fn claude_clean_ready_pane_is_success() {
    let signal = detect_outcome(Agent::Claude, CLAUDE_READY);
    assert!(
        signal.success,
        "clean ready pane should be success: {signal:?}"
    );
}

#[test]
fn claude_api_error_pane_is_failure() {
    // Splice a hard-error banner into an otherwise-ready pane.
    let pane = format!("{CLAUDE_READY}\n● API Error: something went wrong\n");
    assert_failure_mentions(&detect_outcome(Agent::Claude, &pane), "API Error");
}

#[test]
fn claude_401_on_an_error_line_is_failure() {
    // Ambiguous token `401` counts only on an error-banner line (has "error").
    let pane = format!("{CLAUDE_READY}\n● Error: request failed with status 401\n");
    assert_failure_mentions(&detect_outcome(Agent::Claude, &pane), "401");
}

#[test]
fn claude_prose_mentioning_401_is_not_a_hard_error() {
    // Fix 5: the agent's OWN reply discussing HTTP 401 must NOT be misread as a
    // hard error - the `401` is not on an error-banner line.
    let pane = format!("{CLAUDE_READY}\nThe endpoint returns 401 on bad auth, so guard it.\n");
    let signal = detect_outcome(Agent::Claude, &pane);
    assert!(
        signal.success,
        "prose mentioning 401 must not be a hard error: {signal:?}"
    );
}

#[test]
fn claude_prose_mentioning_invalid_api_key_is_not_a_hard_error() {
    let pane =
        format!("{CLAUDE_READY}\nA 403 differs from an Invalid API key rejection in practice.\n");
    let signal = detect_outcome(Agent::Claude, &pane);
    assert!(
        signal.success,
        "prose mentioning 'Invalid API key' off an error line must be success: {signal:?}"
    );
}

#[test]
fn claude_login_required_pane_is_failure() {
    let pane = "Not logged in - Please run /login to authenticate\n";
    assert_failure_mentions(&detect_outcome(Agent::Claude, pane), "Please run /login");
}

#[test]
fn claude_not_ready_pane_is_failure_without_error_marker() {
    // No hard error, but the pane never settled (mid-generation): not success.
    let signal = detect_outcome(Agent::Claude, CLAUDE_GENERATING);
    assert!(!signal.success);
    assert!(
        signal.reason.contains("did not settle"),
        "{}",
        signal.reason
    );
}

// --- codex -----------------------------------------------------------------

#[test]
fn codex_clean_ready_pane_is_success() {
    let signal = detect_outcome(Agent::Codex, CODEX_READY);
    assert!(
        signal.success,
        "clean ready pane should be success: {signal:?}"
    );
}

#[test]
fn codex_not_authenticated_pane_is_failure() {
    let pane = format!("{CODEX_READY}\n▌ You are not logged in. Run `codex login` to continue.\n");
    let signal = detect_outcome(Agent::Codex, &pane);
    assert!(!signal.success, "unauth codex pane should fail: {signal:?}");
}

#[test]
fn codex_unauthorized_pane_is_failure() {
    let pane = format!("{CODEX_READY}\n▌ stream error: 401 Unauthorized\n");
    assert_failure_mentions(&detect_outcome(Agent::Codex, &pane), "Unauthorized");
}

#[test]
fn codex_prose_mentioning_401_is_not_a_hard_error() {
    // Fix 5: codex agent prose about 401 must not be misread as an auth failure.
    let pane = format!("{CODEX_READY}\nNote: a 401 response usually means expired creds.\n");
    let signal = detect_outcome(Agent::Codex, &pane);
    assert!(
        signal.success,
        "codex prose mentioning 401 must be success: {signal:?}"
    );
}

#[test]
fn codex_benign_mcp_warning_is_not_treated_as_failure() {
    // A healthy codex launch prints MCP startup warnings that contain the word
    // "error" - these must NOT be read as a run failure (they collide with a
    // naive `error` marker, which is exactly why the codex set is auth-focused).
    let pane = format!(
        "{CODEX_READY}\n\u{26a0} MCP client for `mcp_agent_mail` failed to start: \
         Send message error Transport error: HTTP request failed\n"
    );
    let signal = detect_outcome(Agent::Codex, &pane);
    assert!(
        signal.success,
        "benign MCP warning must not fail the run: {signal:?}"
    );
}

// --- marker tables ---------------------------------------------------------

#[test]
fn codex_markers_do_not_collide_with_benign_warning_vocabulary() {
    // Guard: none of codex's markers appear in the benign MCP warning text, so
    // the conservative set can't regress into false positives.
    let benign = "\u{26a0} MCP client failed to start: Send message error Transport error: \
                  HTTP request failed: error sending request for url";
    for marker in error_markers(Agent::Codex) {
        assert!(
            !benign.contains(marker),
            "codex marker {marker:?} collides with benign warning text"
        );
    }
}

#[test]
fn gemini_has_no_hard_error_markers_yet() {
    assert!(
        error_markers(Agent::Gemini).is_empty(),
        "gemini is not a Task 5 target; it relies on the readiness floor only"
    );
}
