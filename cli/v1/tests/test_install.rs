use assert_cmd::assert::OutputAssertExt;
use predicates::prelude::*;
use std::fs;
use std::process::Command;
use tempfile::TempDir;

#[test]
fn test_install_to_project() {
    let temp_dir = TempDir::new().unwrap();
    let build_dir = temp_dir.path().join("build");
    fs::create_dir(&build_dir).unwrap();
    // Create valid Claude build directory with mcp.json
    fs::write(build_dir.join("mcp.json"), "{}").unwrap();
    fs::write(build_dir.join("test.txt"), "test content").unwrap();

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(temp_dir.path())
        .arg("install")
        .arg("--provider")
        .arg("claude")
        .arg("--build-dir")
        .arg(build_dir.as_os_str());

    cmd.assert().success().stdout(predicate::str::contains(
        "Installation completed successfully",
    ));

    // Verify files were installed
    let install_location = temp_dir.path().join(".claude");
    assert!(install_location.exists());
    assert!(install_location.join("test.txt").exists());
    assert!(install_location.join("mcp.json").exists());
}

#[test]
fn test_install_with_backup() {
    let temp_dir = TempDir::new().unwrap();

    // Create existing installation
    let install_location = temp_dir.path().join(".claude");
    fs::create_dir(&install_location).unwrap();
    fs::write(install_location.join("old.txt"), "old content").unwrap();

    // Create build directory
    let build_dir = temp_dir.path().join("build");
    fs::create_dir(&build_dir).unwrap();
    // Create valid Claude build directory with mcp.json
    fs::write(build_dir.join("mcp.json"), "{}").unwrap();
    fs::write(build_dir.join("new.txt"), "new content").unwrap();

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(temp_dir.path())
        .arg("install")
        .arg("--provider")
        .arg("claude")
        .arg("--build-dir")
        .arg(build_dir.as_os_str())
        .arg("--backup");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Backed up"));

    // Verify backup was created
    let backup_pattern = format!("{}.backup.", install_location.display());
    let entries: Vec<_> = fs::read_dir(temp_dir.path())
        .unwrap()
        .filter_map(Result::ok)
        .filter(|e| e.path().to_string_lossy().contains(&backup_pattern))
        .collect();

    assert!(!entries.is_empty(), "Backup directory should exist");
}

#[test]
fn test_install_dry_run() {
    let temp_dir = TempDir::new().unwrap();
    let build_dir = temp_dir.path().join("build");
    fs::create_dir(&build_dir).unwrap();
    // Create valid Claude build directory with mcp.json
    fs::write(build_dir.join("mcp.json"), "{}").unwrap();
    fs::write(build_dir.join("test.txt"), "test content").unwrap();

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(temp_dir.path())
        .arg("install")
        .arg("--provider")
        .arg("claude")
        .arg("--build-dir")
        .arg(build_dir.as_os_str())
        .arg("--dry-run");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Dry-run complete"));

    // Verify files were NOT installed
    let install_location = temp_dir.path().join(".claude");
    assert!(!install_location.exists());
}

#[test]
fn test_install_without_build() {
    let temp_dir = TempDir::new().unwrap();

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(temp_dir.path())
        .arg("install")
        .arg("--provider")
        .arg("claude");

    cmd.assert()
        .failure()
        .stderr(predicate::str::contains("Build directory not found"));
}

#[test]
fn test_install_empty_build_dir() {
    let temp_dir = TempDir::new().unwrap();
    let build_dir = temp_dir.path().join("build");
    fs::create_dir(&build_dir).unwrap();
    // Create empty build directory - no files

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(temp_dir.path())
        .arg("install")
        .arg("--provider")
        .arg("unknown_provider")
        .arg("--build-dir")
        .arg(build_dir.as_os_str());

    cmd.assert()
        .failure()
        .stderr(predicate::str::contains("empty"));
}

#[test]
fn test_install_preserves_structure() {
    let temp_dir = TempDir::new().unwrap();
    let build_dir = temp_dir.path().join("build");
    fs::create_dir_all(build_dir.join("subdir/nested")).unwrap();
    // Create valid Claude build directory with mcp.json
    fs::write(build_dir.join("mcp.json"), "{}").unwrap();
    fs::write(build_dir.join("file1.txt"), "content1").unwrap();
    fs::write(build_dir.join("subdir/file2.txt"), "content2").unwrap();
    fs::write(build_dir.join("subdir/nested/file3.txt"), "content3").unwrap();

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(temp_dir.path())
        .arg("install")
        .arg("--provider")
        .arg("claude")
        .arg("--build-dir")
        .arg(build_dir.as_os_str());

    cmd.assert().success();

    // Verify directory structure preserved
    let install_location = temp_dir.path().join(".claude");
    assert!(install_location.join("file1.txt").exists());
    assert!(install_location.join("subdir/file2.txt").exists());
    assert!(install_location.join("subdir/nested/file3.txt").exists());
}

#[test]
fn test_install_verbose() {
    let temp_dir = TempDir::new().unwrap();
    let build_dir = temp_dir.path().join("build");
    fs::create_dir(&build_dir).unwrap();
    // Create valid Claude build directory with mcp.json
    fs::write(build_dir.join("mcp.json"), "{}").unwrap();
    fs::write(build_dir.join("test.txt"), "test content").unwrap();

    let mut cmd = Command::new(assert_cmd::cargo::cargo_bin!("agentic-p"));
    cmd.current_dir(temp_dir.path())
        .arg("install")
        .arg("--provider")
        .arg("claude")
        .arg("--build-dir")
        .arg(build_dir.as_os_str())
        .arg("--verbose");

    cmd.assert()
        .success()
        .stdout(predicate::str::contains("Install location"));
}
