use crate::error::{Error, Result};
use crate::spec_version::SpecVersion;
use jsonschema::JSONSchema;
use serde_json::Value;
use std::collections::HashMap;
use std::path::Path;

/// JSON Schema validator with cached compiled schemas
pub struct SchemaValidator {
    schemas: HashMap<String, JSONSchema>,
    spec_version: SpecVersion,
}

impl SchemaValidator {
    /// Load all schemas from schemas/ directory (uses default V1)
    pub fn load<P: AsRef<Path>>(schemas_dir: P) -> Result<Self> {
        Self::load_with_version(schemas_dir, SpecVersion::V1)
    }

    /// Load all schemas with a specific spec version
    pub fn load_with_version<P: AsRef<Path>>(
        schemas_dir: P,
        spec_version: SpecVersion,
    ) -> Result<Self> {
        let schemas_dir = schemas_dir.as_ref();

        if !schemas_dir.exists() {
            return Err(Error::NotFound(format!(
                "Schemas directory not found: {}",
                schemas_dir.display()
            )));
        }

        let mut schemas = HashMap::new();

        // Define expected schema files
        let schema_files = vec![
            "prompt-meta.schema.json",
            "tool-meta.schema.json",
            "hook-meta.schema.json",
            "model-config.schema.json",
            "provider-impl.schema.json",
        ];

        for schema_file in schema_files {
            let schema_path = schemas_dir.join(schema_file);

            if !schema_path.exists() {
                return Err(Error::NotFound(format!(
                    "Schema file not found: {}",
                    schema_path.display()
                )));
            }

            let content = std::fs::read_to_string(&schema_path)?;
            let schema_value: Value = serde_json::from_str(&content)?;

            let compiled = JSONSchema::compile(&schema_value).map_err(|e| {
                Error::Validation(format!("Failed to compile schema {schema_file}: {e}"))
            })?;

            // Store with key like "prompt-meta", "tool-meta", etc.
            let key = schema_file.trim_end_matches(".schema.json").to_string();
            schemas.insert(key, compiled);
        }

        Ok(Self {
            schemas,
            spec_version,
        })
    }

    /// Get the spec version being used
    pub fn spec_version(&self) -> SpecVersion {
        self.spec_version
    }

    /// Validate prompt metadata
    pub fn validate_prompt_meta(&self, meta: &Value) -> Result<()> {
        self.validate("prompt-meta", meta)
    }

    /// Validate tool metadata
    pub fn validate_tool_meta(&self, meta: &Value) -> Result<()> {
        self.validate("tool-meta", meta)
    }

    /// Validate hook metadata
    pub fn validate_hook_meta(&self, meta: &Value) -> Result<()> {
        self.validate("hook-meta", meta)
    }

    /// Validate model config
    pub fn validate_model_config(&self, config: &Value) -> Result<()> {
        self.validate("model-config", config)
    }

    /// Validate provider implementation
    pub fn validate_provider_impl(&self, impl_data: &Value) -> Result<()> {
        self.validate("provider-impl", impl_data)
    }

