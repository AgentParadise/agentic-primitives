use crate::primitives::{HookEvent, HookMeta, PromptKind, PromptMeta, ToolMeta};
use crate::providers::{ProviderTransformer, TransformResult};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

/// Claude provider transformer - converts primitives to .claude/ format
pub struct ClaudeTransformer {}

impl ClaudeTransformer {
    /// Create a new Claude transformer with default configuration
    pub fn new() -> Self {
        Self {}
    }

    /// Determine the kind of primitive at the given path
    fn detect_primitive_kind(&self, path: &Path) -> Result<PrimitiveKind> {
        // Check for meta files to determine kind
        // Try new pattern first ({id}.hook.yaml), then fall back to legacy (hook.meta.yaml)
        if let Some(dir_name) = path.file_name().and_then(|n| n.to_str()) {
            if path.join(format!("{dir_name}.hook.yaml")).exists()
                || path.join("hook.meta.yaml").exists()
            {
                return Ok(PrimitiveKind::Hook);
            }
            if path.join(format!("{dir_name}.tool.yaml")).exists()
                || path.join("tool.meta.yaml").exists()
            {
                return Ok(PrimitiveKind::Tool);
            }
        }

        // Check for prompt meta files - try multiple patterns
        let meta_file = if path.join("meta.yaml").exists() {
            path.join("meta.yaml")
        } else if let Some(dir_name) = path.file_name().and_then(|n| n.to_str()) {
            // Try {id}.yaml pattern (where id matches directory name)
            let id_meta_file = path.join(format!("{dir_name}.yaml"));
            if id_meta_file.exists() {
                id_meta_file
            } else {
                bail!(
                    "No meta.yaml or {}.yaml file found in {}",
                    dir_name,
                    path.display()
                )
            }
        } else {
            bail!("Unable to determine primitive kind for: {}", path.display())
        };

        let meta_content = fs::read_to_string(&meta_file)?;
        let meta: PromptMeta = serde_yaml::from_str(&meta_content)?;
        match meta.kind {
            PromptKind::Agent => Ok(PrimitiveKind::Agent),
            PromptKind::Command => Ok(PrimitiveKind::Command),
            PromptKind::Skill => Ok(PrimitiveKind::Skill),
            PromptKind::MetaPrompt => Ok(PrimitiveKind::MetaPrompt),
        }
    }

    /// Load prompt metadata and content from a primitive directory
    fn load_prompt_primitive(&self, path: &Path) -> Result<(PromptMeta, String)> {
        // Find meta file - try multiple patterns
        let meta_path = if path.join("meta.yaml").exists() {
            path.join("meta.yaml")
        } else if let Some(dir_name) = path.file_name().and_then(|n| n.to_str()) {
            let id_meta_path = path.join(format!("{dir_name}.yaml"));
            if id_meta_path.exists() {
                id_meta_path
            } else {
                bail!(
                    "No meta.yaml or {}.yaml file found in {}",
                    dir_name,
                    path.display()
                )
            }
        } else {
            bail!("Cannot determine meta file for {}", path.display())
        };

        let meta_content = fs::read_to_string(&meta_path).context(format!(
            "Failed to read {} from {}",
            meta_path.display(),
            path.display()
        ))?;
        let meta: PromptMeta = serde_yaml::from_str(&meta_content)?;

        // Determine which content file to load
        let content_file = if let Some(default_version) = meta.default_version {
            let version_entry = meta
                .versions
                .iter()
                .find(|v| v.version == default_version)
                .context(format!("Version {default_version} not found"))?;
            version_entry.file.clone()
        } else {
            format!("{}.prompt.md", meta.id)
        };

        let content_path = path.join(&content_file);
        let content = fs::read_to_string(&content_path).context(format!(
            "Failed to read content file: {}",
            content_path.display()
        ))?;

        Ok((meta, content))
    }

