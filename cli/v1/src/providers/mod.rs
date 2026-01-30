pub mod claude;
pub mod openai;
pub mod registry;

// Re-export for convenience
pub use claude::ClaudeTransformer;
pub use openai::OpenAITransformer;
pub use registry::{AgentProvider, ModelProvider, ProviderRegistry};

use anyhow::Result;
use std::path::Path;

/// Trait for transforming primitives to provider-specific formats
pub trait ProviderTransformer {
    /// Get provider name (e.g., "claude", "openai")
    fn provider_name(&self) -> &str;

    /// Transform a primitive directory to provider format
    fn transform_primitive(
        &self,
        primitive_path: &Path,
        output_dir: &Path,
    ) -> Result<TransformResult>;

    /// Transform multiple primitives
    fn transform_batch(
        &self,
        primitive_paths: &[&Path],
        output_dir: &Path,
    ) -> Result<Vec<TransformResult>>;

    /// Validate transformation output
    fn validate_output(&self, output_dir: &Path) -> Result<()>;
}

/// Result of a transformation operation
#[derive(Debug, Clone)]
pub struct TransformResult {
    pub primitive_id: String,
    pub primitive_kind: String,
    pub output_files: Vec<String>,
    pub success: bool,
    pub error: Option<String>,
}

impl TransformResult {
    /// Create a successful transformation result
    pub fn success(
        primitive_id: String,
        primitive_kind: String,
        output_files: Vec<String>,
    ) -> Self {
        Self {
            primitive_id,
            primitive_kind,
            output_files,
            success: true,
            error: None,
        }
    }

    /// Create a failed transformation result
    pub fn failure(primitive_id: String, primitive_kind: String, error: String) -> Self {
        Self {
            primitive_id,
            primitive_kind,
            output_files: Vec::new(),
            success: false,
            error: Some(error),
        }
    }
}
