//! Integration tests for version command

use assert_cmd::Command;
use predicates::prelude::*;
use std::fs;
use tempfile::TempDir;

/// Helper to setup a test primitive with versioning
fn setup_versioned_primitive(
    tmp_dir: &TempDir,
    id: &str,
    versions: &[(u32, &str)],
) -> std::io::Result<()> {
    let primitive_dir = tmp_dir.path().join("primitives/v1/prompts/agents").join(id);
    fs::create_dir_all(&primitive_dir)?;

    // Create meta.yaml
    let mut meta_yaml = format!(
        r#"spec_version: v1
id: {id}
kind: agent
category: test
domain: testing
summary: "Test agent for versioning"
context_usage:
  as_system: true
versions:
"#
    );

    for (version, notes) in versions {
        let file = format!("{id}.v{version}.md");
        let hash = format!("blake3:{version:0>64}"); // Dummy hash

        meta_yaml.push_str(&format!(
            r#"  - version: {version}
    file: "{file}"
    status: "draft"
    hash: "{hash}"
    created: "2025-11-13"
    notes: "{notes}"
"#
        ));

        // Create version file
        let content_path = primitive_dir.join(&file);
        fs::write(
            content_path,
            format!("# Version {version}\n\nContent for version {version}"),
        )?;
    }

    if let Some((version, _)) = versions.first() {
        meta_yaml.push_str(&format!("default_version: {version}\n"));
    }

    fs::write(primitive_dir.join("meta.yaml"), meta_yaml)?;

    Ok(())
}

/// Helper to create primitives.config.yaml
fn setup_config(tmp_dir: &TempDir) -> std::io::Result<()> {
    let config = r#"version: "1.0"
paths:
  specs: "specs/v1"
  primitives: "primitives/v1"
  experimental: "primitives/experimental"
  providers: "providers"
  cli: "cli"
  docs: "docs"
validation:
  max_summary_length: 500
"#;
    fs::write(tmp_dir.path().join("primitives.config.yaml"), config)?;
    Ok(())
}

#[test]
fn test_version_list_displays_versions() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_versioned_primitive(
        &tmp_dir,
        "test-agent",
        &[(1, "Initial version"), (2, "Updated version")],
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(tmp_dir.path())
        .arg("version")
        .arg("list")
        .arg("test-agent");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Versions for test-agent"))
        .stdout(predicate::str::contains("v1"))
        .stdout(predicate::str::contains("v2"))
        .stdout(predicate::str::contains("Initial version"))
        .stdout(predicate::str::contains("Updated version"));
}

#[test]
fn test_version_list_no_versions() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();

    // Create primitive without versions
    let primitive_dir = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/no-versions");
    fs::create_dir_all(&primitive_dir).unwrap();

    let meta_yaml = r#"spec_version: v1
id: no-versions
kind: agent
category: test
domain: testing
summary: "Test agent without versioning"
versions: []
"#;
    fs::write(primitive_dir.join("meta.yaml"), meta_yaml).unwrap();

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(tmp_dir.path())
        .arg("version")
        .arg("list")
        .arg("no-versions");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("No versions found"));
}

#[test]
fn test_version_bump_creates_new_version() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_versioned_primitive(&tmp_dir, "test-agent", &[(1, "Initial version")]).unwrap();

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(tmp_dir.path())
        .arg("version")
        .arg("bump")
        .arg("test-agent")
        .arg("--notes")
        .arg("Added new features");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Created version 2"))
        .stdout(predicate::str::contains("Copied"))
        .stdout(predicate::str::contains("Calculated hash"));

    // Verify v2 file was created
    let v2_file = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent/test-agent.prompt.v2.md");
    assert!(v2_file.exists());

    // Verify meta.yaml was updated
    let meta_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent/meta.yaml");
    let meta_content = fs::read_to_string(meta_path).unwrap();
    assert!(meta_content.contains("version: 2"));
    assert!(meta_content.contains("Added new features"));
}

#[test]
fn test_version_bump_with_set_default() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_versioned_primitive(&tmp_dir, "test-agent", &[(1, "Initial version")]).unwrap();

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(tmp_dir.path())
        .arg("version")
        .arg("bump")
        .arg("test-agent")
        .arg("--notes")
        .arg("New default version")
        .arg("--set-default");

    cmd.assert().success();

    // Verify default_version was updated in meta.yaml
    let meta_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent/meta.yaml");
    let meta_content = fs::read_to_string(meta_path).unwrap();
    assert!(meta_content.contains("default_version: 2"));
}

#[test]
fn test_version_promote_changes_status() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_versioned_primitive(
        &tmp_dir,
        "test-agent",
        &[(1, "Initial"), (2, "Draft version")],
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(tmp_dir.path())
        .arg("version")
        .arg("promote")
        .arg("test-agent")
        .arg("2");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Promoted version 2 to active"));

    // Verify status changed in meta.yaml
    let meta_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent/meta.yaml");
    let meta_content = fs::read_to_string(meta_path).unwrap();

    // Parse and check that version 2 has status: active
    assert!(meta_content.contains("version: 2"));
    let version_2_section = meta_content
        .split("version: 2")
        .nth(1)
        .unwrap()
        .split("version:")
        .next()
        .unwrap();
    assert!(
        version_2_section.contains("status: \"active\"")
            || version_2_section.contains("status: active")
    );
}

