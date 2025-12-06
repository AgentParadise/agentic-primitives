use crate::primitives::{HookMeta, PromptKind, PromptMeta, ToolMeta};
use crate::providers::{ProviderTransformer, TransformResult};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::Path;

/// Claude provider transformer - converts primitives to .claude/ format
pub struct ClaudeTransformer {}

impl ClaudeTransformer {
    /// Create a new Claude transformer with default configuration
    pub fn new() -> Self {
        Self {}
    }

    /// Determine the kind of primitive at the given path
    fn detect_primitive_kind(&self, path: &Path) -> Result<PrimitiveKind> {
        // Check for atomic hooks structure (handlers/ directory)
        if let Some(dir_name) = path.file_name().and_then(|n| n.to_str()) {
            if dir_name == "hooks" && path.join("handlers").exists() {
                return Ok(PrimitiveKind::Hook);
            }
        }

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

        // Check for prompt meta files - try new convention first (ADR-019)
        let dir_name = path
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or_else(|| anyhow::anyhow!("Unable to determine primitive kind for: {}", path.display()))?;

        let meta_file = if path.join(format!("{dir_name}.meta.yaml")).exists() {
            path.join(format!("{dir_name}.meta.yaml"))
        } else if path.join(format!("{dir_name}.yaml")).exists() {
            path.join(format!("{dir_name}.yaml"))
        } else if path.join("meta.yaml").exists() {
            path.join("meta.yaml")
        } else {
            bail!("No metadata file found in {}", path.display())
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
        let dir_name = path
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or_else(|| anyhow::anyhow!("Invalid primitive path"))?;

        // Try new convention first (ADR-019): {id}.meta.yaml
        let meta_path = if path.join(format!("{dir_name}.meta.yaml")).exists() {
            path.join(format!("{dir_name}.meta.yaml"))
        // Legacy fallbacks
        } else if path.join(format!("{dir_name}.yaml")).exists() {
            path.join(format!("{dir_name}.yaml"))
        } else if path.join("meta.yaml").exists() {
            path.join("meta.yaml")
        } else {
            bail!("No metadata file found in {}", path.display())
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

    /// Transform hooks using atomic architecture (handlers + validators)
    /// This is called once to set up the entire hooks system, not per-hook
    fn transform_hook(&self, path: &Path, output_dir: &Path) -> Result<Vec<String>> {
        // Create .claude directory structure
        let claude_dir = output_dir.join(".claude");
        let hooks_dir = claude_dir.join("hooks");
        let handlers_dir = hooks_dir.join("handlers");
        let validators_dir = hooks_dir.join("validators");

        fs::create_dir_all(&handlers_dir)?;
        fs::create_dir_all(&validators_dir)?;

        let settings_file = claude_dir.join("settings.json");

        let mut generated_files = vec![settings_file.to_string_lossy().to_string()];

        // Determine hooks root - if path already has handlers/, use it directly
        // Otherwise assume legacy structure and go up
        let hooks_root = if path.join("handlers").exists() {
            path.to_path_buf()
        } else {
            // Legacy path structure: primitives/v1/hooks/{category}/{hook-id}/
            path.parent()
                .and_then(|p| p.parent())
                .context("Failed to find hooks root directory")?
                .to_path_buf()
        };

        // Copy handlers if they exist
        let handlers_src = hooks_root.join("handlers");
        if handlers_src.exists() {
            generated_files.extend(self.copy_directory(&handlers_src, &handlers_dir)?);
        }

        // Copy validators if they exist
        let validators_src = hooks_root.join("validators");
        if validators_src.exists() {
            generated_files.extend(Self::copy_directory_recursive(
                &validators_src,
                &validators_dir,
            )?);
        }

        // Generate settings.json with handlers
        let settings = self.generate_hooks_settings()?;
        let json = serde_json::to_string_pretty(&settings)?;
        fs::write(&settings_file, json)?;

        Ok(generated_files)
    }

    /// Copy a directory's Python files (non-recursive)
    fn copy_directory(&self, src: &Path, dest: &Path) -> Result<Vec<String>> {
        let mut copied = Vec::new();

        if !src.exists() {
            return Ok(copied);
        }

        fs::create_dir_all(dest)?;

        for entry in fs::read_dir(src)? {
            let entry = entry?;
            let path = entry.path();

            if path.is_file() && path.extension().is_some_and(|e| e == "py") {
                let dest_file = dest.join(path.file_name().unwrap());
                fs::copy(&path, &dest_file)?;

                // Make executable
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    let mut perms = fs::metadata(&dest_file)?.permissions();
                    perms.set_mode(0o755);
                    fs::set_permissions(&dest_file, perms)?;
                }

                copied.push(dest_file.to_string_lossy().to_string());
            }
        }

        Ok(copied)
    }

    /// Copy a directory recursively (for validators with subdirectories)
    fn copy_directory_recursive(src: &Path, dest: &Path) -> Result<Vec<String>> {
        let mut copied = Vec::new();

        if !src.exists() {
            return Ok(copied);
        }

        fs::create_dir_all(dest)?;

        for entry in fs::read_dir(src)? {
            let entry = entry?;
            let path = entry.path();
            let file_name = path.file_name().unwrap();

            if path.is_dir() {
                // Recurse into subdirectory
                let dest_subdir = dest.join(file_name);
                copied.extend(Self::copy_directory_recursive(&path, &dest_subdir)?);
            } else if path.is_file() && path.extension().is_some_and(|e| e == "py") {
                let dest_file = dest.join(file_name);
                fs::copy(&path, &dest_file)?;

                // Make executable
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    let mut perms = fs::metadata(&dest_file)?.permissions();
                    perms.set_mode(0o755);
                    fs::set_permissions(&dest_file, perms)?;
                }

                copied.push(dest_file.to_string_lossy().to_string());
            }
        }

        Ok(copied)
    }

    /// Generate settings.json with atomic handlers for all Claude Code events
    pub fn generate_hooks_settings(&self) -> Result<serde_json::Value> {
        let settings = serde_json::json!({
            "hooks": {
                "PreToolUse": [{
                    "matcher": "*",
                    "hooks": [{
                        "type": "command",
                        "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/handlers/pre-tool-use.py",
                        "timeout": 10
                    }]
                }],
                "PostToolUse": [{
                    "matcher": "*",
                    "hooks": [{
                        "type": "command",
                        "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/handlers/post-tool-use.py",
                        "timeout": 10
                    }]
                }],
                "UserPromptSubmit": [{
                    "hooks": [{
                        "type": "command",
                        "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/handlers/user-prompt.py",
                        "timeout": 5
                    }]
                }],
                "Stop": [{
                    "hooks": [{
                        "type": "command",
                        "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/handlers/stop.py",
                        "timeout": 5
                    }]
                }],
                "SubagentStop": [{
                    "hooks": [{
                        "type": "command",
                        "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/handlers/subagent-stop.py",
                        "timeout": 5
                    }]
                }],
                "SessionStart": [{
                    "matcher": "*",
                    "hooks": [{
                        "type": "command",
                        "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/handlers/session-start.py",
                        "timeout": 5
                    }]
                }],
                "SessionEnd": [{
                    "hooks": [{
                        "type": "command",
                        "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/handlers/session-end.py",
                        "timeout": 5
                    }]
                }],
                "PreCompact": [{
                    "matcher": "*",
                    "hooks": [{
                        "type": "command",
                        "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/handlers/pre-compact.py",
                        "timeout": 5
                    }]
                }],
                "Notification": [{
                    "matcher": "*",
                    "hooks": [{
                        "type": "command",
                        "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/handlers/notification.py",
                        "timeout": 5
                    }]
                }]
            }
        });

        Ok(settings)
    }

    /// Transform a tool primitive to MCP config entry
    fn transform_tool(&self, path: &Path, output_dir: &Path) -> Result<Vec<String>> {
        let mcp_file = output_dir.join("mcp.json");

        let dir_name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown");

        // Load tool metadata - try new pattern first (ADR-019)
        let meta_path = {
            let id_tool_path = path.join(format!("{dir_name}.tool.yaml"));
            if id_tool_path.exists() {
                id_tool_path
            } else {
                path.join("tool.meta.yaml")
            }
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

        // Try to get Claude config from providers section in tool.yaml (ADR-019)
        let server_config = if let Some(ref providers) = meta.providers {
            if let Some(claude) = providers.get("claude") {
                // Read from providers.claude in tool.yaml
                let command = claude
                    .get("command")
                    .or_else(|| claude.get("native_tool"))
                    .and_then(|v| v.as_str())
                    .unwrap_or("echo");

                let args = claude
                    .get("args")
                    .and_then(|v| v.as_array())
                    .map(|arr| {
                        arr.iter()
                            .filter_map(|v| v.as_str().map(String::from))
                            .collect()
                    })
                    .unwrap_or_default();

                let env = claude
                    .get("env")
                    .and_then(|v| v.as_object())
                    .map(|obj| {
                        obj.iter()
                            .filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_string())))
                            .collect()
                    })
                    .unwrap_or_default();

                McpServerConfig { command: command.to_string(), args, env }
            } else {
                // No Claude provider in providers section
                self.load_claude_impl_file(path, &meta)?
            }
        } else {
            // No providers section, try fallback files
            self.load_claude_impl_file(path, &meta)?
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

    /// Load Claude implementation from separate file or generate placeholder
    fn load_claude_impl_file(&self, path: &Path, meta: &ToolMeta) -> Result<McpServerConfig> {
        let dir_name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown");

        // Try new convention first: {id}.claude.yaml
        let claude_file = path.join(format!("{dir_name}.claude.yaml"));
        // Legacy fallback: impl.claude.yaml
        let impl_file = path.join("impl.claude.yaml");

        if claude_file.exists() {
            let impl_content = fs::read_to_string(&claude_file)?;
            let impl_data: ClaudeToolImpl = serde_yaml::from_str(&impl_content)?;
            Ok(McpServerConfig {
                command: impl_data.command,
                args: impl_data.args.unwrap_or_default(),
                env: impl_data.env.unwrap_or_default(),
            })
        } else if impl_file.exists() {
            let impl_content = fs::read_to_string(&impl_file)?;
            let impl_data: ClaudeToolImpl = serde_yaml::from_str(&impl_content)?;
            Ok(McpServerConfig {
                command: impl_data.command,
                args: impl_data.args.unwrap_or_default(),
                env: impl_data.env.unwrap_or_default(),
            })
        } else {
            // Generate placeholder config
            Ok(McpServerConfig {
                command: "echo".to_string(),
                args: vec![format!("Tool '{}' has no Claude provider configured", meta.id)],
                env: HashMap::new(),
            })
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
                // Check for atomic hooks structure (handlers/ directory)
                if primitive_path.join("handlers").exists() {
                    let files = self.transform_hook(primitive_path, output_dir)?;
                    ("atomic-hooks".to_string(), "hook", files)
                } else {
                    // Legacy: Try new pattern first ({id}.hook.yaml), then legacy (hook.meta.yaml)
                    let meta_path = if let Some(dir_name) =
                        primitive_path.file_name().and_then(|n| n.to_str())
                    {
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
    fn test_generate_hooks_settings() {
        let transformer = ClaudeTransformer::new();
        let settings = transformer.generate_hooks_settings().unwrap();

        // Verify structure
        assert!(settings.get("hooks").is_some());
        let hooks = settings.get("hooks").unwrap();
        assert!(hooks.get("PreToolUse").is_some());
        assert!(hooks.get("PostToolUse").is_some());
        assert!(hooks.get("UserPromptSubmit").is_some());
    }
}
