//! Integration tests for analytics middleware in the hook system
//!
//! TODO: These tests currently validate YAML parsing and type deserialization.
//! Future enhancements should add tests that:
//! 1. Execute hooks with analytics middleware enabled
//! 2. Verify analytics data is collected and formatted correctly
//! 3. Test middleware pipeline execution order
//! See: https://github.com/AgentParadise/agentic-primitives/issues/TBD

use std::fs;
use tempfile::TempDir;

#[cfg(test)]
mod test_analytics_middleware {
    use super::*;

    /// Test that hook metadata with analytics middleware validates successfully
    #[test]
    fn test_analytics_middleware_validates() {
        let hook_yaml = r#"
version: 1
id: test-analytics-hook
kind: hook
category: analytics
event: PreToolUse
summary: "Test hook with analytics middleware"
execution:
  strategy: parallel
middleware:
  - id: "analytics-normalizer"
    type: analytics
    path: "./middleware/event_normalizer.py"
    enabled: true
  - id: "analytics-publisher"
    type: analytics
    path: "./middleware/event_publisher.py"
    enabled: true
"#;

        // Write to temp file and validate
        let temp_dir = TempDir::new().unwrap();
        let hook_path = temp_dir.path().join("test-analytics-hook");
        fs::create_dir_all(&hook_path).unwrap();

        let hook_meta_path = hook_path.join("test-analytics-hook.hook.yaml");
        fs::write(&hook_meta_path, hook_yaml).unwrap();

        // Parse the hook to ensure it deserializes correctly
        let meta_content = fs::read_to_string(&hook_meta_path).unwrap();
        let result = serde_yaml::from_str::<serde_yaml::Value>(&meta_content);

        assert!(result.is_ok(), "Analytics hook YAML should parse correctly");

        let parsed = result.unwrap();
        let middleware = parsed["middleware"].as_sequence().unwrap();
        assert_eq!(middleware.len(), 2);
        assert_eq!(middleware[0]["type"].as_str().unwrap(), "analytics");
        assert_eq!(middleware[1]["type"].as_str().unwrap(), "analytics");
    }

    /// Test that "analytics" string parses to MiddlewareType::Analytics
    #[test]
    fn test_analytics_middleware_type_parsing() {
        use agentic_primitives::primitives::hook::MiddlewareType;
        use std::str::FromStr;

        // Test that "analytics" string parses to MiddlewareType::Analytics
        let middleware_type = MiddlewareType::from_str("analytics").unwrap();
        assert_eq!(middleware_type, MiddlewareType::Analytics);

        // Test Display implementation
        assert_eq!(middleware_type.to_string(), "analytics");

        // Test case insensitivity
        let uppercase = MiddlewareType::from_str("ANALYTICS").unwrap();
        assert_eq!(uppercase, MiddlewareType::Analytics);
    }

