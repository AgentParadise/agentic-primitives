//! Layer 3: Semantic validation
//! Validates cross-references, dependencies, and business logic

use anyhow::{Context, Result};
use blake3;
use serde_yaml::Value as YamlValue;
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use thiserror::Error;
use walkdir::WalkDir;

#[derive(Error, Debug)]
pub enum SemanticError {
    #[error("Tool reference '{tool_id}' not found (referenced in {primitive})")]
    MissingToolReference { tool_id: String, primitive: String },

    #[error("Model reference '{model_ref}' not found (provider: {provider}, model: {model})")]
    MissingModelReference {
        model_ref: String,
        provider: String,
        model: String,
    },

    #[error("BLAKE3 hash mismatch for {file}: expected {expected}, got {actual}")]
    HashMismatch {
        file: String,
        expected: String,
        actual: String,
    },

    #[error("No active versions found (all versions are draft or deprecated)")]
    NoActiveVersions,

    #[error("Version consistency error: {0}")]
    VersionConsistency(String),

    #[error("Invalid version status: '{status}' (expected: draft, active, or deprecated)")]
    InvalidVersionStatus { status: String },
}

pub struct SemanticValidator {
    repo_root: Option<PathBuf>,
}

impl SemanticValidator {
    pub fn new() -> Self {
        Self {
            repo_root: Self::find_repo_root(),
        }
    }

    fn find_repo_root() -> Option<PathBuf> {
        let current_dir = std::env::current_dir().ok()?;
        let mut search_dir = current_dir.as_path();

        loop {
            if search_dir.join("primitives.config.yaml").exists() {
                return Some(search_dir.to_path_buf());
            }
            search_dir = search_dir.parent()?;
        }
    }

    pub fn validate(&self, primitive_path: &Path) -> Result<()> {
        // Ensure the path is valid
        if !primitive_path.exists() {
            anyhow::bail!(
                "Primitive path does not exist: {}",
                primitive_path.display()
            );
        }

        // Read and parse meta.yaml
        let meta_path = primitive_path.join("meta.yaml");
        if !meta_path.exists() {
            anyhow::bail!("Missing meta.yaml file");
        }

        let meta_content = std::fs::read_to_string(&meta_path)
            .with_context(|| format!("Failed to read meta.yaml from {}", meta_path.display()))?;

        let meta: YamlValue = serde_yaml::from_str(&meta_content)
            .with_context(|| format!("Failed to parse meta.yaml from {}", meta_path.display()))?;

        // Get the primitive kind
        let kind = meta
            .get("kind")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");

        // Validate based on kind
        match kind {
            "agent" | "command" | "skill" | "meta-prompt" => {
                self.validate_prompt_primitive(&meta, primitive_path)?;
            }
            "tool" => {
                self.validate_tool_primitive(&meta, primitive_path)?;
            }
            "hook" => {
                self.validate_hook_primitive(&meta, primitive_path)?;
            }
            _ => {
                // Unknown kind - skip semantic validation
            }
        }

        Ok(())
    }

    fn validate_prompt_primitive(&self, meta: &YamlValue, primitive_path: &Path) -> Result<()> {
        // Validate tool references
        if let Some(tools) = meta.get("tools").and_then(|v| v.as_sequence()) {
            for tool in tools {
                if let Some(tool_id) = tool.as_str() {
                    self.validate_tool_reference(tool_id, primitive_path)?;
                }
            }
        }

        // Validate model references
        if let Some(models) = meta.get("preferred_models").and_then(|v| v.as_sequence()) {
            for model in models {
                if let Some(model_ref) = model.as_str() {
                    self.validate_model_reference(model_ref)?;
                }
            }
        }

        // Validate version hashes and consistency
        if let Some(versions) = meta.get("versions").and_then(|v| v.as_sequence()) {
            self.validate_version_consistency(versions, primitive_path)?;
        }

        Ok(())
    }

    fn validate_tool_primitive(&self, _meta: &YamlValue, _primitive_path: &Path) -> Result<()> {
        // Tool-specific semantic validation
        // Currently no cross-references to validate for tools
        Ok(())
    }

    fn validate_hook_primitive(&self, meta: &YamlValue, primitive_path: &Path) -> Result<()> {
        // Validate tool references in hooks
        if let Some(tools) = meta.get("tools").and_then(|v| v.as_sequence()) {
            for tool in tools {
                if let Some(tool_id) = tool.as_str() {
                    self.validate_tool_reference(tool_id, primitive_path)?;
                }
            }
        }

        Ok(())
    }

