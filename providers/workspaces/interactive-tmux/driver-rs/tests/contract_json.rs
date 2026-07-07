//! TDD contract tests for the `itmux run` JSON contract (Plan B Task 1).
//!
//! Covers: round-trip JSON for every struct, `deny_unknown_fields` rejection,
//! and the `AgentRunEvent` envelope (R6: `run_id`/`seq`/`ts` + a `type`-tagged
//! payload, one JSON object per line).

use std::path::PathBuf;

use itmux::run::contract::{
    AgentRunCredentials, AgentRunEvent, AgentRunEventPayload, AgentRunLimits, AgentRunOutcome,
    AgentRunResult, AgentRunSpec, ClaudeCredentials, CodexCredentials, ObservabilityBundle,
    ObservabilityExporter,
};

fn roundtrip<T>(value: &T)
where
    T: serde::Serialize + serde::de::DeserializeOwned + PartialEq + std::fmt::Debug,
{
    let json = serde_json::to_string(value).expect("serialize");
    let back: T = serde_json::from_str(&json).expect("deserialize");
    assert_eq!(value, &back, "round-trip mismatch for json: {json}");
}

#[test]
fn agent_run_spec_round_trips_minimal() {
    let spec = AgentRunSpec {
        recipe: PathBuf::from("/recipes/my-recipe"),
        task: "fix the bug".to_string(),
        input_artifacts: vec![],
        credentials: AgentRunCredentials::default(),
        observability: vec![],
        limits: None,
    };
    roundtrip(&spec);
}

#[test]
fn agent_run_spec_round_trips_full() {
    let spec = AgentRunSpec {
        recipe: PathBuf::from("/recipes/my-recipe"),
        task: "fix the bug".to_string(),
        input_artifacts: vec![
            PathBuf::from("/tmp/in/a.txt"),
            PathBuf::from("/tmp/in/b.txt"),
        ],
        credentials: AgentRunCredentials {
            claude: Some(ClaudeCredentials {
                oauth_token: "sk-oauth-abc123".to_string(),
            }),
            codex: Some(CodexCredentials {
                auth_json: r#"{"token":"xyz"}"#.to_string(),
            }),
        },
        observability: vec![ObservabilityExporter {
            name: "otel".to_string(),
            config: serde_json::json!({"endpoint": "http://collector:4318"}),
        }],
        limits: Some(AgentRunLimits {
            timeout_s: Some(120.0),
            token_budget: Some(50_000),
        }),
    };
    roundtrip(&spec);
}

#[test]
fn agent_run_spec_recipe_is_a_directory_path_not_inline() {
    // R4 (authoritative): recipe is a directory PathBuf only, no inline
    // recipe variant. Deserializing a bare string into `recipe` must work
    // exactly like any other path field - no `oneOf` / untagged handling.
    let json = r#"{
        "recipe": "/recipes/my-recipe",
        "task": "do the thing"
    }"#;
    let spec: AgentRunSpec = serde_json::from_str(json).expect("deserialize");
    assert_eq!(spec.recipe, PathBuf::from("/recipes/my-recipe"));
    assert_eq!(spec.task, "do the thing");
    assert!(spec.input_artifacts.is_empty());
    assert_eq!(spec.credentials, AgentRunCredentials::default());
    assert!(spec.observability.is_empty());
    assert!(spec.limits.is_none());
}

#[test]
fn agent_run_spec_rejects_unknown_field() {
    let json = r#"{
        "recipe": "/recipes/my-recipe",
        "task": "do the thing",
        "not_a_real_field": true
    }"#;
    let err = serde_json::from_str::<AgentRunSpec>(json).unwrap_err();
    assert!(err.to_string().contains("not_a_real_field"), "err: {err}");
}

#[test]
fn agent_run_credentials_round_trip_and_reject_unknown_field() {
    let creds = AgentRunCredentials {
        claude: Some(ClaudeCredentials {
            oauth_token: "tok".to_string(),
        }),
        codex: None,
    };
    roundtrip(&creds);

    let json = r#"{"claude": {"oauth_token": "tok"}, "gemini": {}}"#;
    let err = serde_json::from_str::<AgentRunCredentials>(json).unwrap_err();
    assert!(err.to_string().contains("gemini"), "err: {err}");
}

#[test]
fn claude_credentials_reject_unknown_field() {
    let json = r#"{"oauth_token": "tok", "extra": "nope"}"#;
    let err = serde_json::from_str::<ClaudeCredentials>(json).unwrap_err();
    assert!(err.to_string().contains("extra"), "err: {err}");
}

