use crate::error::{Error, Result};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Hook event types
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum HookEvent {
    PreToolUse,
    PostToolUse,
    UserPromptSubmit,
    Stop,
    SubagentStop,
    SessionStart,
    SessionEnd,
    PreCompact,
    Notification,
}

/// Execution strategy for middleware pipeline
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ExecutionStrategy {
    Pipeline, // Sequential with fail-fast
    Parallel, // All middleware runs in parallel
}

/// Hook metadata structure
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HookMeta {
    pub id: String,
    pub kind: String,
    pub category: String,
    pub event: HookEvent,
    pub summary: String,
    pub execution: ExecutionConfig,
    #[serde(default)]
    pub middleware: Vec<MiddlewareConfig>,
    #[serde(default)]
    pub default_decision: Option<String>,
    #[serde(default)]
    pub providers: Option<serde_json::Value>,
    #[serde(default)]
    pub metrics: Option<MetricsConfig>,
    #[serde(default)]
    pub logging: Option<LoggingConfig>,
    #[serde(default)]
    pub versions: Vec<VersionEntry>,
}

/// Execution configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionConfig {
    pub strategy: ExecutionStrategy,
    #[serde(default)]
    pub timeout_sec: Option<u32>,
    #[serde(default)]
    pub fail_on_error: Option<bool>,
}

/// Middleware configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MiddlewareConfig {
    pub id: String,
    pub path: String,
    #[serde(rename = "type")]
    pub middleware_type: String,
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default)]
    pub priority: Option<u32>,
    #[serde(default)]
    pub config: Option<serde_json::Value>,
}

/// Metrics configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MetricsConfig {
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default)]
    pub backend: Option<String>,
    #[serde(default)]
    pub tags: Option<serde_json::Value>,
}

/// Logging configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoggingConfig {
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default)]
    pub level: Option<String>,
    #[serde(default)]
    pub output: Option<String>,
    #[serde(default)]
    pub format: Option<String>,
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

// Default value function
fn default_true() -> bool {
    true
}

/// Complete hook primitive with metadata
#[derive(Debug, Clone)]
pub struct HookPrimitive {
    pub path: PathBuf,
    pub meta: HookMeta,
}

impl HookPrimitive {
    /// Load a hook primitive from a directory
    /// Expected structure:
    ///   <primitive_dir>/
    ///     {id}.hook.yaml (preferred) or hook.meta.yaml (legacy)
    pub fn load<P: AsRef<std::path::Path>>(primitive_dir: P) -> Result<Self> {
        let primitive_dir = primitive_dir.as_ref();

        if !primitive_dir.exists() {
            return Err(Error::NotFound(format!(
                "Hook directory not found: {}",
                primitive_dir.display()
            )));
        }

        // Try {id}.hook.yaml first (new pattern)
        let meta_path = if let Some(dir_name) = primitive_dir.file_name().and_then(|n| n.to_str()) {
            let id_hook_path = primitive_dir.join(format!("{dir_name}.hook.yaml"));
            if id_hook_path.exists() {
                id_hook_path
            } else {
                // Fall back to hook.meta.yaml (legacy)
                primitive_dir.join("hook.meta.yaml")
            }
        } else {
            primitive_dir.join("hook.meta.yaml")
        };

        if !meta_path.exists() {
            return Err(Error::NotFound(format!(
                "hook meta file not found in {} (tried {{id}}.hook.yaml and hook.meta.yaml)",
                primitive_dir.display()
            )));
        }

        let meta_content = std::fs::read_to_string(&meta_path)?;
        let meta: HookMeta = serde_yaml::from_str(&meta_content)?;

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
    fn test_deserialize_hook_event() {
        let events = vec![
            ("PreToolUse", HookEvent::PreToolUse),
            ("PostToolUse", HookEvent::PostToolUse),
            ("UserPromptSubmit", HookEvent::UserPromptSubmit),
            ("Stop", HookEvent::Stop),
            ("SubagentStop", HookEvent::SubagentStop),
            ("SessionStart", HookEvent::SessionStart),
            ("SessionEnd", HookEvent::SessionEnd),
            ("PreCompact", HookEvent::PreCompact),
            ("Notification", HookEvent::Notification),
        ];

        for (yaml_str, expected) in events {
            let event: HookEvent = serde_yaml::from_str(yaml_str).unwrap();
            assert_eq!(event, expected);
        }
    }

    #[test]
    fn test_deserialize_execution_strategy() {
        let pipeline: ExecutionStrategy = serde_yaml::from_str("pipeline").unwrap();
        assert_eq!(pipeline, ExecutionStrategy::Pipeline);

        let parallel: ExecutionStrategy = serde_yaml::from_str("parallel").unwrap();
        assert_eq!(parallel, ExecutionStrategy::Parallel);
    }

    #[test]
    fn test_deserialize_hook_meta() {
        let yaml = r#"
id: test-hook
kind: hook
category: testing
event: PreToolUse
summary: "A test hook for unit testing"
execution:
  strategy: pipeline
"#;
        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.id, "test-hook");
        assert_eq!(meta.kind, "hook");
        assert_eq!(meta.category, "testing");
        assert_eq!(meta.event, HookEvent::PreToolUse);
        assert_eq!(meta.execution.strategy, ExecutionStrategy::Pipeline);
    }