    /// Transform an agent primitive to Claude custom prompt
    fn transform_agent(&self, path: &Path, output_dir: &Path) -> Result<Vec<String>> {
        let (meta, content) = self.load_prompt_primitive(path)?;

        let custom_prompts_dir = output_dir.join("custom_prompts");
        fs::create_dir_all(&custom_prompts_dir)?;

        let output_file = custom_prompts_dir.join(format!("{}.md", meta.id));

        // Build frontmatter
        let mut frontmatter = String::new();
        frontmatter.push_str("---\n");
        frontmatter.push_str(&format!("id: {}\n", meta.id));
        frontmatter.push_str(&format!("domain: {}\n", meta.domain));

        if let Some(default_version) = meta.default_version {
            frontmatter.push_str(&format!("version: {default_version}\n"));
            if let Some(version_entry) = meta.versions.iter().find(|v| v.version == default_version)
            {
                frontmatter.push_str(&format!("status: {}\n", version_entry.status));
            }
        }

        frontmatter.push_str("---\n\n");

        // Combine frontmatter and content
        let full_content = format!("{frontmatter}{content}");

        fs::write(&output_file, full_content)?;

        Ok(vec![output_file.to_string_lossy().to_string()])
    }

    /// Transform a command primitive to Claude command file
    fn transform_command(&self, path: &Path, output_dir: &Path) -> Result<Vec<String>> {
        let (meta, content) = self.load_prompt_primitive(path)?;

        let commands_dir = output_dir.join("commands");
        fs::create_dir_all(&commands_dir)?;

        let output_file = commands_dir.join(format!("{}.md", meta.id));

        // For commands, we just write the content directly (no frontmatter needed)
        fs::write(&output_file, &content)?;

        Ok(vec![output_file.to_string_lossy().to_string()])
    }

    /// Transform a skill primitive to manifest entry
    fn transform_skill(&self, path: &Path, output_dir: &Path) -> Result<Vec<String>> {
        let (meta, _content) = self.load_prompt_primitive(path)?;

        let skills_file = output_dir.join("skills.json");

        // Load existing skills or create new
        let mut skills: SkillsManifest = if skills_file.exists() {
            let content = fs::read_to_string(&skills_file)?;
            serde_json::from_str(&content)?
        } else {
            SkillsManifest {
                skills: Vec::new(),
                note: "This is a manifest file only. Skills are injected into system prompts by the orchestrator.".to_string(),
            }
        };

        // Add this skill
        skills.skills.push(SkillEntry {
            id: meta.id.clone(),
            domain: meta.domain.clone(),
            category: meta.category.clone(),
            summary: meta.summary.clone(),
            version: meta.default_version,
        });

        // Write updated manifest
        let json = serde_json::to_string_pretty(&skills)?;
        fs::write(&skills_file, json)?;

        Ok(vec![skills_file.to_string_lossy().to_string()])
    }

