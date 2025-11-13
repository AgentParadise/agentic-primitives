use crate::primitives::{HookPrimitive, PromptKind, PromptPrimitive, ToolPrimitive};
use crate::providers::{ProviderTransformer, TransformResult};
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::fs;
use std::path::Path;

/// OpenAI-specific transformer that converts generic primitives into OpenAI formats
///
/// # Example
/// ```
/// use agentic_primitives::providers::openai::OpenAITransformer;
/// use agentic_primitives::providers::ProviderTransformer;
///
/// let transformer = OpenAITransformer::new();
/// assert_eq!(transformer.provider_name(), "openai");
/// ```
pub struct OpenAITransformer {
    spec_version: String,
}

impl OpenAITransformer {
    /// Create a new OpenAI transformer
    pub fn new() -> Self {
        Self {
            spec_version: "v1".to_string(),
        }
    }

    /// Transform a prompt primitive to OpenAI message format
    fn transform_prompt(
        &self,
        primitive: &PromptPrimitive,
        output_dir: &Path,
    ) -> Result<TransformResult> {
        let meta = &primitive.meta;

        // Determine the role based on prompt kind
        let (role, subdir) = match meta.kind {
            PromptKind::Agent => ("system", "agents"),
            PromptKind::Command => ("user", "commands"),
            PromptKind::Skill => ("assistant", "skills"),
            PromptKind::MetaPrompt => {
                // Meta-prompts are not transformed for OpenAI
                return Ok(TransformResult {
                    primitive_id: meta.id.clone(),
                    primitive_kind: "prompt".to_string(),
                    output_files: Vec::new(),
                    success: true,
                    error: Some("Meta-prompts are skipped for OpenAI".to_string()),
                });
            }
        };

        // Extract variable names from content if it's a command
        let variables = if meta.kind == PromptKind::Command {
            Self::extract_variables(&primitive.content)
        } else {
            Vec::new()
        };

        // Build the output JSON
        let mut output = json!({
            "id": meta.id,
            "type": format!("{:?}", meta.kind).to_lowercase(),
            "spec_version": self.spec_version,
            "messages": [
                {
                    "role": role,
                    "content": primitive.content.trim(),
                }
            ],
            "metadata": {
                "domain": meta.domain,
                "tags": meta.tags,
            }
        });

        // Add version if available
        if let Some(default_version) = meta.default_version {
            output["version"] = json!(default_version);
        }

        // Add variables for commands
        if !variables.is_empty() {
            output["messages"][0]["variables"] = json!(variables);
        }

        // Add model preferences if available
        if !meta.defaults.preferred_models.is_empty() {
            output["metadata"]["model_preferences"] = json!(meta.defaults.preferred_models);
        }

        // Add context usage info for skills
        if meta.kind == PromptKind::Skill {
            if let Some(ref context_usage) = meta.context_usage {
                if context_usage.as_overlay {
                    output["metadata"]["usage"] = json!("overlay");
                }
            }
        }

        // Create output directory structure
        let prompt_dir = output_dir.join("prompts").join(subdir);
        fs::create_dir_all(&prompt_dir)?;

        // Write the output file
        let output_file = prompt_dir.join(format!("{}.json", meta.id));
        let output_str = serde_json::to_string_pretty(&output)?;
        fs::write(&output_file, output_str)?;

        Ok(TransformResult::success(
            meta.id.clone(),
            "prompt".to_string(),
            vec![output_file.to_string_lossy().to_string()],
        ))
    }

    /// Extract variable names from prompt content (simple implementation)
    /// Looks for {{variable}} patterns
    fn extract_variables(content: &str) -> Vec<String> {
        let mut variables = Vec::new();
        let mut chars = content.chars().peekable();

        while let Some(c) = chars.next() {
            if c == '{' {
                if let Some(&next_c) = chars.peek() {
                    if next_c == '{' {
                        chars.next(); // consume second {
                        let mut var_name = String::new();

                        // Read until }}
                        while let Some(vc) = chars.next() {
                            if vc == '}' {
                                if let Some(&next_vc) = chars.peek() {
                                    if next_vc == '}' {
                                        chars.next(); // consume second }
                                        let trimmed = var_name.trim().to_string();
                                        if !trimmed.is_empty() && !variables.contains(&trimmed) {
                                            variables.push(trimmed);
                                        }
                                        break;
                                    }
                                }
                            }
                            var_name.push(vc);
                        }
                    }
                }
            }
        }

        variables
    }

