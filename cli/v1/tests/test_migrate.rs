//! Integration tests for migrate command

use assert_cmd::assert::OutputAssertExt;
use predicates::prelude::*;
use std::fs;
use std::process::Command;
use tempfile::TempDir;

/// Helper to setup a test primitive with specific spec version
fn setup_primitive(
    tmp_dir: &TempDir,
    id: &str,
    spec_version: &str,
    has_preferred_models: bool,
) -> std::io::Result<()> {
    let primitive_dir = tmp_dir
        .path()
        .join(format!("primitives/{spec_version}/prompts/agents"))
        .join(id);
    fs::create_dir_all(&primitive_dir)?;

    let mut meta_yaml = format!(
        r#"spec_version: {spec_version}
id: {id}
kind: agent
category: test
domain: testing
summary: "Test agent for migration"
context_usage:
  as_system: true
"#
    );

    if has_preferred_models {
        meta_yaml.push_str(
            r#"defaults:
  preferred_models:
    - "claude/sonnet"
    - "openai/gpt-codex"
"#,
        );
    }

    fs::write(primitive_dir.join("meta.yaml"), meta_yaml)?;

    // Create content file
    fs::write(
        primitive_dir.join(format!("{id}.prompt.md")),
        "# Test content",
    )?;

    Ok(())
}

/// Helper to create primitives.config.yaml
fn setup_config(tmp_dir: &TempDir) -> std::io::Result<()> {
    let config = r#"primitives:
  - primitives/v1
  - primitives/v2
  - primitives/experimental
hooks:
  - hooks
tools:
  - tools
"#;
    fs::write(tmp_dir.path().join("primitives.config.yaml"), config)?;
    Ok(())
}

#[test]
fn test_migrate_dry_run() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_primitive(&tmp_dir, "test-agent", "v1", true).unwrap();

    let primitive_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent");

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(tmp_dir.path())
        .arg("migrate")
        .arg(&primitive_path)
        .arg("--to-spec")
        .arg("v2")
        .arg("--dry-run");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Migration Plan"))
        .stdout(predicate::str::contains("v1"))
        .stdout(predicate::str::contains("v2"))
        .stdout(predicate::str::contains("spec_version"))
        .stdout(predicate::str::contains(
            "Run without --dry-run to apply changes",
        ));

    // Verify no changes were made
    let meta_path = primitive_path.join("meta.yaml");
    let meta_content = fs::read_to_string(meta_path).unwrap();
    assert!(meta_content.contains("spec_version: v1"));
}

#[test]
fn test_migrate_v1_to_v2() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_primitive(&tmp_dir, "test-agent", "v1", true).unwrap();

    let primitive_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent");

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(tmp_dir.path())
        .arg("migrate")
        .arg(&primitive_path)
        .arg("--to-spec")
        .arg("v2");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Migration complete"));

    // Verify spec_version was updated
    let meta_path = primitive_path.join("meta.yaml");
    let meta_content = fs::read_to_string(meta_path).unwrap();
    assert!(meta_content.contains("spec_version: v2"));

    // Verify field rename
    assert!(meta_content.contains("model_preferences"));
    assert!(!meta_content.contains("preferred_models"));
}

#[test]
fn test_migrate_v1_to_v2_auto_fix() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_primitive(&tmp_dir, "test-agent", "v1", false).unwrap();

    let primitive_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent");

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(tmp_dir.path())
        .arg("migrate")
        .arg(&primitive_path)
        .arg("--to-spec")
        .arg("v2")
        .arg("--auto-fix");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Migration complete"));

    // Verify compatibility field was added
    let meta_path = primitive_path.join("meta.yaml");
    let meta_content = fs::read_to_string(meta_path).unwrap();
    assert!(meta_content.contains("compatibility"));
}

#[test]
fn test_migrate_to_experimental() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_primitive(&tmp_dir, "test-agent", "v1", false).unwrap();

    let primitive_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent");

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(tmp_dir.path())
        .arg("migrate")
        .arg(&primitive_path)
        .arg("--to-spec")
        .arg("experimental");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Migration complete"));

    // Verify primitive was moved to experimental
    let new_path = tmp_dir
        .path()
        .join("primitives/experimental/prompts/agents/test-agent");
    assert!(new_path.exists());

    // Old path should not exist
    assert!(!primitive_path.exists());

    // Verify spec_version was updated
    let meta_path = new_path.join("meta.yaml");
    let meta_content = fs::read_to_string(meta_path).unwrap();
    assert!(meta_content.contains("spec_version: experimental"));
}

#[test]
fn test_migrate_directory() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_primitive(&tmp_dir, "test-agent-1", "v1", false).unwrap();
    setup_primitive(&tmp_dir, "test-agent-2", "v1", false).unwrap();

    let primitives_dir = tmp_dir.path().join("primitives/v1/prompts/agents");

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(tmp_dir.path())
        .arg("migrate")
        .arg(&primitives_dir)
        .arg("--to-spec")
        .arg("v2");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("2 primitive(s)"))
        .stdout(predicate::str::contains("Migration complete"));

    // Verify both were migrated
    let meta1_path = primitives_dir.join("test-agent-1/meta.yaml");
    let meta1_content = fs::read_to_string(meta1_path).unwrap();
    assert!(meta1_content.contains("spec_version: v2"));

    let meta2_path = primitives_dir.join("test-agent-2/meta.yaml");
    let meta2_content = fs::read_to_string(meta2_path).unwrap();
    assert!(meta2_content.contains("spec_version: v2"));
}