    /// Transform a hook primitive to .claude/settings.json entry
    fn transform_hook(&self, path: &Path, output_dir: &Path) -> Result<Vec<String>> {
        use crate::providers::registry::ProviderRegistry;

        // Create .claude directory structure
        let claude_dir = output_dir.join(".claude");
        let hooks_dir = claude_dir.join("hooks");
        fs::create_dir_all(&hooks_dir)?;

        // Use settings.json instead of hooks.json
        let settings_file = claude_dir.join("settings.json");

        // Load hook metadata - try new pattern first
        let meta_path = if let Some(dir_name) = path.file_name().and_then(|n| n.to_str()) {
            let id_hook_path = path.join(format!("{dir_name}.hook.yaml"));
            if id_hook_path.exists() {
                id_hook_path
            } else {
                path.join("hook.meta.yaml")
            }
        } else {
            path.join("hook.meta.yaml")
        };

        let meta_content = fs::read_to_string(&meta_path).context(format!(
            "Failed to read hook meta file from {}",
            path.display()
        ))?;
        let meta: HookMeta = serde_yaml::from_str(&meta_content)?;

        // Try to load agent hook config (optional)
        // Look for providers/agents/claude-code/hooks-config/{hook_id}.yaml
        let workspace_root = output_dir
            .parent()
            .and_then(|p| p.parent())
            .context("Failed to find workspace root")?;

        let providers_dir = workspace_root.join("providers");
        let agent_hook_config = if providers_dir.exists() {
            // Try to load provider registry and agent hook config
            match ProviderRegistry::load(&providers_dir) {
                Ok(registry) => {
                    if let Some(agent) = registry.get_agent("claude-code") {
                        match agent.load_hook_config(&meta.id) {
                            Ok(config) => {
                                // Validate middleware events
                                if let Err(e) = agent.validate_middleware_events(&config.middleware)
                                {
                                    eprintln!("⚠️  Warning: {}", e);
                                }
                                Some(config)
                            }
                            Err(_) => {
                                // No agent-specific config, use primitive config only
                                None
                            }
                        }
                    } else {
                        None
                    }
                }
                Err(_) => None,
            }
        } else {
            None
        };

        // Load existing settings or create new
        // Settings file contains: { "hooks": { ... } }
        let mut settings = if settings_file.exists() {
            let content = fs::read_to_string(&settings_file)?;
            serde_json::from_str(&content)?
        } else {
            serde_json::json!({})
        };

        // Extract hooks from settings, or create new
        let mut hooks: ClaudeHooksConfig = if let Some(hooks_obj) = settings.get("hooks") {
            serde_json::from_value(hooks_obj.clone())?
        } else {
            ClaudeHooksConfig::default()
        };

        // Determine events to register
        let events_to_register = if let Some(ref _agent_config) = agent_hook_config {
            // Use agent's supported events (universal hook)
            if let Ok(registry) = ProviderRegistry::load(&providers_dir) {
                if let Some(agent) = registry.get_agent("claude-code") {
                    agent.supported_events.clone()
                } else {
                    meta.get_events()
                }
            } else {
                meta.get_events()
            }
        } else {
            meta.get_events()
        };

        if events_to_register.is_empty() {
            return Err(anyhow::anyhow!(
                "Hook '{}' has no events specified",
                meta.id
            ));
        }

        // Generate ONE Python wrapper that will be used for ALL events
        // Organize by category (e.g., hooks/core/, hooks/security/)
        // Extract category from path: primitives/v1/hooks/{category}/{id}/
        let category = path
            .parent()
            .and_then(|p| p.file_name())
            .and_then(|n| n.to_str())
            .unwrap_or("uncategorized");

        let category_dir = hooks_dir.join(category);
        fs::create_dir_all(&category_dir)?;

        let mut generated_files = vec![settings_file.to_string_lossy().to_string()];

        // Generate Python wrapper with embedded config
        let wrapper_path = self.generate_python_wrapper_with_config(
            &meta,
            &category_dir,
            output_dir,
            agent_hook_config.as_ref(),
        )?;
        generated_files.push(wrapper_path.to_string_lossy().to_string());

        // Copy Python implementation if it exists (use directory name, not impl.python.py)
        let python_impl = path.join(format!("{}.py", meta.id));
        if python_impl.exists() {
            let dest_impl = category_dir.join(format!("{}.impl.py", meta.id));
            fs::copy(&python_impl, &dest_impl)?;
            generated_files.push(dest_impl.to_string_lossy().to_string());
        }

        // Load agent provider for event config
        let agent_provider = if providers_dir.exists() {
            ProviderRegistry::load(&providers_dir)
                .ok()
                .and_then(|r| r.get_agent("claude-code").cloned())
        } else {
            None
        };

        // Register the same hook command for ALL events
        for event in &events_to_register {
            let event_key = self.hook_event_to_claude(event);

            // Determine if matcher is needed for this event
            let matcher = if let Some(ref agent) = agent_provider {
                if let Some(event_cfg) = agent.get_event_config(event) {
                    if event_cfg.requires_matcher {
                        Some(meta.category.clone())
                    } else {
                        None
                    }
                } else {
                    Some(meta.category.clone())
                }
            } else {
                Some(meta.category.clone())
            };

            // Create hook entry (using .py wrapper, not .sh!)
            let hook_entry = ClaudeHookEntry {
                matcher: matcher.unwrap_or_else(|| "*".to_string()),
                hooks: vec![ClaudeHook {
                    hook_type: "command".to_string(),
                    command: format!(
                        "${{CLAUDE_PROJECT_DIR}}/.claude/hooks/{}/{}.py",
                        category, meta.id
                    ),
                    timeout: agent_hook_config
                        .as_ref()
                        .and_then(|c| c.execution.as_ref())
                        .and_then(|e| e.timeout_sec)
                        .or(meta.execution.timeout_sec),
                }],
            };

            // Add hook entry for this event
            hooks.add_hook(&event_key, hook_entry);
        }

        // Write updated settings.json with hooks nested under "hooks" key
        settings["hooks"] = serde_json::to_value(&hooks)?;
        let json = serde_json::to_string_pretty(&settings)?;
        fs::write(&settings_file, json)?;

        Ok(generated_files)
    }

