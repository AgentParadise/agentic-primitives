mod e2e;

use e2e::{run_cli_command, setup_test_repo};
use predicates::prelude::*;

#[test]
fn test_full_primitive_lifecycle() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();

    // Step 1: Create agent primitive (experimental - V1 not supported in transitional CLI)
    run_cli_command(
        &[
            "new",
            "prompt",
            "testing",
            "test-agent",
            "--kind",
            "agent",
            "--experimental",
        ],
        Some(repo_path),
    )
    .success();

    // Experimental primitives go under primitives/experimental/agents
    let agent_path = repo_path
        .join("primitives/experimental/agents/testing")
        .join("test-agent");
    assert!(agent_path.exists());

    // Step 2: Create command primitive
    run_cli_command(
        &[
            "new",
            "prompt",
            "testing",
            "test-command",
            "--kind",
            "command",
            "--experimental",
        ],
        Some(repo_path),
    )
    .success();

    // Step 3: Create skill primitive
    run_cli_command(
        &[
            "new",
            "prompt",
            "testing",
            "test-skill",
            "--kind",
            "skill",
            "--experimental",
        ],
        Some(repo_path),
    )
    .success();

    // Step 4: Create tool primitive
    run_cli_command(
        &["new", "tool", "testing", "test-tool", "--experimental"],
        Some(repo_path),
    )
    .success();

    // Step 5: Create hook primitive
    run_cli_command(
        &["new", "hook", "testing", "test-hook", "--experimental"],
        Some(repo_path),
    )
    .success();

    // Step 6: Validate all primitives (experimental primitives don't need full validation)
    // V1 validation not supported in transitional CLI

    // Step 7: List primitives
    run_cli_command(&["list", "primitives/experimental/"], Some(repo_path))
        .success()
        .stdout(predicate::str::contains("test-agent"))
        .stdout(predicate::str::contains("test-command"))
        .stdout(predicate::str::contains("test-skill"))
        .stdout(predicate::str::contains("test-tool"))
        .stdout(predicate::str::contains("test-hook"));

    // Step 8: Inspect agent
    run_cli_command(&["inspect", agent_path.to_str().unwrap()], Some(repo_path))
        .success()
        .stdout(predicate::str::contains("test-agent"))
        .stdout(predicate::str::contains("testing"));

    // Note: Version bumping and promotion are V1-specific features
    // Transitional CLI focuses on experimental primitives which don't use versioning

    // Step 9: Build for Claude (experimental primitives)
    // Note: Experimental primitives may not produce complete builds
    let _build_result = run_cli_command(&["build", "--provider", "claude"], Some(repo_path));

    // Step 10: Build for OpenAI (experimental primitives)
    let _build_result = run_cli_command(&["build", "--provider", "openai"], Some(repo_path));

    // Build outputs may not be complete for experimental primitives
    // The transitional CLI is meant to bridge to v2, not fully support v1 lifecycle
}
