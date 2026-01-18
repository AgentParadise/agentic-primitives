mod e2e;

use e2e::{run_cli_command, setup_test_repo};
use predicates::prelude::*;
use std::fs;

#[test]
fn test_invalid_primitive_structure() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();
    
    // Create invalid primitive (missing metadata)
    let invalid_path = repo_path
        .join("primitives/v1/prompts/agents/testing/invalid-agent");
    fs::create_dir_all(&invalid_path).unwrap();
    fs::write(invalid_path.join("invalid-agent.v1.md"), "Content").unwrap();
    // No metadata file
    
    run_cli_command(
        &["validate", &invalid_path.to_str().unwrap()],
        Some(repo_path),
    )
    .failure()
    .stderr(predicate::str::contains("metadata").or(predicate::str::contains("Not found")));
}

#[test]
fn test_missing_required_files() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();
    
    // Create primitive with metadata but no content file
    let incomplete_path = repo_path
        .join("primitives/v1/prompts/agents/testing/incomplete-agent");
    fs::create_dir_all(&incomplete_path).unwrap();
    
    let meta = r#"id: incomplete-agent
kind: agent
category: testing
summary: Incomplete agent
model_ref: claude/sonnet
version: 1
status: active
"#;
    fs::write(incomplete_path.join("incomplete-agent.yaml"), meta).unwrap();
    // No .v1.md file
    
    run_cli_command(
        &["validate", &incomplete_path.to_str().unwrap()],
        Some(repo_path),
    )
    .failure()
    .stderr(predicate::str::contains("content file").or(predicate::str::contains("Not found")));
}

#[test]
fn test_malformed_yaml() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();
    
    // Create primitive with malformed YAML
    let malformed_path = repo_path
        .join("primitives/v1/prompts/agents/testing/malformed-agent");
    fs::create_dir_all(&malformed_path).unwrap();
    
    let bad_yaml = r#"id: malformed-agent
kind: agent
category: testing
summary: "Unclosed quote
model_ref: claude/sonnet
"#;
    fs::write(malformed_path.join("malformed-agent.yaml"), bad_yaml).unwrap();
    fs::write(malformed_path.join("malformed-agent.v1.md"), "Content").unwrap();
    
    run_cli_command(
        &["validate", &malformed_path.to_str().unwrap()],
        Some(repo_path),
    )
    .failure()
    .stderr(predicate::str::contains("YAML").or(predicate::str::contains("parse")));
}

#[test]
fn test_build_without_provider() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();
    
    run_cli_command(
        &["build"],  // Missing --provider flag
        Some(repo_path),
    )
    .failure();
}

#[test]
fn test_install_without_build() {
    let temp_repo = setup_test_repo();
    let repo_path = temp_repo.path();
    
    // Try to install without building first
    run_cli_command(
        &["install", "--provider", "claude"],
        Some(repo_path),
    )
    .failure()
    .stderr(predicate::str::contains("build directory").or(predicate::str::contains("not found")));
}