#[test]
fn codex_credentials_hold_contents_not_a_path() {
    let creds = CodexCredentials {
        auth_json: r#"{"token":"abc"}"#.to_string(),
    };
    roundtrip(&creds);
    let value = serde_json::to_value(&creds).unwrap();
    assert_eq!(value["auth_json"], r#"{"token":"abc"}"#);
}

#[test]
fn agent_run_limits_round_trip_and_reject_unknown_field() {
    let limits = AgentRunLimits {
        timeout_s: Some(30.5),
        token_budget: None,
    };
    roundtrip(&limits);

    let json = r#"{"timeout_s": 1.0, "token_budget": 5, "extra_limit": 1}"#;
    let err = serde_json::from_str::<AgentRunLimits>(json).unwrap_err();
    assert!(err.to_string().contains("extra_limit"), "err: {err}");
}

#[test]
fn observability_exporter_round_trips_with_opaque_config() {
    let exporter = ObservabilityExporter {
        name: "otel".to_string(),
        config: serde_json::json!({"anything": [1, 2, 3]}),
    };
    roundtrip(&exporter);
}

#[test]
fn agent_run_result_round_trips_minimal() {
    let result = AgentRunResult {
        result: AgentRunOutcome {
            success: true,
            summary: "all good".to_string(),
        },
        output_artifacts: vec![],
        session_log: "pane contents here".to_string(),
        observability: None,
    };
    roundtrip(&result);
}

#[test]
fn agent_run_result_round_trips_full_and_rejects_unknown_field() {
    let result = AgentRunResult {
        result: AgentRunOutcome {
            success: false,
            summary: "agent hit an auth error".to_string(),
        },
        output_artifacts: vec![PathBuf::from("/tmp/out/report.md")],
        session_log: "pane contents here".to_string(),
        observability: Some(ObservabilityBundle::default()),
    };
    roundtrip(&result);

    let json = r#"{
        "result": {"success": true, "summary": "ok"},
        "session_log": "log",
        "bogus": 1
    }"#;
    let err = serde_json::from_str::<AgentRunResult>(json).unwrap_err();
    assert!(err.to_string().contains("bogus"), "err: {err}");
}

#[test]
fn agent_run_outcome_rejects_unknown_field() {
    let json = r#"{"success": true, "summary": "ok", "reason_code": 7}"#;
    let err = serde_json::from_str::<AgentRunOutcome>(json).unwrap_err();
    assert!(err.to_string().contains("reason_code"), "err: {err}");
}

// --- AgentRunEvent envelope (R6) -------------------------------------------

#[test]
fn agent_run_event_envelope_has_run_id_seq_ts_and_typed_payload() {
    let event = AgentRunEvent {
        run_id: "run-1".to_string(),
        seq: 0,
        ts: "2026-07-07T12:00:00Z".to_string(),
        payload: AgentRunEventPayload::ToolStart {
            tool_name: "Read".to_string(),
            tool_input: serde_json::json!({"path": "/tmp/a.txt"}),
        },
    };
    let value = serde_json::to_value(&event).unwrap();
    assert_eq!(value["run_id"], "run-1");
    assert_eq!(value["seq"], 0);
    assert_eq!(value["ts"], "2026-07-07T12:00:00Z");
    assert_eq!(value["type"], "tool_start");
    assert_eq!(value["tool_name"], "Read");
    roundtrip(&event);
}

#[test]
fn agent_run_event_tool_start_round_trips() {
    let json = r#"{
        "run_id": "run-1",
        "seq": 0,
        "ts": "2026-07-07T12:00:00Z",
        "type": "tool_start",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"}
    }"#;
    let event: AgentRunEvent = serde_json::from_str(json).expect("deserialize");
    match &event.payload {
        AgentRunEventPayload::ToolStart {
            tool_name,
            tool_input,
        } => {
            assert_eq!(tool_name, "Bash");
            assert_eq!(tool_input["command"], "ls");
        }
        other => panic!("expected ToolStart, got {other:?}"),
    }
    roundtrip(&event);
}

#[test]
fn agent_run_event_tool_end_round_trips() {
    let json = r#"{
        "run_id": "run-1",
        "seq": 1,
        "ts": "2026-07-07T12:00:01Z",
        "type": "tool_end",
        "tool_name": "Bash",
        "success": true,
        "output_summary": "listed 3 files"
    }"#;
    let event: AgentRunEvent = serde_json::from_str(json).expect("deserialize");
    match &event.payload {
        AgentRunEventPayload::ToolEnd {
            tool_name,
            success,
            output_summary,
        } => {
            assert_eq!(tool_name, "Bash");
            assert!(*success);
            assert_eq!(output_summary.as_deref(), Some("listed 3 files"));
        }
        other => panic!("expected ToolEnd, got {other:?}"),
    }
    roundtrip(&event);
}

#[test]
fn agent_run_event_token_usage_round_trips() {
    let json = r#"{
        "run_id": "run-1",
        "seq": 2,
        "ts": "2026-07-07T12:00:02Z",
        "type": "token_usage",
        "input_tokens": 1000,
        "output_tokens": 250,
        "cost_usd": 0.015
    }"#;
    let event: AgentRunEvent = serde_json::from_str(json).expect("deserialize");
    match &event.payload {
        AgentRunEventPayload::TokenUsage {
            input_tokens,
            output_tokens,
            cost_usd,
        } => {
            assert_eq!(*input_tokens, 1000);
            assert_eq!(*output_tokens, 250);
            assert_eq!(*cost_usd, Some(0.015));
        }
        other => panic!("expected TokenUsage, got {other:?}"),
    }
    roundtrip(&event);
}

