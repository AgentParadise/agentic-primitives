//! Layer 1: Structural validation
//! Validates file structure, naming conventions, required files

use anyhow::{Context, Result};
use serde_yaml::Value;
use std::path::{Path, PathBuf};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum StructuralError {
    #[error("Primitive path does not exist: {0}")]
    PathNotFound(PathBuf),

    #[error("Primitive path is not a directory: {0}")]
    NotADirectory(PathBuf),

    #[error("Missing required file: {file} in {path}")]
    MissingFile { path: PathBuf, file: String },

    #[error("Invalid directory structure: expected {expected}, got {actual}")]
    InvalidStructure { expected: String, actual: String },

    #[error("ID mismatch: folder name is '{folder}' but meta.yaml has '{meta_id}'")]
    IdMismatch { folder: String, meta_id: String },

    #[error("Non-kebab-case identifier: '{value}' in {context}")]
    NonKebabCase { value: String, context: String },

    #[error("No version files found (at least one <id>.vN.md file required, where <id> matches directory name)")]
    NoVersionFiles,

    #[error("Invalid primitive type: {0}")]
    InvalidType(String),
}

pub struct StructuralValidator;

impl StructuralValidator {
    pub fn new() -> Self {
        Self
    }

    /// Validate a primitive's structural correctness
    pub fn validate(&self, primitive_path: &Path) -> Result<()> {
        // Check if path exists
        if !primitive_path.exists() {
            return Err(StructuralError::PathNotFound(primitive_path.to_path_buf()).into());
        }

        // Check if it's a directory
        if !primitive_path.is_dir() {
            return Err(StructuralError::NotADirectory(primitive_path.to_path_buf()).into());
        }

        // Check for metadata file - try multiple naming conventions
        // Priority: {id}.yaml > {id}.tool.yaml > {id}.hook.yaml > meta.yaml (legacy)
        let dir_name = primitive_path
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or_else(|| anyhow::anyhow!("Invalid directory name"))?;

        // Try to find metadata file (prioritize new naming convention)
        let meta_path = [
            format!("{dir_name}.yaml"),      // Prompt: {id}.yaml
            format!("{dir_name}.tool.yaml"), // Tool: {id}.tool.yaml
            format!("{dir_name}.hook.yaml"), // Hook: {id}.hook.yaml
            "meta.yaml".to_string(),           // Legacy prompt
            "tool.meta.yaml".to_string(),      // Legacy tool
            "hook.meta.yaml".to_string(),      // Legacy hook
        ]
        .iter()
        .map(|f| primitive_path.join(f))
        .find(|p| p.exists())
        .ok_or_else(|| StructuralError::MissingFile {
            path: primitive_path.to_path_buf(),
            file: format!(
                "{dir_name}.yaml, {dir_name}.tool.yaml, {dir_name}.hook.yaml, or meta.yaml"
            ),
        })?;

        // Parse metadata file to get primitive type and ID
        let meta_content = std::fs::read_to_string(&meta_path)
            .with_context(|| format!("Failed to read metadata from {}", meta_path.display()))?;

        let meta: Value = serde_yaml::from_str(&meta_content)
            .with_context(|| format!("Failed to parse meta.yaml from {}", meta_path.display()))?;

        // Get ID from meta.yaml
        let meta_id = meta
            .get("id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing or invalid 'id' field in meta.yaml"))?;

        // Get kind/type
        let kind = meta
            .get("kind")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");

        // Validate ID is kebab-case
        self.validate_kebab_case(meta_id, "meta.yaml id")?;

        // Get folder name
        let folder_name = primitive_path
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or_else(|| anyhow::anyhow!("Invalid folder name"))?;

        // Validate folder name is kebab-case
        self.validate_kebab_case(folder_name, "folder name")?;

        // Check ID matches folder name
        if folder_name != meta_id {
            return Err(StructuralError::IdMismatch {
                folder: folder_name.to_string(),
                meta_id: meta_id.to_string(),
            }
            .into());
        }

