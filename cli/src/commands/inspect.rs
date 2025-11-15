//! Inspect primitives in detail with rich formatting

use anyhow::Result;
use clap::ValueEnum;
use colored::*;
use comfy_table::{modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Table};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

use crate::config::PrimitivesConfig;
use crate::primitives::{HookMeta, PromptMeta, ToolMeta};

/// Output format for inspect command
#[derive(Debug, Clone, ValueEnum)]
pub enum OutputFormat {
    Pretty,
    Json,
    Yaml,
}

/// Arguments for inspect command
#[derive(Debug)]
pub struct InspectArgs {
    pub primitive: String,
    pub version: Option<u32>,
    pub full_content: bool,
    pub format: OutputFormat,
}

/// Complete primitive information for inspection
#[derive(Debug, Serialize, Deserialize)]
struct InspectInfo {
    #[serde(rename = "type")]
    prim_type: String,
    category: String,
    id: String,
    kind: String,
    path: String,
    summary: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    tags: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    domain: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    preferred_models: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tools: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    versions: Option<Vec<VersionDetail>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    default_version: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    content_preview: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    files: Option<Vec<String>>,
}

/// Detailed version information
#[derive(Debug, Serialize, Deserialize)]
struct VersionDetail {
    version: String,
    file: Option<String>,
    status: String,
    hash: String,
    created: String,
    notes: Option<String>,
    deprecated: Option<String>,
}

/// Execute the inspect command
pub fn execute(args: &InspectArgs, config: &PrimitivesConfig) -> Result<()> {
    // Resolve primitive path
    let primitive_path = resolve_primitive_path(&args.primitive, config)?;

    if !primitive_path.exists() {
        anyhow::bail!("Primitive not found: {primitive_path:?}");
    }

    // Detect primitive type and load metadata
    let inspect_info = load_primitive_info(&primitive_path, args)?;

    // Output in requested format
    match args.format {
        OutputFormat::Pretty => output_pretty(&inspect_info, args)?,
        OutputFormat::Json => output_json(&inspect_info)?,
        OutputFormat::Yaml => output_yaml(&inspect_info)?,
    }

    Ok(())
}