    /// Transform a tool primitive to MCP config entry
    fn transform_tool(&self, path: &Path, output_dir: &Path) -> Result<Vec<String>> {
        let mcp_file = output_dir.join("mcp.json");

        // Load tool metadata - try new pattern first
        let meta_path = if let Some(dir_name) = path.file_name().and_then(|n| n.to_str()) {
            let id_tool_path = path.join(format!("{dir_name}.tool.yaml"));
            if id_tool_path.exists() {
                id_tool_path
            } else {
                path.join("tool.meta.yaml")
            }
        } else {
            path.join("tool.meta.yaml")
        };

        let meta_content = fs::read_to_string(&meta_path).context(format!(
            "Failed to read tool meta file from {}",
            path.display()
        ))?;
        let meta: ToolMeta = serde_yaml::from_str(&meta_content)?;

        // Load existing MCP config or create new
        let mut mcp_config: McpConfig = if mcp_file.exists() {
            let content = fs::read_to_string(&mcp_file)?;
            serde_json::from_str(&content)?
        } else {
            McpConfig {
                mcp_servers: HashMap::new(),
            }
        };

        // Check if there's a Claude-specific implementation
        let impl_file = path.join("impl.claude.yaml");

        let server_config = if impl_file.exists() {
            // Load Claude-specific config
            let impl_content = fs::read_to_string(&impl_file)?;
            let impl_data: ClaudeToolImpl = serde_yaml::from_str(&impl_content)?;
            McpServerConfig {
                command: impl_data.command,
                args: impl_data.args.unwrap_or_default(),
                env: impl_data.env.unwrap_or_default(),
            }
        } else {
            // Generate generic config from metadata
            McpServerConfig {
                command: "echo".to_string(),
                args: vec![format!("Tool '{}' not implemented", meta.id)],
                env: HashMap::new(),
            }
        };

        // Add to MCP servers
        mcp_config
            .mcp_servers
            .insert(meta.id.clone(), server_config);

        // Write updated config
        let json = serde_json::to_string_pretty(&mcp_config)?;
        fs::write(&mcp_file, json)?;

        Ok(vec![mcp_file.to_string_lossy().to_string()])
    }

