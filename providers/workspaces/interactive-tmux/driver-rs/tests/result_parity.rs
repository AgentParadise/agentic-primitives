//! Parity tests for the JSON shape of `AwaitResult` — must match the
//! Python `to_dict()` output (minus `pane` for the CLI surface).

use itmux::adapter::Agent;
use itmux::result::AwaitResult;

#[test]
fn await_result_ready_json_shape_matches_python() {
    let r = AwaitResult::ready(123.4, 5, "pane".to_string());
    let v: serde_json::Value = serde_json::to_value(&r).unwrap();
    assert_eq!(v["ready"], true);
    assert_eq!(v["timed_out"], false);
    assert_eq!(v["reason"], "ready");
    assert_eq!(v["stable_polls_observed"], 5);
    assert!(v.get("duration_ms").is_some());
    assert_eq!(v["pane"], "pane");
    assert!(v["error"].is_null());
}

#[test]
fn await_result_timeout_never_ready_carries_zero_stable_polls() {
    let r = AwaitResult::timeout_never_ready(99.0, "pane".to_string());
    assert!(!r.ready);
    assert!(r.timed_out);
    assert_eq!(r.reason, "timeout_never_ready");
    assert_eq!(r.stable_polls_observed, 0);
    assert_eq!(r.cli_exit_code(), 2);
}

#[test]
fn await_result_timeout_unstable_preserves_stable_polls() {
    let r = AwaitResult::timeout_unstable(50.0, 2, "pane".to_string());
    assert!(!r.ready);
    assert_eq!(r.reason, "timeout_unstable");
    assert_eq!(r.stable_polls_observed, 2);
}

#[test]
fn await_result_error_includes_message() {
    let r = AwaitResult::error(10.0, "pane".to_string(), "boom");
    assert_eq!(r.reason, "error");
    assert_eq!(r.error.as_deref(), Some("boom"));
    assert_eq!(r.cli_exit_code(), 2);
}

#[test]
fn agent_parse_round_trips_for_each_name() {
    for agent in [Agent::Claude, Agent::Codex, Agent::Gemini] {
        assert_eq!(Agent::parse(agent.as_str()), Some(agent));
        assert_eq!(agent.window(), agent.as_str());
    }
    assert_eq!(Agent::parse("ghost"), None);
}

#[test]
fn agent_response_markers_match_python_constants() {
    assert_eq!(Agent::Claude.response_marker(), "● ");
    assert_eq!(Agent::Codex.response_marker(), "• ");
    assert_eq!(Agent::Gemini.response_marker(), "✦ ");
}