    /// Transform a tool primitive to OpenAI function calling format
    fn transform_tool(
        &self,
        primitive: &ToolPrimitive,
        output_dir: &Path,
    ) -> Result<TransformResult> {
        let meta = &primitive.meta;

        // Build properties for function parameters
        let mut properties: HashMap<String, Value> = HashMap::new();
        let mut required_fields: Vec<String> = Vec::new();

        for arg in &meta.args {
            let mut prop = json!({
                "type": Self::map_type_to_openai(&arg.arg_type),
                "description": arg.description,
            });

            // Add default value if present
            if let Some(ref default) = arg.default {
                prop["default"] = default.clone();
            }

            // Add enum values if present
            if let Some(ref enum_vals) = arg.enum_values {
                prop["enum"] = json!(enum_vals);
            }

            // Add pattern if present
            if let Some(ref pattern) = arg.pattern {
                prop["pattern"] = json!(pattern);
            }

            properties.insert(arg.name.clone(), prop);

            if arg.required {
                required_fields.push(arg.name.clone());
            }
        }

        // Build the OpenAI function definition
        let output = json!({
            "type": "function",
            "function": {
                "name": meta.id.replace('-', "_"), // OpenAI prefers underscores
                "description": meta.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required_fields,
                }
            },
            "metadata": {
                "id": meta.id,
                "category": meta.category,
                "safety": {
                    "max_runtime_sec": meta.safety.max_runtime_sec,
                    "working_dir": meta.safety.working_dir,
                    "allow_write": meta.safety.allow_write,
                    "allow_network": meta.safety.allow_network,
                }
            }
        });

        // Create output directory
        let functions_dir = output_dir.join("functions");
        fs::create_dir_all(&functions_dir)?;

        // Write the output file
        let output_file = functions_dir.join(format!("{}.json", meta.id));
        let output_str = serde_json::to_string_pretty(&output)?;
        fs::write(&output_file, output_str)?;

