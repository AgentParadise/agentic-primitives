use agentic_primitives::providers::claude::ClaudeTransformer;
use agentic_primitives::providers::ProviderTransformer;
use std::fs;
use std::path::PathBuf;
use tempfile::TempDir;

/// Helper to get fixture path
fn fixture_path(relative: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/v1/valid")
        .join(relative)
}

#[test]
fn test_provider_name() {
    let transformer = ClaudeTransformer::new();
    assert_eq!(transformer.provider_name(), "claude");
}

#[test]
fn test_transform_agent_to_custom_prompt() {
    let transformer = ClaudeTransformer::new();
    let agent_path = fixture_path("prompts/agents/python/python-pro");
    let output_dir = TempDir::new().unwrap();

    let result = transformer
        .transform_primitive(&agent_path, output_dir.path())
        .unwrap();

    assert!(result.success);
    assert_eq!(result.primitive_id, "python-pro");
    assert_eq!(result.primitive_kind, "agent");
    assert!(!result.output_files.is_empty());

    // Check that custom prompt file was created
    let custom_prompt = output_dir.path().join("custom_prompts/python-pro.md");
    assert!(custom_prompt.exists());

    // Verify content
    let content = fs::read_to_string(&custom_prompt).unwrap();
    assert!(content.contains("---"));
    assert!(content.contains("id: python-pro"));
    assert!(content.contains("domain: development"));
    assert!(content.contains("version: 2"));
    assert!(content.contains("status: active"));
    assert!(content.contains("Python Pro"));
}

#[test]
fn test_transform_command_to_command_file() {
    let transformer = ClaudeTransformer::new();
    let command_path = fixture_path("prompts/commands/scaffolding/python-scaffold");
    let output_dir = TempDir::new().unwrap();

    let result = transformer
        .transform_primitive(&command_path, output_dir.path())
        .unwrap();

    assert!(result.success);
    assert_eq!(result.primitive_id, "python-scaffold");
    assert_eq!(result.primitive_kind, "command");

    // Check that command file was created
    let command_file = output_dir.path().join("commands/python-scaffold.md");
    assert!(command_file.exists());

    // Verify it's just the content (no frontmatter)
    let content = fs::read_to_string(&command_file).unwrap();
    assert!(!content.is_empty());
}

#[test]
fn test_transform_skill_to_manifest() {
    let transformer = ClaudeTransformer::new();
    let skill_path = fixture_path("prompts/skills/testing/python-testing-patterns");
    let output_dir = TempDir::new().unwrap();

    let result = transformer
        .transform_primitive(&skill_path, output_dir.path())
        .unwrap();

    assert!(result.success);
    assert_eq!(result.primitive_id, "python-testing-patterns");
    assert_eq!(result.primitive_kind, "skill");

    // Check that skills.json was created
    let skills_file = output_dir.path().join("skills.json");
    assert!(skills_file.exists());

    // Verify JSON structure
    let content = fs::read_to_string(&skills_file).unwrap();
    let json: serde_json::Value = serde_json::from_str(&content).unwrap();
    assert!(json.get("skills").is_some());
    assert!(json.get("note").is_some());

    let skills = json["skills"].as_array().unwrap();
    assert_eq!(skills.len(), 1);
    assert_eq!(skills[0]["id"], "python-testing-patterns");
}

#[test]
fn test_transform_hook_to_hooks_json() {
    let transformer = ClaudeTransformer::new();
    let hook_path = fixture_path("hooks/safety/bash-validator");
    let output_dir = TempDir::new().unwrap();

    let result = transformer
        .transform_primitive(&hook_path, output_dir.path())
        .unwrap();

    assert!(result.success);
    assert_eq!(result.primitive_id, "bash-validator");
    assert_eq!(result.primitive_kind, "hook");

    // Check that hooks.json was created
    let hooks_file = output_dir.path().join("hooks/hooks.json");
    assert!(hooks_file.exists());

    // Verify JSON structure
    let content = fs::read_to_string(&hooks_file).unwrap();
    let json: serde_json::Value = serde_json::from_str(&content).unwrap();
    assert!(json.get("PreToolUse").is_some());

    let pre_tool_use = json["PreToolUse"].as_array().unwrap();
    assert!(!pre_tool_use.is_empty());
    assert_eq!(pre_tool_use[0]["matcher"], "safety");
}

#[test]
fn test_transform_tool_to_mcp_json() {
    let transformer = ClaudeTransformer::new();
    let tool_path = fixture_path("tools/shell/run-tests");
    let output_dir = TempDir::new().unwrap();

    let result = transformer
        .transform_primitive(&tool_path, output_dir.path())
        .unwrap();

    assert!(result.success);
    assert_eq!(result.primitive_id, "run-tests");
    assert_eq!(result.primitive_kind, "tool");

    // Check that mcp.json was created
    let mcp_file = output_dir.path().join("mcp.json");
    assert!(mcp_file.exists());

    // Verify JSON structure
    let content = fs::read_to_string(&mcp_file).unwrap();
    let json: serde_json::Value = serde_json::from_str(&content).unwrap();
    assert!(json.get("mcpServers").is_some());

    let servers = json["mcpServers"].as_object().unwrap();
    assert!(servers.contains_key("run-tests"));
}