#[test]
fn agent_run_event_session_end_carries_terminal_outcome() {
    let json = r#"{
        "run_id": "run-1",
        "seq": 42,
        "ts": "2026-07-07T12:05:00Z",
        "type": "session_end",
        "outcome": {"success": false, "summary": "timed out waiting for readiness"}
    }"#;
    let event: AgentRunEvent = serde_json::from_str(json).expect("deserialize");
    assert_eq!(event.seq, 42);
    match &event.payload {
        AgentRunEventPayload::SessionEnd { outcome } => {
            assert!(!outcome.success);
            assert_eq!(outcome.summary, "timed out waiting for readiness");
        }
        other => panic!("expected SessionEnd, got {other:?}"),
    }
    roundtrip(&event);
}

#[test]
fn agent_run_event_rejects_unknown_top_level_field() {
    let json = r#"{
        "run_id": "run-1",
        "seq": 0,
        "ts": "2026-07-07T12:00:00Z",
        "type": "tool_start",
        "tool_name": "Read",
        "not_a_real_field": 1
    }"#;
    let err = serde_json::from_str::<AgentRunEvent>(json).unwrap_err();
    assert!(err.to_string().contains("not_a_real_field"), "err: {err}");
}

#[test]
fn agent_run_event_rejects_unknown_variant_tag() {
    let json = r#"{
        "run_id": "run-1",
        "seq": 0,
        "ts": "2026-07-07T12:00:00Z",
        "type": "not_a_real_event_type"
    }"#;
    let err = serde_json::from_str::<AgentRunEvent>(json).unwrap_err();
    assert!(
        err.to_string().contains("not_a_real_event_type"),
        "err: {err}"
    );
}

#[test]
fn agent_run_event_jsonl_stream_of_four_events_parses_line_by_line() {
    let lines = [
        r#"{"run_id":"r1","seq":0,"ts":"2026-07-07T00:00:00Z","type":"tool_start","tool_name":"Read","tool_input":{}}"#,
        r#"{"run_id":"r1","seq":1,"ts":"2026-07-07T00:00:01Z","type":"tool_end","tool_name":"Read","success":true,"output_summary":null}"#,
        r#"{"run_id":"r1","seq":2,"ts":"2026-07-07T00:00:02Z","type":"token_usage","input_tokens":10,"output_tokens":5,"cost_usd":null}"#,
        r#"{"run_id":"r1","seq":3,"ts":"2026-07-07T00:00:03Z","type":"session_end","outcome":{"success":true,"summary":"done"}}"#,
    ];

    let events: Vec<AgentRunEvent> = lines
        .iter()
        .map(|line| serde_json::from_str(line).expect("each line parses"))
        .collect();

    assert_eq!(events.len(), 4);
    for (i, event) in events.iter().enumerate() {
        assert_eq!(event.seq, i as u64, "seq strictly increasing from 0");
        assert_eq!(event.run_id, "r1");
    }
    assert!(matches!(
        events.last().unwrap().payload,
        AgentRunEventPayload::SessionEnd { .. }
    ));
}

#[test]
fn agent_run_event_result_variant_round_trips_as_an_event() {
    // Fix 4: the final result is delivered as a real AgentRunEvent (with the
    // run_id/seq/ts envelope), so a stdout consumer can parse EVERY line as an
    // AgentRunEvent. This exercises the `result` payload variant.
    let result = AgentRunResult {
        result: AgentRunOutcome {
            success: true,
            summary: "all good".to_string(),
        },
        output_artifacts: vec![PathBuf::from("/tmp/out/report.md")],
        session_log: "pane".to_string(),
        observability: None,
    };
    let event = AgentRunEvent::result("run-1", 11, "2026-07-07T12:00:00Z", result.clone());

    // Envelope fields present + type-tagged as "result".
    let value = serde_json::to_value(&event).unwrap();
    assert_eq!(value["run_id"], "run-1");
    assert_eq!(value["seq"], 11);
    assert_eq!(value["ts"], "2026-07-07T12:00:00Z");
    assert_eq!(value["type"], "result");

    // Round-trips and carries the full result.
    roundtrip(&event);
    match &event.payload {
        AgentRunEventPayload::Result { result: carried } => {
            assert_eq!(**carried, result);
        }
        other => panic!("expected Result payload, got {other:?}"),
    }

    // Every serialized line still parses as an AgentRunEvent (R6 stdout purity).
    let line = serde_json::to_string(&event).unwrap();
    let parsed: AgentRunEvent =
        serde_json::from_str(&line).expect("result line is an AgentRunEvent");
    assert_eq!(parsed, event);
}