    /// Generate Python wrapper for hook execution (replaces bash scripts)
    fn generate_python_wrapper(
        &self,
        hook_meta: &HookMeta,
        scripts_dir: &Path,
        output_dir: &Path,
    ) -> Result<std::path::PathBuf> {
        // Wrapper will be hook_id.py (NOT .sh!)
        let wrapper_path = scripts_dir.join(format!("{}.py", hook_meta.id));

        // Load template
        let template_str = include_str!("../templates/hook_wrapper.py.template");

        // Calculate relative path from build output to services directory
        let services_relative_path = self.calculate_services_path(output_dir)?;

        // Simple template substitution (not using handlebars to avoid extra dependency)
        let mut rendered = template_str.replace("{{hook_id}}", &hook_meta.id);
        rendered = rendered.replace("{{impl_filename}}", &format!("{}.impl.py", hook_meta.id));

        // Handle conditional for services path
        if !services_relative_path.is_empty() {
            // Replace placeholders when we have a services path
            rendered = rendered.replace("{{services_relative_path}}", &services_relative_path);

            // Remove conditional markers
            rendered = rendered.replace("{{#if services_relative_path}}", "");
            rendered = rendered.replace("{{else}}", "# No services path, using:");
            rendered = rendered.replace("{{/if}}", "");
        } else {
            // When no services path, remove the if block content, keep else
            if let Some(if_start) = rendered.find("{{#if services_relative_path}}") {
                if let Some(else_start) = rendered.find("{{else}}") {
                    if let Some(if_end) = rendered.find("{{/if}}") {
                        let before = &rendered[..if_start];
                        let else_content = &rendered[else_start + 8..if_end]; // Skip "{{else}}"
                        let after = &rendered[if_end + 7..]; // Skip "{{/if}}"
                        rendered = format!("{}{}{}", before, else_content, after);
                    }
                }
            }
        }

        // Write wrapper
        fs::write(&wrapper_path, rendered)?;

        // Make executable (Unix only)
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = fs::metadata(&wrapper_path)?.permissions();
            perms.set_mode(0o755);
            fs::set_permissions(&wrapper_path, perms)?;
        }

        Ok(wrapper_path)
    }

    /// Generate Python wrapper with embedded middleware config
    fn generate_python_wrapper_with_config(
        &self,
        hook_meta: &HookMeta,
        scripts_dir: &Path,
        output_dir: &Path,
        agent_config: Option<&crate::providers::registry::AgentHookConfig>,
    ) -> Result<PathBuf> {
        // If agent config provided, use the new template with embedded config
        if let Some(config) = agent_config {
            self.generate_python_wrapper_with_embedded_config(
                hook_meta,
                scripts_dir,
                output_dir,
                config,
            )
        } else {
            // Fallback to original wrapper without embedded config
            self.generate_python_wrapper(hook_meta, scripts_dir, output_dir)
        }
    }

    /// Generate Python wrapper with embedded middleware config (new approach)
    fn generate_python_wrapper_with_embedded_config(
        &self,
        hook_meta: &HookMeta,
        scripts_dir: &Path,
        output_dir: &Path,
        agent_config: &crate::providers::registry::AgentHookConfig,
    ) -> Result<PathBuf> {
        use handlebars::Handlebars;
        use serde_json::json;

        let wrapper_path = scripts_dir.join(format!("{}.py", hook_meta.id));

        // Serialize middleware config as JSON
        let config_json = serde_json::to_string_pretty(&agent_config)?;

        // Load template
        let template_str = include_str!("../templates/hook_wrapper_with_config.py.template");
        let handlebars = Handlebars::new();

        // Calculate services path
        let services_relative_path = self
            .calculate_services_path(output_dir)
            .unwrap_or_else(|_| String::new());

        // Prepare template data
        let data = json!({
            "hook_id": hook_meta.id,
            "impl_filename": agent_config.primitive.impl_file,
            "services_relative_path": services_relative_path,
            "config_json": config_json,
            "has_config": true,
        });

        // Render template
        let rendered = handlebars.render_template(template_str, &data)?;

        // Write wrapper
        fs::write(&wrapper_path, rendered)?;

        // Make executable (Unix only)
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = fs::metadata(&wrapper_path)?.permissions();
            perms.set_mode(0o755);
            fs::set_permissions(&wrapper_path, perms)?;
        }

        Ok(wrapper_path)
    }

    /// Calculate relative path from build output to services directory
    fn calculate_services_path(&self, output_dir: &Path) -> Result<String> {
        // From build/claude/hooks/scripts/ to services/analytics/
        // This is: ../../../../services/analytics

        // Try to find services directory relative to output
        let output_abs = output_dir
            .canonicalize()
            .unwrap_or_else(|_| output_dir.to_path_buf());
        let services_dir = output_abs
            .parent()
            .and_then(|p| p.parent())
            .map(|p| p.join("services/analytics"));

        if let Some(services) = services_dir {
            if services.exists() {
                // Calculate relative path from scripts_dir to services
                // scripts_dir is output_dir/hooks/scripts
                // So we need: ../../../../services/analytics
                return Ok("../../../../services/analytics".to_string());
            }
        }

        // No services directory found, use current directory
        Ok(String::new())
    }

    /// Convert HookEvent to Claude event name
    fn hook_event_to_claude(&self, event: &HookEvent) -> String {
        match event {
            HookEvent::PreToolUse => "PreToolUse".to_string(),
            HookEvent::PostToolUse => "PostToolUse".to_string(),
            HookEvent::UserPromptSubmit => "UserPromptSubmit".to_string(),
            HookEvent::Stop => "Stop".to_string(),
            HookEvent::SubagentStop => "SubagentStop".to_string(),
            HookEvent::SessionStart => "SessionStart".to_string(),
            HookEvent::SessionEnd => "SessionEnd".to_string(),
            HookEvent::PreCompact => "PreCompact".to_string(),
            HookEvent::Notification => "Notification".to_string(),
        }
    }
}