        // Validate directory structure based on primitive type
        self.validate_directory_structure(primitive_path)?;

        // Check for required files based on primitive type
        self.check_required_files(primitive_path, kind)?;

        Ok(())
    }

    /// Validate that a string is in kebab-case
    fn validate_kebab_case(&self, value: &str, context: &str) -> Result<()> {
        // Kebab-case: lowercase letters, numbers, and hyphens only
        // Must start with a letter, no consecutive hyphens
        let is_kebab = value
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
            && value.starts_with(|c: char| c.is_ascii_lowercase())
            && !value.contains("--");

        if !is_kebab {
            return Err(StructuralError::NonKebabCase {
                value: value.to_string(),
                context: context.to_string(),
            }
            .into());
        }

        Ok(())
    }

    /// Validate directory structure matches expected pattern
    fn validate_directory_structure(&self, primitive_path: &Path) -> Result<()> {
        // Expected: primitives/v1/<type>/<category>/<id>/
        // We need to check that we're in the right structure

        let path_str = primitive_path.to_string_lossy();

        // Check if path contains v1 or experimental (but be lenient for test scenarios)
        // If path doesn't contain either, we skip deep structure validation
        let has_version_structure =
            path_str.contains("/v1/") || path_str.contains("/experimental/");

        if !has_version_structure {
            // Skip detailed structure validation - likely a test or non-standard layout
            return Ok(());
        }

        // Get parent and grandparent to validate structure
        if let Some(parent) = primitive_path.parent() {
            // parent should be the category
            if let Some(category_name) = parent.file_name().and_then(|n| n.to_str()) {
                self.validate_kebab_case(category_name, "category name")?;
            }

            // grandparent should be the type (prompts, tools, hooks)
            if let Some(grandparent) = parent.parent() {
                if let Some(type_name) = grandparent.file_name().and_then(|n| n.to_str()) {
                    // For prompts, we have an additional level (agents, commands, skills, meta-prompts)
                    // So we need to check great-grandparent
                    match type_name {
                        "agents" | "commands" | "skills" | "meta-prompts" => {
                            // These should have "prompts" as great-grandparent
                            if let Some(great_grandparent) = grandparent.parent() {
                                if let Some(gp_name) =
                                    great_grandparent.file_name().and_then(|n| n.to_str())
                                {
                                    if gp_name != "prompts" {
                                        return Err(StructuralError::InvalidStructure {
                                            expected: format!("primitives/v1/prompts/{type_name}/<category>/<id>/"),
                                            actual: path_str.to_string(),
                                        }
                                        .into());
                                    }
                                }
                            }
                        }
                        "tools" | "hooks" => {
                            // These are directly under v1
                        }
                        _ => {
                            // Could be valid for experimental
                        }
                    }
                }
            }
        }

        Ok(())
    }

    /// Check for required files based on primitive type
    fn check_required_files(&self, primitive_path: &Path, kind: &str) -> Result<()> {
        match kind {
            "agent" | "command" | "skill" | "meta-prompt" => {
                // Get the directory name (which should match the ID)
                let dir_name = primitive_path
                    .file_name()
                    .and_then(|n| n.to_str())
                    .context("Invalid primitive directory name")?;

                // Prompts require at least one version file matching pattern:
                // {id}.prompt.v{N}.md (new) or {id}.v{N}.md (legacy)
                let has_version_file = std::fs::read_dir(primitive_path)?
                    .filter_map(|e| e.ok())
                    .any(|e| {
                        let filename = e.file_name().to_string_lossy().to_string();
                        (filename.starts_with(&format!("{dir_name}.prompt.v"))
                            || filename.starts_with(&format!("{dir_name}.v")))
                            && filename.ends_with(".md")
                    });

                if !has_version_file {
                    return Err(StructuralError::NoVersionFiles.into());
                }
            }
            "tool" => {
                // Tools require {id}.tool.yaml or tool.meta.yaml (legacy)
                let dir_name = primitive_path
                    .file_name()
                    .and_then(|n| n.to_str())
                    .context("Invalid tool directory name")?;

                let new_tool_meta = primitive_path.join(format!("{dir_name}.tool.yaml"));
                let legacy_tool_meta = primitive_path.join("tool.meta.yaml");

                if !new_tool_meta.exists() && !legacy_tool_meta.exists() {
                    return Err(StructuralError::MissingFile {
                        path: primitive_path.to_path_buf(),
                        file: format!("{dir_name}.tool.yaml or tool.meta.yaml"),
                    }
                    .into());
                }
            }
            "hook" => {
                // Hooks require {id}.hook.yaml or hook.meta.yaml (legacy)
                let dir_name = primitive_path
                    .file_name()
                    .and_then(|n| n.to_str())
                    .context("Invalid hook directory name")?;

                let new_hook_meta = primitive_path.join(format!("{dir_name}.hook.yaml"));
                let legacy_hook_meta = primitive_path.join("hook.meta.yaml");

                if !new_hook_meta.exists() && !legacy_hook_meta.exists() {
                    return Err(StructuralError::MissingFile {
                        path: primitive_path.to_path_buf(),
                        file: format!("{dir_name}.hook.yaml or hook.meta.yaml"),
                    }
                    .into());
                }
            }
            _ => {
                // Unknown type - might be experimental
            }
        }

        Ok(())
    }
}