/// Resolve a short-form primitive path to full path
fn resolve_primitive_path(short_path: &str, _config: &PrimitivesConfig) -> Result<PathBuf> {
    let path = PathBuf::from(short_path);

    // If path exists as-is, use it
    if path.exists() {
        return Ok(path);
    }

    // Define search paths
    let base_paths = vec![
        PathBuf::from("primitives/v1"),
        PathBuf::from("primitives/experimental"),
        PathBuf::from("."),
    ];

    // Search in configured primitives paths
    for base_path in &base_paths {
        if !base_path.exists() {
            continue;
        }

        // Try direct match under base path
        let full_path = base_path.join(short_path);
        if full_path.exists() {
            return Ok(full_path);
        }

        // Search for matching primitive by ID
        // Format: category/id or just id
        let parts: Vec<&str> = short_path.split('/').collect();
        let search_id = parts.last().unwrap_or(&short_path);

        // Walk the primitives directory to find matching ID
        for entry in WalkDir::new(base_path)
            .min_depth(1)
            .max_depth(10)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            let file_name = entry.file_name().to_string_lossy();

            // Look for meta files
            if file_name == "meta.yaml"
                || file_name == "tool.meta.yaml"
                || file_name == "hook.meta.yaml"
            {
                if let Some(parent) = entry.path().parent() {
                    // Check if directory name matches search_id
                    if let Some(dir_name) = parent.file_name() {
                        if dir_name.to_string_lossy() == *search_id {
                            // Verify ID in metadata
                            if let Ok(content) = fs::read_to_string(entry.path()) {
                                if let Ok(meta) =
                                    serde_yaml::from_str::<serde_yaml::Value>(&content)
                                {
                                    if let Some(id) = meta.get("id") {
                                        if id.as_str() == Some(search_id) {
                                            return Ok(parent.to_path_buf());
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    anyhow::bail!("Could not resolve primitive path: {short_path}")
}

/// Load complete primitive information
fn load_primitive_info(path: &Path, args: &InspectArgs) -> Result<InspectInfo> {
    // Detect primitive type by checking for meta files
    // Try new naming convention first, then fall back to legacy
    let dir_name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");

    let meta_path = if let Ok(entries) = std::fs::read_dir(path) {
        let mut found_meta = None;
        for entry in entries.filter_map(|e| e.ok()) {
            let file_name = entry.file_name().to_string_lossy().to_string();

            // Check for {id}.tool.yaml or {id}.hook.yaml first
            if file_name.ends_with(".tool.yaml") || file_name.ends_with(".hook.yaml") {
                found_meta = Some(entry.path());
                break;
            } else if file_name == format!("{dir_name}.yaml") 
                || (file_name == "meta.yaml" && found_meta.is_none()) {
                found_meta = Some(entry.path());
            }
        }
        found_meta
    } else {
        None
    };

    let meta_path = meta_path.ok_or_else(|| anyhow::anyhow!("No meta file found in {path:?}"))?;

    // Load based on type
    let file_name = meta_path.file_name().and_then(|n| n.to_str()).unwrap_or("");
    if file_name.ends_with(".tool.yaml") {
        load_tool_info(path, &meta_path, args)
    } else if file_name.ends_with(".hook.yaml") {
        load_hook_info(path, &meta_path, args)
    } else {
        load_prompt_info(path, &meta_path, args)
    }
}

/// Load prompt primitive information
fn load_prompt_info(path: &Path, meta_path: &Path, args: &InspectArgs) -> Result<InspectInfo> {
    let content = fs::read_to_string(meta_path)?;
    let meta: PromptMeta = serde_yaml::from_str(&content)?;

    // Get version to inspect
    let target_version = args.version.or(meta.default_version);

    // Load content preview
    let content_preview = if let Some(ver) = target_version {
        let version_entry = meta.versions.iter().find(|v| v.version == ver);
        if let Some(entry) = version_entry {
            let content_path = path.join(&entry.file);
            if content_path.exists() {
                let content = fs::read_to_string(&content_path)?;
                Some(preview_content(&content, args.full_content))
            } else {
                None
            }
        } else {
            None
        }
    } else {
        None
    };

    // List files in directory
    let files = list_directory_files(path)?;

    // Build version details
    let versions = if !meta.versions.is_empty() {
        Some(
            meta.versions
                .iter()
                .map(|v| VersionDetail {
                    version: v.version.to_string(),
                    file: Some(v.file.clone()),
                    status: v.status.clone(),
                    hash: v.hash.clone(),
                    created: v.created.clone(),
                    notes: Some(v.notes.clone()),
                    deprecated: v.deprecated.clone(),
                })
                .collect(),
        )
    } else {
        None
    };

    Ok(InspectInfo {
        prim_type: "prompt".to_string(),
        category: meta.category,
        id: meta.id,
        kind: format!("{:?}", meta.kind).to_lowercase(),
        path: path.display().to_string(),
        summary: meta.summary,
        tags: if meta.tags.is_empty() {
            None
        } else {
            Some(meta.tags)
        },
        domain: Some(meta.domain),
        preferred_models: if meta.defaults.preferred_models.is_empty() {
            None
        } else {
            Some(meta.defaults.preferred_models)
        },
        tools: if meta.tools.is_empty() {
            None
        } else {
            Some(meta.tools)
        },
        versions,
        default_version: meta.default_version,
        content_preview,
        files: Some(files),
    })
}

/// Load tool primitive information
fn load_tool_info(path: &Path, meta_path: &Path, args: &InspectArgs) -> Result<InspectInfo> {
    let content = fs::read_to_string(meta_path)?;
    let meta: ToolMeta = serde_yaml::from_str(&content)?;

    // List files in directory
    let files = list_directory_files(path)?;

    // Build version details
    let versions = if !meta.versions.is_empty() {
        Some(
            meta.versions
                .iter()
                .map(|v| VersionDetail {
                    version: v.version.clone(),
                    file: None,
                    status: v.status.clone(),
                    hash: v.hash.clone(),
                    created: v.created.clone(),
                    notes: v.notes.clone(),
                    deprecated: v.deprecated.clone(),
                })
                .collect(),
        )
    } else {
        None
    };

    // No content preview for tools (they're code/config)
    let content_preview = if args.full_content {
        Some("<Tool primitives don't have markdown content>".to_string())
    } else {
        None
    };

    Ok(InspectInfo {
        prim_type: "tool".to_string(),
        category: meta.category,
        id: meta.id,
        kind: meta.kind,
        path: path.display().to_string(),
        summary: meta.description,
        tags: None,
        domain: None,
        preferred_models: None,
        tools: None,
        versions,
        default_version: None,
        content_preview,
        files: Some(files),
    })
}

/// Load hook primitive information
fn load_hook_info(path: &Path, meta_path: &Path, args: &InspectArgs) -> Result<InspectInfo> {
    let content = fs::read_to_string(meta_path)?;
    let meta: HookMeta = serde_yaml::from_str(&content)?;

    // List files in directory
    let files = list_directory_files(path)?;

    // Build version details
    let versions = if !meta.versions.is_empty() {
        Some(
            meta.versions
                .iter()
                .map(|v| VersionDetail {
                    version: v.version.clone(),
                    file: None,
                    status: v.status.clone(),
                    hash: v.hash.clone(),
                    created: v.created.clone(),
                    notes: v.notes.clone(),
                    deprecated: v.deprecated.clone(),
                })
                .collect(),
        )
    } else {
        None
    };

    // No content preview for hooks (they're code)
    let content_preview = if args.full_content {
        Some("<Hook primitives don't have markdown content>".to_string())
    } else {
        None
    };

    Ok(InspectInfo {
        prim_type: "hook".to_string(),
        category: meta.category,
        id: meta.id,
        kind: meta.kind,
        path: path.display().to_string(),
        summary: meta.summary,
        tags: None,
        domain: None,
        preferred_models: None,
        tools: None,
        versions,
        default_version: None,
        content_preview,
        files: Some(files),
    })
}

/// List files in a directory
fn list_directory_files(path: &Path) -> Result<Vec<String>> {
    let mut files = Vec::new();
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        if entry.path().is_file() {
            if let Some(name) = entry.file_name().to_str() {
                files.push(name.to_string());
            }
        }
    }
    files.sort();
    Ok(files)
}

/// Preview content (first 50 lines or full)
fn preview_content(content: &str, full: bool) -> String {
    if full {
        content.to_string()
    } else {
        let lines: Vec<&str> = content.lines().collect();
        if lines.len() <= 50 {
            content.to_string()
        } else {
            let preview = lines[..50].join("\n");
            format!("{}\n\n... ({} more lines)", preview, lines.len() - 50)
        }
    }
}

/// Output in pretty format
fn output_pretty(info: &InspectInfo, args: &InspectArgs) -> Result<()> {
    // Header
    println!(
        "\n{} {} ({})\n",
        "Primitive:".bold(),
        info.id.cyan(),
        info.prim_type.yellow()
    );

    // Basic info
    println!("{}:", "Metadata".bold().underline());
    println!("  {}: {}", "Type".dimmed(), info.prim_type);
    println!("  {}: {}", "Category".dimmed(), info.category);
    println!("  {}: {}", "Kind".dimmed(), info.kind);
    println!("  {}: {}", "Path".dimmed(), info.path);
    println!("  {}: {}", "Summary".dimmed(), info.summary);

    if let Some(domain) = &info.domain {
        println!("  {}: {}", "Domain".dimmed(), domain);
    }

    if let Some(tags) = &info.tags {
        println!("  {}: {}", "Tags".dimmed(), tags.join(", "));
    }

    // Model preferences
    if let Some(models) = &info.preferred_models {
        println!("\n{}:", "Preferred Models".bold().underline());
        for model in models {
            println!("  • {}", model.green());
        }
    }

    // Tool dependencies
    if let Some(tools) = &info.tools {
        println!("\n{}:", "Tool Dependencies".bold().underline());
        for tool in tools {
            println!("  • {}", tool.cyan());
        }
    }

    // Versions
    if let Some(versions) = &info.versions {
        println!("\n{}:", "Versions".bold().underline());

        let mut table = Table::new();
        table
            .load_preset(UTF8_FULL)
            .apply_modifier(UTF8_ROUND_CORNERS)
            .set_header(vec!["Version", "Status", "Created", "Hash", "Notes"]);

        for v in versions {
            let status = match v.status.as_str() {
                "active" => v.status.green().to_string(),
                "deprecated" => v.status.yellow().to_string(),
                "draft" => v.status.cyan().to_string(),
                _ => v.status.to_string(),
            };

            // Highlight if this is the requested version
            let version_str = if args.version.map(|ver| ver.to_string()) == Some(v.version.clone())
            {
                format!("{} ◄", v.version).bold().to_string()
            } else if info.default_version.map(|ver| ver.to_string()) == Some(v.version.clone()) {
                format!("{} (default)", v.version).bold().to_string()
            } else {
                v.version.clone()
            };

            let hash_short = if v.hash.len() > 15 {
                format!("{}...", &v.hash[..15])
            } else {
                v.hash.clone()
            };

            table.add_row(vec![
                version_str,
                status,
                v.created.clone(),
                hash_short,
                v.notes.clone().unwrap_or_else(|| "-".to_string()),
            ]);
        }

        println!("{table}");
    }

    // Files
    if let Some(files) = &info.files {
        println!("\n{}:", "Files".bold().underline());
        for file in files {
            println!("  • {file}");
        }
    }

    // Content preview
    if let Some(content) = &info.content_preview {
        println!("\n{}:", "Content Preview".bold().underline());
        println!("{}", "─".repeat(80).dimmed());
        println!("{content}");
        println!("{}", "─".repeat(80).dimmed());
    }

    println!();

    Ok(())
}

/// Output in JSON format
fn output_json(info: &InspectInfo) -> Result<()> {
    println!("{}", serde_json::to_string_pretty(info)?);
    Ok(())
}

/// Output in YAML format
fn output_yaml(info: &InspectInfo) -> Result<()> {
    println!("{}", serde_yaml::to_string(info)?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn create_test_prompt(base: &Path, category: &str, id: &str) -> PathBuf {
        let path = base
            .join("primitives/v1/prompts/agents")
            .join(category)
            .join(id);
        fs::create_dir_all(&path).unwrap();

        let meta = format!(
            r#"
id: {id}
kind: agent
category: {category}
domain: test
summary: Test agent for inspection
tags:
  - test
  - agent
defaults:
  preferred_models:
    - claude/sonnet
    - openai/gpt-codex
context_usage:
  as_system: true
tools:
  - run-tests
  - search-code
versions:
  - version: 1
    file: {id}.v1.md
    status: active
    hash: blake3:abc123
    created: "2025-01-01"
    notes: Initial version
  - version: 2
    file: {id}.v2.md
    status: draft
    hash: blake3:def456
    created: "2025-01-15"
    notes: Updated version
default_version: 1
"#
        );
        fs::write(path.join("meta.yaml"), meta).unwrap();
        fs::write(
            path.join(format!("{id}.v1.md")),
            "# Test Agent\n\nThis is test content.",
        )
        .unwrap();
        fs::write(
            path.join(format!("{id}.v2.md")),
            "# Test Agent V2\n\nUpdated content.",
        )
        .unwrap();

        path
    }

    #[test]
    fn test_load_prompt_info() {
        let temp_dir = TempDir::new().unwrap();
        let prim_path = create_test_prompt(temp_dir.path(), "testing", "test-agent");

        let args = InspectArgs {
            primitive: prim_path.display().to_string(),
            version: Some(1),
            full_content: false,
            format: OutputFormat::Pretty,
        };

        let info = load_primitive_info(&prim_path, &args).unwrap();
        assert_eq!(info.id, "test-agent");
        assert_eq!(info.prim_type, "prompt");
        assert_eq!(info.category, "testing");
        assert!(info.content_preview.is_some());
        assert!(info.versions.is_some());
    }

    #[test]
    fn test_preview_content() {
        let short = "Line 1\nLine 2\nLine 3";
        assert_eq!(preview_content(short, false), short);
        assert_eq!(preview_content(short, true), short);

        let long = (0..100)
            .map(|i| format!("Line {i}"))
            .collect::<Vec<_>>()
            .join("\n");
        let preview = preview_content(&long, false);
        assert!(preview.contains("... (50 more lines)"));

        let full = preview_content(&long, true);
        assert_eq!(full, long);
    }

    #[test]
    fn test_list_directory_files() {
        let temp_dir = TempDir::new().unwrap();
        let path = temp_dir.path();

        fs::write(path.join("file1.txt"), "content").unwrap();
        fs::write(path.join("file2.md"), "content").unwrap();
        fs::write(path.join("meta.yaml"), "content").unwrap();

        let files = list_directory_files(path).unwrap();
        assert_eq!(files.len(), 3);
        assert!(files.contains(&"file1.txt".to_string()));
        assert!(files.contains(&"file2.md".to_string()));
        assert!(files.contains(&"meta.yaml".to_string()));
    }

    #[test]
    fn test_output_json() {
        let info = InspectInfo {
            prim_type: "prompt".to_string(),
            category: "test".to_string(),
            id: "test-agent".to_string(),
            kind: "agent".to_string(),
            path: "/test/path".to_string(),
            summary: "Test summary".to_string(),
            tags: Some(vec!["test".to_string()]),
            domain: Some("testing".to_string()),
            preferred_models: None,
            tools: None,
            versions: None,
            default_version: Some(1),
            content_preview: None,
            files: None,
        };

        let result = output_json(&info);
        assert!(result.is_ok());
    }

    #[test]
    fn test_output_yaml() {
        let info = InspectInfo {
            prim_type: "prompt".to_string(),
            category: "test".to_string(),
            id: "test-agent".to_string(),
            kind: "agent".to_string(),
            path: "/test/path".to_string(),
            summary: "Test summary".to_string(),
            tags: Some(vec!["test".to_string()]),
            domain: Some("testing".to_string()),
            preferred_models: None,
            tools: None,
            versions: None,
            default_version: Some(1),
            content_preview: None,
            files: None,
        };

        let result = output_yaml(&info);
        assert!(result.is_ok());
    }
}