        Ok(TransformResult::success(
            meta.id.clone(),
            "tool".to_string(),
            vec![output_file.to_string_lossy().to_string()],
        ))
    }

    /// Map generic type to OpenAI JSON schema type
    fn map_type_to_openai(type_str: &str) -> String {
        match type_str {
            "string" => "string",
            "number" | "integer" | "int" | "float" => "number",
            "boolean" | "bool" => "boolean",
            "array" | "list" => "array",
            "object" | "dict" => "object",
            _ => "string", // Default to string for unknown types
        }
        .to_string()
    }

    /// Transform a hook primitive to OpenAI middleware config
    fn transform_hook(
        &self,
        primitive: &HookPrimitive,
        output_dir: &Path,
    ) -> Result<TransformResult> {
        let meta = &primitive.meta;

        // Build middleware configurations
        let middleware_configs: Vec<Value> = meta
            .middleware
            .iter()
            .map(|m| {
                json!({
                    "name": m.id,
                    "type": m.middleware_type,
                    "enabled": m.enabled,
                    "priority": m.priority,
                    "config": m.config,
                })
            })
            .collect();

        // Build the output JSON
        let output = json!({
            "id": meta.id,
            "type": "hook",
            "event": format!("{:?}", meta.event).to_lowercase().replace("tooluse", "_tool_use").replace("promptsubmit", "_prompt_submit").replace("agentstop", "_agent_stop").replace("sessionstart", "_session_start").replace("sessionend", "_session_end").replace("precompact", "_pre_compact"),
            "matcher": ".*", // Default matcher
            "middleware": middleware_configs,
            "metadata": {
                "description": meta.summary,
                "execution": format!("{:?}", meta.execution.strategy).to_lowercase(),
                "timeout_sec": meta.execution.timeout_sec,
            }
        });

        // Create output directory
        let middleware_dir = output_dir.join("middleware");
        fs::create_dir_all(&middleware_dir)?;

        // Write the output file
        let output_file = middleware_dir.join(format!("{}.json", meta.id));
        let output_str = serde_json::to_string_pretty(&output)?;
        fs::write(&output_file, output_str)?;

        Ok(TransformResult::success(
            meta.id.clone(),
            "hook".to_string(),
            vec![output_file.to_string_lossy().to_string()],
        ))
    }

    /// Determine primitive type from path
    fn detect_primitive_type(path: &Path) -> Result<String> {
        if !path.exists() {
            bail!("Path does not exist: {}", path.display());
        }

        // Check for meta files - try new pattern first, then legacy
        if let Some(dir_name) = path.file_name().and_then(|n| n.to_str()) {
            if path.join(format!("{dir_name}.tool.yaml")).exists()
                || path.join("tool.meta.yaml").exists()
            {
                return Ok("tool".to_string());
            }
            if path.join(format!("{dir_name}.hook.yaml")).exists()
                || path.join("hook.meta.yaml").exists()
            {
                return Ok("hook".to_string());
            }
        }

        // Check for prompt meta files (meta.yaml or {id}.yaml pattern)
        if path.join("meta.yaml").exists() {
            return Ok("prompt".to_string());
        }

        // Check for {id}.yaml pattern (where id matches the directory name)
        if let Some(dir_name) = path.file_name().and_then(|n| n.to_str()) {
            let id_meta_file = format!("{dir_name}.yaml");
            if path.join(&id_meta_file).exists() {
                return Ok("prompt".to_string());
            }
        }

        bail!("Could not determine primitive type for: {}", path.display())
    }

    /// Generate a manifest file indexing all transformed primitives
    fn generate_manifest(&self, output_dir: &Path) -> Result<()> {
        let mut prompts_agents = Vec::new();
        let mut prompts_commands = Vec::new();
        let mut prompts_skills = Vec::new();
        let mut tools = Vec::new();
        let mut hooks = Vec::new();

        // Scan agents
        let agents_dir = output_dir.join("prompts/agents");
        if agents_dir.exists() {
            for entry in fs::read_dir(agents_dir)? {
                let entry = entry?;
                if entry.path().extension().and_then(|s| s.to_str()) == Some("json") {
                    if let Some(stem) = entry.path().file_stem() {
                        prompts_agents.push(stem.to_string_lossy().to_string());
                    }
                }
            }
        }

        // Scan commands
        let commands_dir = output_dir.join("prompts/commands");
        if commands_dir.exists() {
            for entry in fs::read_dir(commands_dir)? {
                let entry = entry?;
                if entry.path().extension().and_then(|s| s.to_str()) == Some("json") {
                    if let Some(stem) = entry.path().file_stem() {
                        prompts_commands.push(stem.to_string_lossy().to_string());
                    }
                }
            }
        }

        // Scan skills
        let skills_dir = output_dir.join("prompts/skills");
        if skills_dir.exists() {
            for entry in fs::read_dir(skills_dir)? {
                let entry = entry?;
                if entry.path().extension().and_then(|s| s.to_str()) == Some("json") {
                    if let Some(stem) = entry.path().file_stem() {
                        prompts_skills.push(stem.to_string_lossy().to_string());
                    }
                }
            }
        }

        // Scan tools
        let functions_dir = output_dir.join("functions");
        if functions_dir.exists() {
            for entry in fs::read_dir(functions_dir)? {
                let entry = entry?;
                if entry.path().extension().and_then(|s| s.to_str()) == Some("json") {
                    if let Some(stem) = entry.path().file_stem() {
                        tools.push(stem.to_string_lossy().to_string());
                    }
                }
            }
        }

        // Scan hooks
        let middleware_dir = output_dir.join("middleware");
        if middleware_dir.exists() {
            for entry in fs::read_dir(middleware_dir)? {
                let entry = entry?;
                if entry.path().extension().and_then(|s| s.to_str()) == Some("json") {
                    if let Some(stem) = entry.path().file_stem() {
                        hooks.push(stem.to_string_lossy().to_string());
                    }
                }
            }
        }

        // Build manifest
        let manifest = json!({
            "spec_version": self.spec_version,
            "generated_at": chrono::Utc::now().to_rfc3339(),
            "provider": "openai",
            "primitives": {
                "prompts": {
                    "agents": prompts_agents,
                    "commands": prompts_commands,
                    "skills": prompts_skills,
                },
                "tools": tools,
                "hooks": hooks,
            }
        });

        // Write manifest
        let manifest_file = output_dir.join("manifest.json");
        let manifest_str = serde_json::to_string_pretty(&manifest)?;
        fs::write(manifest_file, manifest_str)?;

        Ok(())
    }
}