impl Default for StructuralValidator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn create_test_primitive(temp_dir: &Path, id: &str, kind: &str) -> PathBuf {
        let primitive_path = temp_dir.join(id);
        fs::create_dir_all(&primitive_path).unwrap();

        let meta_content = format!(
            "id: {id}\nkind: {kind}\nsummary: Test primitive\ncategory: test\ndomain: testing"
        );
        fs::write(primitive_path.join("meta.yaml"), meta_content).unwrap();

        // Create version file for prompts (filename must match directory name)
        if matches!(kind, "agent" | "command" | "skill" | "meta-prompt") {
            let version_file = format!("{id}.v1.md");
            fs::write(primitive_path.join(version_file), "# Test Prompt").unwrap();
        }

        primitive_path
    }

    #[test]
    fn test_validate_missing_directory() {
        let validator = StructuralValidator::new();
        let result = validator.validate(Path::new("/nonexistent/path"));
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("does not exist"));
    }

    #[test]
    fn test_validate_not_a_directory() {
        let temp_dir = TempDir::new().unwrap();
        let file_path = temp_dir.path().join("not_a_dir.txt");
        fs::write(&file_path, "content").unwrap();

        let validator = StructuralValidator::new();
        let result = validator.validate(&file_path);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("not a directory"));
    }

    #[test]
    fn test_validate_missing_meta_yaml() {
        let temp_dir = TempDir::new().unwrap();
        let validator = StructuralValidator::new();
        let result = validator.validate(temp_dir.path());
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("meta.yaml"));
    }

    #[test]
    fn test_validate_valid_agent_structure() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = create_test_primitive(temp_dir.path(), "test-agent", "agent");

        let validator = StructuralValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_valid_command_structure() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = create_test_primitive(temp_dir.path(), "test-command", "command");

        let validator = StructuralValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_kebab_case_valid() {
        let validator = StructuralValidator::new();
        assert!(validator.validate_kebab_case("valid-name", "test").is_ok());
        assert!(validator.validate_kebab_case("test123", "test").is_ok());
        assert!(validator
            .validate_kebab_case("test-name-123", "test")
            .is_ok());
    }

    #[test]
    fn test_validate_kebab_case_invalid_uppercase() {
        let validator = StructuralValidator::new();
        let result = validator.validate_kebab_case("InvalidName", "test");
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("Non-kebab-case"));
    }

    #[test]
    fn test_validate_kebab_case_invalid_underscore() {
        let validator = StructuralValidator::new();
        let result = validator.validate_kebab_case("invalid_name", "test");
        assert!(result.is_err());
    }

    #[test]
    fn test_validate_kebab_case_invalid_double_hyphen() {
        let validator = StructuralValidator::new();
        let result = validator.validate_kebab_case("invalid--name", "test");
        assert!(result.is_err());
    }

    #[test]
    fn test_validate_kebab_case_invalid_starts_with_number() {
        let validator = StructuralValidator::new();
        let result = validator.validate_kebab_case("123-invalid", "test");
        assert!(result.is_err());
    }

    #[test]
    fn test_validate_id_mismatch() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("folder-name");
        fs::create_dir_all(&primitive_path).unwrap();

        // Create meta.yaml with different ID
        fs::write(
            primitive_path.join("meta.yaml"),
            "id: different-id\nkind: agent\nsummary: Test\ncategory: test\ndomain: testing",
        )
        .unwrap();
        // Filename must match folder name (folder-name.v1.md)
        fs::write(primitive_path.join("folder-name.v1.md"), "# Test").unwrap();

        let validator = StructuralValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("ID mismatch"));
    }

    #[test]
    fn test_validate_missing_version_file_for_prompt() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-agent");
        fs::create_dir_all(&primitive_path).unwrap();

        fs::write(
            primitive_path.join("meta.yaml"),
            "id: test-agent\nkind: agent\nsummary: Test\ncategory: test\ndomain: testing",
        )
        .unwrap();
        // Don't create test-agent.v1.md (testing missing version file)

        let validator = StructuralValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("No version files"));
    }

    #[test]
    fn test_validate_multiple_version_files() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = create_test_primitive(temp_dir.path(), "test-agent", "agent");

        // Add more version files (must match directory name: test-agent)
        fs::write(primitive_path.join("test-agent.v2.md"), "# Test v2").unwrap();
        fs::write(primitive_path.join("test-agent.v3.md"), "# Test v3").unwrap();

        let validator = StructuralValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_tool_requires_tool_meta_yaml() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-tool");
        fs::create_dir_all(&primitive_path).unwrap();

        fs::write(
            primitive_path.join("meta.yaml"),
            "id: test-tool\nkind: tool\ncategory: test\ndescription: Test tool",
        )
        .unwrap();
        // Don't create tool.meta.yaml

        let validator = StructuralValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("tool.meta.yaml"));
    }

    #[test]
    fn test_validate_hook_requires_hook_meta_yaml() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-hook");
        fs::create_dir_all(&primitive_path).unwrap();

        fs::write(
            primitive_path.join("meta.yaml"),
            "id: test-hook\nkind: hook\ncategory: test\nsummary: Test hook",
        )
        .unwrap();
        // Don't create hook.meta.yaml

        let validator = StructuralValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("hook.meta.yaml"));
    }

    #[test]
    fn test_validate_valid_tool_with_tool_meta() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-tool");
        fs::create_dir_all(&primitive_path).unwrap();

        fs::write(
            primitive_path.join("meta.yaml"),
            "id: test-tool\nkind: tool\ncategory: test\ndescription: Test tool",
        )
        .unwrap();
        fs::write(
            primitive_path.join("tool.meta.yaml"),
            "id: test-tool\nname: Test Tool",
        )
        .unwrap();

        let validator = StructuralValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_valid_hook_with_hook_meta() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-hook");
        fs::create_dir_all(&primitive_path).unwrap();

        fs::write(
            primitive_path.join("meta.yaml"),
            "id: test-hook\nkind: hook\ncategory: test\nsummary: Test hook",
        )
        .unwrap();
        fs::write(
            primitive_path.join("hook.meta.yaml"),
            "id: test-hook\nevent: PreToolUse",
        )
        .unwrap();

        let validator = StructuralValidator::new();
        let result = validator.validate(&primitive_path);
        assert!(result.is_ok());
    }
}
