//! List primitives with filtering and multiple output formats

use anyhow::{Context, Result};
use clap::ValueEnum;
use colored::*;
use comfy_table::{modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Table};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

use crate::config::PrimitivesConfig;
use crate::primitives::{HookMeta, PromptMeta, ToolMeta};

/// Output format for list command
#[derive(Debug, Clone, ValueEnum)]
pub enum OutputFormat {
    Table,
    Json,
    Yaml,
}

/// Arguments for list command
#[derive(Debug)]
pub struct ListArgs {
    pub path: Option<PathBuf>,
    pub type_filter: Option<String>,
    pub kind: Option<String>,
    pub category: Option<String>,
    pub tag: Option<String>,
    pub all_versions: bool,
    pub format: OutputFormat,
}

/// Information about a discovered primitive
#[derive(Debug, Clone, Serialize, Deserialize)]
struct PrimitiveInfo {
    #[serde(rename = "type")]
    prim_type: String,
    category: String,
    id: String,
    kind: String,
    summary: String,
    version: String,
    path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    tags: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    versions: Option<Vec<VersionInfo>>,
}

/// Version information for display
#[derive(Debug, Clone, Serialize, Deserialize)]
struct VersionInfo {
    version: u32,
    status: String,
    created: String,
}

/// Execute the list command
pub fn execute(args: &ListArgs, _config: &PrimitivesConfig) -> Result<()> {
    // Determine search path
    let search_path = if let Some(path) = &args.path {
        path.clone()
    } else {
        // Use primitives/v1 as default search path
        PathBuf::from("primitives/v1")
    };

    if !search_path.exists() {
        anyhow::bail!("Path does not exist: {search_path:?}");
    }

    // Discover primitives
    let mut primitives = discover_primitives(&search_path)?;

    if primitives.is_empty() {
        println!("No primitives found at {search_path:?}");
        return Ok(());
    }

    // Apply filters
    if let Some(type_filter) = &args.type_filter {
        primitives.retain(|p| p.prim_type == *type_filter);
    }
    if let Some(kind) = &args.kind {
        primitives.retain(|p| p.kind == *kind);
    }
    if let Some(category) = &args.category {
        primitives.retain(|p| p.category == *category);
    }
    if let Some(tag) = &args.tag {
        primitives.retain(|p| {
            p.tags
                .as_ref()
                .map(|tags| tags.contains(tag))
                .unwrap_or(false)
        });
    }

    // Output results
    match args.format {
        OutputFormat::Table => output_table(&primitives, args.all_versions)?,
        OutputFormat::Json => output_json(&primitives)?,
        OutputFormat::Yaml => output_yaml(&primitives)?,
    }

    Ok(())
}

/// Discover all primitives in a directory tree
fn discover_primitives(path: &Path) -> Result<Vec<PrimitiveInfo>> {
    let mut primitives = Vec::new();

    for entry in WalkDir::new(path)
        .min_depth(1)
        .max_depth(10)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        let file_name = entry.file_name().to_string_lossy();

        // Look for meta files (new naming convention and legacy)
        if file_name.ends_with(".tool.yaml") {
            if let Ok(info) = extract_tool_info(entry.path()) {
                primitives.push(info);
            }
        } else if file_name.ends_with(".hook.yaml") {
            if let Ok(info) = extract_hook_info(entry.path()) {
                primitives.push(info);
            }
        } else if file_name == "meta.yaml"
            || (file_name.ends_with(".yaml")
                && !file_name.contains("tool.")
                && !file_name.contains("hook."))
        {
            // Check if it's a prompt meta file (either legacy meta.yaml or {id}.yaml)
            // Skip primitive config files and other non-meta yamls
            if file_name != "primitives.config.yaml" {
                if let Ok(info) = extract_prompt_info(entry.path()) {
                    primitives.push(info);
                }
            }
        }
    }

    Ok(primitives)
}

/// Extract information from a prompt primitive
fn extract_prompt_info(meta_path: &Path) -> Result<PrimitiveInfo> {
    let content = fs::read_to_string(meta_path)
        .with_context(|| format!("Failed to read meta.yaml: {meta_path:?}"))?;
    let meta: PromptMeta =
        serde_yaml::from_str(&content).context("Failed to parse prompt meta.yaml")?;

    let primitive_dir = meta_path
        .parent()
        .context("Failed to get parent directory")?;

    // Determine version display
    let version = if let Some(default_v) = meta.default_version {
        format!("v{default_v}")
    } else {
        "unversioned".to_string()
    };

    // Extract versions if present
    let versions = if !meta.versions.is_empty() {
        Some(
            meta.versions
                .iter()
                .map(|v| VersionInfo {
                    version: v.version,
                    status: v.status.clone(),
                    created: v.created.clone(),
                })
                .collect(),
        )
    } else {
        None
    };

    Ok(PrimitiveInfo {
        prim_type: "prompt".to_string(),
        category: meta.category.clone(),
        id: meta.id.clone(),
        kind: format!("{:?}", meta.kind).to_lowercase(),
        summary: meta.summary.clone(),
        version,
        path: primitive_dir.display().to_string(),
        tags: if meta.tags.is_empty() {
            None
        } else {
            Some(meta.tags.clone())
        },
        versions,
    })
}

