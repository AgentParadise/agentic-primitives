use crate::error::{Error, Result};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Prompt primitive kinds
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PromptKind {
    Agent,
    Command,
    Skill,
    #[serde(rename = "meta-prompt")]
    MetaPrompt,
}

/// Prompt metadata structure
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptMeta {
    pub id: String,
    pub kind: PromptKind,
    pub category: String,
    pub domain: String,
    pub summary: String,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub defaults: PromptDefaults,
    #[serde(default)]
    pub context_usage: Option<ContextUsage>,
    #[serde(default)]
    pub tools: Vec<String>,
    #[serde(default)]
    pub inputs: Option<InputsSpec>,
    #[serde(default)]
    pub versions: Vec<VersionEntry>,
    #[serde(default)]
    pub default_version: Option<u32>,
}

/// Default configuration for prompts
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PromptDefaults {
    #[serde(default)]
    pub preferred_models: Vec<String>, // "provider/model-id" format
    #[serde(default)]
    pub temperature: Option<f64>,
    #[serde(default)]
    pub max_tokens: Option<u32>,
}

/// How the prompt should be injected into conversation context
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextUsage {
    #[serde(default)]
    pub as_system: bool,
    #[serde(default)]
    pub as_user: bool,
    #[serde(default)]
    pub as_overlay: bool,
}

/// Input parameters specification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InputsSpec {
    #[serde(default)]
    pub required: Vec<InputParam>,
    #[serde(default)]
    pub optional: Vec<InputParam>,
}

/// Individual input parameter
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InputParam {
    pub name: String,
    #[serde(rename = "type")]
    pub param_type: String,
    pub description: String,
    #[serde(default)]
    pub default: Option<serde_json::Value>,
}

/// Version entry (placeholder for Milestone 6, will be expanded)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VersionEntry {
    pub version: u32,
    pub file: String,
    pub status: String,
    pub hash: String,
    pub created: String,
    #[serde(default)]
    pub deprecated: Option<String>,
    pub notes: String,
}

/// Complete prompt primitive with metadata and content
#[derive(Debug, Clone)]
pub struct PromptPrimitive {
    pub path: PathBuf,
    pub meta: PromptMeta,
    pub content: String,
}

