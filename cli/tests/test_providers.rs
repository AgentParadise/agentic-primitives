mod e2e;

use e2e::{run_cli_command, setup_test_repo};
use predicates::prelude::*;
use std::fs;

#[test]
fn test_provider_transformations() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();

    // Create test primitives using v2 CLI commands
    run_cli_command(
        &[
            "new",
            "command",
            "testing",
            "provider-test-command",
            "--description",
            "A test command",
            "--model",
            "sonnet",
            "--non-interactive",
        ],
        Some(repo_path),
    )
    .success();

    run_cli_command(
        &[
            "new",
            "skill",
            "testing",
            "provider-test-skill",
            "--description",
            "A test skill",
            "--model",
            "sonnet",
            "--non-interactive",
        ],
        Some(repo_path),
    )
    .success();

    // Build for Claude (v2 primitives)
    run_cli_command(
        &[
            "build",
            "--provider",
            "claude",
            "--verbose",
            "--primitives-version",
            "v2",
        ],
        Some(repo_path),
    )
    .success()
    .stdout(predicate::str::contains("Transforming:"));

    // Verify Claude output structure
    let claude_build = repo_path.join("build/claude");
    assert!(claude_build.exists());

    let has_claude_structure = claude_build.join(".claude").exists()
        || claude_build.join("system.md").exists()
        || claude_build.join("commands").exists();

    if !has_claude_structure {
        let entries: Vec<_> = fs::read_dir(&claude_build).unwrap().collect();
        assert!(
            !entries.is_empty(),
            "Claude build directory should contain files"
        );
    }
}

#[test]
fn test_provider_filtering() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();

    run_cli_command(
        &[
            "new",
            "command",
            "testing",
            "filter-test-command",
            "--description",
            "A test command",
            "--model",
            "sonnet",
            "--non-interactive",
        ],
        Some(repo_path),
    )
    .success();

    run_cli_command(
        &[
            "new",
            "tool",
            "testing",
            "filter-test-tool",
            "--description",
            "A test tool",
            "--model",
            "sonnet",
            "--non-interactive",
        ],
        Some(repo_path),
    )
    .success();

    // Build only prompts for Claude (v2)
    run_cli_command(
        &[
            "build",
            "--provider",
            "claude",
            "--type-filter",
            "prompt",
            "--primitives-version",
            "v2",
        ],
        Some(repo_path),
    )
    .success();
}
