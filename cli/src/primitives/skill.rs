//! Skill primitive types and operations
//!
//! Skills are versioned, provider-agnostic primitives that define agent capabilities.
//! They are transformed into provider-specific formats during build (e.g., Claude's SKILL.md).

use crate::error::{Error, Result};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Skill metadata structure
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillMeta {
    pub id: String,
    pub kind: String,
    pub category: String,
    #[serde(default)]
    pub domain: Option<String>,
    #[serde(default)]
    pub summary: Option<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub claude: Option<ClaudeSkillConfig>,
    #[serde(default)]
    pub resources: Vec<ResourceRef>,
    #[serde(default)]
    pub tools: Vec<ToolRef>,
    #[serde(default)]
    pub scripts: Vec<ScriptRef>,
    #[serde(default)]
    pub versions: Vec<VersionEntry>,
    #[serde(default)]
    pub default_version: u32,
    #[serde(default)]
    pub targets: SkillTargets,
    #[serde(default)]
    pub defaults: Option<SkillDefaults>,
}

/// Claude Code specific configuration for skills
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClaudeSkillConfig {
    pub name: String,
    pub description: String,
    #[serde(default)]
    pub allowed_tools: Option<Vec<String>>,
}

/// Reference to a resource file
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceRef {
    pub path: String,
    pub description: String,
}

/// Reference to a bundled tool - can be a simple string or a struct
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum ToolRef {
    /// Simple tool reference (just the tool name/ID)
    Simple(String),
    /// Full tool reference with path and description
    Full {
        path: String,
        #[serde(default)]
        description: Option<String>,
    },
}

/// Reference to a script
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScriptRef {
    pub path: String,
    pub description: String,
}

/// Version entry for skill content
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VersionEntry {
    pub version: u32,
    pub file: String,
    pub status: String,
    pub hash: String,
    pub created: String,
    #[serde(default)]
    pub deprecated: Option<String>,
    #[serde(default)]
    pub notes: Option<String>,
}

/// Build targets for skill
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SkillTargets {
    #[serde(default)]
    pub claude: bool,
}

/// Default settings for skill execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillDefaults {
    #[serde(default)]
    pub preferred_models: Vec<String>,
}

/// Complete skill primitive with metadata and path
#[derive(Debug, Clone)]
pub struct SkillPrimitive {
    pub path: PathBuf,
    pub meta: SkillMeta,
}

impl SkillPrimitive {
    /// Load a skill primitive from a directory
    /// Expected structure:
    ///   <primitive_dir>/
    ///     {id}.skill.yaml (preferred) or {id}.meta.yaml (legacy)
    ///     {id}.skill.v{N}.md (content files)
    ///     resources/ (optional)
    ///     tools/ (optional)
    ///     scripts/ (optional)
    pub fn load<P: AsRef<std::path::Path>>(primitive_dir: P) -> Result<Self> {
        let primitive_dir = primitive_dir.as_ref();

        if !primitive_dir.exists() {
            return Err(Error::NotFound(format!(
                "Skill directory not found: {}",
                primitive_dir.display()
            )));
        }

        // Try {id}.skill.yaml first (new pattern), then {id}.meta.yaml (legacy)
        let meta_path = if let Some(dir_name) = primitive_dir.file_name().and_then(|n| n.to_str()) {
            let skill_yaml_path = primitive_dir.join(format!("{dir_name}.skill.yaml"));
            if skill_yaml_path.exists() {
                skill_yaml_path
            } else {
                // Fall back to legacy {id}.meta.yaml
                let meta_yaml_path = primitive_dir.join(format!("{dir_name}.meta.yaml"));
                if meta_yaml_path.exists() {
                    meta_yaml_path
                } else {
                    // Try meta.yaml as last resort
                    primitive_dir.join("meta.yaml")
                }
            }
        } else {
            primitive_dir.join("meta.yaml")
        };

        if !meta_path.exists() {
            return Err(Error::NotFound(format!(
                "Skill meta file not found in {} (tried {{id}}.skill.yaml, {{id}}.meta.yaml, meta.yaml)",
                primitive_dir.display()
            )));
        }

        let meta_content = std::fs::read_to_string(&meta_path)?;
        let meta: SkillMeta = serde_yaml::from_str(&meta_content)?;

        Ok(Self {
            path: primitive_dir.to_path_buf(),
            meta,
        })
    }

    /// Get the content file path for the default version
    pub fn get_content_path(&self) -> PathBuf {
        let version = self.meta.default_version;
        // Try new naming convention first: {id}.skill.v{N}.md
        let new_path = self
            .path
            .join(format!("{}.skill.v{}.md", self.meta.id, version));
        if new_path.exists() {
            return new_path;
        }

        // Fall back to legacy naming: {id}.prompt.v{N}.md or {id}.v{N}.md
        let legacy_prompt_path = self
            .path
            .join(format!("{}.prompt.v{}.md", self.meta.id, version));
        if legacy_prompt_path.exists() {
            return legacy_prompt_path;
        }

        self.path.join(format!("{}.v{}.md", self.meta.id, version))
    }

    /// Check if this skill has resources
    pub fn has_resources(&self) -> bool {
        self.path.join("resources").exists()
    }

    /// Check if this skill has bundled tools
    pub fn has_tools(&self) -> bool {
        self.path.join("tools").exists()
    }

