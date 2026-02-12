use anyhow::{bail, Result};
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

use crate::commands::build::BuildArgs;

/// Discover v2 primitives (simplified flat structure)
pub fn discover_v2_primitives(args: &BuildArgs, primitives_base: &Path) -> Result<Vec<PathBuf>> {
    let mut primitives = Vec::new();
    let v2_dir = primitives_base.join("v2");

    if !v2_dir.exists() {
        bail!("V2 primitives directory not found: {}", v2_dir.display());
    }

    // If specific primitive requested, return it
    if let Some(ref prim_path) = args.primitive {
        let path = PathBuf::from(prim_path);
        if path.exists() {
            return Ok(vec![path]);
        } else {
            bail!("Primitive not found: {prim_path}");
        }
    }

    // Walk commands/ and skills/ for markdown files
    discover_markdown_primitives(&v2_dir.join("commands"), &mut primitives, args)?;
    discover_markdown_primitives(&v2_dir.join("skills"), &mut primitives, args)?;

    // Walk tools/ for directories with tool.yaml
    discover_tool_primitives(&v2_dir.join("tools"), &mut primitives, args)?;

    Ok(primitives)
}

/// Discover markdown-based primitives (commands, skills)
fn discover_markdown_primitives(
    base_dir: &Path,
    primitives: &mut Vec<PathBuf>,
    args: &BuildArgs,
) -> Result<()> {
    if !base_dir.exists() {
        return Ok(()); // Directory optional
    }

    for entry in WalkDir::new(base_dir)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().is_file())
    {
        let path = entry.path();

        // Only .md files
        if path.extension().and_then(|s| s.to_str()) != Some("md") {
            continue;
        }

        // Apply filters
        if should_include_v2_primitive(path, args, base_dir)? {
            primitives.push(path.to_path_buf());
        }
    }

    Ok(())
}

/// Discover tool primitives (directories with tool.yaml)
fn discover_tool_primitives(
    base_dir: &Path,
    primitives: &mut Vec<PathBuf>,
    args: &BuildArgs,
) -> Result<()> {
    if !base_dir.exists() {
        return Ok(()); // Directory optional
    }

    for entry in WalkDir::new(base_dir)
        .min_depth(1)
        .max_depth(5)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        let path = entry.path();

        // Look for directories containing tool.yaml
        if path.is_dir() && path.join("tool.yaml").exists()
            && should_include_v2_primitive(path, args, base_dir)? {
            primitives.push(path.to_path_buf());
        }
    }

    Ok(())
}

/// Check if a v2 primitive should be included based on filters
fn should_include_v2_primitive(path: &Path, args: &BuildArgs, base_dir: &Path) -> Result<bool> {
    // Type filter (command, skill, tool)
    if let Some(ref type_filter) = args.type_filter {
        let base_name = base_dir.file_name().and_then(|n| n.to_str()).unwrap_or("");

        let matches = match type_filter.as_str() {
            "command" | "commands" => base_name == "commands",
            "skill" | "skills" => base_name == "skills",
            "tool" | "tools" => base_name == "tools",
            "prompt" => base_name == "commands" || base_name == "skills", // prompts = commands + skills
            _ => {
                bail!("Invalid type filter: {type_filter}. Use: command, skill, tool, or prompt");
            }
        };

        if !matches {
            return Ok(false);
        }
    }

    // Kind filter (for backward compatibility, map to type)
    if let Some(ref kind_filter) = args.kind {
        let base_name = base_dir.file_name().and_then(|n| n.to_str()).unwrap_or("");
        let kind_plural = format!("{kind_filter}s");

        if base_name != kind_plural {
            return Ok(false);
        }
    }

    // --only pattern filter (category/name patterns)
    if let Some(ref only) = args.only {
        // Extract relative path from base_dir
        let rel_path = path.strip_prefix(base_dir).unwrap_or(path);
        let path_str = rel_path.to_string_lossy();

        // Simple pattern matching (supports globs like "qa/*", exact matches like "qa/review")
        let patterns: Vec<&str> = only.split(',').map(|s| s.trim()).collect();
        let mut matches = false;

        for pattern in patterns {
            // Remove .md extension from path for comparison
            let path_without_ext = path_str.trim_end_matches(".md");

            if pattern.contains('*') {
                // Glob pattern matching
                if let Ok(glob) = glob::Pattern::new(pattern) {
                    if glob.matches(path_without_ext) {
                        matches = true;
                        break;
                    }
                }
            } else if path_without_ext == pattern
                || path_without_ext.starts_with(&format!("{pattern}/"))
            {
                // Exact match or prefix match
                matches = true;
                break;
            }
        }

        if !matches {
            return Ok(false);
        }
    }

    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_v2_discovery_structure() {
        // v2 structure: primitives/v2/commands/{category}/{name}.md
        let path = PathBuf::from("primitives/v2/commands/qa/review.md");
        assert_eq!(path.extension().and_then(|s| s.to_str()), Some("md"));
    }
}