impl Default for ClaudeTransformer {
    fn default() -> Self {
        Self::new()
    }
}

impl ProviderTransformer for ClaudeTransformer {
    fn provider_name(&self) -> &str {
        "claude"
    }

    fn transform_primitive(
        &self,
        primitive_path: &Path,
        output_dir: &Path,
    ) -> Result<TransformResult> {
        // Detect primitive kind
        let kind = self.detect_primitive_kind(primitive_path)?;

        // Transform based on kind
        let output_files = match kind {
            PrimitiveKind::Agent => {
                let (meta, _) = self.load_prompt_primitive(primitive_path)?;
                let id = meta.id.clone();
                let files = self.transform_agent(primitive_path, output_dir)?;
                (id, "agent", files)
            }
            PrimitiveKind::Command => {
                let (meta, _) = self.load_prompt_primitive(primitive_path)?;
                let id = meta.id.clone();
                let files = self.transform_command(primitive_path, output_dir)?;
                (id, "command", files)
            }
            PrimitiveKind::Skill => {
                let (meta, _) = self.load_prompt_primitive(primitive_path)?;
                let id = meta.id.clone();
                let files = self.transform_skill(primitive_path, output_dir)?;
                (id, "skill", files)
            }
            PrimitiveKind::MetaPrompt => {
                let (meta, _) = self.load_prompt_primitive(primitive_path)?;
                let id = meta.id.clone();
                // Meta-prompts are treated like commands
                let files = self.transform_command(primitive_path, output_dir)?;
                (id, "meta-prompt", files)
            }
            PrimitiveKind::Hook => {
                // Try new pattern first ({id}.hook.yaml), then legacy (hook.meta.yaml)
                let meta_path =
                    if let Some(dir_name) = primitive_path.file_name().and_then(|n| n.to_str()) {
                        let id_hook_path = primitive_path.join(format!("{dir_name}.hook.yaml"));
                        if id_hook_path.exists() {
                            id_hook_path
                        } else {
                            primitive_path.join("hook.meta.yaml")
                        }
                    } else {
                        primitive_path.join("hook.meta.yaml")
                    };
                let meta_content = fs::read_to_string(&meta_path)?;
                let meta: HookMeta = serde_yaml::from_str(&meta_content)?;
                let id = meta.id.clone();
                let files = self.transform_hook(primitive_path, output_dir)?;
                (id, "hook", files)
            }
            PrimitiveKind::Tool => {
                // Try new pattern first ({id}.tool.yaml), then legacy (tool.meta.yaml)
                let meta_path =
                    if let Some(dir_name) = primitive_path.file_name().and_then(|n| n.to_str()) {
                        let id_tool_path = primitive_path.join(format!("{dir_name}.tool.yaml"));
                        if id_tool_path.exists() {
                            id_tool_path
                        } else {
                            primitive_path.join("tool.meta.yaml")
                        }
                    } else {
                        primitive_path.join("tool.meta.yaml")
                    };
                let meta_content = fs::read_to_string(&meta_path)?;
                let meta: ToolMeta = serde_yaml::from_str(&meta_content)?;
                let id = meta.id.clone();
                let files = self.transform_tool(primitive_path, output_dir)?;
                (id, "tool", files)
            }
        };

        Ok(TransformResult::success(
            output_files.0,
            output_files.1.to_string(),
            output_files.2,
        ))
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
                    // On error, create a failure result
                    let id = path
                        .file_name()
                        .and_then(|n| n.to_str())
                        .unwrap_or("unknown")
                        .to_string();
                    results.push(TransformResult::failure(
                        id,
                        "unknown".to_string(),
                        e.to_string(),
                    ));
                }
            }
        }

        Ok(results)
    }

    fn validate_output(&self, output_dir: &Path) -> Result<()> {
        // Ensure output directory exists
        if !output_dir.exists() {
            bail!("Output directory does not exist: {}", output_dir.display());
        }

        // Check for valid JSON files if they exist
        let mcp_file = output_dir.join("mcp.json");
        if mcp_file.exists() {
            let content = fs::read_to_string(&mcp_file).context("Failed to read mcp.json")?;
            serde_json::from_str::<serde_json::Value>(&content)
                .context("Invalid JSON in mcp.json")?;
        }

        let hooks_file = output_dir.join("hooks").join("hooks.json");
        if hooks_file.exists() {
            let content = fs::read_to_string(&hooks_file).context("Failed to read hooks.json")?;
            serde_json::from_str::<serde_json::Value>(&content)
                .context("Invalid JSON in hooks.json")?;
        }

        let skills_file = output_dir.join("skills.json");
        if skills_file.exists() {
            let content = fs::read_to_string(&skills_file).context("Failed to read skills.json")?;
            serde_json::from_str::<serde_json::Value>(&content)
                .context("Invalid JSON in skills.json")?;
        }

        Ok(())
    }
}

