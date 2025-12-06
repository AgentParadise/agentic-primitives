use agentic_primitives::providers::openai::OpenAITransformer;
use agentic_primitives::providers::ProviderTransformer;
use serde_json::Value;
use std::fs;
use std::path::PathBuf;
use tempfile::TempDir;

/// Helper to get test fixtures path
fn fixtures_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("v1")
        .join("valid")
}

/// Helper to read JSON file
fn read_json(path: &std::path::Path) -> Value {
    let content = fs::read_to_string(path).expect("Failed to read file");
    serde_json::from_str(&content).expect("Failed to parse JSON")
}

#[test]
fn test_transform_agent_to_system_message() {
    let transformer = OpenAITransformer::new();
    let agent_path = fixtures_dir()
        .join("agents")
        .join("python")
        .join("python-pro");

    let output_dir = TempDir::new().unwrap();
    let result = transformer
        .transform_primitive(&agent_path, output_dir.path())
        .expect("Failed to transform agent");

    assert!(result.success);
    assert_eq!(result.primitive_id, "python-pro");
    assert_eq!(result.primitive_kind, "prompt");

    // Check output file exists
    let output_file = output_dir.path().join("prompts/agents/python-pro.json");
    assert!(output_file.exists(), "Output file should exist");

    // Validate JSON structure
    let json = read_json(&output_file);
    assert_eq!(json["id"], "python-pro");
    assert_eq!(json["type"], "agent");
    assert_eq!(json["spec_version"], "v1");
    assert_eq!(json["version"], 2); // default_version from fixture

    // Check messages array
    let messages = json["messages"]
        .as_array()
        .expect("messages should be array");
    assert_eq!(messages.len(), 1);
    assert_eq!(messages[0]["role"], "system");
    assert!(!messages[0]["content"].as_str().unwrap().is_empty());

    // Check metadata
    assert_eq!(json["metadata"]["domain"], "development");
    assert!(!json["metadata"]["tags"].as_array().unwrap().is_empty());
}

#[test]
fn test_transform_command_to_user_message() {
    let transformer = OpenAITransformer::new();
    let command_path = fixtures_dir()
        .join("commands")
        .join("scaffolding")
        .join("python-scaffold");

    let output_dir = TempDir::new().unwrap();
    let result = transformer
        .transform_primitive(&command_path, output_dir.path())
        .expect("Failed to transform command");

    assert!(result.success);
    assert_eq!(result.primitive_id, "python-scaffold");
    assert_eq!(result.primitive_kind, "prompt");

    // Check output file exists
    let output_file = output_dir
        .path()
        .join("prompts/commands/python-scaffold.json");
    assert!(output_file.exists(), "Output file should exist");

    // Validate JSON structure
    let json = read_json(&output_file);
    assert_eq!(json["id"], "python-scaffold");
    assert_eq!(json["type"], "command");

    // Check messages array
    let messages = json["messages"]
        .as_array()
        .expect("messages should be array");
    assert_eq!(messages.len(), 1);
    assert_eq!(messages[0]["role"], "user");
}

#[test]
fn test_transform_skill_to_context_message() {
    let transformer = OpenAITransformer::new();
    let skill_path = fixtures_dir()
        .join("skills")
        .join("testing")
        .join("python-testing-patterns");

    let output_dir = TempDir::new().unwrap();
    let result = transformer
        .transform_primitive(&skill_path, output_dir.path())
        .expect("Failed to transform skill");

    assert!(result.success);
    assert_eq!(result.primitive_id, "python-testing-patterns");
    assert_eq!(result.primitive_kind, "prompt");

    // Check output file exists
    let output_file = output_dir
        .path()
        .join("prompts/skills/python-testing-patterns.json");
    assert!(output_file.exists(), "Output file should exist");

    // Validate JSON structure
    let json = read_json(&output_file);
    assert_eq!(json["id"], "python-testing-patterns");
    assert_eq!(json["type"], "skill");

    // Check messages array
    let messages = json["messages"]
        .as_array()
        .expect("messages should be array");
    assert_eq!(messages.len(), 1);
    assert_eq!(messages[0]["role"], "assistant");

    // Check metadata
    assert_eq!(json["metadata"]["usage"], "overlay");
}

