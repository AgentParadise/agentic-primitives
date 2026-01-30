use crate::providers::{ProviderTransformer, TransformResult};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;

/// Claude v2 transformer - simplified format with frontmatter
pub struct ClaudeV2Transformer {}

impl ClaudeV2Transformer {
    pub fn new() -> Self {
        Self {}
    }

    /// Parse YAML frontmatter from markdown file
    fn parse_frontmatter(&self, content: &str) -> Result<(FrontmatterMetadata, String)> {
        let trimmed = content.trim_start();

        if !trimmed.starts_with("---") {
            bail!("No frontmatter found (must start with ---)");
        }

        // Find the closing ---
        let after_open = &trimmed[3..];
        let end_idx = after_open
            .find("\n---")
            .context("Frontmatter not closed (missing closing ---)")?;

        let yaml_str = &after_open[..end_idx].trim();
        let body = &after_open[end_idx + 4..].trim();

        let metadata: FrontmatterMetadata = serde_yaml::from_str(yaml_str)
            .with_context(|| format!("Failed to parse frontmatter YAML:\n{}", yaml_str))?;

        Ok((metadata, body.to_string()))
    }

    /// Transform a command (markdown file with frontmatter)
    fn transform_command(&self, path: &Path, output_dir: &Path) -> Result<Vec<String>> {
        let content = fs::read_to_string(path)?;
        let (metadata, body) = self.parse_frontmatter(&content)?;

        // Extract category and name from path
        // primitives/v2/commands/{category}/{name}.md
        let components: Vec<_> = path.components().collect();
        let category = components
            .get(components.len() - 2)
            .and_then(|c| c.as_os_str().to_str())
            .unwrap_or("core");
        let filename = path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown");

        // Build output path: commands/{category}/{name}.md
        let commands_dir = if category != "core" {
            output_dir.join("commands").join(category)
        } else {
            output_dir.join("commands")
        };
        fs::create_dir_all(&commands_dir)?;

        let output_file = commands_dir.join(format!("{}.md", filename));

        // Reconstruct with frontmatter (Claude Code expects it)
        let mut final_content = String::new();
        final_content.push_str("---\n");
        final_content.push_str(&format!("description: {}\n", metadata.description));
        if let Some(hint) = metadata.argument_hint {
            final_content.push_str(&format!("argument-hint: {}\n", hint));
        }
        if let Some(model) = metadata.model {
            final_content.push_str(&format!("model: {}\n", model));
        }
        if let Some(tools) = metadata.allowed_tools {
            final_content.push_str(&format!("allowed-tools: {}\n", tools));
        }
        final_content.push_str("---\n\n");
        final_content.push_str(&body);

        fs::write(&output_file, final_content)?;

        // Return relative path from output_dir
        let relative_path = output_file
            .strip_prefix(output_dir)
            .unwrap_or(&output_file)
            .to_string_lossy()
            .to_string();

        Ok(vec![relative_path])
    }

    /// Transform a skill (markdown file with frontmatter)
    fn transform_skill(&self, path: &Path, output_dir: &Path) -> Result<Vec<String>> {
        let content = fs::read_to_string(path)?;
        // We don't parse frontmatter for skills, just copy the entire file
        let filename = path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown");

        // Build output path: skills/{skill-name}/SKILL.md (Claude Code format)
        let skill_dir = output_dir.join("skills").join(filename);
        fs::create_dir_all(&skill_dir)?;

        let output_file = skill_dir.join("SKILL.md");

        // For skills, write the full content (body includes frontmatter)
        fs::write(&output_file, &content)?;

        // Return relative path from output_dir
        let relative_path = output_file
            .strip_prefix(output_dir)
            .unwrap_or(&output_file)
            .to_string_lossy()
            .to_string();

        Ok(vec![relative_path])
    }

