//! Integration tests for the build command

#[allow(deprecated)]
use assert_cmd::Command;
use predicates::prelude::*;
use std::fs;
use std::path::{Path, PathBuf};
use tempfile::TempDir;

/// Helper to create a minimal test primitive directory structure
fn create_test_primitives_dir(temp_dir: &TempDir) -> PathBuf {
    let primitives_dir = temp_dir.path().join("primitives/v1");
    fs::create_dir_all(&primitives_dir).unwrap();

    // Create a test agent prompt
    let agent_dir = primitives_dir.join("prompts/agents/test-agent");
    fs::create_dir_all(&agent_dir).unwrap();

    // Create meta.yaml
    let meta_content = r#"
spec_version: v1
id: test-agent
kind: agent
domain: test
category: testing
summary: A test agent
tags:
  - test
defaults:
  preferred_models: []
  temperature: 0.7
  max_tokens: 2000
versions:
  - version: 1
    file: test-agent.prompt.md
    status: active
    hash: abc123def456
    created: "2024-01-01"
    notes: Test agent version 1
default_version: 1
"#;
    fs::write(agent_dir.join("meta.yaml"), meta_content).unwrap();

    // Create prompt content
    let prompt_content = "You are a test agent.";
    fs::write(agent_dir.join("test-agent.prompt.md"), prompt_content).unwrap();

    // Create a test command prompt
    let command_dir = primitives_dir.join("prompts/commands/test-command");
    fs::create_dir_all(&command_dir).unwrap();

    let command_meta = r#"
spec_version: v1
id: test-command
kind: command
domain: test
category: testing
summary: A test command
tags:
  - test
defaults:
  preferred_models: []
  temperature: 0.7
  max_tokens: 2000
versions:
  - version: 1
    file: test-command.prompt.md
    status: active
    hash: xyz789uvw012
    created: "2024-01-01"
    notes: Test command version 1
default_version: 1
"#;
    fs::write(command_dir.join("meta.yaml"), command_meta).unwrap();
    fs::write(command_dir.join("test-command.prompt.md"), "Test command").unwrap();

    // Create a test tool
    let tool_dir = primitives_dir.join("tools/utilities/test-tool");
    fs::create_dir_all(&tool_dir).unwrap();

    let tool_meta = r#"
id: test-tool
kind: tool
category: utilities
description: A test tool
args:
  - name: input
    type: string
    description: Test input
    required: true
"#;
    fs::write(tool_dir.join("tool.meta.yaml"), tool_meta).unwrap();

    primitives_dir
}

/// Helper to create a test config file
fn create_test_config(temp_dir: &TempDir, primitives_dir: &Path) {
    let config_content = format!(
        r#"
spec_version: v1
repository:
  name: test-repo
  description: Test repository
paths:
  primitives: {}
defaults:
  prompt_defaults:
    temperature: 0.7
    max_tokens: 2000
"#,
        primitives_dir.to_string_lossy()
    );

    fs::write(
        temp_dir.path().join("primitives.config.yaml"),
        config_content,
    )
    .unwrap();
}

#[test]
fn test_build_claude_all_primitives() {
    let temp_dir = TempDir::new().unwrap();
    let primitives_dir = create_test_primitives_dir(&temp_dir);
    create_test_config(&temp_dir, &primitives_dir);

    let output_dir = temp_dir.path().join("build/claude");

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(temp_dir.path())
        .arg("build")
        .arg("--provider")
        .arg("claude")
        .arg("--output")
        .arg(output_dir.to_str().unwrap())
        .arg("--verbose");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Build Summary"))
        .stdout(predicate::str::contains("claude"));

    // Verify output directory was created
    assert!(output_dir.exists());
}

#[test]
fn test_build_openai_all_primitives() {
    let temp_dir = TempDir::new().unwrap();
    let primitives_dir = create_test_primitives_dir(&temp_dir);
    create_test_config(&temp_dir, &primitives_dir);

    let output_dir = temp_dir.path().join("build/openai");

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(temp_dir.path())
        .arg("build")
        .arg("--provider")
        .arg("openai")
        .arg("--output")
        .arg(output_dir.to_str().unwrap())
        .arg("--verbose");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Build Summary"))
        .stdout(predicate::str::contains("openai"));

    // Verify output directory was created
    assert!(output_dir.exists());
}

#[test]
fn test_build_single_primitive() {
    let temp_dir = TempDir::new().unwrap();
    let primitives_dir = create_test_primitives_dir(&temp_dir);
    create_test_config(&temp_dir, &primitives_dir);

    let primitive_path = primitives_dir.join("prompts/agents/test-agent");
    let output_dir = temp_dir.path().join("build/claude");

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(temp_dir.path())
        .arg("build")
        .arg("--provider")
        .arg("claude")
        .arg("--output")
        .arg(output_dir.to_str().unwrap())
        .arg("--primitive")
        .arg(primitive_path.to_str().unwrap());

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Build Summary"))
        .stdout(predicate::str::contains("Primitives:   1"));
}

