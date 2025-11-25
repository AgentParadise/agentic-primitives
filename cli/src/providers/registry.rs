use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

use crate::primitives::hook::HookEvent;

/// Provider registry containing all loaded model and agent providers
#[derive(Debug, Serialize, Deserialize)]
pub struct ProviderRegistry {
    pub models: HashMap<String, ModelProvider>,
    pub agents: HashMap<String, AgentProvider>,
}

/// Model provider (LLM API provider)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelProvider {
    pub id: String,
    pub name: String,
    pub models: Vec<ModelConfig>,
    pub config_path: PathBuf,
    #[serde(flatten)]
    pub metadata: ProviderMetadata,
}

/// Individual model configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelConfig {
    pub id: String,
    pub name: String,
    pub family: String,
    pub provider: String,
    pub context_window: u32,
    pub max_output_tokens: Option<u32>,
    pub capabilities: Option<Capabilities>,
    pub pricing: PricingInfo,
    pub api: ApiInfo,
    pub release_date: Option<String>,
    pub status: Option<String>,
}

/// Model capabilities
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Capabilities {
    pub vision: Option<bool>,
    pub function_calling: Option<bool>,
    pub streaming: Option<bool>,
    pub json_mode: Option<bool>,
}

/// Pricing information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PricingInfo {
    pub input: f64,
    pub output: f64,
    pub currency: String,
    pub per_tokens: u32,
    pub updated: Option<String>,
}

/// API configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiInfo {
    pub model_id: String,
    pub endpoint: Option<String>,
}

/// Provider metadata (for both model and agent providers)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderMetadata {
    #[serde(rename = "type")]
    pub provider_type: Option<String>,
    pub description: Option<String>,
    pub api: Option<ApiConfig>,
    pub model_families: Option<Vec<String>>,
    pub rate_limits: Option<RateLimits>,
    pub support: Option<SupportInfo>,
}

/// API configuration for provider
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiConfig {
    pub base_url: Option<String>,
    pub docs_url: Option<String>,
    pub authentication: Option<String>,
    pub env_var: Option<String>,
}

/// Rate limit information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RateLimits {
    pub requests_per_minute: Option<u32>,
    pub tokens_per_minute: Option<u32>,
}

/// Support information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SupportInfo {
    pub website: Option<String>,
    pub documentation: Option<String>,
    pub support_email: Option<String>,
}

/// Agent provider (execution framework)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentProvider {
    pub id: String,
    pub name: String,
    pub vendor: String,
    pub supported_events: Vec<HookEvent>,
    pub event_config: HashMap<String, EventConfig>,
    pub hooks_format: String,
    pub config_path: PathBuf,
    #[serde(flatten)]
    pub metadata: AgentMetadata,
}

/// Event-specific configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventConfig {
    pub requires_matcher: bool,
    pub decision_control: bool,
    pub description: Option<String>,
    pub matchers: Option<Vec<String>>,
}

/// Agent-specific metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentMetadata {
    #[serde(rename = "type")]
    pub agent_type: Option<String>,
    pub description: Option<String>,
    pub default_model_provider: Option<String>,
    pub default_model: Option<String>,
    pub hooks: Option<HooksConfig>,
    pub tools: Option<ToolsConfig>,
    pub execution: Option<ExecutionConfig>,
    pub workspace: Option<WorkspaceConfig>,
    pub documentation: Option<String>,
    pub repository: Option<String>,
    pub support: Option<String>,
    pub version: Option<String>,
    pub status: Option<String>,
}

/// Hooks configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HooksConfig {
    pub format: Option<String>,
    pub config_location: Option<String>,
    pub supports_plugin_hooks: Option<bool>,
    pub supports_prompt_hooks: Option<bool>,
    pub event_delivery: Option<String>,
}

/// Tools configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolsConfig {
    pub format: Option<String>,
    pub supports_custom_tools: Option<bool>,
    pub tool_discovery: Option<String>,
}

/// Execution configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionConfig {
    pub context_window_management: Option<String>,
    pub permission_modes: Option<Vec<String>>,
    pub features: Option<Vec<String>>,
}

/// Workspace configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceConfig {
    pub config_directory: Option<String>,
    pub settings_file: Option<String>,
    pub hooks_directory: Option<String>,
    pub cache_directory: Option<String>,
}

/// Hooks supported configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
struct HooksSupportedConfig {
    agent: String,
    version: String,
    supported_events: Vec<HookEvent>,
    event_config: Option<HashMap<String, EventConfig>>,
}

/// Agent-specific hook configuration (from providers/agents/{agent}/hooks-config/{hook}.yaml)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentHookConfig {
    pub agent: String,
    pub hook_id: String,
    pub primitive: HookPrimitiveRef,
    #[serde(default)]
    pub middleware: Vec<MiddlewareConfig>,
    pub execution: Option<HookExecutionConfig>,
    pub default_decision: Option<String>,
}

