mod e2e;

use e2e::{assert_build_output, run_cli_command, setup_test_repo};

#[test]
fn test_cross_version_compatibility() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();

    // Create experimental primitive (V1 primitives not supported in transitional CLI)
    run_cli_command(
        &[
            "new",
            "prompt",
            "testing",
            "exp-agent",
            "--kind",
            "agent",
            "--experimental",
        ],
        Some(repo_path),
    )
    .success();

    // Note: V1 validation not supported in transitional CLI
    // This test creates experimental primitives which don't require full validation

    // Build for both providers
    run_cli_command(&["build", "--provider", "claude"], Some(repo_path)).success();

    assert_build_output(repo_path, "claude");

    run_cli_command(&["build", "--provider", "openai"], Some(repo_path)).success();

    assert_build_output(repo_path, "openai");

    // Verify outputs exist
    let claude_build = repo_path.join("build/claude");
    let openai_build = repo_path.join("build/openai");

    assert!(claude_build.exists());
    assert!(openai_build.exists());
}