#[test]
fn test_build_with_type_filter() {
    let temp_dir = TempDir::new().unwrap();
    let primitives_dir = create_test_primitives_dir(&temp_dir);
    create_test_config(&temp_dir, &primitives_dir);

    let output_dir = temp_dir.path().join("build/claude");

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(temp_dir.path())
        .arg("build")
        .arg("--provider")
        .arg("claude")
        .arg("--output")
        .arg(output_dir.to_str().unwrap())
        .arg("--type-filter")
        .arg("prompt")
        .arg("--verbose");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Build Summary"));
}

#[test]
fn test_build_with_kind_filter() {
    let temp_dir = TempDir::new().unwrap();
    let primitives_dir = create_test_primitives_dir(&temp_dir);
    create_test_config(&temp_dir, &primitives_dir);

    let output_dir = temp_dir.path().join("build/claude");

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(temp_dir.path())
        .arg("build")
        .arg("--provider")
        .arg("claude")
        .arg("--output")
        .arg(output_dir.to_str().unwrap())
        .arg("--kind")
        .arg("agent")
        .arg("--verbose");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Build Summary"));
}

#[test]
fn test_build_unknown_provider() {
    let temp_dir = TempDir::new().unwrap();
    let primitives_dir = create_test_primitives_dir(&temp_dir);
    create_test_config(&temp_dir, &primitives_dir);

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(temp_dir.path())
        .arg("build")
        .arg("--provider")
        .arg("unknown");

    cmd.assert()
        .failure()
        .stderr(predicate::str::contains("Unknown provider"));
}

#[test]
fn test_build_clean_mode() {
    let temp_dir = TempDir::new().unwrap();
    let primitives_dir = create_test_primitives_dir(&temp_dir);
    create_test_config(&temp_dir, &primitives_dir);

    let output_dir = temp_dir.path().join("build/claude");
    fs::create_dir_all(&output_dir).unwrap();

    // Create a dummy file in output dir
    let dummy_file = output_dir.join("old-file.txt");
    fs::write(&dummy_file, "old content").unwrap();
    assert!(dummy_file.exists());

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(temp_dir.path())
        .arg("build")
        .arg("--provider")
        .arg("claude")
        .arg("--output")
        .arg(output_dir.to_str().unwrap())
        .arg("--clean");

    cmd.assert().success();

    // Verify old file was removed
    assert!(!dummy_file.exists());
}

#[test]
fn test_build_custom_output() {
    let temp_dir = TempDir::new().unwrap();
    let primitives_dir = create_test_primitives_dir(&temp_dir);
    create_test_config(&temp_dir, &primitives_dir);

    let custom_output_dir = temp_dir.path().join("custom/output/path");

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(temp_dir.path())
        .arg("build")
        .arg("--provider")
        .arg("claude")
        .arg("--output")
        .arg(custom_output_dir.to_str().unwrap());

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("custom/output/path"));

    // Verify custom output directory was created
    assert!(custom_output_dir.exists());
}

#[test]
fn test_build_default_output_path() {
    let temp_dir = TempDir::new().unwrap();
    let primitives_dir = create_test_primitives_dir(&temp_dir);
    create_test_config(&temp_dir, &primitives_dir);

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(temp_dir.path())
        .arg("build")
        .arg("--provider")
        .arg("claude");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("./build/claude"));

    // Verify default output directory was created
    let default_output = temp_dir.path().join("build/claude");
    assert!(default_output.exists());
}

#[test]
fn test_build_nonexistent_primitive() {
    let temp_dir = TempDir::new().unwrap();
    let primitives_dir = create_test_primitives_dir(&temp_dir);
    create_test_config(&temp_dir, &primitives_dir);

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(temp_dir.path())
        .arg("build")
        .arg("--provider")
        .arg("claude")
        .arg("--primitive")
        .arg("/nonexistent/path");

    cmd.assert()
        .failure()
        .stderr(predicate::str::contains("Primitive not found"));
}

#[test]
fn test_build_invalid_type_filter() {
    let temp_dir = TempDir::new().unwrap();
    let primitives_dir = create_test_primitives_dir(&temp_dir);
    create_test_config(&temp_dir, &primitives_dir);

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(temp_dir.path())
        .arg("build")
        .arg("--provider")
        .arg("claude")
        .arg("--type-filter")
        .arg("invalid");

    cmd.assert()
        .failure()
        .stderr(predicate::str::contains("Invalid type filter"));
}
