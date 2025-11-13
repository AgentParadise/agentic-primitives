use crate::error::{Error, Result};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Tool metadata structure
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolMeta {
    pub id: String,
    pub kind: String,
    pub category: String,
    pub description: String,
    #[serde(default)]
    pub args: Vec<ToolArg>,
    #[serde(default)]
    pub returns: Option<ToolReturns>,
    #[serde(default)]
    pub safety: ToolSafety,
    #[serde(default)]
    pub providers: Option<serde_json::Value>,
    #[serde(default)]
    pub examples: Vec<ToolExample>,
    #[serde(default)]
    pub versions: Vec<VersionEntry>,
}

/// Tool argument specification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolArg {
    pub name: String,
    #[serde(rename = "type")]
    pub arg_type: String,
    pub description: String,
    #[serde(default)]
    pub required: bool,
    #[serde(default)]
    pub default: Option<serde_json::Value>,
    #[serde(default)]
    #[serde(rename = "enum")]
    pub enum_values: Option<Vec<serde_json::Value>>,
    #[serde(default)]
    pub pattern: Option<String>,
}

/// Tool return value specification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolReturns {
    #[serde(rename = "type")]
    pub return_type: String,
    pub description: String,
}

/// Tool safety constraints
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ToolSafety {
    #[serde(default)]
    pub max_runtime_sec: Option<u32>,
    #[serde(default)]
    pub working_dir: Option<String>,
    #[serde(default)]
    pub allow_write: Option<bool>,
    #[serde(default)]
    pub allow_network: Option<bool>,
    #[serde(default)]
    pub danger_level: Option<String>,
    #[serde(default)]
    pub requires_confirmation: Option<bool>,
}

/// Tool usage example
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolExample {
    pub description: String,
    pub args: serde_json::Value,
    #[serde(default)]
    pub expected_result: Option<String>,
}

/// Version entry (placeholder for versioning, will be expanded in Milestone 6)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VersionEntry {
    pub version: String,
    pub status: String,
    pub hash: String,
    pub created: String,
    #[serde(default)]
    pub deprecated: Option<String>,
    #[serde(default)]
    pub notes: Option<String>,
}

/// Complete tool primitive with metadata
#[derive(Debug, Clone)]
pub struct ToolPrimitive {
    pub path: PathBuf,
    pub meta: ToolMeta,
}