impl PromptPrimitive {
    /// Load a prompt primitive from a directory
    /// Expected structure:
    ///   <primitive_dir>/
    ///     <id>.meta.yaml
    ///     <id>.prompt.md (or versioned files like <id>.prompt.v1.md)
    pub fn load<P: AsRef<std::path::Path>>(primitive_dir: P) -> Result<Self> {
        let primitive_dir = primitive_dir.as_ref();

        if !primitive_dir.exists() {
            return Err(Error::NotFound(format!(
                "Primitive directory not found: {}",
                primitive_dir.display()
            )));
        }

        // Find meta file - try new convention first (ADR-019), then legacy patterns
        let dir_name = primitive_dir
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or_else(|| {
                Error::NotFound(format!(
                    "Cannot determine meta file for {}",
                    primitive_dir.display()
                ))
            })?;

        let meta_path = if primitive_dir
            .join(format!("{dir_name}.meta.yaml"))
            .exists()
        {
            // New convention (ADR-019): {id}.meta.yaml
            primitive_dir.join(format!("{dir_name}.meta.yaml"))
        } else if primitive_dir.join(format!("{dir_name}.yaml")).exists() {
            // Legacy: {id}.yaml
            primitive_dir.join(format!("{dir_name}.yaml"))
        } else if primitive_dir.join("meta.yaml").exists() {
            // Legacy: meta.yaml
            primitive_dir.join("meta.yaml")
        } else {
            return Err(Error::NotFound(format!(
                "No metadata file found in {}",
                primitive_dir.display()
            )));
        };

        // Load and parse metadata
        let meta_content = std::fs::read_to_string(&meta_path)?;
        let meta: PromptMeta = serde_yaml::from_str(&meta_content)?;

        // Determine which content file to load
        let content_file = if let Some(default_version) = meta.default_version {
            // Use specific version
            let version_entry = meta
                .versions
                .iter()
                .find(|v| v.version == default_version)
                .ok_or_else(|| {
                    Error::NotFound(format!(
                        "Version {default_version} not found in versions list"
                    ))
                })?;
            version_entry.file.clone()
        } else {
            // Look for unversioned .prompt.md file
            format!("{}.prompt.md", meta.id)
        };

        let content_path = primitive_dir.join(&content_file);
        if !content_path.exists() {
            return Err(Error::NotFound(format!(
                "Content file not found: {}",
                content_path.display()
            )));
        }

        let content = std::fs::read_to_string(&content_path)?;

        Ok(Self {
            path: primitive_dir.to_path_buf(),
            meta,
            content,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deserialize_prompt_meta() {
        let yaml = r#"
id: test-agent
kind: agent
category: testing
domain: test
summary: "A test agent"
context_usage:
  as_system: true
  as_user: false
  as_overlay: false
versions:
  - version: 1
    file: "test-agent.prompt.v1.md"
    status: "draft"
    hash: "blake3:0000000000000000000000000000000000000000000000000000000000000000"
    created: "2025-01-01"
    notes: "Initial version"
default_version: 1
"#;
        let meta: PromptMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.id, "test-agent");
        assert_eq!(meta.kind, PromptKind::Agent);
        assert_eq!(meta.category, "testing");
        assert_eq!(meta.domain, "test");
        assert!(meta.context_usage.is_some());
        assert_eq!(meta.versions.len(), 1);
        assert_eq!(meta.default_version, Some(1));
    }

    #[test]
    fn test_deserialize_prompt_kinds() {
        let agent: PromptKind = serde_yaml::from_str("agent").unwrap();
        assert_eq!(agent, PromptKind::Agent);

        let command: PromptKind = serde_yaml::from_str("command").unwrap();
        assert_eq!(command, PromptKind::Command);

        let skill: PromptKind = serde_yaml::from_str("skill").unwrap();
        assert_eq!(skill, PromptKind::Skill);

        let meta_prompt: PromptKind = serde_yaml::from_str("meta-prompt").unwrap();
        assert_eq!(meta_prompt, PromptKind::MetaPrompt);
    }

    #[test]
    fn test_deserialize_skill_without_versions() {
        let yaml = r#"
id: test-skill
kind: skill
category: testing
domain: test
summary: "A test skill without versioning"
context_usage:
  as_overlay: true
"#;
        let meta: PromptMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.id, "test-skill");
        assert_eq!(meta.kind, PromptKind::Skill);
        assert!(meta.versions.is_empty());
        assert!(meta.default_version.is_none());
    }

    #[test]
    fn test_deserialize_with_defaults() {
        let yaml = r#"
id: test-command
kind: command
category: testing
domain: test
summary: "A test command with defaults"
defaults:
  preferred_models:
    - "claude/sonnet"
    - "openai/gpt-codex"
  temperature: 0.7
  max_tokens: 4096
context_usage:
  as_user: true
"#;
        let meta: PromptMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.defaults.preferred_models.len(), 2);
        assert_eq!(meta.defaults.temperature, Some(0.7));
        assert_eq!(meta.defaults.max_tokens, Some(4096));
    }

    #[test]
    fn test_deserialize_with_inputs() {
        let yaml = r#"
id: test-command
kind: command
category: testing
domain: test
summary: "A test command with inputs"
inputs:
  required:
    - name: "file_path"
      type: "string"
      description: "Path to the file"
  optional:
    - name: "verbose"
      type: "boolean"
      description: "Enable verbose output"
      default: false
"#;
        let meta: PromptMeta = serde_yaml::from_str(yaml).unwrap();
        let inputs = meta.inputs.unwrap();
        assert_eq!(inputs.required.len(), 1);
        assert_eq!(inputs.required[0].name, "file_path");
        assert_eq!(inputs.optional.len(), 1);
        assert_eq!(inputs.optional[0].name, "verbose");
    }

    #[test]
    fn test_deserialize_with_tools() {
        let yaml = r#"
id: test-agent
kind: agent
category: testing
domain: test
summary: "A test agent with tools"
tools:
  - "run-tests"
  - "search-code"
  - "format-code"
"#;
        let meta: PromptMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.tools.len(), 3);
        assert!(meta.tools.contains(&"run-tests".to_string()));
    }

    #[test]
    fn test_deserialize_with_tags() {
        let yaml = r#"
id: test-agent
kind: agent
category: testing
domain: test
summary: "A test agent with tags"
tags:
  - "python"
  - "backend"
  - "testing"
"#;
        let meta: PromptMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.tags.len(), 3);
        assert!(meta.tags.contains(&"python".to_string()));
    }

    #[test]
    fn test_load_primitive_nonexistent_dir() {
        let result = PromptPrimitive::load("/nonexistent/directory");
        assert!(result.is_err());
    }
}