#[test]
fn test_migrate_same_version_no_changes() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_primitive(&tmp_dir, "test-agent", "v1", false).unwrap();

    let primitive_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent");

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(tmp_dir.path())
        .arg("migrate")
        .arg(&primitive_path)
        .arg("--to-spec")
        .arg("v1");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Migration complete"));
}

#[test]
fn test_migrate_invalid_spec() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_primitive(&tmp_dir, "test-agent", "v1", false).unwrap();

    let primitive_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent");

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(tmp_dir.path())
        .arg("migrate")
        .arg(&primitive_path)
        .arg("--to-spec")
        .arg("v99");

    cmd.assert()
        .failure()
        .stderr(predicate::str::contains("Unknown spec version"));
}

#[test]
fn test_migrate_nonexistent_path() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(tmp_dir.path())
        .arg("migrate")
        .arg("nonexistent/path")
        .arg("--to-spec")
        .arg("v2");

    cmd.assert()
        .failure()
        .stderr(predicate::str::contains("does not exist"));
}

#[test]
fn test_migrate_experimental_to_v2() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();

    // Create experimental primitive
    let primitive_dir = tmp_dir
        .path()
        .join("primitives/experimental/prompts/agents/test-agent");
    fs::create_dir_all(&primitive_dir).unwrap();

    let meta_yaml = r#"spec_version: experimental
id: test-agent
kind: agent
category: test
domain: testing
summary: "Experimental agent"
context_usage:
  as_system: true
"#;
    fs::write(primitive_dir.join("meta.yaml"), meta_yaml).unwrap();
    fs::write(primitive_dir.join("test-agent.prompt.md"), "# Test").unwrap();

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(tmp_dir.path())
        .arg("migrate")
        .arg(&primitive_dir)
        .arg("--to-spec")
        .arg("v2");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Migration complete"));

    // Verify spec_version was updated
    let meta_path = primitive_dir.join("meta.yaml");
    let meta_content = fs::read_to_string(meta_path).unwrap();
    assert!(meta_content.contains("spec_version: v2"));
}

#[test]
fn test_migrate_shows_summary() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_primitive(&tmp_dir, "test-agent", "v1", true).unwrap();

    let primitive_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent");

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(tmp_dir.path())
        .arg("migrate")
        .arg(&primitive_path)
        .arg("--to-spec")
        .arg("v2");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Migration Results"))
        .stdout(predicate::str::contains("test-agent"))
        .stdout(predicate::str::contains("From"))
        .stdout(predicate::str::contains("To"))
        .stdout(predicate::str::contains("Status"));
}

#[test]
fn test_migrate_dry_run_shows_planned_changes() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_primitive(&tmp_dir, "test-agent", "v1", true).unwrap();

    let primitive_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent");

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(tmp_dir.path())
        .arg("migrate")
        .arg(&primitive_path)
        .arg("--to-spec")
        .arg("v2")
        .arg("--dry-run");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Planned Changes"))
        .stdout(predicate::str::contains("test-agent"))
        .stdout(predicate::str::contains("spec_version"))
        .stdout(predicate::str::contains("preferred_models"));
}

#[test]
fn test_migrate_missing_meta_yaml() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();

    // Create directory without meta.yaml
    let primitive_dir = tmp_dir.path().join("primitives/v1/prompts/agents/invalid");
    fs::create_dir_all(&primitive_dir).unwrap();

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(tmp_dir.path())
        .arg("migrate")
        .arg(&primitive_dir)
        .arg("--to-spec")
        .arg("v2");

    // Should show error but not crash
    cmd.assert()
        .failure()
        .stdout(predicate::str::contains("migration(s) failed"));
}

#[test]
fn test_migrate_v1_to_v2_field_rename() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_primitive(&tmp_dir, "test-agent", "v1", true).unwrap();

    let primitive_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent");

    // Read original content
    let meta_path = primitive_path.join("meta.yaml");
    let original_content = fs::read_to_string(&meta_path).unwrap();
    assert!(original_content.contains("preferred_models"));

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(tmp_dir.path())
        .arg("migrate")
        .arg(&primitive_path)
        .arg("--to-spec")
        .arg("v2");

    cmd.assert().success();

    // Verify field was renamed
    let migrated_content = fs::read_to_string(&meta_path).unwrap();
    assert!(!migrated_content.contains("preferred_models"));
    assert!(migrated_content.contains("model_preferences"));

    // Verify the values were preserved
    assert!(migrated_content.contains("claude/sonnet"));
    assert!(migrated_content.contains("openai/gpt-codex"));
}