#[test]
fn test_transform_tool_to_function_calling() {
    let transformer = OpenAITransformer::new();
    let tool_path = fixtures_dir().join("tools").join("shell").join("run-tests");

    let output_dir = TempDir::new().unwrap();
    let result = transformer
        .transform_primitive(&tool_path, output_dir.path())
        .expect("Failed to transform tool");

    assert!(result.success);
    assert_eq!(result.primitive_id, "run-tests");
    assert_eq!(result.primitive_kind, "tool");

    // Check output file exists
    let output_file = output_dir.path().join("functions/run-tests.json");
    assert!(output_file.exists(), "Output file should exist");

    // Validate JSON structure
    let json = read_json(&output_file);
    assert_eq!(json["type"], "function");

    // Check function definition
    let function = &json["function"];
    assert_eq!(function["name"], "run_tests"); // Hyphens converted to underscores
    assert!(!function["description"].as_str().unwrap().is_empty());

    // Check parameters
    let parameters = &function["parameters"];
    assert_eq!(parameters["type"], "object");
    assert!(parameters["properties"].is_object());

    // Check metadata
    assert_eq!(json["metadata"]["id"], "run-tests");
    assert_eq!(json["metadata"]["category"], "shell");
}

#[test]
fn test_transform_hook_to_middleware() {
    let transformer = OpenAITransformer::new();
    let hook_path = fixtures_dir()
        .join("hooks")
        .join("safety")
        .join("bash-validator");

    let output_dir = TempDir::new().unwrap();
    let result = transformer
        .transform_primitive(&hook_path, output_dir.path())
        .expect("Failed to transform hook");

    assert!(result.success);
    assert_eq!(result.primitive_id, "bash-validator");
    assert_eq!(result.primitive_kind, "hook");

    // Check output file exists
    let output_file = output_dir.path().join("middleware/bash-validator.json");
    assert!(output_file.exists(), "Output file should exist");

    // Validate JSON structure
    let json = read_json(&output_file);
    assert_eq!(json["id"], "bash-validator");
    assert_eq!(json["type"], "hook");
    assert_eq!(json["event"], "pre_tool_use");

    // Check metadata
    assert!(!json["metadata"]["description"].as_str().unwrap().is_empty());
    assert!(json["metadata"]["execution"].is_string());
}

#[test]
fn test_transform_versioned_primitive() {
    let transformer = OpenAITransformer::new();
    let agent_path = fixtures_dir()
        .join("agents")
        .join("python")
        .join("python-pro");

    let output_dir = TempDir::new().unwrap();
    let result = transformer
        .transform_primitive(&agent_path, output_dir.path())
        .expect("Failed to transform versioned primitive");

    assert!(result.success);

    // Check that version is included in output
    let output_file = output_dir.path().join("prompts/agents/python-pro.json");
    let json = read_json(&output_file);

    // Should use default_version (2) from the fixture
    assert_eq!(json["version"], 2);
}

#[test]
fn test_transform_batch_multiple_primitives() {
    let transformer = OpenAITransformer::new();

    let agent_path = fixtures_dir()
        .join("agents")
        .join("python")
        .join("python-pro");
    let command_path = fixtures_dir()
        .join("commands")
        .join("scaffolding")
        .join("python-scaffold");
    let skill_path = fixtures_dir()
        .join("skills")
        .join("testing")
        .join("python-testing-patterns");

    let output_dir = TempDir::new().unwrap();
    let paths = vec![
        agent_path.as_path(),
        command_path.as_path(),
        skill_path.as_path(),
    ];

    let results = transformer
        .transform_batch(&paths, output_dir.path())
        .expect("Failed to transform batch");

    assert_eq!(results.len(), 3);
    assert!(results.iter().all(|r| r.success));

    // Check that all output files exist
    assert!(output_dir
        .path()
        .join("prompts/agents/python-pro.json")
        .exists());
    assert!(output_dir
        .path()
        .join("prompts/commands/python-scaffold.json")
        .exists());
    assert!(output_dir
        .path()
        .join("prompts/skills/python-testing-patterns.json")
        .exists());

    // Check that manifest was generated
    assert!(output_dir.path().join("manifest.json").exists());
}

#[test]
fn test_function_parameters_mapping() {
    let transformer = OpenAITransformer::new();
    let tool_path = fixtures_dir().join("tools").join("shell").join("run-tests");

    let output_dir = TempDir::new().unwrap();
    transformer
        .transform_primitive(&tool_path, output_dir.path())
        .expect("Failed to transform tool");

    let output_file = output_dir.path().join("functions/run-tests.json");
    let json = read_json(&output_file);

    let properties = &json["function"]["parameters"]["properties"];
    assert!(properties.is_object());

    // Check that properties have correct structure
    for (_key, value) in properties.as_object().unwrap() {
        assert!(value["type"].is_string());
        assert!(value["description"].is_string());
    }
}

