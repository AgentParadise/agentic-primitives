use crate::error::Result;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// Main configuration for the agentic-primitives repository
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PrimitivesConfig {
    pub version: String,
    pub paths: PathsConfig,
    pub validation: ValidationConfig,
    #[serde(default)]
    pub defaults: DefaultsConfig,
}

/// Directory paths configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PathsConfig {
    #[serde(default = "default_specs_path")]
    pub specs: PathBuf,
    #[serde(default = "default_primitives_path")]
    pub primitives: PathBuf,
    #[serde(default = "default_experimental_path")]
    pub experimental: PathBuf,
    #[serde(default = "default_providers_path")]
    pub providers: PathBuf,
    #[serde(default = "default_cli_path")]
    pub cli: PathBuf,
    #[serde(default = "default_docs_path")]
    pub docs: PathBuf,
}

/// Validation settings
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ValidationConfig {
    #[serde(default)]
    pub required_fields: Vec<String>,
    #[serde(default = "default_id_pattern")]
    pub id_pattern: String,
    #[serde(default = "default_version_pattern")]
    pub version_pattern: String,
    #[serde(default)]
    pub enforce_category: bool,
    #[serde(default = "default_max_summary_length")]
    pub max_summary_length: usize,
}

/// Default values configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DefaultsConfig {
    #[serde(default = "default_prompt_kind")]
    pub prompt_kind: String,
    #[serde(default = "default_tool_kind")]
    pub tool_kind: String,
    #[serde(default = "default_hook_event")]
    pub hook_event: String,
    #[serde(default = "default_execution_strategy")]
    pub execution_strategy: String,
}

impl Default for DefaultsConfig {
    fn default() -> Self {
        Self {
            prompt_kind: default_prompt_kind(),
            tool_kind: default_tool_kind(),
            hook_event: default_hook_event(),
            execution_strategy: default_execution_strategy(),
        }
    }
}

// Default value functions for serde
fn default_specs_path() -> PathBuf {
    PathBuf::from("specs/v1")
}

fn default_primitives_path() -> PathBuf {
    PathBuf::from("primitives/v1")
}

fn default_experimental_path() -> PathBuf {
    PathBuf::from("primitives/experimental")
}

fn default_providers_path() -> PathBuf {
    PathBuf::from("providers")
}

fn default_cli_path() -> PathBuf {
    PathBuf::from("cli")
}

fn default_docs_path() -> PathBuf {
    PathBuf::from("docs")
}

fn default_id_pattern() -> String {
    "^[a-z0-9]+(-[a-z0-9]+)*$".to_string()
}

fn default_version_pattern() -> String {
    "^v?\\d+\\.\\d+\\.\\d+$".to_string()
}

fn default_max_summary_length() -> usize {
    500
}

fn default_prompt_kind() -> String {
    "skill".to_string()
}

fn default_tool_kind() -> String {
    "tool".to_string()
}

fn default_hook_event() -> String {
    "PreToolUse".to_string()
}

fn default_execution_strategy() -> String {
    "pipeline".to_string()
}

impl PrimitivesConfig {
    /// Load configuration from a specific path
    pub fn load<P: AsRef<Path>>(path: P) -> Result<Self> {
        let path = path.as_ref();
        let content = std::fs::read_to_string(path).map_err(|e| {
            crate::error::Error::NotFound(format!(
                "Config file not found at {}: {}",
                path.display(),
                e
            ))
        })?;

        let config: Self = serde_yaml::from_str(&content)?;
        Ok(config)
    }

    /// Load configuration from current directory or parent directories
    /// Searches upward like git does for .git directory
    pub fn load_from_current_dir() -> Result<Self> {
        let current_dir = std::env::current_dir()?;
        let mut search_dir = current_dir.as_path();

        loop {
            let config_path = search_dir.join("primitives.config.yaml");
            if config_path.exists() {
                return Self::load(config_path);
            }

            // Move to parent directory
            match search_dir.parent() {
                Some(parent) => search_dir = parent,
                None => break,
            }
        }

        Err(crate::error::Error::NotFound(
            "primitives.config.yaml not found in current directory or any parent directory"
                .to_string(),
        ))
    }

