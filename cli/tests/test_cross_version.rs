mod e2e;

use e2e::{assert_build_output, run_cli_command, setup_test_repo};

#[test]
fn test_cross_version_compatibility() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();

    // Create v2 primitive using CLI command
    run_cli_command(
        &[
            "new",
            "command",
            "testing",
            "v1-agent",
            "--description",
            "A test command primitive",
            "--model",
            "sonnet",
            "--non-interactive",
        ],
        Some(repo_path),
    )
    .success();

    // Validate the created primitive
    run_cli_command(
        &["validate", "primitives/v2/commands/testing/v1-agent.md"],
        Some(repo_path),
    )
    .success();

    // Build for Claude (v2 only supports claude currently)
    run_cli_command(
        &[
            "build",
            "--provider",
            "claude",
            "--primitives-version",
            "v2",
        ],
        Some(repo_path),
    )
    .success();

    assert_build_output(repo_path, "claude");

    // Verify output exists
    let claude_build = repo_path.join("build/claude");
    assert!(claude_build.exists());
}