#[test]
fn test_required_fields_in_function() {
    let transformer = OpenAITransformer::new();
    let tool_path = fixtures_dir().join("tools").join("shell").join("run-tests");

    let output_dir = TempDir::new().unwrap();
    transformer
        .transform_primitive(&tool_path, output_dir.path())
        .expect("Failed to transform tool");

    let output_file = output_dir.path().join("functions/run-tests.json");
    let json = read_json(&output_file);

    let required = &json["function"]["parameters"]["required"];
    assert!(required.is_array());
}

#[test]
fn test_generate_manifest() {
    let transformer = OpenAITransformer::new();

    let agent_path = fixtures_dir()
        .join("agents")
        .join("python")
        .join("python-pro");
    let tool_path = fixtures_dir().join("tools").join("shell").join("run-tests");

    let output_dir = TempDir::new().unwrap();
    let paths = vec![agent_path.as_path(), tool_path.as_path()];

    transformer
        .transform_batch(&paths, output_dir.path())
        .expect("Failed to transform batch");

    // Check manifest exists
    let manifest_file = output_dir.path().join("manifest.json");
    assert!(manifest_file.exists());

    // Validate manifest structure
    let json = read_json(&manifest_file);
    assert_eq!(json["spec_version"], "v1");
    assert_eq!(json["provider"], "openai");
    assert!(json["generated_at"].is_string());

    // Check primitives are indexed
    let primitives = &json["primitives"];
    assert!(primitives["prompts"]["agents"]
        .as_array()
        .unwrap()
        .contains(&serde_json::json!("python-pro")));
    assert!(primitives["tools"]
        .as_array()
        .unwrap()
        .contains(&serde_json::json!("run-tests")));
}

#[test]
fn test_validate_output_structure() {
    let transformer = OpenAITransformer::new();

    let agent_path = fixtures_dir()
        .join("agents")
        .join("python")
        .join("python-pro");

    let output_dir = TempDir::new().unwrap();

    // Transform and generate manifest
    transformer
        .transform_batch(&[agent_path.as_path()], output_dir.path())
        .expect("Failed to transform");

    // Validate output
    let validation_result = transformer.validate_output(output_dir.path());
    assert!(validation_result.is_ok(), "Validation should pass");
}

#[test]
fn test_error_on_missing_meta_yaml() {
    let transformer = OpenAITransformer::new();
    let nonexistent_path = fixtures_dir().join("nonexistent");

    let output_dir = TempDir::new().unwrap();
    let result = transformer.transform_primitive(&nonexistent_path, output_dir.path());

    assert!(result.is_err());
}

#[test]
fn test_error_on_invalid_primitive_kind() {
    let transformer = OpenAITransformer::new();

    // Create a temporary directory without any meta files
    let temp_dir = TempDir::new().unwrap();
    let invalid_path = temp_dir.path().join("invalid");
    fs::create_dir(&invalid_path).unwrap();

    let output_dir = TempDir::new().unwrap();
    let result = transformer.transform_primitive(&invalid_path, output_dir.path());

    assert!(result.is_err());
}

#[test]
fn test_provider_name() {
    let transformer = OpenAITransformer::new();
    assert_eq!(transformer.provider_name(), "openai");
}

#[test]
fn test_batch_continues_on_error() {
    let transformer = OpenAITransformer::new();

    let valid_path = fixtures_dir()
        .join("agents")
        .join("python")
        .join("python-pro");

    let temp_dir = TempDir::new().unwrap();
    let invalid_path = temp_dir.path().join("invalid");
    fs::create_dir(&invalid_path).unwrap();

    let output_dir = TempDir::new().unwrap();
    let paths = vec![valid_path.as_path(), invalid_path.as_path()];

    let results = transformer
        .transform_batch(&paths, output_dir.path())
        .expect("Batch should not fail completely");

    // Should have 2 results
    assert_eq!(results.len(), 2);

    // First should succeed, second should fail
    assert!(results[0].success);
    assert!(!results[1].success);
    assert!(results[1].error.is_some());
}

#[test]
fn test_meta_prompt_is_skipped() {
    let transformer = OpenAITransformer::new();
    let meta_prompt_path = fixtures_dir()
        .join("commands")
        .join("meta")
        .join("prompt-builder");

    let output_dir = TempDir::new().unwrap();
    let result = transformer
        .transform_primitive(&meta_prompt_path, output_dir.path())
        .expect("Failed to transform meta-prompt");

    // Meta-prompts should be skipped (success but no output)
    assert!(result.success);
    assert!(result.error.is_some());
    assert!(result.error.unwrap().contains("skipped"));
}

#[test]
fn test_validate_output_missing_manifest() {
    let transformer = OpenAITransformer::new();
    let temp_dir = TempDir::new().unwrap();

    // Don't create manifest
    let result = transformer.validate_output(temp_dir.path());
    assert!(result.is_err());
}