#[test]
fn test_version_promote_with_set_default() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_versioned_primitive(&tmp_dir, "test-agent", &[(1, "Initial"), (2, "Draft")]).unwrap();

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(tmp_dir.path())
        .arg("version")
        .arg("promote")
        .arg("test-agent")
        .arg("2")
        .arg("--set-default");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Promoted version 2"));

    let meta_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent/meta.yaml");
    let meta_content = fs::read_to_string(meta_path).unwrap();
    assert!(meta_content.contains("default_version: 2"));
}

#[test]
fn test_version_deprecate() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_versioned_primitive(
        &tmp_dir,
        "test-agent",
        &[(1, "Old version"), (2, "Current")],
    )
    .unwrap();

    // First promote version 2 to active
    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(tmp_dir.path())
        .arg("version")
        .arg("promote")
        .arg("test-agent")
        .arg("2");
    cmd.assert().success();

    // Now deprecate version 1
    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(tmp_dir.path())
        .arg("version")
        .arg("deprecate")
        .arg("test-agent")
        .arg("1")
        .arg("--reason")
        .arg("Superseded by v2");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Deprecated version 1"));

    // Verify status changed
    let meta_path = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent/meta.yaml");
    let meta_content = fs::read_to_string(meta_path).unwrap();

    let version_1_section = meta_content
        .split("version: 1")
        .nth(1)
        .unwrap()
        .split("version:")
        .next()
        .unwrap();
    assert!(
        version_1_section.contains("status: \"deprecated\"")
            || version_1_section.contains("status: deprecated")
    );
    assert!(version_1_section.contains("Superseded by v2"));
}

#[test]
fn test_version_check_valid_hashes() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();

    // Create primitive with correct hash
    let primitive_dir = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent");
    fs::create_dir_all(&primitive_dir).unwrap();

    let content = "# Version 1\n\nTest content";
    let content_path = primitive_dir.join("test-agent.prompt.v1.md");
    fs::write(&content_path, content).unwrap();

    // Calculate actual hash
    use blake3::Hasher;
    let mut hasher = Hasher::new();
    hasher.update(content.as_bytes());
    let hash = format!("blake3:{}", hasher.finalize().to_hex());

    let meta_yaml = format!(
        r#"spec_version: v1
id: test-agent
kind: agent
category: test
domain: testing
summary: "Test agent"
versions:
  - version: 1
    file: "test-agent.prompt.v1.md"
    status: "active"
    hash: "{hash}"
    created: "2025-11-13"
    notes: "Test version"
"#
    );
    fs::write(primitive_dir.join("meta.yaml"), meta_yaml).unwrap();

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(tmp_dir.path()).arg("version").arg("check");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("valid"))
        .stdout(predicate::str::contains("test-agent v1"));
}

#[test]
fn test_version_check_detects_mismatch() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();

    let primitive_dir = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent");
    fs::create_dir_all(&primitive_dir).unwrap();

    // Write content
    let content_path = primitive_dir.join("test-agent.prompt.v1.md");
    fs::write(&content_path, "# Modified content").unwrap();

    // Use a different hash (intentionally wrong)
    let wrong_hash = "blake3:0000000000000000000000000000000000000000000000000000000000000000";

    let meta_yaml = format!(
        r#"spec_version: v1
id: test-agent
kind: agent
category: test
domain: testing
summary: "Test agent"
versions:
  - version: 1
    file: "test-agent.prompt.v1.md"
    status: "active"
    hash: "{wrong_hash}"
    created: "2025-11-13"
    notes: "Test version"
"#
    );
    fs::write(primitive_dir.join("meta.yaml"), meta_yaml).unwrap();

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(tmp_dir.path()).arg("version").arg("check");

    cmd.assert()
        .failure()
        .stdout(predicate::str::contains("HASH MISMATCH"))
        .stdout(predicate::str::contains("Expected"))
        .stdout(predicate::str::contains("Got"));
}

#[test]
fn test_version_check_specific_primitive() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_versioned_primitive(&tmp_dir, "test-agent", &[(1, "Version 1")]).unwrap();

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(tmp_dir.path())
        .arg("version")
        .arg("check")
        .arg("test-agent");

    // Will fail because the hash in setup is a dummy hash
    cmd.assert()
        .failure()
        .stdout(predicate::str::contains("test-agent"));
}

#[test]
fn test_version_bump_from_unversioned() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();

    // Create unversioned primitive
    let primitive_dir = tmp_dir
        .path()
        .join("primitives/v1/prompts/agents/test-agent");
    fs::create_dir_all(&primitive_dir).unwrap();

    let meta_yaml = r#"spec_version: v1
id: test-agent
kind: agent
category: test
domain: testing
summary: "Test agent"
versions: []
"#;
    fs::write(primitive_dir.join("meta.yaml"), meta_yaml).unwrap();

    // Create unversioned content file
    fs::write(
        primitive_dir.join("test-agent.prompt.md"),
        "# Unversioned content",
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(tmp_dir.path())
        .arg("version")
        .arg("bump")
        .arg("test-agent")
        .arg("--notes")
        .arg("First versioned release");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Created version 1"));

    // Verify v1 file was created
    let v1_file = primitive_dir.join("test-agent.prompt.v1.md");
    assert!(v1_file.exists());
}

#[test]
fn test_version_promote_version_not_found() {
    let tmp_dir = TempDir::new().unwrap();
    setup_config(&tmp_dir).unwrap();
    setup_versioned_primitive(&tmp_dir, "test-agent", &[(1, "Version 1")]).unwrap();

    let mut cmd = Command::cargo_bin("agentic-p").unwrap();
    cmd.current_dir(tmp_dir.path())
        .arg("version")
        .arg("promote")
        .arg("test-agent")
        .arg("99");

    cmd.assert()
        .failure()
        .stderr(predicate::str::contains("Version 99 not found"));
}
