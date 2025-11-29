use crate::error::{Error, Result};
use serde::{Deserialize, Serialize};
use std::fmt;
use std::path::PathBuf;
use std::str::FromStr;

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

/// Middleware types defining execution behavior
///
/// - **Safety**: Blocking middleware that can stop execution (e.g., security checks)
/// - **Observability**: Non-blocking middleware for monitoring (e.g., logging, metrics)
/// - **Analytics**: Non-blocking middleware for event collection and analysis
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MiddlewareType {
    /// Blocking middleware for security and safety checks
    Safety,
    /// Non-blocking middleware for observability (logging, metrics)
    Observability,
    /// Non-blocking middleware for analytics (event tracking, analysis)
    Analytics,
}

impl fmt::Display for MiddlewareType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            MiddlewareType::Safety => write!(f, "safety"),
            MiddlewareType::Observability => write!(f, "observability"),
            MiddlewareType::Analytics => write!(f, "analytics"),
        }
    }
}

impl FromStr for MiddlewareType {
    type Err = Error;

    fn from_str(s: &str) -> Result<Self> {
        match s.to_lowercase().as_str() {
            "safety" => Ok(MiddlewareType::Safety),
            "observability" => Ok(MiddlewareType::Observability),
            "analytics" => Ok(MiddlewareType::Analytics),
            _ => Err(Error::InvalidFormat(format!(
                "Invalid middleware type: '{s}'. Expected: safety, observability, or analytics"
            ))),
        }
    }
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

    /// Single event (deprecated - use `events` for multi-event support)
    /// Kept for backward compatibility
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub event: Option<HookEvent>,

    /// Multiple events - hook will register for all specified events
    /// If empty/None and event is also None, hook will register for ALL agent-supported events
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub events: Option<Vec<HookEvent>>,

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
    pub middleware_type: MiddlewareType,
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

impl HookMeta {
    /// Get all events this hook should register for
    ///
    /// Returns:
    /// - If `events` is present: returns the vec of events
    /// - If `event` is present: returns vec with single event (backward compat)
    /// - If both are None: returns empty vec (means "register for ALL agent events")
    pub fn get_events(&self) -> Vec<HookEvent> {
        if let Some(events) = &self.events {
            events.clone()
        } else if let Some(event) = self.event {
            vec![event]
        } else {
            // Empty means "use all agent-supported events"
            vec![]
        }
    }

    /// Check if hook should register for all agent events
    pub fn is_universal(&self) -> bool {
        self.event.is_none() && self.events.is_none()
    }
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
        assert_eq!(meta.event, Some(HookEvent::PreToolUse));
        assert_eq!(meta.execution.strategy, ExecutionStrategy::Pipeline);
        // Test backward compat: single event
        assert_eq!(meta.get_events(), vec![HookEvent::PreToolUse]);
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
        assert_eq!(meta.middleware[0].middleware_type, MiddlewareType::Safety);
        assert_eq!(meta.middleware[0].priority, Some(10));
        assert_eq!(meta.middleware[1].id, "log-operations");
        assert_eq!(
            meta.middleware[1].middleware_type,
            MiddlewareType::Observability
        );
    }

