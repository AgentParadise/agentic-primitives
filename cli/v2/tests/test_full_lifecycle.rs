mod e2e;

use e2e::{assert_build_output, assert_primitive_exists, run_cli_command, setup_test_repo};
use predicates::prelude::*;

#[test]
fn test_full_primitive_lifecycle() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();

    // Step 1: Create agent primitive
    run_cli_command(
        &["new", "prompt", "testing", "test-agent", "--kind", "agent"],
        Some(repo_path),
    )
    .success();

    // New structure (ADR-021): agents directly under v1/
    let agent_path = assert_primitive_exists(repo_path, "agents", "testing", "test-agent");
    assert!(agent_path.join("test-agent.yaml").exists()); // Legacy naming still supported
    assert!(agent_path.join("test-agent.prompt.v1.md").exists());

    // Step 2: Create command primitive
    run_cli_command(
        &[
            "new",
            "prompt",
            "testing",
            "test-command",
            "--kind",
            "command",
        ],
        Some(repo_path),
    )
    .success();

    assert_primitive_exists(repo_path, "commands", "testing", "test-command");

    // Step 3: Create skill primitive
    run_cli_command(
        &["new", "prompt", "testing", "test-skill", "--kind", "skill"],
        Some(repo_path),
    )
    .success();

    assert_primitive_exists(repo_path, "skills", "testing", "test-skill");

    // Step 4: Create tool primitive
    run_cli_command(&["new", "tool", "testing", "test-tool"], Some(repo_path)).success();

    assert_primitive_exists(repo_path, "tools", "testing", "test-tool");

    // Step 5: Create hook primitive
    run_cli_command(&["new", "hook", "testing", "test-hook"], Some(repo_path)).success();

    assert_primitive_exists(repo_path, "hooks", "testing", "test-hook");

    // Step 6: Validate all primitives
    run_cli_command(&["validate", "primitives/v1/"], Some(repo_path))
        .success()
        .stdout(predicate::str::contains("✅"));

    // Step 7: List primitives
    run_cli_command(&["list", "primitives/v1/"], Some(repo_path))
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

    // Step 9: Version bump
    run_cli_command(
        &[
            "version",
            "bump",
            agent_path.to_str().unwrap(),
            "--notes",
            "Test version bump",
        ],
        Some(repo_path),
    )
    .success()
    .stdout(predicate::str::contains("v2"));

    assert!(agent_path.join("test-agent.prompt.v2.md").exists());

    // Step 10: Version promote
    run_cli_command(
        &["version", "promote", agent_path.to_str().unwrap(), "2"],
        Some(repo_path),
    )
    .success();

    // Step 11: Build for Claude
    run_cli_command(&["build", "--provider", "claude"], Some(repo_path)).success();

    assert_build_output(repo_path, "claude");

    // Step 12: Build for OpenAI
    run_cli_command(&["build", "--provider", "openai"], Some(repo_path)).success();

    assert_build_output(repo_path, "openai");

    // Step 13: Install dry-run for Claude
    run_cli_command(
        &["install", "--provider", "claude", "--dry-run"],
        Some(repo_path),
    )
    .success()
    .stdout(predicate::str::contains("Sync Preview"))
    .stdout(predicate::str::contains("New primitives:"));
}