    /// Get default configuration for testing or init command
    pub fn get_default() -> Self {
        Self::default()
    }
}

impl Default for PrimitivesConfig {
    fn default() -> Self {
        Self {
            version: "1.0".to_string(),
            paths: PathsConfig {
                specs: default_specs_path(),
                primitives: default_primitives_path(),
                experimental: default_experimental_path(),
                providers: default_providers_path(),
                cli: default_cli_path(),
                docs: default_docs_path(),
            },
            validation: ValidationConfig {
                required_fields: vec![],
                id_pattern: default_id_pattern(),
                version_pattern: default_version_pattern(),
                enforce_category: true,
                max_summary_length: default_max_summary_length(),
            },
            defaults: DefaultsConfig::default(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_load_config() {
        let config_yaml = r#"
version: "1.0"
paths:
  specs: "specs/v1"
  primitives: "primitives/v1"
  experimental: "primitives/experimental"
  providers: "providers"
  cli: "cli"
  docs: "docs"
validation:
  required_fields: ["id", "kind"]
  id_pattern: "^[a-z0-9-]+$"
  version_pattern: "^v?\\d+\\.\\d+\\.\\d+$"
  enforce_category: true
  max_summary_length: 500
defaults:
  prompt_kind: "skill"
  tool_kind: "tool"
  hook_event: "PreToolUse"
  execution_strategy: "pipeline"
"#;

        let mut temp_file = NamedTempFile::new().unwrap();
        temp_file.write_all(config_yaml.as_bytes()).unwrap();

        let config = PrimitivesConfig::load(temp_file.path()).unwrap();

        assert_eq!(config.version, "1.0");
        assert_eq!(config.paths.specs, PathBuf::from("specs/v1"));
        assert_eq!(config.paths.primitives, PathBuf::from("primitives/v1"));
        assert_eq!(config.validation.max_summary_length, 500);
        assert!(config.validation.enforce_category);
        assert_eq!(config.defaults.prompt_kind, "skill");
    }

    #[test]
    fn test_config_defaults() {
        let config = PrimitivesConfig::default();

        assert_eq!(config.version, "1.0");
        assert_eq!(config.paths.primitives, PathBuf::from("primitives/v1"));
        assert_eq!(config.validation.max_summary_length, 500);
        assert_eq!(config.defaults.prompt_kind, "skill");
        assert_eq!(config.defaults.execution_strategy, "pipeline");
    }

    #[test]
    fn test_load_nonexistent_file() {
        let result = PrimitivesConfig::load("/nonexistent/path/config.yaml");
        assert!(result.is_err());
    }

    #[test]
    fn test_load_invalid_yaml() {
        let invalid_yaml = "this is not: valid: yaml: content";

        let mut temp_file = NamedTempFile::new().unwrap();
        temp_file.write_all(invalid_yaml.as_bytes()).unwrap();

        let result = PrimitivesConfig::load(temp_file.path());
        assert!(result.is_err());
    }

    #[test]
    fn test_minimal_config() {
        let minimal_yaml = r#"
version: "1.0"
paths:
  specs: "specs/v1"
  primitives: "primitives/v1"
  experimental: "primitives/experimental"
  providers: "providers"
  cli: "cli"
  docs: "docs"
validation:
  max_summary_length: 300
"#;

        let mut temp_file = NamedTempFile::new().unwrap();
        temp_file.write_all(minimal_yaml.as_bytes()).unwrap();

        let config = PrimitivesConfig::load(temp_file.path()).unwrap();

        assert_eq!(config.version, "1.0");
        assert_eq!(config.validation.max_summary_length, 300);
        // Defaults should be applied
        assert_eq!(config.defaults.prompt_kind, "skill");
    }
}