impl ToolPrimitive {
    /// Load a tool primitive from a directory
    /// Expected structure:
    ///   <primitive_dir>/
    ///     {id}.tool.yaml (preferred) or tool.meta.yaml (legacy)
    pub fn load<P: AsRef<std::path::Path>>(primitive_dir: P) -> Result<Self> {
        let primitive_dir = primitive_dir.as_ref();

        if !primitive_dir.exists() {
            return Err(Error::NotFound(format!(
                "Tool directory not found: {}",
                primitive_dir.display()
            )));
        }

        // Try {id}.tool.yaml first (new pattern)
        let meta_path = if let Some(dir_name) = primitive_dir.file_name().and_then(|n| n.to_str()) {
            let id_tool_path = primitive_dir.join(format!("{dir_name}.tool.yaml"));
            if id_tool_path.exists() {
                id_tool_path
            } else {
                // Fall back to tool.meta.yaml (legacy)
                primitive_dir.join("tool.meta.yaml")
            }
        } else {
            primitive_dir.join("tool.meta.yaml")
        };

        if !meta_path.exists() {
            return Err(Error::NotFound(format!(
                "tool meta file not found in {} (tried {{id}}.tool.yaml and tool.meta.yaml)",
                primitive_dir.display()
            )));
        }

        let meta_content = std::fs::read_to_string(&meta_path)?;
        let meta: ToolMeta = serde_yaml::from_str(&meta_content)?;

        Ok(Self {
            path: primitive_dir.to_path_buf(),
            meta,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deserialize_tool_meta() {
        let yaml = r#"
id: test-tool
kind: tool
category: testing
description: "A test tool for unit testing"
"#;
        let meta: ToolMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.id, "test-tool");
        assert_eq!(meta.kind, "tool");
        assert_eq!(meta.category, "testing");
        assert_eq!(meta.description, "A test tool for unit testing");
    }

    #[test]
    fn test_deserialize_tool_with_args() {
        let yaml = r#"
id: test-tool
kind: tool
category: testing
description: "A test tool with arguments"
args:
  - name: "input_file"
    type: "string"
    description: "Path to input file"
    required: true
  - name: "verbose"
    type: "boolean"
    description: "Enable verbose output"
    required: false
    default: false
"#;
        let meta: ToolMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.args.len(), 2);
        assert_eq!(meta.args[0].name, "input_file");
        assert!(meta.args[0].required);
        assert_eq!(meta.args[1].name, "verbose");
        assert!(!meta.args[1].required);
    }

    #[test]
    fn test_deserialize_tool_with_returns() {
        let yaml = r#"
id: test-tool
kind: tool
category: testing
description: "A test tool with return type"
returns:
  type: "object"
  description: "Test results with pass/fail counts"
"#;
        let meta: ToolMeta = serde_yaml::from_str(yaml).unwrap();
        let returns = meta.returns.unwrap();
        assert_eq!(returns.return_type, "object");
        assert_eq!(returns.description, "Test results with pass/fail counts");
    }

    #[test]
    fn test_deserialize_tool_with_safety() {
        let yaml = r#"
id: test-tool
kind: tool
category: testing
description: "A test tool with safety constraints"
safety:
  max_runtime_sec: 300
  working_dir: "."
  allow_write: false
  allow_network: false
  danger_level: "safe"
  requires_confirmation: false
"#;
        let meta: ToolMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.safety.max_runtime_sec, Some(300));
        assert_eq!(meta.safety.working_dir, Some(".".to_string()));
        assert_eq!(meta.safety.allow_write, Some(false));
        assert_eq!(meta.safety.danger_level, Some("safe".to_string()));
    }

    #[test]
    fn test_deserialize_tool_with_examples() {
        let yaml = r#"
id: test-tool
kind: tool
category: testing
description: "A test tool with examples"
examples:
  - description: "Run basic test"
    args:
      test_path: "tests/"
      verbose: true
    expected_result: "All tests passed"
  - description: "Run specific test"
    args:
      test_path: "tests/test_specific.py"
"#;
        let meta: ToolMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.examples.len(), 2);
        assert_eq!(meta.examples[0].description, "Run basic test");
        assert!(meta.examples[0].expected_result.is_some());
    }

    #[test]
    fn test_deserialize_tool_with_enum_arg() {
        let yaml = r#"
id: test-tool
kind: tool
category: testing
description: "A test tool with enum argument"
args:
  - name: "log_level"
    type: "string"
    description: "Logging level"
    required: false
    enum:
      - "debug"
      - "info"
      - "warn"
      - "error"
    default: "info"
"#;
        let meta: ToolMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.args.len(), 1);
        assert!(meta.args[0].enum_values.is_some());
        let enum_values = meta.args[0].enum_values.as_ref().unwrap();
        assert_eq!(enum_values.len(), 4);
    }

    #[test]
    fn test_deserialize_tool_with_pattern() {
        let yaml = r#"
id: test-tool
kind: tool
category: testing
description: "A test tool with pattern validation"
args:
  - name: "email"
    type: "string"
    description: "Email address"
    required: true
    pattern: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
"#;
        let meta: ToolMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.args.len(), 1);
        assert!(meta.args[0].pattern.is_some());
    }

    #[test]
    fn test_load_tool_nonexistent_dir() {
        let result = ToolPrimitive::load("/nonexistent/directory");
        assert!(result.is_err());
    }

    #[test]
    fn test_default_safety() {
        let yaml = r#"
id: test-tool
kind: tool
category: testing
description: "A test tool with default safety"
"#;
        let meta: ToolMeta = serde_yaml::from_str(yaml).unwrap();
        // Default ToolSafety should have None values
        assert!(meta.safety.max_runtime_sec.is_none());
        assert!(meta.safety.allow_write.is_none());
    }
}