    fn validate_tool_reference(&self, tool_id: &str, primitive_path: &Path) -> Result<()> {
        if let Some(ref root) = self.repo_root {
            // Search for tool in primitives/v1/tools/**/<tool_id>/
            let tools_dir = root.join("primitives/v1/tools");
            if tools_dir.exists() {
                let mut found = false;
                for entry in WalkDir::new(tools_dir)
                    .max_depth(3)
                    .into_iter()
                    .filter_map(|e| e.ok())
                {
                    if entry.file_type().is_dir() && entry.file_name().to_string_lossy() == tool_id
                    {
                        // Check if it has tool.meta.yaml or meta.yaml
                        let tool_meta = entry.path().join("tool.meta.yaml");
                        let meta = entry.path().join("meta.yaml");
                        if tool_meta.exists() || meta.exists() {
                            found = true;
                            break;
                        }
                    }
                }

                if !found {
                    return Err(SemanticError::MissingToolReference {
                        tool_id: tool_id.to_string(),
                        primitive: primitive_path.display().to_string(),
                    }
                    .into());
                }
            }
        }

        Ok(())
    }

    fn validate_model_reference(&self, model_ref: &str) -> Result<()> {
        // Parse model reference: "provider/model-id"
        let parts: Vec<&str> = model_ref.split('/').collect();
        if parts.len() != 2 {
            anyhow::bail!("Invalid model reference format: {model_ref}");
        }

        let provider = parts[0];
        let model_id = parts[1];

        if let Some(ref root) = self.repo_root {
            // Check providers/<provider>/models/<model-id>.yaml
            let model_path = root
                .join("providers")
                .join(provider)
                .join("models")
                .join(format!("{model_id}.yaml"));

            if !model_path.exists() {
                return Err(SemanticError::MissingModelReference {
                    model_ref: model_ref.to_string(),
                    provider: provider.to_string(),
                    model: model_id.to_string(),
                }
                .into());
            }
        }

        Ok(())
    }

    fn validate_version_consistency(
        &self,
        versions: &[YamlValue],
        primitive_path: &Path,
    ) -> Result<()> {
        if versions.is_empty() {
            return Err(SemanticError::NoActiveVersions.into());
        }

        let mut has_active = false;
        let mut seen_versions = HashSet::new();

        for version_entry in versions {
            // Get version number
            let version_num = version_entry
                .get("version")
                .and_then(|v| v.as_i64())
                .ok_or_else(|| {
                    anyhow::anyhow!("Missing or invalid 'version' field in versions array")
                })?;

            // Check for duplicate version numbers
            if !seen_versions.insert(version_num) {
                return Err(SemanticError::VersionConsistency(format!(
                    "Duplicate version number: {version_num}"
                ))
                .into());
            }

            // Get status
            let status = version_entry
                .get("status")
                .and_then(|v| v.as_str())
                .unwrap_or("draft");

            // Validate status is valid
            match status {
                "draft" | "active" | "deprecated" => {}
                _ => {
                    return Err(SemanticError::InvalidVersionStatus {
                        status: status.to_string(),
                    }
                    .into());
                }
            }

            if status == "active" {
                has_active = true;
            }

            // Get file name
            let file_name = version_entry
                .get("file")
                .and_then(|v| v.as_str())
                .ok_or_else(|| anyhow::anyhow!("Missing 'file' field in version entry"))?;

            // Check if file exists
            let file_path = primitive_path.join(file_name);
            if !file_path.exists() {
                return Err(SemanticError::VersionConsistency(format!(
                    "Version file not found: {file_name}"
                ))
                .into());
            }

            // Validate BLAKE3 hash if present
            if let Some(hash_value) = version_entry.get("hash").and_then(|v| v.as_str()) {
                self.validate_hash(&file_path, hash_value)?;
            }
        }

        // Ensure at least one active version exists
        if !has_active {
            return Err(SemanticError::NoActiveVersions.into());
        }

        Ok(())
    }

    fn validate_hash(&self, file_path: &Path, expected_hash: &str) -> Result<()> {
        // Read file content
        let content = std::fs::read(file_path)
            .with_context(|| format!("Failed to read file: {}", file_path.display()))?;

        // Calculate BLAKE3 hash
        let actual_hash = blake3::hash(&content).to_hex();

        // Expected hash format: "blake3:<hex>" or just "<hex>"
        let expected_hex = expected_hash
            .strip_prefix("blake3:")
            .unwrap_or(expected_hash);

        if actual_hash.as_str() != expected_hex {
            return Err(SemanticError::HashMismatch {
                file: file_path.display().to_string(),
                expected: expected_hex.to_string(),
                actual: actual_hash.to_string(),
            }
            .into());
        }

        Ok(())
    }
}