impl Default for OpenAITransformer {
    fn default() -> Self {
        Self::new()
    }
}

impl ProviderTransformer for OpenAITransformer {
    fn provider_name(&self) -> &str {
        "openai"
    }

    fn transform_primitive(
        &self,
        primitive_path: &Path,
        output_dir: &Path,
    ) -> Result<TransformResult> {
        // Detect primitive type
        let primitive_type = Self::detect_primitive_type(primitive_path).context(format!(
            "Failed to detect primitive type: {}",
            primitive_path.display()
        ))?;

        // Transform based on type
        match primitive_type.as_str() {
            "prompt" => {
                let primitive = PromptPrimitive::load(primitive_path)?;
                self.transform_prompt(&primitive, output_dir)
            }
            "tool" => {
                let primitive = ToolPrimitive::load(primitive_path)?;
                self.transform_tool(&primitive, output_dir)
            }
            "hook" => {
                let primitive = HookPrimitive::load(primitive_path)?;
                self.transform_hook(&primitive, output_dir)
            }
            _ => bail!("Unknown primitive type: {primitive_type}"),
        }
    }

    fn transform_batch(
        &self,
        primitive_paths: &[&Path],
        output_dir: &Path,
    ) -> Result<Vec<TransformResult>> {
        let mut results = Vec::new();

        for path in primitive_paths {
            match self.transform_primitive(path, output_dir) {
                Ok(result) => results.push(result),
                Err(e) => {
                    // Continue with other primitives even if one fails
                    results.push(TransformResult::failure(
                        path.file_name()
                            .and_then(|s| s.to_str())
                            .unwrap_or("unknown")
                            .to_string(),
                        "unknown".to_string(),
                        format!("Error: {e}"),
                    ));
                }
            }
        }

        // Generate manifest after all transformations
        self.generate_manifest(output_dir)?;

        Ok(results)
    }

    fn validate_output(&self, output_dir: &Path) -> Result<()> {
        if !output_dir.exists() {
            bail!("Output directory does not exist: {}", output_dir.display());
        }

        // Check for manifest
        let manifest_path = output_dir.join("manifest.json");
        if !manifest_path.exists() {
            bail!("Manifest file not found: {}", manifest_path.display());
        }

        // Validate manifest structure
        let manifest_content = fs::read_to_string(&manifest_path)?;
        let manifest: Value = serde_json::from_str(&manifest_content)?;

        // Check required fields
        if manifest.get("spec_version").is_none() {
            bail!("Manifest missing 'spec_version' field");
        }
        if manifest.get("provider").is_none() {
            bail!("Manifest missing 'provider' field");
        }
        if manifest.get("primitives").is_none() {
            bail!("Manifest missing 'primitives' field");
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_map_type_to_openai() {
        assert_eq!(OpenAITransformer::map_type_to_openai("string"), "string");
        assert_eq!(OpenAITransformer::map_type_to_openai("number"), "number");
        assert_eq!(OpenAITransformer::map_type_to_openai("integer"), "number");
        assert_eq!(OpenAITransformer::map_type_to_openai("boolean"), "boolean");
        assert_eq!(OpenAITransformer::map_type_to_openai("array"), "array");
        assert_eq!(OpenAITransformer::map_type_to_openai("object"), "object");
        assert_eq!(
            OpenAITransformer::map_type_to_openai("unknown_type"),
            "string"
        );
    }

    #[test]
    fn test_extract_variables() {
        let content = "Hello {{name}}, welcome to {{place}}!";
        let vars = OpenAITransformer::extract_variables(content);
        assert_eq!(vars, vec!["name", "place"]);
    }

    #[test]
    fn test_extract_variables_with_duplicates() {
        let content = "{{name}} is {{name}}";
        let vars = OpenAITransformer::extract_variables(content);
        assert_eq!(vars, vec!["name"]);
    }

    #[test]
    fn test_extract_variables_empty() {
        let content = "No variables here";
        let vars = OpenAITransformer::extract_variables(content);
        assert!(vars.is_empty());
    }

    #[test]
    fn test_provider_name() {
        let transformer = OpenAITransformer::new();
        assert_eq!(transformer.provider_name(), "openai");
    }
}
