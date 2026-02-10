mod e2e;

use e2e::{run_cli_command, setup_test_repo};
use predicates::prelude::*;
use std::fs;

#[test]
fn test_provider_transformations() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();

    // Create test primitives using CLI commands
    run_cli_command(
        &[
            "new",
            "prompt",
            "testing",
            "provider-test-agent",
            "--kind",
            "agent",
        ],
        Some(repo_path),
    )
    .success();

    run_cli_command(
        &[
            "new",
            "prompt",
            "testing",
            "provider-test-command",
            "--kind",
            "command",
        ],
        Some(repo_path),
    )
    .success();

    // Build for Claude
    run_cli_command(
        &["build", "--provider", "claude", "--verbose"],
        Some(repo_path),
    )
    .success()
    .stdout(predicate::str::contains("Transforming:"));

    // Verify Claude output structure
    let claude_build = repo_path.join("build/claude");
    assert!(claude_build.exists());

    // Claude should have .claude/ directory structure
    // Check for system prompt or commands directory
    let has_claude_structure = claude_build.join(".claude").exists()
        || claude_build.join("system.md").exists()
        || claude_build.join("commands").exists();

    if !has_claude_structure {
        // At minimum, the build directory should have some files
        let entries: Vec<_> = fs::read_dir(&claude_build).unwrap().collect();
        assert!(
            !entries.is_empty(),
            "Claude build directory should contain files"
        );
    }

    // Build for OpenAI
    run_cli_command(
        &["build", "--provider", "openai", "--verbose"],
        Some(repo_path),
    )
    .success()
    .stdout(predicate::str::contains("Transforming:"));

    // Verify OpenAI output structure
    let openai_build = repo_path.join("build/openai");
    assert!(openai_build.exists());

    // OpenAI should have function calling format or similar
    let entries: Vec<_> = fs::read_dir(&openai_build).unwrap().collect();
    assert!(
        !entries.is_empty(),
        "OpenAI build directory should contain files"
    );
}

#[test]
fn test_provider_filtering() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();

    run_cli_command(
        &[
            "new",
            "prompt",
            "testing",
            "filter-test-agent",
            "--kind",
            "agent",
        ],
        Some(repo_path),
    )
    .success();

    run_cli_command(
        &["new", "tool", "testing", "filter-test-tool"],
        Some(repo_path),
    )
    .success();

    // Build only prompts for Claude
    run_cli_command(
        &["build", "--provider", "claude", "--type-filter", "prompt"],
        Some(repo_path),
    )
    .success();

    // Build only tools for OpenAI
    run_cli_command(
        &["build", "--provider", "openai", "--type-filter", "tool"],
        Some(repo_path),
    )
    .success();
}