    /// Check if this skill has scripts
    pub fn has_scripts(&self) -> bool {
        self.path.join("scripts").exists()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deserialize_skill_meta_minimal() {
        let yaml = r#"
id: test-skill
kind: skill
category: testing
"#;
        let meta: SkillMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.id, "test-skill");
        assert_eq!(meta.kind, "skill");
        assert_eq!(meta.category, "testing");
        assert!(meta.claude.is_none());
        assert!(meta.resources.is_empty());
    }

    #[test]
    fn test_deserialize_skill_meta_with_claude_config() {
        let yaml = r#"
id: prioritize
kind: skill
category: review

claude:
  name: prioritize
  description: Prioritize review comments by severity.
  allowed_tools:
    - Read
    - Grep
"#;
        let meta: SkillMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.id, "prioritize");

        let claude = meta.claude.expect("claude config should exist");
        assert_eq!(claude.name, "prioritize");
        assert!(claude.description.contains("Prioritize"));
        assert_eq!(
            claude.allowed_tools,
            Some(vec!["Read".to_string(), "Grep".to_string()])
        );
    }

    #[test]
    fn test_deserialize_skill_meta_with_resources() {
        let yaml = r#"
id: my-skill
kind: skill
category: test

resources:
  - path: resources/guide.md
    description: "Usage guide"
  - path: resources/patterns.json
    description: "Pattern definitions"
"#;
        let meta: SkillMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.resources.len(), 2);
        assert_eq!(meta.resources[0].path, "resources/guide.md");
        assert_eq!(meta.resources[0].description, "Usage guide");
    }

    #[test]
    fn test_deserialize_skill_meta_with_versions() {
        let yaml = r#"
id: versioned-skill
kind: skill
category: test

versions:
  - version: 1
    file: versioned-skill.skill.v1.md
    status: active
    hash: "blake3:abc123"
    created: "2025-12-09"
    notes: "Initial version"
  - version: 2
    file: versioned-skill.skill.v2.md
    status: draft
    hash: "blake3:def456"
    created: "2025-12-10"

default_version: 1
"#;
        let meta: SkillMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.versions.len(), 2);
        assert_eq!(meta.default_version, 1);
        assert_eq!(meta.versions[0].version, 1);
        assert_eq!(meta.versions[0].status, "active");
    }

    #[test]
    fn test_deserialize_skill_meta_with_tools_full() {
        let yaml = r#"
id: tool-skill
kind: skill
category: test

tools:
  - path: tools/comment-parser
    description: "Parse review comments"
"#;
        let meta: SkillMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.tools.len(), 1);
        match &meta.tools[0] {
            ToolRef::Full {
                path,
                description: _,
            } => assert_eq!(path, "tools/comment-parser"),
            ToolRef::Simple(_) => panic!("Expected Full variant"),
        }
    }

    #[test]
    fn test_deserialize_skill_meta_with_tools_simple() {
        let yaml = r#"
id: tool-skill
kind: skill
category: test

tools:
  - Read
  - Grep
"#;
        let meta: SkillMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.tools.len(), 2);
        match &meta.tools[0] {
            ToolRef::Simple(name) => assert_eq!(name, "Read"),
            ToolRef::Full { .. } => panic!("Expected Simple variant"),
        }
    }

    #[test]
    fn test_deserialize_skill_meta_with_scripts() {
        let yaml = r#"
id: script-skill
kind: skill
category: test

scripts:
  - path: scripts/fetch-data.sh
    description: "Fetch data from API"
"#;
        let meta: SkillMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.scripts.len(), 1);
        assert_eq!(meta.scripts[0].path, "scripts/fetch-data.sh");
    }

    #[test]
    fn test_deserialize_skill_meta_with_targets() {
        let yaml = r#"
id: targeted-skill
kind: skill
category: test

targets:
  claude: true
"#;
        let meta: SkillMeta = serde_yaml::from_str(yaml).unwrap();
        assert!(meta.targets.claude);
    }

    #[test]
    fn test_deserialize_skill_meta_legacy_format() {
        // Test parsing the existing prioritize skill format
        let yaml = r#"
id: prioritize
kind: skill
category: review
domain: code-review
summary: "Prioritize review comments by severity: security > logic > style"
tags:
  - review
  - triage
defaults:
  preferred_models:
    - claude/sonnet
tools:
  - Read
versions:
  - version: 1
    file: prioritize.prompt.v1.md
    hash: "blake3:722de9b..."
    status: active
    created: "2025-12-06"
default_version: 1
"#;
        let meta: SkillMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.id, "prioritize");
        assert_eq!(meta.domain, Some("code-review".to_string()));
        assert!(meta.summary.is_some());
        assert_eq!(meta.tags.len(), 2);
        assert!(meta.defaults.is_some());
    }

    #[test]
    fn test_load_skill_nonexistent_dir() {
        let result = SkillPrimitive::load("/nonexistent/directory");
        assert!(result.is_err());
    }

    #[test]
    fn test_default_targets() {
        let yaml = r#"
id: test-skill
kind: skill
category: testing
"#;
        let meta: SkillMeta = serde_yaml::from_str(yaml).unwrap();
        // Default targets should have claude: false
        assert!(!meta.targets.claude);
    }
}