/// Reference to a hook primitive
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HookPrimitiveRef {
    pub id: String,
    pub path: String,
    pub impl_file: String,
}

/// Middleware configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MiddlewareConfig {
    pub id: String,
    pub path: Option<String>,
    #[serde(rename = "type")]
    pub middleware_type: String,
    pub enabled: bool,
    #[serde(default)]
    pub events: Vec<String>,
    pub priority: Option<u32>,
    pub config: Option<serde_json::Value>,
}

/// Hook execution configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HookExecutionConfig {
    pub strategy: Option<String>,
    pub timeout_sec: Option<u32>,
    pub fail_on_error: Option<bool>,
}

impl ProviderRegistry {
    /// Load provider registry from providers directory
    pub fn load(providers_dir: &Path) -> Result<Self> {
        let mut models = HashMap::new();
        let mut agents = HashMap::new();

        // Load model providers
        let models_dir = providers_dir.join("models");
        if models_dir.exists() {
            for entry in fs::read_dir(&models_dir).context("Failed to read models directory")? {
                let entry = entry?;
                if entry.path().is_dir() {
                    match ModelProvider::load(&entry.path()) {
                        Ok(provider) => {
                            models.insert(provider.id.clone(), provider);
                        }
                        Err(e) => {
                            eprintln!(
                                "⚠️  Failed to load model provider '{}': {}",
                                entry.path().display(),
                                e
                            );
                        }
                    }
                }
            }
        }

        // Load agent providers
        let agents_dir = providers_dir.join("agents");
        if agents_dir.exists() {
            for entry in fs::read_dir(&agents_dir).context("Failed to read agents directory")? {
                let entry = entry?;
                if entry.path().is_dir() {
                    match AgentProvider::load(&entry.path()) {
                        Ok(provider) => {
                            agents.insert(provider.id.clone(), provider);
                        }
                        Err(e) => {
                            eprintln!(
                                "⚠️  Failed to load agent provider '{}': {}",
                                entry.path().display(),
                                e
                            );
                        }
                    }
                }
            }
        }

        Ok(Self { models, agents })
    }

    /// Get agent provider by ID
    pub fn get_agent(&self, id: &str) -> Option<&AgentProvider> {
        self.agents.get(id)
    }

    /// Get model provider by ID
    pub fn get_model(&self, id: &str) -> Option<&ModelProvider> {
        self.models.get(id)
    }

    /// Check if agent supports a specific hook event
    pub fn agent_supports_event(&self, agent_id: &str, event: &HookEvent) -> bool {
        self.get_agent(agent_id)
            .map(|agent| agent.supports_event(event))
            .unwrap_or(false)
    }
}

impl ModelProvider {
    /// Load model provider from directory
    pub fn load(provider_dir: &Path) -> Result<Self> {
        let provider_name = provider_dir
            .file_name()
            .and_then(|n| n.to_str())
            .context("Invalid provider directory name")?;

        // Load config.yaml
        let config_path = provider_dir.join("config.yaml");
        let config_content = fs::read_to_string(&config_path)
            .with_context(|| format!("Failed to read config.yaml for {}", provider_name))?;
        let metadata: ProviderMetadata = serde_yaml::from_str(&config_content)
            .with_context(|| format!("Failed to parse config.yaml for {}", provider_name))?;

        // Load all model YAML files
        let mut models = Vec::new();
        for entry in fs::read_dir(provider_dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.is_file()
                && path.extension().and_then(|s| s.to_str()) == Some("yaml")
                && path.file_stem().and_then(|s| s.to_str()) != Some("config")
            {
                let model_content = fs::read_to_string(&path)?;
                let model: ModelConfig = serde_yaml::from_str(&model_content)
                    .with_context(|| format!("Failed to parse model file {}", path.display()))?;

                // Validate model ID matches filename
                let filename = path.file_stem().and_then(|s| s.to_str()).unwrap();
                if model.id != filename {
                    anyhow::bail!(
                        "Model ID '{}' doesn't match filename '{}' in {}",
                        model.id,
                        filename,
                        path.display()
                    );
                }

                models.push(model);
            }
        }

        // Extract ID and name from metadata
        let id = metadata
            .provider_type
            .as_ref()
            .map(|_| provider_name.to_string())
            .unwrap_or_else(|| provider_name.to_string());

        Ok(Self {
            id,
            name: provider_name.to_string(),
            models,
            config_path: config_path.to_path_buf(),
            metadata,
        })
    }
}