    /// Test that analytics middleware deserializes correctly in hook metadata
    #[test]
    fn test_deserialize_analytics_hook_meta() {
        use agentic_primitives::primitives::hook::{HookMeta, MiddlewareType};

        let yaml = r#"
id: analytics-test
kind: hook
category: analytics
event: PostToolUse
summary: "Analytics collection hook"
execution:
  strategy: parallel
  timeout_sec: 30
middleware:
  - id: "normalizer"
    path: "middleware/event_normalizer.py"
    type: "analytics"
    enabled: true
  - id: "publisher"
    path: "middleware/event_publisher.py"
    type: "analytics"
    enabled: true
"#;

        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.id, "analytics-test");
        assert_eq!(meta.middleware.len(), 2);
        assert_eq!(
            meta.middleware[0].middleware_type,
            MiddlewareType::Analytics
        );
        assert_eq!(
            meta.middleware[1].middleware_type,
            MiddlewareType::Analytics
        );
        assert_eq!(meta.middleware[0].id, "normalizer");
        assert_eq!(meta.middleware[1].id, "publisher");
    }

    /// Test that mixed middleware types (safety, observability, analytics) work together
    #[test]
    fn test_mixed_middleware_types() {
        use agentic_primitives::primitives::hook::{HookMeta, MiddlewareType};

        let yaml = r#"
id: mixed-middleware-hook
kind: hook
category: testing
event: PreToolUse
summary: "Hook with mixed middleware types"
execution:
  strategy: parallel
middleware:
  - id: "safety-check"
    path: "middleware/safety.py"
    type: "safety"
    priority: 10
  - id: "observability-log"
    path: "middleware/observability.py"
    type: "observability"
    priority: 90
  - id: "analytics-track"
    path: "middleware/analytics.py"
    type: "analytics"
    priority: 95
"#;

        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.middleware.len(), 3);
        assert_eq!(meta.middleware[0].middleware_type, MiddlewareType::Safety);
        assert_eq!(
            meta.middleware[1].middleware_type,
            MiddlewareType::Observability
        );
        assert_eq!(
            meta.middleware[2].middleware_type,
            MiddlewareType::Analytics
        );
    }

    /// Test that analytics middleware with parallel execution strategy is valid
    #[test]
    fn test_analytics_with_parallel_execution() {
        use agentic_primitives::primitives::hook::{ExecutionStrategy, HookMeta};

        let yaml = r#"
id: parallel-analytics
kind: hook
category: analytics
event: SessionStart
summary: "Analytics with parallel execution"
execution:
  strategy: parallel
middleware:
  - id: "analytics-1"
    path: "middleware/analytics1.py"
    type: "analytics"
  - id: "analytics-2"
    path: "middleware/analytics2.py"
    type: "analytics"
"#;

        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(meta.execution.strategy, ExecutionStrategy::Parallel);
        assert_eq!(meta.middleware.len(), 2);
    }

    /// Test that analytics middleware can be disabled
    #[test]
    fn test_analytics_middleware_disabled() {
        use agentic_primitives::primitives::hook::HookMeta;

        let yaml = r#"
id: disabled-analytics
kind: hook
category: testing
event: PreToolUse
summary: "Analytics middleware that is disabled"
execution:
  strategy: parallel
middleware:
  - id: "analytics-disabled"
    path: "middleware/analytics.py"
    type: "analytics"
    enabled: false
"#;

        let meta: HookMeta = serde_yaml::from_str(yaml).unwrap();
        assert!(!meta.middleware[0].enabled);
    }

    /// Test that invalid middleware type fails parsing
    #[test]
    fn test_invalid_middleware_type() {
        use agentic_primitives::primitives::hook::MiddlewareType;
        use std::str::FromStr;

        let result = MiddlewareType::from_str("invalid-type");
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("Invalid middleware type"));
    }

    /// Test serialization of analytics middleware type
    #[test]
    fn test_serialize_analytics_middleware() {
        use agentic_primitives::primitives::hook::{MiddlewareConfig, MiddlewareType};

        let middleware = MiddlewareConfig {
            id: "test-analytics".to_string(),
            path: "middleware/test.py".to_string(),
            middleware_type: MiddlewareType::Analytics,
            enabled: true,
            priority: Some(50),
            config: None,
        };

        let serialized = serde_yaml::to_string(&middleware).unwrap();
        assert!(serialized.contains("type: analytics"));
        assert!(serialized.contains("id: test-analytics"));
    }

    /// Test that all middleware types serialize to lowercase
    #[test]
    fn test_middleware_type_serialization_lowercase() {
        use agentic_primitives::primitives::hook::MiddlewareType;

        let safety = serde_yaml::to_string(&MiddlewareType::Safety).unwrap();
        assert_eq!(safety.trim(), "safety");

        let observability = serde_yaml::to_string(&MiddlewareType::Observability).unwrap();
        assert_eq!(observability.trim(), "observability");

        let analytics = serde_yaml::to_string(&MiddlewareType::Analytics).unwrap();
        assert_eq!(analytics.trim(), "analytics");
    }

    /// Test that HookPrimitive can load analytics hooks from directory
    #[test]
    fn test_load_analytics_hook_primitive() {
        use agentic_primitives::primitives::hook::HookPrimitive;

        let hook_yaml = r#"
id: loadable-analytics-hook
kind: hook
category: analytics
event: PreToolUse
summary: "Loadable analytics hook"
execution:
  strategy: parallel
middleware:
  - id: "analytics-normalizer"
    type: analytics
    path: "./middleware/event_normalizer.py"
"#;

        let temp_dir = TempDir::new().unwrap();
        let hook_dir = temp_dir.path().join("loadable-analytics-hook");
        fs::create_dir_all(&hook_dir).unwrap();

        let hook_meta_path = hook_dir.join("loadable-analytics-hook.hook.yaml");
        fs::write(&hook_meta_path, hook_yaml).unwrap();

        let result = HookPrimitive::load(&hook_dir);
        assert!(result.is_ok(), "Should load analytics hook primitive");

        let primitive = result.unwrap();
        assert_eq!(primitive.meta.id, "loadable-analytics-hook");
        assert_eq!(primitive.meta.middleware.len(), 1);
    }
}