/// Extract information from a tool primitive
fn extract_tool_info(meta_path: &Path) -> Result<PrimitiveInfo> {
    let content = fs::read_to_string(meta_path)
        .with_context(|| format!("Failed to read tool.meta.yaml: {meta_path:?}"))?;
    let meta: ToolMeta =
        serde_yaml::from_str(&content).context("Failed to parse tool.meta.yaml")?;

    let primitive_dir = meta_path
        .parent()
        .context("Failed to get parent directory")?;

    // Determine version display (tools use String version)
    let version = if !meta.versions.is_empty() {
        let latest = meta
            .versions
            .iter()
            .rfind(|v| v.status == "active")
            .or_else(|| meta.versions.last());
        if let Some(v) = latest {
            format!("v{}", v.version)
        } else {
            "unversioned".to_string()
        }
    } else {
        "unversioned".to_string()
    };

    // Extract versions if present (convert String version to u32 for display)
    let versions = if !meta.versions.is_empty() {
        Some(
            meta.versions
                .iter()
                .filter_map(|v| {
                    // Try to parse version string as number
                    v.version.parse::<u32>().ok().map(|ver| VersionInfo {
                        version: ver,
                        status: v.status.clone(),
                        created: v.created.clone(),
                    })
                })
                .collect(),
        )
    } else {
        None
    };

    Ok(PrimitiveInfo {
        prim_type: "tool".to_string(),
        category: meta.category.clone(),
        id: meta.id.clone(),
        kind: meta.kind.clone(),
        summary: meta.description.clone(), // Tools use 'description' not 'summary'
        version,
        path: primitive_dir.display().to_string(),
        tags: None, // Tools don't have tags in current schema
        versions,
    })
}

/// Extract information from a hook primitive
fn extract_hook_info(meta_path: &Path) -> Result<PrimitiveInfo> {
    let content = fs::read_to_string(meta_path)
        .with_context(|| format!("Failed to read hook.meta.yaml: {meta_path:?}"))?;
    let meta: HookMeta =
        serde_yaml::from_str(&content).context("Failed to parse hook.meta.yaml")?;

    let primitive_dir = meta_path
        .parent()
        .context("Failed to get parent directory")?;

    // Determine version display (hooks use String version)
    let version = if !meta.versions.is_empty() {
        let latest = meta
            .versions
            .iter()
            .rfind(|v| v.status == "active")
            .or_else(|| meta.versions.last());
        if let Some(v) = latest {
            format!("v{}", v.version)
        } else {
            "unversioned".to_string()
        }
    } else {
        "unversioned".to_string()
    };

    // Extract versions if present (convert String version to u32 for display)
    let versions = if !meta.versions.is_empty() {
        Some(
            meta.versions
                .iter()
                .filter_map(|v| {
                    // Try to parse version string as number
                    v.version.parse::<u32>().ok().map(|ver| VersionInfo {
                        version: ver,
                        status: v.status.clone(),
                        created: v.created.clone(),
                    })
                })
                .collect(),
        )
    } else {
        None
    };

    Ok(PrimitiveInfo {
        prim_type: "hook".to_string(),
        category: meta.category.clone(),
        id: meta.id.clone(),
        kind: meta.kind.clone(),
        summary: meta.summary.clone(),
        version,
        path: primitive_dir.display().to_string(),
        tags: None, // Hooks don't have tags in current schema
        versions,
    })
}

/// Output primitives as a colored table
fn output_table(primitives: &[PrimitiveInfo], all_versions: bool) -> Result<()> {
    if all_versions {
        // Show version history for each primitive
        for prim in primitives {
            println!(
                "\n{} {} ({})",
                "Primitive:".bold(),
                prim.id.cyan(),
                prim.prim_type.yellow()
            );
            println!("  {}: {}", "Category".dimmed(), prim.category);
            println!("  {}: {}", "Kind".dimmed(), prim.kind);
            println!("  {}: {}", "Summary".dimmed(), prim.summary);

            if let Some(versions) = &prim.versions {
                println!("\n  {}:", "Versions".bold());
                let mut table = Table::new();
                table
                    .load_preset(UTF8_FULL)
                    .apply_modifier(UTF8_ROUND_CORNERS)
                    .set_header(vec!["Version", "Status", "Created"]);

                for v in versions {
                    let status = match v.status.as_str() {
                        "active" => v.status.green().to_string(),
                        "deprecated" => v.status.yellow().to_string(),
                        "draft" => v.status.cyan().to_string(),
                        _ => v.status.to_string(),
                    };
                    table.add_row(vec![format!("v{}", v.version), status, v.created.clone()]);
                }
                println!("{table}");
            } else {
                println!("  {}: None", "Versions".dimmed());
            }
        }
        println!();
    } else {
        // Standard table view
        let mut table = Table::new();
        table
            .load_preset(UTF8_FULL)
            .apply_modifier(UTF8_ROUND_CORNERS)
            .set_header(vec!["Type", "Category", "ID", "Kind", "Version", "Summary"]);

        for prim in primitives {
            let type_colored = match prim.prim_type.as_str() {
                "prompt" => prim.prim_type.cyan().to_string(),
                "tool" => prim.prim_type.green().to_string(),
                "hook" => prim.prim_type.yellow().to_string(),
                _ => prim.prim_type.to_string(),
            };

            table.add_row(vec![
                type_colored,
                prim.category.clone(),
                prim.id.clone(),
                prim.kind.clone(),
                prim.version.clone(),
                truncate_summary(&prim.summary, 50),
            ]);
        }

        println!("\n{table}\n");
        println!(
            "{} {} primitives\n",
            "Found".bold(),
            primitives.len().to_string().cyan()
        );
    }

    Ok(())
}