impl AgentProvider {
    /// Load agent provider from directory
    pub fn load(agent_dir: &Path) -> Result<Self> {
        let agent_name = agent_dir
            .file_name()
            .and_then(|n| n.to_str())
            .context("Invalid agent directory name")?;

        // Load config.yaml
        let config_path = agent_dir.join("config.yaml");
        let config_content = fs::read_to_string(&config_path)
            .with_context(|| format!("Failed to read config.yaml for {}", agent_name))?;
        let metadata: AgentMetadata = serde_yaml::from_str(&config_content)
            .with_context(|| format!("Failed to parse config.yaml for {}", agent_name))?;

        // Load hooks-supported.yaml
        let hooks_supported_path = agent_dir.join("hooks-supported.yaml");
        let hooks_content = fs::read_to_string(&hooks_supported_path)
            .with_context(|| format!("Failed to read hooks-supported.yaml for {}", agent_name))?;
        let hooks_config: HooksSupportedConfig = serde_yaml::from_str(&hooks_content)
            .with_context(|| format!("Failed to parse hooks-supported.yaml for {}", agent_name))?;

        // Get hooks format from hooks-format.yaml or use default
        let hooks_format_path = agent_dir.join("hooks-format.yaml");
        let hooks_format = if hooks_format_path.exists() {
            let format_content = fs::read_to_string(&hooks_format_path)?;
            let format_config: serde_yaml::Value = serde_yaml::from_str(&format_content)?;
            format_config
                .get("format")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown")
                .to_string()
        } else {
            "unknown".to_string()
        };

        Ok(Self {
            id: hooks_config.agent.clone(),
            name: agent_name.to_string(),
            vendor: metadata
                .agent_type
                .clone()
                .unwrap_or_else(|| "unknown".to_string()),
            supported_events: hooks_config.supported_events,
            event_config: hooks_config.event_config.unwrap_or_default(),
            hooks_format,
            config_path: config_path.to_path_buf(),
            metadata,
        })
    }

    /// Check if agent supports a specific hook event
    pub fn supports_event(&self, event: &HookEvent) -> bool {
        self.supported_events.contains(event)
    }

    /// Get event configuration for a specific event
    pub fn get_event_config(&self, event: &HookEvent) -> Option<&EventConfig> {
        let event_str = format!("{:?}", event);
        self.event_config.get(&event_str)
    }

    /// Load agent-specific hook configuration
    pub fn load_hook_config(&self, hook_id: &str) -> Result<AgentHookConfig> {
        let agent_dir = self
            .config_path
            .parent()
            .context("Failed to get agent directory")?;

        let hooks_config_dir = agent_dir.join("hooks-config");
        let hook_config_path = hooks_config_dir.join(format!("{}.yaml", hook_id));

        if !hook_config_path.exists() {
            anyhow::bail!(
                "Hook config not found: {} for agent '{}'",
                hook_config_path.display(),
                self.id
            );
        }

        let config_content = fs::read_to_string(&hook_config_path).with_context(|| {
            format!("Failed to read hook config {}", hook_config_path.display())
        })?;

        let config: AgentHookConfig = serde_yaml::from_str(&config_content).with_context(|| {
            format!("Failed to parse hook config {}", hook_config_path.display())
        })?;

        // Validate that config matches
        if config.agent != self.id {
            anyhow::bail!(
                "Hook config agent '{}' doesn't match provider '{}'",
                config.agent,
                self.id
            );
        }

        if config.hook_id != hook_id {
            anyhow::bail!(
                "Hook config ID '{}' doesn't match requested '{}'",
                config.hook_id,
                hook_id
            );
        }

        Ok(config)
    }

    /// Validate middleware events against agent's supported events
    pub fn validate_middleware_events(&self, middleware: &[MiddlewareConfig]) -> Result<()> {
        for mw in middleware {
            for event_str in &mw.events {
                // "*" means all events
                if event_str == "*" {
                    continue;
                }

                // Try to parse event string
                let event: HookEvent = serde_yaml::from_str(event_str).with_context(|| {
                    format!("Invalid event '{}' in middleware '{}'", event_str, mw.id)
                })?;

                if !self.supports_event(&event) {
                    anyhow::bail!(
                        "Middleware '{}' requests event '{:?}' but agent '{}' doesn't support it",
                        mw.id,
                        event,
                        self.id
                    );
                }
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_load_registry() {
        // This test will work once providers/ directory is committed
        let providers_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .join("providers");

        if providers_dir.exists() {
            let result = ProviderRegistry::load(&providers_dir);
            assert!(
                result.is_ok(),
                "Failed to load registry: {:?}",
                result.err()
            );

            let registry = result.unwrap();
            assert!(!registry.models.is_empty(), "No model providers loaded");
            assert!(!registry.agents.is_empty(), "No agent providers loaded");
        }
    }
}