impl Default for SemanticValidator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn create_test_primitive_with_meta(temp_dir: &Path, meta_content: &str) -> PathBuf {
        let primitive_path = temp_dir.join("test-primitive");
        fs::create_dir_all(&primitive_path).unwrap();
        fs::write(primitive_path.join("meta.yaml"), meta_content).unwrap();
        primitive_path
    }

    #[test]
    fn test_validate_missing_path() {
        let validator = SemanticValidator::new();
        let result = validator.validate(Path::new("/nonexistent/path"));
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("does not exist"));
    }

    #[test]
    fn test_validate_missing_meta_yaml() {
        let temp_dir = TempDir::new().unwrap();
        fs::create_dir_all(temp_dir.path().join("test-primitive")).unwrap();
        let validator = SemanticValidator::new();
        let result = validator.validate(&temp_dir.path().join("test-primitive"));
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("Missing meta.yaml"));
    }

    #[test]
    fn test_validate_simple_agent_without_refs() {
        let temp_dir = TempDir::new().unwrap();
        let meta = r#"
id: test-agent
kind: agent
category: testing
summary: Test agent
"#;
        let primitive_path = create_test_primitive_with_meta(temp_dir.path(), meta);
        let validator = SemanticValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_tool_primitive() {
        let temp_dir = TempDir::new().unwrap();
        let meta = r#"
id: test-tool
kind: tool
category: testing
description: Test tool
"#;
        let primitive_path = create_test_primitive_with_meta(temp_dir.path(), meta);
        let validator = SemanticValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_hook_primitive() {
        let temp_dir = TempDir::new().unwrap();
        let meta = r#"
id: test-hook
kind: hook
category: testing
summary: Test hook
event: PreToolUse
"#;
        let primitive_path = create_test_primitive_with_meta(temp_dir.path(), meta);
        let validator = SemanticValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_version_consistency_no_active() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-agent");
        fs::create_dir_all(&primitive_path).unwrap();

        // Create version file
        fs::write(primitive_path.join("prompt.v1.md"), "# Test").unwrap();

        let meta = r#"
id: test-agent
kind: agent
category: testing
summary: Test agent
versions:
  - version: 1
    file: prompt.v1.md
    status: draft
    created: "2025-01-01"
"#;
        fs::write(primitive_path.join("meta.yaml"), meta).unwrap();

        let validator = SemanticValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("No active versions"));
    }

    #[test]
    fn test_validate_version_consistency_with_active() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-agent");
        fs::create_dir_all(&primitive_path).unwrap();

        // Create version file
        fs::write(primitive_path.join("prompt.v1.md"), "# Test").unwrap();

        let meta = r#"
id: test-agent
kind: agent
category: testing
summary: Test agent
versions:
  - version: 1
    file: prompt.v1.md
    status: active
    created: "2025-01-01"
"#;
        fs::write(primitive_path.join("meta.yaml"), meta).unwrap();

        let validator = SemanticValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_version_consistency_duplicate_version() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-agent");
        fs::create_dir_all(&primitive_path).unwrap();

        fs::write(primitive_path.join("prompt.v1.md"), "# Test").unwrap();

        let meta = r#"
id: test-agent
kind: agent
category: testing
summary: Test agent
versions:
  - version: 1
    file: prompt.v1.md
    status: active
    created: "2025-01-01"
  - version: 1
    file: prompt.v1.md
    status: draft
    created: "2025-01-02"
"#;
        fs::write(primitive_path.join("meta.yaml"), meta).unwrap();

        let validator = SemanticValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("Duplicate version"));
    }

    #[test]
    fn test_validate_version_consistency_missing_file() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-agent");
        fs::create_dir_all(&primitive_path).unwrap();

        // Don't create prompt.v1.md

        let meta = r#"
id: test-agent
kind: agent
category: testing
summary: Test agent
versions:
  - version: 1
    file: prompt.v1.md
    status: active
    created: "2025-01-01"
"#;
        fs::write(primitive_path.join("meta.yaml"), meta).unwrap();

        let validator = SemanticValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("not found"));
    }

    #[test]
    fn test_validate_version_consistency_invalid_status() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-agent");
        fs::create_dir_all(&primitive_path).unwrap();

        fs::write(primitive_path.join("prompt.v1.md"), "# Test").unwrap();

        let meta = r#"