// ============================================================================
// Helper Types
// ============================================================================

#[derive(Debug, Clone, Copy)]
enum PrimitiveKind {
    Agent,
    Command,
    Skill,
    MetaPrompt,
    Hook,
    Tool,
}

// ============================================================================
// Claude Output Structures
// ============================================================================

#[derive(Debug, Serialize, Deserialize)]
struct SkillsManifest {
    note: String,
    skills: Vec<SkillEntry>,
}

#[derive(Debug, Serialize, Deserialize)]
struct SkillEntry {
    id: String,
    domain: String,
    category: String,
    summary: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    version: Option<u32>,
}

#[derive(Debug, Serialize, Deserialize, Default)]
struct ClaudeHooksConfig {
    #[serde(rename = "PreToolUse", skip_serializing_if = "Option::is_none")]
    pre_tool_use: Option<Vec<ClaudeHookEntry>>,

    #[serde(rename = "PostToolUse", skip_serializing_if = "Option::is_none")]
    post_tool_use: Option<Vec<ClaudeHookEntry>>,

    #[serde(rename = "UserPromptSubmit", skip_serializing_if = "Option::is_none")]
    user_prompt_submit: Option<Vec<ClaudeHookEntry>>,

    #[serde(rename = "Stop", skip_serializing_if = "Option::is_none")]
    stop: Option<Vec<ClaudeHookEntry>>,

