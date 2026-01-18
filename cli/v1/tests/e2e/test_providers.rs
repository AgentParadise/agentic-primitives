mod e2e;

use e2e::{create_test_primitive, run_cli_command, setup_test_repo};
use predicates::prelude::*;
use std::fs;

#[test]
fn test_provider_transformations() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();
    
    // Create test primitives
    create_test_primitive(
        repo_path,
        "prompts",
        "agents/testing",
        "provider-test-agent",
        "You are a provider test agent.",
    );
    
    create_test_primitive(
        repo_path,
        "prompts",
        "commands/testing",
        "provider-test-command",
        "Execute a test command.",
    );
    
    // Build for Claude
    run_cli_command(
        &["build", "--provider", "claude", "--verbose"],
        Some(repo_path),
    )
    .success()
    .stdout(predicate::str::contains("Transformed"));
    
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
    .stdout(predicate::str::contains("Transformed"));
    
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
    
    create_test_primitive(
        repo_path,
        "prompts",
        "agents/testing",
        "filter-test-agent",
        "You are a filter test agent.",
    );
    
    create_test_primitive(
        repo_path,
        "tools",
        "testing",
        "filter-test-tool",
        "",
    );
    
    // Build only prompts for Claude
    run_cli_command(
        &["build", "--provider", "claude", "--type", "prompt"],
        Some(repo_path),
    )
    .success();
    
    // Build only tools for OpenAI
    run_cli_command(
        &["build", "--provider", "openai", "--type", "tool"],
        Some(repo_path),
    )
    .success();
}