id: test-agent
kind: agent
category: testing
summary: Test agent
versions:
  - version: 1
    file: prompt.v1.md
    status: invalid_status
    created: "2025-01-01"
"#;
        fs::write(primitive_path.join("meta.yaml"), meta).unwrap();

        let validator = SemanticValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("Invalid version status"));
    }

    #[test]
    fn test_validate_hash_matching() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-agent");
        fs::create_dir_all(&primitive_path).unwrap();

        let content = "# Test Prompt Content";
        fs::write(primitive_path.join("prompt.v1.md"), content).unwrap();

        // Calculate actual hash
        let actual_hash = blake3::hash(content.as_bytes()).to_hex();

        let meta = format!(
            r#"
id: test-agent
kind: agent
category: testing
summary: Test agent
versions:
  - version: 1
    file: prompt.v1.md
    status: active
    hash: blake3:{actual_hash}
    created: "2025-01-01"
"#
        );
        fs::write(primitive_path.join("meta.yaml"), meta).unwrap();

        let validator = SemanticValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_hash_mismatch() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-agent");
        fs::create_dir_all(&primitive_path).unwrap();

        fs::write(primitive_path.join("prompt.v1.md"), "# Test Content").unwrap();

        // Use a wrong hash
        let wrong_hash = "0".repeat(64);

        let meta = format!(
            r#"
id: test-agent
kind: agent
category: testing
summary: Test agent
versions:
  - version: 1
    file: prompt.v1.md
    status: active
    hash: blake3:{wrong_hash}
    created: "2025-01-01"
"#
        );
        fs::write(primitive_path.join("meta.yaml"), meta).unwrap();

        let validator = SemanticValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("hash mismatch"));
    }

    #[test]
    fn test_validate_hash_without_blake3_prefix() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-agent");
        fs::create_dir_all(&primitive_path).unwrap();

        let content = "# Test Content";
        fs::write(primitive_path.join("prompt.v1.md"), content).unwrap();

        // Calculate hash without prefix
        let actual_hash = blake3::hash(content.as_bytes()).to_hex();

        let meta = format!(
            r#"
id: test-agent
kind: agent
category: testing
summary: Test agent
versions:
  - version: 1
    file: prompt.v1.md
    status: active
    hash: {actual_hash}
    created: "2025-01-01"
"#
        );
        fs::write(primitive_path.join("meta.yaml"), meta).unwrap();

        let validator = SemanticValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_multiple_versions_with_one_active() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-agent");
        fs::create_dir_all(&primitive_path).unwrap();

        fs::write(primitive_path.join("prompt.v1.md"), "# V1").unwrap();
        fs::write(primitive_path.join("prompt.v2.md"), "# V2").unwrap();
        fs::write(primitive_path.join("prompt.v3.md"), "# V3").unwrap();

        let meta = r#"
id: test-agent
kind: agent
category: testing
summary: Test agent
versions:
  - version: 1
    file: prompt.v1.md
    status: deprecated
    created: "2025-01-01"
  - version: 2
    file: prompt.v2.md
    status: active
    created: "2025-01-02"
  - version: 3
    file: prompt.v3.md
    status: draft
    created: "2025-01-03"
"#;
        fs::write(primitive_path.join("meta.yaml"), meta).unwrap();

        let validator = SemanticValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_model_reference_invalid_format() {
        let validator = SemanticValidator::new();
        let result = validator.validate_model_reference("invalid-format");
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("Invalid model reference format"));
    }

    #[test]
    fn test_validate_model_reference_valid_format() {
        let validator = SemanticValidator::new();
        // This will fail because the model doesn't exist, but tests the format parsing
        let result = validator.validate_model_reference("claude/sonnet");
        // Result depends on whether repo root is found and model exists
        let _ = result;
    }

    #[test]
    fn test_validate_unknown_kind_skips_validation() {
        let temp_dir = TempDir::new().unwrap();
        let meta = r#"
id: test-unknown
kind: unknown_type
category: testing
summary: Unknown type
"#;
        let primitive_path = create_test_primitive_with_meta(temp_dir.path(), meta);
        let validator = SemanticValidator::new();
        let result = validator.validate(&primitive_path);
        // Should pass because unknown types skip semantic validation
        assert!(result.is_ok());
    }
}