    #[test]
    fn test_hook_meta_multiple_events() {
        let yaml = r#"
id: test-multi-event
kind: hook
category: testing
events:
  - PreToolUse
  - PostToolUse
  - SessionStart
summary: "A test hook for multiple events"
execution:
  strategy: parallel
"#;
        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.id, "test-multi-event");
        assert_eq!(meta.event, None); // Should be None when using events
        assert_eq!(meta.events.as_ref().unwrap().len(), 3);
        assert_eq!(
            meta.get_events(),
            vec![
                HookEvent::PreToolUse,
                HookEvent::PostToolUse,
                HookEvent::SessionStart
            ]
        );
        assert!(!meta.is_universal());
    }

    #[test]
    fn test_hook_meta_universal() {
        let yaml = r#"
id: test-universal
kind: hook
category: "*"
summary: "A universal hook that registers for all agent events"
execution:
  strategy: parallel
"#;
        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.id, "test-universal");
        assert_eq!(meta.event, None);
        assert_eq!(meta.events, None);
        assert_eq!(meta.get_events(), vec![]); // Empty means use agent's supported events
        assert!(meta.is_universal());
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
        assert_eq!(meta.event, Some(HookEvent::PreToolUse));
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
        assert_eq!(meta.event, Some(HookEvent::SessionStart));
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

    #[test]
    fn test_middleware_type_parsing() {
        // Test FromStr implementation
        assert_eq!(
            "safety".parse::<MiddlewareType>().unwrap(),
            MiddlewareType::Safety
        );
        assert_eq!(
            "observability".parse::<MiddlewareType>().unwrap(),
            MiddlewareType::Observability
        );
        assert_eq!(
            "analytics".parse::<MiddlewareType>().unwrap(),
            MiddlewareType::Analytics
        );

        // Test case insensitivity
        assert_eq!(
            "SAFETY".parse::<MiddlewareType>().unwrap(),
            MiddlewareType::Safety
        );
        assert_eq!(
            "Observability".parse::<MiddlewareType>().unwrap(),
            MiddlewareType::Observability
        );
        assert_eq!(
            "ANALYTICS".parse::<MiddlewareType>().unwrap(),
            MiddlewareType::Analytics
        );
    }

    #[test]
    fn test_middleware_type_display() {
        // Test Display implementation
        assert_eq!(MiddlewareType::Safety.to_string(), "safety");
        assert_eq!(MiddlewareType::Observability.to_string(), "observability");
        assert_eq!(MiddlewareType::Analytics.to_string(), "analytics");
    }

    #[test]
    fn test_middleware_type_invalid() {
        // Test invalid middleware type
        let result = "invalid".parse::<MiddlewareType>();
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("Invalid middleware type"));
    }

    #[test]
    fn test_deserialize_hook_with_analytics_middleware() {
        let yaml = r#"
id: test-analytics-hook
kind: hook
category: analytics
event: PreToolUse
summary: "Test hook with analytics middleware"
execution:
  strategy: parallel
middleware:
  - id: "analytics-normalizer"
    path: "middleware/analytics/event_normalizer.py"
    type: "analytics"
    enabled: true
  - id: "analytics-publisher"
    path: "middleware/analytics/event_publisher.py"
    type: "analytics"
    enabled: true
"#;
        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.middleware.len(), 2);
        assert_eq!(
            meta.middleware[0].middleware_type,
            MiddlewareType::Analytics
        );
        assert_eq!(
            meta.middleware[1].middleware_type,
            MiddlewareType::Analytics
        );
    }

    #[test]
    fn test_get_events_backward_compat() {
        // Single event (old format)
        let yaml = r#"
id: old-style
kind: hook
category: testing
event: PreToolUse
summary: "Old style single event"
execution:
  strategy: pipeline
"#;
        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.get_events(), vec![HookEvent::PreToolUse]);
        assert!(!meta.is_universal());
    }

    #[test]
    fn test_get_events_new_multi() {
        // Multiple events (new format)
        let yaml = r#"
id: new-style
kind: hook
category: testing
events:
  - PreToolUse
  - PostToolUse
summary: "New style multiple events"
execution:
  strategy: pipeline
"#;
        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(
            meta.get_events(),
            vec![HookEvent::PreToolUse, HookEvent::PostToolUse]
        );
        assert!(!meta.is_universal());
    }

    #[test]
    fn test_get_events_universal_hook() {
        // Universal hook (no events specified)
        let yaml = r#"
id: universal
kind: hook
category: "*"
summary: "Universal hook for all events"
execution:
  strategy: parallel
"#;
        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.get_events(), vec![]); // Empty vec means "all agent events"
        assert!(meta.is_universal());
    }
}