/// Output primitives as JSON
fn output_json(primitives: &[PrimitiveInfo]) -> Result<()> {
    println!("{}", serde_json::to_string_pretty(primitives)?);
    Ok(())
}

/// Output primitives as YAML
fn output_yaml(primitives: &[PrimitiveInfo]) -> Result<()> {
    println!("{}", serde_yaml::to_string(primitives)?);
    Ok(())
}

/// Truncate summary to specified length
fn truncate_summary(summary: &str, max_len: usize) -> String {
    if summary.len() <= max_len {
        summary.to_string()
    } else {
        format!("{}...", &summary[..max_len - 3])
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn create_test_prompt(base: &Path, category: &str, id: &str) -> PathBuf {
        // New structure (ADR-021): agents directly under v1/
        let path = base.join("primitives/v1/agents").join(category).join(id);
        fs::create_dir_all(&path).unwrap();

        let meta = format!(
            r#"
id: {id}
kind: agent
category: {category}
domain: test
summary: Test agent summary
tags:
  - test
  - agent
context_usage:
  as_system: true
  as_user: false
  as_overlay: false
versions:
  - version: 1
    file: {id}.v1.md
    status: active
    hash: blake3:0000000000000000000000000000000000000000000000000000000000000000
    created: "2025-01-01"
    notes: Initial version
  - version: 2
    file: {id}.v2.md
    status: draft
    hash: blake3:1111111111111111111111111111111111111111111111111111111111111111
    created: "2025-01-15"
    notes: Updated version
default_version: 1
"#
        );
        fs::write(path.join("meta.yaml"), meta).unwrap();
        fs::write(path.join(format!("{id}.v1.md")), "# Test").unwrap();

        path
    }

    #[test]
    fn test_discover_primitives() {
        let temp_dir = TempDir::new().unwrap();
        create_test_prompt(temp_dir.path(), "test", "agent1");
        create_test_prompt(temp_dir.path(), "test", "agent2");

        let result = discover_primitives(&temp_dir.path().join("primitives/v1")).unwrap();
        assert_eq!(result.len(), 2);
        assert!(result.iter().any(|p| p.id == "agent1"));
        assert!(result.iter().any(|p| p.id == "agent2"));
    }

    #[test]
    fn test_extract_prompt_info() {
        let temp_dir = TempDir::new().unwrap();
        let prim_path = create_test_prompt(temp_dir.path(), "testing", "test-agent");
        let meta_path = prim_path.join("meta.yaml");

        let info = extract_prompt_info(&meta_path).unwrap();
        assert_eq!(info.id, "test-agent");
        assert_eq!(info.prim_type, "prompt");
        assert_eq!(info.category, "testing");
        assert_eq!(info.kind, "agent");
        assert_eq!(info.version, "v1");
        assert!(info.versions.is_some());
        assert_eq!(info.versions.unwrap().len(), 2);
    }

    #[test]
    fn test_truncate_summary() {
        let long = "This is a very long summary that should be truncated";
        assert!(truncate_summary(long, 20).len() <= 20);
        assert!(truncate_summary(long, 20).ends_with("..."));

        let short = "Short summary";
        assert_eq!(truncate_summary(short, 50), short);
    }

    #[test]
    fn test_output_json() {
        let primitives = vec![PrimitiveInfo {
            prim_type: "prompt".to_string(),
            category: "test".to_string(),
            id: "test-agent".to_string(),
            kind: "agent".to_string(),
            summary: "Test summary".to_string(),
            version: "v1".to_string(),
            path: "/test/path".to_string(),
            tags: Some(vec!["test".to_string()]),
            versions: None,
        }];

        let result = output_json(&primitives);
        assert!(result.is_ok());
    }

    #[test]
    fn test_output_yaml() {
        let primitives = vec![PrimitiveInfo {
            prim_type: "prompt".to_string(),
            category: "test".to_string(),
            id: "test-agent".to_string(),
            kind: "agent".to_string(),
            summary: "Test summary".to_string(),
            version: "v1".to_string(),
            path: "/test/path".to_string(),
            tags: Some(vec!["test".to_string()]),
            versions: None,
        }];

        let result = output_yaml(&primitives);
        assert!(result.is_ok());
    }
}