    /// Internal validation helper
    fn validate(&self, schema_key: &str, data: &Value) -> Result<()> {
        let schema = self
            .schemas
            .get(schema_key)
            .ok_or_else(|| Error::Validation(format!("Schema not found: {schema_key}")))?;

        match schema.validate(data) {
            Ok(_) => Ok(()),
            Err(errors) => {
                let error_messages: Vec<String> = errors
                    .map(|e| format!("  - {}: {}", e.instance_path, e))
                    .collect();

                Err(Error::Validation(format!(
                    "Validation failed for {}:\n{}",
                    schema_key,
                    error_messages.join("\n")
                )))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn find_repo_root() -> Option<std::path::PathBuf> {
        let current_dir = std::env::current_dir().ok()?;
        let mut search_dir = current_dir.as_path();

        loop {
            if search_dir.join("primitives.config.yaml").exists() {
                return Some(search_dir.to_path_buf());
            }
            search_dir = search_dir.parent()?;
        }
    }

    #[test]
    fn test_load_schemas() {
        let repo_root = match find_repo_root() {
            Some(root) => root,
            None => {
                eprintln!("Skipping test: repo root not found");
                return;
            }
        };

        let schemas_dir = repo_root.join("specs/v1");
        let validator = SchemaValidator::load(&schemas_dir);

        match validator {
            Ok(v) => {
                assert!(v.schemas.contains_key("prompt-meta"));
                assert!(v.schemas.contains_key("tool-meta"));
                assert!(v.schemas.contains_key("hook-meta"));
                assert!(v.schemas.contains_key("model-config"));
                assert_eq!(v.spec_version(), SpecVersion::V1);
            }
            Err(e) => {
                eprintln!("Warning: Could not load schemas: {e}");
            }
        }
    }

    #[test]
    fn test_validate_valid_prompt() {
        let repo_root = match find_repo_root() {
            Some(root) => root,
            None => {
                eprintln!("Skipping test: repo root not found");
                return;
            }
        };

        let schemas_dir = repo_root.join("specs/v1");
        let validator = match SchemaValidator::load(&schemas_dir) {
            Ok(v) => v,
            Err(_) => {
                eprintln!("Skipping test: schemas not loaded");
                return;
            }
        };

        let valid_prompt = json!({
            "id": "test-agent",
            "kind": "agent",
            "category": "testing",
            "domain": "test",
            "summary": "A test agent for unit testing",
            "context_usage": {
                "as_system": true,
                "as_user": false,
                "as_overlay": false
            },
            "versions": [{
                "version": 1,
                "file": "test-agent.prompt.v1.md",
                "status": "draft",
                "hash": "blake3:0000000000000000000000000000000000000000000000000000000000000000",
                "created": "2025-01-01",
                "notes": "Initial version"
            }],
            "default_version": 1
        });

        let result = validator.validate_prompt_meta(&valid_prompt);
        assert!(result.is_ok(), "Valid prompt should pass validation");
    }

    #[test]
    fn test_validate_invalid_prompt() {
        let repo_root = match find_repo_root() {
            Some(root) => root,
            None => {
                eprintln!("Skipping test: repo root not found");
                return;
            }
        };

        let schemas_dir = repo_root.join("specs/v1");
        let validator = match SchemaValidator::load(&schemas_dir) {
            Ok(v) => v,
            Err(_) => {
                eprintln!("Skipping test: schemas not loaded");
                return;
            }
        };

        // Missing required field "summary"
        let invalid_prompt = json!({
            "id": "test-agent",
            "kind": "agent",
            "category": "testing",
            "domain": "test"
        });

        let result = validator.validate_prompt_meta(&invalid_prompt);
        assert!(result.is_err(), "Invalid prompt should fail validation");
    }

    #[test]
    fn test_validate_valid_tool() {
        let repo_root = match find_repo_root() {
            Some(root) => root,
            None => {
                eprintln!("Skipping test: repo root not found");
                return;
            }
        };

        let schemas_dir = repo_root.join("specs/v1");
        let validator = match SchemaValidator::load(&schemas_dir) {
            Ok(v) => v,
            Err(_) => {
                eprintln!("Skipping test: schemas not loaded");
                return;
            }
        };

        let valid_tool = json!({
            "id": "test-tool",
            "kind": "tool",
            "category": "testing",
            "description": "A test tool for unit testing purposes"
        });

        let result = validator.validate_tool_meta(&valid_tool);
        assert!(result.is_ok(), "Valid tool should pass validation");
    }

    #[test]
    fn test_validate_valid_hook() {
        let repo_root = match find_repo_root() {
            Some(root) => root,
            None => {
                eprintln!("Skipping test: repo root not found");
                return;
            }
        };

        let schemas_dir = repo_root.join("specs/v1");
        let validator = match SchemaValidator::load(&schemas_dir) {
            Ok(v) => v,
            Err(_) => {
                eprintln!("Skipping test: schemas not loaded");
                return;
            }
        };

        let valid_hook = json!({
            "id": "test-hook",
            "kind": "hook",
            "category": "testing",
            "event": "PreToolUse",
            "summary": "A test hook for unit testing",
            "execution": {
                "strategy": "pipeline"
            }
        });

        let result = validator.validate_hook_meta(&valid_hook);
        assert!(result.is_ok(), "Valid hook should pass validation");
    }

    #[test]
    fn test_validate_valid_model_config() {
        let repo_root = match find_repo_root() {
            Some(root) => root,
            None => {
                eprintln!("Skipping test: repo root not found");
                return;
            }
        };

        let schemas_dir = repo_root.join("specs/v1");
        let validator = match SchemaValidator::load(&schemas_dir) {
            Ok(v) => v,
            Err(_) => {
                eprintln!("Skipping test: schemas not loaded");
                return;
            }
        };

        let valid_model = json!({
            "id": "test-model",
            "full_name": "Test Model",
            "api_name": "test-model-v1",
            "provider": "claude",
            "capabilities": {
                "max_tokens": 100000,
                "context_window": 200000
            },
            "performance": {
                "speed": "fast",
                "quality": "high"
            },
            "pricing": {
                "input_per_1m_tokens": 1.0,
                "output_per_1m_tokens": 3.0,
                "currency": "USD"
            },
            "strengths": ["Testing"],
            "recommended_for": ["unit tests"]
        });

        let result = validator.validate_model_config(&valid_model);
        assert!(result.is_ok(), "Valid model config should pass validation");
    }

    #[test]
    fn test_load_nonexistent_schemas_dir() {
        let result = SchemaValidator::load("/nonexistent/schemas");
        assert!(result.is_err());
    }
}