#[test]
fn test_transform_versioned_primitive() {
    let transformer = ClaudeTransformer::new();
    let agent_path = fixture_path("prompts/agents/python/python-pro");
    let output_dir = TempDir::new().unwrap();

    let result = transformer
        .transform_primitive(&agent_path, output_dir.path())
        .unwrap();

    assert!(result.success);

    // Verify version info in output
    let custom_prompt = output_dir.path().join("custom_prompts/python-pro.md");
    let content = fs::read_to_string(&custom_prompt).unwrap();

    // Should include version 2 (the default_version)
    assert!(content.contains("version: 2"));
    assert!(content.contains("status: active"));
}

#[test]
fn test_transform_batch_multiple_primitives() {
    let transformer = ClaudeTransformer::new();
    let output_dir = TempDir::new().unwrap();

    let agent_path = fixture_path("prompts/agents/python/python-pro");
    let command_path = fixture_path("prompts/commands/scaffolding/python-scaffold");
    let skill_path = fixture_path("prompts/skills/testing/python-testing-patterns");

    let paths = vec![
        agent_path.as_path(),
        command_path.as_path(),
        skill_path.as_path(),
    ];

    let results = transformer
        .transform_batch(&paths, output_dir.path())
        .unwrap();

    assert_eq!(results.len(), 3);
    assert!(results.iter().all(|r| r.success));

    // Verify all files were created
    assert!(output_dir
        .path()
        .join("custom_prompts/python-pro.md")
        .exists());
    assert!(output_dir
        .path()
        .join("commands/python-scaffold.md")
        .exists());
    assert!(output_dir.path().join("skills.json").exists());
}

#[test]
fn test_merge_multiple_hooks() {
    let transformer = ClaudeTransformer::new();
    let hook_path = fixture_path("hooks/safety/bash-validator");
    let output_dir = TempDir::new().unwrap();

    // Transform the same hook twice to test merging
    let result1 = transformer
        .transform_primitive(&hook_path, output_dir.path())
        .unwrap();
    let result2 = transformer
        .transform_primitive(&hook_path, output_dir.path())
        .unwrap();

    assert!(result1.success);
    assert!(result2.success);

    // Check that hooks were merged
    let hooks_file = output_dir.path().join("hooks/hooks.json");
    let content = fs::read_to_string(&hooks_file).unwrap();
    let json: serde_json::Value = serde_json::from_str(&content).unwrap();

    let pre_tool_use = json["PreToolUse"].as_array().unwrap();
    // Should have 2 entries now
    assert_eq!(pre_tool_use.len(), 2);
}

#[test]
fn test_merge_multiple_tools() {
    let transformer = ClaudeTransformer::new();
    let tool_path = fixture_path("tools/shell/run-tests");
    let output_dir = TempDir::new().unwrap();

    // Transform the same tool twice to test merging
    let result1 = transformer
        .transform_primitive(&tool_path, output_dir.path())
        .unwrap();
    let result2 = transformer
        .transform_primitive(&tool_path, output_dir.path())
        .unwrap();

    assert!(result1.success);
    assert!(result2.success);

    // Check that tools were merged
    let mcp_file = output_dir.path().join("mcp.json");
    let content = fs::read_to_string(&mcp_file).unwrap();
    let json: serde_json::Value = serde_json::from_str(&content).unwrap();

    let servers = json["mcpServers"].as_object().unwrap();
    // Should still have only 1 entry (overwritten)
    assert_eq!(servers.len(), 1);
    assert!(servers.contains_key("run-tests"));
}

#[test]
fn test_validate_output_structure() {
    let transformer = ClaudeTransformer::new();
    let agent_path = fixture_path("prompts/agents/python/python-pro");
    let output_dir = TempDir::new().unwrap();

    transformer
        .transform_primitive(&agent_path, output_dir.path())
        .unwrap();

    // Validation should pass
    let result = transformer.validate_output(output_dir.path());
    assert!(result.is_ok());
}

#[test]
fn test_validate_output_with_invalid_json() {
    let transformer = ClaudeTransformer::new();
    let output_dir = TempDir::new().unwrap();

    // Create invalid JSON file
    let mcp_file = output_dir.path().join("mcp.json");
    fs::write(&mcp_file, "{ invalid json }").unwrap();

    // Validation should fail
    let result = transformer.validate_output(output_dir.path());
    assert!(result.is_err());
}

#[test]
fn test_error_on_missing_meta_yaml() {
    let transformer = ClaudeTransformer::new();
    let output_dir = TempDir::new().unwrap();

    // Create empty directory
    let invalid_path = TempDir::new().unwrap();

    let result = transformer.transform_primitive(invalid_path.path(), output_dir.path());
    assert!(result.is_err());
}

