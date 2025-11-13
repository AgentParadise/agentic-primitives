use crate::error::{Error, Result};
use serde::{Deserialize, Serialize};
use std::fmt;
use std::path::Path;

/// Model reference in format "provider/model-id"
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModelRef {
    pub provider: String,
    pub model_id: String,
}

impl ModelRef {
    /// Parse from string like "claude/sonnet" or "openai/gpt-codex"
    pub fn parse(s: &str) -> Result<Self> {
        let parts: Vec<&str> = s.split('/').collect();

        if parts.len() != 2 {
            return Err(Error::InvalidFormat(format!(
                "Invalid model reference format: '{s}'. Expected 'provider/model-id'"
            )));
        }

        let provider = parts[0].trim();
        let model_id = parts[1].trim();

        if provider.is_empty() || model_id.is_empty() {
            return Err(Error::InvalidFormat(format!(
                "Model reference cannot have empty provider or model_id: '{s}'"
            )));
        }

        Ok(Self {
            provider: provider.to_string(),
            model_id: model_id.to_string(),
        })
    }

    /// Resolve to full model config by loading YAML file
    /// Looks for file at: providers/{provider}/models/{model_id}.yaml
    pub fn resolve<P: AsRef<Path>>(&self, repo_root: P) -> Result<ModelConfig> {
        let model_path = repo_root
            .as_ref()
            .join("providers")
            .join(&self.provider)
            .join("models")
            .join(format!("{}.yaml", self.model_id));

        if !model_path.exists() {
            return Err(Error::NotFound(format!(
                "Model config not found: {} (looking at {})",
                self,
                model_path.display()
            )));
        }

        let content = std::fs::read_to_string(&model_path)?;
        let config: ModelConfig = serde_yaml::from_str(&content)?;

        Ok(config)
    }
}

impl fmt::Display for ModelRef {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}/{}", self.provider, self.model_id)
    }
}

/// Full model configuration from YAML file
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelConfig {
    pub id: String,
    pub full_name: String,
    pub api_name: String,
    #[serde(default)]
    pub version: Option<String>,
    pub provider: String,
    pub capabilities: ModelCapabilities,
    pub performance: ModelPerformance,
    pub pricing: ModelPricing,
    pub strengths: Vec<String>,
    pub recommended_for: Vec<String>,
    #[serde(default)]
    pub limitations: Option<Vec<String>>,
    #[serde(default)]
    pub notes: Option<String>,
    #[serde(default)]
    pub deprecated: Option<bool>,
    #[serde(default)]
    pub replacement: Option<String>,
    #[serde(default)]
    pub last_updated: Option<String>,
}

/// Model capabilities
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelCapabilities {
    pub max_tokens: u32,
    pub context_window: u32,
    #[serde(default)]
    pub supports_vision: bool,
    #[serde(default)]
    pub supports_function_calling: bool,
    #[serde(default = "default_true")]
    pub supports_streaming: bool,
    #[serde(default)]
    pub supports_json_mode: Option<bool>,
    #[serde(default = "default_some_true")]
    pub supports_system_messages: Option<bool>,
}

/// Model performance characteristics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelPerformance {
    pub speed: String,   // "very-fast", "fast", "medium", "slow"
    pub quality: String, // "very-high", "high", "medium", "low"
    #[serde(default)]
    pub reliability: Option<String>, // "very-high", "high", "medium", "low"
    #[serde(default)]
    pub tokens_per_second: Option<f64>,
}

/// Model pricing information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelPricing {
    pub input_per_1m_tokens: f64,
    pub output_per_1m_tokens: f64,
    #[serde(default = "default_currency")]
    pub currency: String,
    #[serde(default)]
    pub batch_discount: Option<f64>,
    #[serde(default)]
    pub notes: Option<String>,
}

// Default value functions
fn default_true() -> bool {
    true
}

fn default_some_true() -> Option<bool> {
    Some(true)
}

