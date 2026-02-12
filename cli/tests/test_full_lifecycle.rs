mod e2e;

use e2e::{assert_build_output, run_cli_command, setup_test_repo};
#[test]
fn test_full_primitive_lifecycle() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();

    // Step 1: Create command primitive (v2 style)
    run_cli_command(
        &[
            "new",
            "command",
            "testing",
            "test-command",
            "--description",
            "A test command",
            "--model",
            "sonnet",
            "--non-interactive",
        ],
        Some(repo_path),
    )
    .success();

    let command_path = repo_path.join("primitives/v2/commands/testing/test-command.md");
    assert!(command_path.exists(), "Command primitive should exist");

    // Step 2: Create skill primitive (v2 style)
    run_cli_command(
        &[
            "new",
            "skill",
            "testing",
            "test-skill",
            "--description",
            "A test skill",
            "--model",
            "sonnet",
            "--non-interactive",
        ],
        Some(repo_path),
    )
    .success();

    let skill_path = repo_path.join("primitives/v2/skills/testing/test-skill.md");
    assert!(skill_path.exists(), "Skill primitive should exist");

    // Step 3: Create tool primitive (v2 style)
    run_cli_command(
        &[
            "new",
            "tool",
            "testing",
            "test-tool",
            "--description",
            "A test tool",
            "--model",
            "sonnet",
            "--non-interactive",
        ],
        Some(repo_path),
    )
    .success();

    let tool_dir = repo_path.join("primitives/v2/tools/testing/test-tool");
    assert!(tool_dir.exists(), "Tool primitive directory should exist");

    // Step 4: Validate a specific primitive
    run_cli_command(
        &["validate", "primitives/v2/commands/testing/test-command.md"],
        Some(repo_path),
    )
    .success();

    // Step 5: Build for Claude
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
}
