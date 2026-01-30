use assert_cmd::assert::OutputAssertExt;
use predicates::prelude::*;
use std::fs;
use std::process::Command;
use tempfile::TempDir;

fn setup_test_hook(temp_dir: &TempDir, hook_id: &str, event: &str) -> std::path::PathBuf {
    let hook_dir = temp_dir.path().join(hook_id);
    fs::create_dir_all(&hook_dir).unwrap();

    // Create hook metadata
    let meta_content = format!(
        r#"id: {hook_id}
kind: hook
category: safety
event: {event}
summary: Test hook for integration tests

execution:
  strategy: pipeline
  timeout_sec: 5
"#
    );

    fs::write(hook_dir.join(format!("{hook_id}.hook.yaml")), meta_content).unwrap();

    // Create simple Python implementation
    let impl_content = r#"#!/usr/bin/env python3
import json
import sys

# Read input
hook_input = json.load(sys.stdin)

# Simple decision logic
tool_name = hook_input.get("tool_name", "")
tool_input = hook_input.get("tool_input", {})
command = tool_input.get("command", "")

decision = "allow"
reason = "All checks passed"

if "rm -rf" in command:
    decision = "block"
    reason = "Dangerous command detected: rm -rf"

output = {
    "decision": decision,
    "reason": reason,
    "middleware_results": [
        {
            "id": "test-middleware",
            "type": "safety",
            "decision": decision,
            "reason": reason,
            "metrics": {}
        }
    ],
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "metrics": {"checks_run": 1}
    }
}

print(json.dumps(output))
sys.exit(2 if decision == "block" else 0)
"#;

    fs::write(hook_dir.join("impl.python.py"), impl_content).unwrap();

    hook_dir
}

#[test]
fn test_hook_with_passing_test_case() {
    let temp_dir = TempDir::new().unwrap();
    let hook_dir = setup_test_hook(&temp_dir, "test-hook", "PreToolUse");

    let input_file = temp_dir.path().join("test-input.json");
    fs::write(
        &input_file,
        r#"{"tool_name":"Bash","tool_input":{"command":"ls -la"}}"#,
    )
    .unwrap();

    Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"))
        .arg("test-hook")
        .arg(hook_dir.to_str().unwrap())
        .arg("--input")
        .arg(input_file.to_str().unwrap())
        .assert()
        .success()
        .stdout(predicate::str::contains("Decision: ✓ ALLOW"));
}

#[test]
fn test_hook_with_blocking_test_case() {
    let temp_dir = TempDir::new().unwrap();
    let hook_dir = setup_test_hook(&temp_dir, "test-hook", "PreToolUse");

    let input_file = temp_dir.path().join("test-input.json");
    fs::write(
        &input_file,
        r#"{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}"#,
    )
    .unwrap();

    Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"))
        .arg("test-hook")
        .arg(hook_dir.to_str().unwrap())
        .arg("--input")
        .arg(input_file.to_str().unwrap())
        .assert()
        .code(2)
        .stdout(predicate::str::contains("Decision: ✗ BLOCK"))
        .stdout(predicate::str::contains("Dangerous command detected"));
}

#[test]
fn test_hook_with_inline_json() {
    let temp_dir = TempDir::new().unwrap();
    let hook_dir = setup_test_hook(&temp_dir, "test-hook", "PreToolUse");

    Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"))
        .arg("test-hook")
        .arg(hook_dir.to_str().unwrap())
        .arg("--input")
        .arg(r#"{"tool_name":"Bash","tool_input":{"command":"echo hello"}}"#)
        .assert()
        .success()
        .stdout(predicate::str::contains("Decision: ✓ ALLOW"));
}

#[test]
fn test_hook_json_output_mode() {
    let temp_dir = TempDir::new().unwrap();
    let hook_dir = setup_test_hook(&temp_dir, "test-hook", "PreToolUse");

    let input_file = temp_dir.path().join("test-input.json");
    fs::write(
        &input_file,
        r#"{"tool_name":"Bash","tool_input":{"command":"ls"}}"#,
    )
    .unwrap();

    Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"))
        .arg("test-hook")
        .arg(hook_dir.to_str().unwrap())
        .arg("--input")
        .arg(input_file.to_str().unwrap())
        .arg("--json")
        .assert()
        .success()
        .stdout(predicate::str::contains(r#""decision": "allow""#))
        .stdout(predicate::str::contains(r#""hook_id": "test-hook""#));
}

#[test]
fn test_hook_verbose_mode() {
    let temp_dir = TempDir::new().unwrap();
    let hook_dir = setup_test_hook(&temp_dir, "test-hook", "PreToolUse");

    let input_file = temp_dir.path().join("test-input.json");
    fs::write(
        &input_file,
        r#"{"tool_name":"Bash","tool_input":{"command":"ls"}}"#,
    )
    .unwrap();

    Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"))
        .arg("test-hook")
        .arg(hook_dir.to_str().unwrap())
        .arg("--input")
        .arg(input_file.to_str().unwrap())
        .arg("--verbose")
        .assert()
        .success()
        .stderr(predicate::str::contains("Hook:"))
        .stderr(predicate::str::contains("Implementation:"));
}

#[test]
fn test_hook_missing_implementation() {
    let temp_dir = TempDir::new().unwrap();
    let hook_dir = temp_dir.path().join("missing-impl-hook");
    fs::create_dir_all(&hook_dir).unwrap();

    let meta_content = r#"id: missing-impl-hook
kind: hook
category: safety
event: PreToolUse
summary: Hook without implementation

execution:
  strategy: pipeline
"#;

    fs::write(hook_dir.join("missing-impl-hook.hook.yaml"), meta_content).unwrap();

    Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"))
        .arg("test-hook")
        .arg(hook_dir.to_str().unwrap())
        .arg("--input")
        .arg(r#"{"tool_name":"Bash"}"#)
        .assert()
        .failure()
        .stderr(predicate::str::contains("No implementation file found"));
}

#[test]
fn test_hook_malformed_input_json() {
    let temp_dir = TempDir::new().unwrap();
    let hook_dir = setup_test_hook(&temp_dir, "test-hook", "PreToolUse");

    Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"))
        .arg("test-hook")
        .arg(hook_dir.to_str().unwrap())
        .arg("--input")
        .arg(r#"{"invalid json"#)
        .assert()
        .failure()
        .stderr(predicate::str::contains("Failed to parse"));
}