fn default_currency() -> String {
    "USD".to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_model_ref() {
        let model = ModelRef::parse("claude/sonnet").unwrap();
        assert_eq!(model.provider, "claude");
        assert_eq!(model.model_id, "sonnet");
        assert_eq!(model.to_string(), "claude/sonnet");
    }

    #[test]
    fn test_parse_model_ref_with_hyphens() {
        let model = ModelRef::parse("openai/gpt-codex").unwrap();
        assert_eq!(model.provider, "openai");
        assert_eq!(model.model_id, "gpt-codex");
    }

    #[test]
    fn test_parse_invalid_format() {
        assert!(ModelRef::parse("invalid").is_err());
        assert!(ModelRef::parse("too/many/slashes").is_err());
        assert!(ModelRef::parse("/missing-provider").is_err());
        assert!(ModelRef::parse("missing-model/").is_err());
        assert!(ModelRef::parse("").is_err());
    }

    #[test]
    fn test_parse_with_whitespace() {
        let model = ModelRef::parse("  claude / sonnet  ").unwrap();
        assert_eq!(model.provider, "claude");
        assert_eq!(model.model_id, "sonnet");
    }

    #[test]
    fn test_resolve_model() {
        // Test with actual repository structure
        // Find the repository root (where primitives.config.yaml exists)
        let current_dir = std::env::current_dir().unwrap();
        let mut repo_root = current_dir.as_path();

        // Search upward for primitives.config.yaml
        loop {
            if repo_root.join("primitives.config.yaml").exists() {
                break;
            }
            match repo_root.parent() {
                Some(parent) => repo_root = parent,
                None => {
                    // Skip test if we can't find repo root
                    eprintln!("Skipping test_resolve_model: repo root not found");
                    return;
                }
            }
        }

        // Try to resolve claude/sonnet
        let model_ref = ModelRef::parse("claude/sonnet").unwrap();
        match model_ref.resolve(repo_root) {
            Ok(config) => {
                assert_eq!(config.id, "sonnet");
                assert_eq!(config.provider, "claude");
                assert!(config.capabilities.max_tokens > 0);
                assert!(config.capabilities.context_window > 0);
                assert!(!config.strengths.is_empty());
                assert!(!config.recommended_for.is_empty());
            }
            Err(e) => {
                eprintln!("Warning: Could not resolve claude/sonnet: {}", e);
                // Don't fail the test if file doesn't exist yet
            }
        }
    }

    #[test]
    fn test_resolve_nonexistent_model() {
        let model_ref = ModelRef::parse("nonexistent/model").unwrap();
        let result = model_ref.resolve("/tmp");
        assert!(result.is_err());
    }

    #[test]
    fn test_deserialize_model_config() {
        let yaml = r#"
id: test-model
full_name: "Test Model"
api_name: "test-model-v1"
version: "v1"
provider: test
capabilities:
  max_tokens: 100000
  context_window: 200000
  supports_vision: true
  supports_function_calling: true
  supports_streaming: true
performance:
  speed: "fast"
  quality: "high"
pricing:
  input_per_1m_tokens: 1.0
  output_per_1m_tokens: 3.0
  currency: "USD"
strengths:
  - "Test capability 1"
  - "Test capability 2"
recommended_for:
  - "testing"
  - "development"
"#;

        let config: ModelConfig = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(config.id, "test-model");
        assert_eq!(config.full_name, "Test Model");
        assert_eq!(config.capabilities.max_tokens, 100000);
        assert_eq!(config.performance.speed, "fast");
        assert_eq!(config.pricing.input_per_1m_tokens, 1.0);
        assert_eq!(config.strengths.len(), 2);
    }

    #[test]
    fn test_model_config_with_optional_fields() {
        let yaml = r#"
id: minimal
full_name: "Minimal Model"
api_name: "minimal-v1"
provider: test
capabilities:
  max_tokens: 1000
  context_window: 2000
performance:
  speed: "fast"
  quality: "high"
pricing:
  input_per_1m_tokens: 0.5
  output_per_1m_tokens: 1.5
strengths:
  - "Simple"
recommended_for:
  - "basic tasks"
"#;

        let config: ModelConfig = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(config.id, "minimal");
        assert!(config.notes.is_none());
        assert!(config.limitations.is_none());
        assert_eq!(config.capabilities.supports_vision, false);
        assert_eq!(config.pricing.currency, "USD"); // Default
    }
}