#[test]
fn test_error_on_invalid_primitive_path() {
    let transformer = ClaudeTransformer::new();
    let output_dir = TempDir::new().unwrap();

    // Use non-existent path
    let invalid_path = PathBuf::from("/nonexistent/path/to/primitive");

    let result = transformer.transform_primitive(&invalid_path, output_dir.path());
    assert!(result.is_err());
}

#[test]
fn test_validate_nonexistent_output_directory() {
    let transformer = ClaudeTransformer::new();
    let nonexistent_dir = PathBuf::from("/nonexistent/output/directory");

    let result = transformer.validate_output(&nonexistent_dir);
    assert!(result.is_err());
}

#[test]
fn test_transform_meta_prompt() {
    let transformer = ClaudeTransformer::new();
    let meta_prompt_path = fixture_path("prompts/meta-prompts/generators/prompt-builder");
    let output_dir = TempDir::new().unwrap();

    let result = transformer
        .transform_primitive(&meta_prompt_path, output_dir.path())
        .unwrap();

    assert!(result.success);
    assert_eq!(result.primitive_id, "prompt-builder");
    assert_eq!(result.primitive_kind, "meta-prompt");

    // Meta-prompts are treated like commands
    let command_file = output_dir.path().join("commands/prompt-builder.md");
    assert!(command_file.exists());
}

#[test]
fn test_batch_with_partial_failures() {
    let transformer = ClaudeTransformer::new();
    let output_dir = TempDir::new().unwrap();

    let valid_path = fixture_path("prompts/agents/python/python-pro");
    let invalid_path = PathBuf::from("/nonexistent/primitive");

    let paths = vec![valid_path.as_path(), invalid_path.as_path()];

    let results = transformer
        .transform_batch(&paths, output_dir.path())
        .unwrap();

    assert_eq!(results.len(), 2);
    // First should succeed
    assert!(results[0].success);
    // Second should fail
    assert!(!results[1].success);
    assert!(results[1].error.is_some());
}

#[test]
fn test_skills_manifest_accumulation() {
    let transformer = ClaudeTransformer::new();
    let skill_path = fixture_path("prompts/skills/testing/python-testing-patterns");
    let output_dir = TempDir::new().unwrap();

    // Transform skill twice
    transformer
        .transform_primitive(&skill_path, output_dir.path())
        .unwrap();
    transformer
        .transform_primitive(&skill_path, output_dir.path())
        .unwrap();

    // Check that skills accumulated
    let skills_file = output_dir.path().join("skills.json");
    let content = fs::read_to_string(&skills_file).unwrap();
    let json: serde_json::Value = serde_json::from_str(&content).unwrap();

    let skills = json["skills"].as_array().unwrap();
    // Should have 2 entries
    assert_eq!(skills.len(), 2);
}

#[test]
fn test_output_directory_creation() {
    let transformer = ClaudeTransformer::new();
    let agent_path = fixture_path("prompts/agents/python/python-pro");
    let output_dir = TempDir::new().unwrap();

    transformer
        .transform_primitive(&agent_path, output_dir.path())
        .unwrap();

    // Check that subdirectories were created
    assert!(output_dir.path().join("custom_prompts").exists());
    assert!(output_dir.path().join("custom_prompts").is_dir());
}

#[test]
fn test_hooks_json_structure() {
    let transformer = ClaudeTransformer::new();
    let hook_path = fixture_path("hooks/safety/bash-validator");
    let output_dir = TempDir::new().unwrap();

    transformer
        .transform_primitive(&hook_path, output_dir.path())
        .unwrap();

    let hooks_file = output_dir.path().join("hooks/hooks.json");
    let content = fs::read_to_string(&hooks_file).unwrap();
    let json: serde_json::Value = serde_json::from_str(&content).unwrap();

    // Verify structure
    let pre_tool_use = json["PreToolUse"].as_array().unwrap();
    let hook_entry = &pre_tool_use[0];

    assert!(hook_entry.get("matcher").is_some());
    assert!(hook_entry.get("hooks").is_some());

    let hooks = hook_entry["hooks"].as_array().unwrap();
    assert!(!hooks.is_empty());

    let hook = &hooks[0];
    assert_eq!(hook["type"], "command");
    assert!(hook["command"]
        .as_str()
        .unwrap()
        .contains("bash-validator.sh"));
}

#[test]
fn test_mcp_json_structure() {
    let transformer = ClaudeTransformer::new();
    let tool_path = fixture_path("tools/shell/run-tests");
    let output_dir = TempDir::new().unwrap();

    transformer
        .transform_primitive(&tool_path, output_dir.path())
        .unwrap();

    let mcp_file = output_dir.path().join("mcp.json");
    let content = fs::read_to_string(&mcp_file).unwrap();
    let json: serde_json::Value = serde_json::from_str(&content).unwrap();

    // Verify structure
    let servers = json["mcpServers"].as_object().unwrap();
    let server_config = &servers["run-tests"];

    assert!(server_config.get("command").is_some());
    assert!(server_config["command"].is_string());
}
