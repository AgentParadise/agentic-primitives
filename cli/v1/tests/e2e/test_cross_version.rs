mod e2e;

use e2e::{assert_build_output, create_test_primitive, run_cli_command, setup_test_repo};

#[test]
fn test_cross_version_compatibility() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();
    
    // Create v1 primitives
    create_test_primitive(
        repo_path,
        "prompts",
        "agents/testing",
        "v1-agent",
        "You are a test agent.",
    );
    
    // Validate with spec-version v1
    run_cli_command(
        &["validate", "primitives/v1/prompts/agents/testing/v1-agent/"],
        Some(repo_path),
    )
    .success();
    
    // Build for both providers
    run_cli_command(
        &["build", "--provider", "claude"],
        Some(repo_path),
    )
    .success();
    
    assert_build_output(repo_path, "claude");
    
    run_cli_command(
        &["build", "--provider", "openai"],
        Some(repo_path),
    )
    .success();
    
    assert_build_output(repo_path, "openai");
    
    // Verify outputs exist
    let claude_build = repo_path.join("build/claude");
    let openai_build = repo_path.join("build/openai");
    
    assert!(claude_build.exists());
    assert!(openai_build.exists());
}