    #[test]
    fn test_deserialize_hook_with_middleware() {
        let yaml = r#"
id: test-hook
kind: hook
category: testing
event: PreToolUse
summary: "A test hook with middleware"
execution:
  strategy: pipeline
  timeout_sec: 60
  fail_on_error: true
middleware:
  - id: "block-dangerous"
    path: "middleware/safety/block-dangerous.py"
    type: "safety"
    enabled: true
    priority: 10
    config:
      patterns:
        - "rm -rf"
        - "sudo rm"
  - id: "log-operations"
    path: "middleware/observability/log-operations.py"
    type: "observability"
    enabled: true
    priority: 90
"#;
        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.middleware.len(), 2);
        assert_eq!(meta.middleware[0].id, "block-dangerous");
        assert_eq!(meta.middleware[0].middleware_type, "safety");
        assert_eq!(meta.middleware[0].priority, Some(10));
        assert_eq!(meta.middleware[1].id, "log-operations");
        assert_eq!(meta.middleware[1].middleware_type, "observability");
    }

    #[test]
    fn test_deserialize_hook_with_default_decision() {
        let yaml = r#"
id: test-hook
kind: hook
category: testing
event: PreToolUse
summary: "A test hook with default decision"
execution:
  strategy: pipeline
default_decision: "allow"
"#;
        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.default_decision, Some("allow".to_string()));
    }

    #[test]
    fn test_deserialize_hook_with_metrics() {
        let yaml = r#"
id: test-hook
kind: hook
category: testing
event: PreToolUse
summary: "A test hook with metrics"
execution:
  strategy: pipeline
metrics:
  enabled: true
  backend: "statsd"
  tags:
    environment: "production"
    hook: "pre-tool-use"
"#;
        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        let metrics = meta.metrics.unwrap();
        assert!(metrics.enabled);
        assert_eq!(metrics.backend, Some("statsd".to_string()));
    }

    #[test]
    fn test_deserialize_hook_with_logging() {
        let yaml = r#"
id: test-hook
kind: hook
category: testing
event: PreToolUse
summary: "A test hook with logging"
execution:
  strategy: pipeline
logging:
  enabled: true
  level: "info"
  output: "logs/hooks.jsonl"
  format: "json"
"#;
        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        let logging = meta.logging.unwrap();
        assert!(logging.enabled);
        assert_eq!(logging.level, Some("info".to_string()));
        assert_eq!(logging.format, Some("json".to_string()));
    }

    #[test]
    fn test_deserialize_hook_parallel_execution() {
        let yaml = r#"
id: test-hook
kind: hook
category: testing
event: SessionStart
summary: "A test hook with parallel execution"
execution:
  strategy: parallel
  timeout_sec: 30
"#;
        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.execution.strategy, ExecutionStrategy::Parallel);
        assert_eq!(meta.execution.timeout_sec, Some(30));
    }

    #[test]
    fn test_load_hook_nonexistent_dir() {
        let result = HookPrimitive::load("/nonexistent/directory");
        assert!(result.is_err());
    }

    #[test]
    fn test_middleware_default_enabled() {
        let yaml = r#"
id: "test-middleware"
path: "middleware/test.py"
type: "safety"
"#;
        let middleware: MiddlewareConfig = serde_yaml::from_str(yaml).unwrap();
        assert!(middleware.enabled); // Default should be true
    }

    #[test]
    fn test_middleware_disabled() {
        let yaml = r#"
id: "test-middleware"
path: "middleware/test.py"
type: "safety"
enabled: false
"#;
        let middleware: MiddlewareConfig = serde_yaml::from_str(yaml).unwrap();
        assert!(!middleware.enabled);
    }
}