    #[serde(rename = "SubagentStop", skip_serializing_if = "Option::is_none")]
    subagent_stop: Option<Vec<ClaudeHookEntry>>,

    #[serde(rename = "SessionStart", skip_serializing_if = "Option::is_none")]
    session_start: Option<Vec<ClaudeHookEntry>>,

    #[serde(rename = "SessionEnd", skip_serializing_if = "Option::is_none")]
    session_end: Option<Vec<ClaudeHookEntry>>,

    #[serde(rename = "PreCompact", skip_serializing_if = "Option::is_none")]
    pre_compact: Option<Vec<ClaudeHookEntry>>,

    #[serde(rename = "Notification", skip_serializing_if = "Option::is_none")]
    notification: Option<Vec<ClaudeHookEntry>>,
}

impl ClaudeHooksConfig {
    /// Add a hook entry to the appropriate event
    fn add_hook(&mut self, event: &str, entry: ClaudeHookEntry) {
        match event {
            "PreToolUse" => {
                self.pre_tool_use.get_or_insert_with(Vec::new).push(entry);
            }
            "PostToolUse" => {
                self.post_tool_use.get_or_insert_with(Vec::new).push(entry);
            }
            "UserPromptSubmit" => {
                self.user_prompt_submit
                    .get_or_insert_with(Vec::new)
                    .push(entry);
            }
            "Stop" => {
                self.stop.get_or_insert_with(Vec::new).push(entry);
            }
            "SubagentStop" => {
                self.subagent_stop.get_or_insert_with(Vec::new).push(entry);
            }
            "SessionStart" => {
                self.session_start.get_or_insert_with(Vec::new).push(entry);
            }
            "SessionEnd" => {
                self.session_end.get_or_insert_with(Vec::new).push(entry);
            }
            "PreCompact" => {
                self.pre_compact.get_or_insert_with(Vec::new).push(entry);
            }
            "Notification" => {
                self.notification.get_or_insert_with(Vec::new).push(entry);
            }
            _ => {
                eprintln!("⚠️  Unknown hook event: {}", event);
            }
        }
    }
}

#[derive(Debug, Serialize, Deserialize)]
struct ClaudeHookEntry {
    matcher: String,
    hooks: Vec<ClaudeHook>,
}

#[derive(Debug, Serialize, Deserialize)]
struct ClaudeHook {
    #[serde(rename = "type")]
    hook_type: String,
    command: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    timeout: Option<u32>,
}

#[derive(Debug, Serialize, Deserialize)]
struct McpConfig {
    #[serde(rename = "mcpServers")]
    mcp_servers: HashMap<String, McpServerConfig>,
}

#[derive(Debug, Serialize, Deserialize)]
struct McpServerConfig {
    command: String,
    #[serde(skip_serializing_if = "Vec::is_empty", default)]
    args: Vec<String>,
    #[serde(skip_serializing_if = "HashMap::is_empty", default)]
    env: HashMap<String, String>,
}

#[derive(Debug, Deserialize)]
struct ClaudeToolImpl {
    command: String,
    args: Option<Vec<String>>,
    env: Option<HashMap<String, String>>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_provider_name() {
        let transformer = ClaudeTransformer::new();
        assert_eq!(transformer.provider_name(), "claude");
    }

    #[test]
    fn test_hook_event_conversion() {
        let transformer = ClaudeTransformer::new();
        assert_eq!(
            transformer.hook_event_to_claude(&HookEvent::PreToolUse),
            "PreToolUse"
        );
        assert_eq!(
            transformer.hook_event_to_claude(&HookEvent::PostToolUse),
            "PostToolUse"
        );
    }
}