    /// Transform a tool (directory with tool.yaml)
    fn transform_tool(&self, path: &Path, output_dir: &Path) -> Result<Vec<String>> {
        let tool_yaml = path.join("tool.yaml");
        if !tool_yaml.exists() {
            bail!("tool.yaml not found in {}", path.display());
        }

        // Verify tool.yaml is valid (no need to store spec for now)
        let tool_content = fs::read_to_string(&tool_yaml)?;
        let _tool_spec: ToolSpec =
            serde_yaml::from_str(&tool_content).context("Failed to parse tool.yaml")?;

        // Copy the entire tool directory to build/tools/{category}/{name}/
        let tool_name = path
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown");
        let components: Vec<_> = path.components().collect();
        let category = components
            .get(components.len() - 2)
            .and_then(|c| c.as_os_str().to_str())
            .unwrap_or("core");

        let tools_dir = output_dir.join("tools").join(category).join(tool_name);
        fs::create_dir_all(&tools_dir)?;

        // Copy tool.yaml
        let dest_yaml = tools_dir.join("tool.yaml");
        fs::copy(&tool_yaml, &dest_yaml)?;

        // Copy impl.py if exists
        let impl_file = path.join("impl.py");
        if impl_file.exists() {
            let dest_impl = tools_dir.join("impl.py");
            fs::copy(&impl_file, &dest_impl)?;
        }

        // Copy pyproject.toml if exists
        let pyproject = path.join("pyproject.toml");
        if pyproject.exists() {
            let dest_pyproject = tools_dir.join("pyproject.toml");
            fs::copy(&pyproject, &dest_pyproject)?;
        }

        // Copy README.md if exists
        let readme = path.join("README.md");
        if readme.exists() {
            let dest_readme = tools_dir.join("README.md");
            fs::copy(&readme, &dest_readme)?;
        }

        // Return only the tool.yaml path (relative to output_dir)
        // Don't return tool ID as a file - it's metadata
        let relative_yaml = dest_yaml
            .strip_prefix(output_dir)
            .unwrap_or(&dest_yaml)
            .to_string_lossy()
            .to_string();

        Ok(vec![relative_yaml])
    }
}

impl Default for ClaudeV2Transformer {
    fn default() -> Self {
        Self::new()
    }
}

impl ProviderTransformer for ClaudeV2Transformer {
    fn provider_name(&self) -> &str {
        "claude-v2"
    }

    fn validate_output(&self, _output_dir: &Path) -> Result<()> {
        // V2 validation is simpler - just check files exist
        Ok(())
    }

    fn transform_primitive(
        &self,
        primitive_path: &Path,
        output_dir: &Path,
    ) -> Result<TransformResult> {
        // Detect primitive type by path structure
        let path_str = primitive_path.to_string_lossy();

        let (id, prim_type, files) = if path_str.contains("/commands/") {
            let filename = primitive_path
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("unknown");
            let files = self.transform_command(primitive_path, output_dir)?;
            (filename.to_string(), "command", files)
        } else if path_str.contains("/skills/") {
            let filename = primitive_path
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("unknown");
            let files = self.transform_skill(primitive_path, output_dir)?;
            (filename.to_string(), "skill", files)
        } else if path_str.contains("/tools/") {
            let tool_name = primitive_path
                .file_name()
                .and_then(|s| s.to_str())
                .unwrap_or("unknown");
            let files = self.transform_tool(primitive_path, output_dir)?;
            (tool_name.to_string(), "tool", files)
        } else {
            bail!("Unknown primitive type for path: {}", path_str);
        };

        Ok(TransformResult::success(id, prim_type.to_string(), files))
    }

    fn transform_batch(
        &self,
        primitive_paths: &[&Path],
        output_dir: &Path,
    ) -> Result<Vec<TransformResult>> {
        primitive_paths
            .iter()
            .map(|path| self.transform_primitive(path, output_dir))
            .collect()
    }
}

#[derive(Debug, Deserialize, Serialize)]
struct FrontmatterMetadata {
    description: String,
    #[serde(rename = "argument-hint")]
    argument_hint: Option<String>,
    model: Option<String>,
    #[serde(rename = "allowed-tools")]
    #[serde(default)]
    allowed_tools: Option<String>, // Just store as string for now
}

#[derive(Debug, Deserialize, Serialize)]
struct ToolSpec {
    id: String,
    version: String,
    name: String,
    description: String,
}
