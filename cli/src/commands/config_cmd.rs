//! Config command - manage per-project agentic configuration
//!
//! This allows consumer projects to customize which primitives are installed
//! and pin specific versions (like npm resolutions).

use anyhow::{Context, Result};
use clap::Subcommand;
use colored::Colorize;
use std::fs;
use std::path::Path;

use crate::config::PrimitivesConfig;

/// The template for agentic.yaml with all options commented out (tsconfig-style)
const CONFIG_TEMPLATE: &str = include_str!("../templates/agentic.config.template.yaml");

#[derive(Debug, Subcommand)]
pub enum ConfigCommand {
    /// Generate a new agentic.yaml config file with all options (commented out)
    Init {
        /// Output path (default: ./agentic.yaml)
        #[arg(short, long)]
        output: Option<String>,

        /// Overwrite existing file
        #[arg(long)]
        force: bool,

        /// Include example values for common use cases
        #[arg(long)]
        with_examples: bool,
    },

    /// Show current resolved configuration
    Show {
        /// Output as JSON
        #[arg(long)]
        json: bool,
    },

    /// List available primitives that can be configured
    List {
        /// Filter by type (command, meta-prompt, agent, skill)
        #[arg(long)]
        kind: Option<String>,
    },
}

/// Execute config commands
pub fn execute(command: &ConfigCommand, config: &PrimitivesConfig) -> Result<()> {
    match command {
        ConfigCommand::Init {
            output,
            force,
            with_examples,
        } => init_config(output.as_deref(), *force, *with_examples),
        ConfigCommand::Show { json } => show_config(*json, config),
        ConfigCommand::List { kind } => list_primitives(kind.as_deref(), config),
    }
}

/// Generate a new agentic.yaml config file
fn init_config(output: Option<&str>, force: bool, with_examples: bool) -> Result<()> {
    let output_path = output.unwrap_or("agentic.yaml");
    let path = Path::new(output_path);

    // Check if file exists
    if path.exists() && !force {
        anyhow::bail!("Config file already exists: {output_path}\nUse --force to overwrite");
    }

    // Generate content
    let content = if with_examples {
        generate_config_with_examples()
    } else {
        CONFIG_TEMPLATE.to_string()
    };

    // Write file
    fs::write(path, &content)
        .with_context(|| format!("Failed to write config to {output_path}"))?;

    println!("{}", "✓ Created agentic.yaml".green().bold());
    println!();
    println!("{}:", "File created".bold());
    println!("  {}", output_path.cyan());
    println!();
    println!("{}:", "Next steps".bold());
    println!("  1. Edit the file to customize your configuration");
    println!("  2. Uncomment any options you want to change");
    println!(
        "  3. Run {} to build with your config",
        "agentic-p build".cyan()
    );
    println!();
    println!(
        "{}",
        "Tip: Only uncomment/add primitives you want to override.".dimmed()
    );
    println!(
        "{}",
        "     Everything else uses sensible defaults.".dimmed()
    );

    Ok(())
}

/// Generate config with example values uncommented
fn generate_config_with_examples() -> String {
    r#"# Agentic Primitives Project Configuration
# =========================================
# This file configures how agentic-primitives are built and installed for this project.
#
# Usage:
#   agentic-p build --provider claude    # Uses this config automatically
#   agentic-p install --provider claude  # Installs to .claude/

version: "1.0"

# Default provider for build/install commands
provider: claude

# ============================================================================
# PRIMITIVE VERSION OVERRIDES (like npm resolutions)
# ============================================================================
# Only add primitives you want to override from their default versions.
primitives:
  # Pin QA commands to v1 for stability
  qa/review: 1
  qa/pre-commit-qa: 1
  
  # Always use the latest version of prompt generator
  # core/prompt-generator: latest

# ============================================================================
# EXCLUDE PATTERNS
# ============================================================================
# Primitives to exclude from build
# exclude:
#   - meta-prompts/*        # Exclude all meta-prompts from build

# ============================================================================
# HOOKS CONFIGURATION
# ============================================================================
hooks:
  enabled: true
  timeout: 60

# ============================================================================
# BUILD OUTPUT
# ============================================================================
output:
  dir: ./build
  clean: true
"#
    .to_string()
}

/// Show current resolved configuration
fn show_config(json_output: bool, config: &PrimitivesConfig) -> Result<()> {
    // Try to load project-specific config
    let project_config_path = Path::new("agentic.yaml");
    let has_project_config = project_config_path.exists();

    if json_output {
        // Output as JSON
        let output = serde_json::json!({
            "has_project_config": has_project_config,
            "project_config_path": if has_project_config { Some("agentic.yaml") } else { None },
            "primitives_dir": config.paths.primitives.display().to_string(),
            "default_provider": "claude",
        });
        println!("{}", serde_json::to_string_pretty(&output)?);
    } else {
        println!("{}", "Agentic Configuration".bold());
        println!("{}", "=".repeat(40));
        println!();

        if has_project_config {
            println!("  {} {}", "Project config:".bold(), "agentic.yaml".green());

            // Parse and show overrides
            let content = fs::read_to_string(project_config_path)?;
            if let Ok(yaml) = serde_yaml::from_str::<serde_yaml::Value>(&content) {
                if let Some(primitives) = yaml.get("primitives") {
                    println!();
                    println!("  {}:", "Version Overrides".bold());
                    if let Some(map) = primitives.as_mapping() {
                        for (key, value) in map {
                            let value_str = match value {
                                serde_yaml::Value::Number(n) => n.to_string(),
                                serde_yaml::Value::String(s) => s.clone(),
                                _ => format!("{value:?}"),
                            };
                            println!(
                                "    {} → {}",
                                key.as_str().unwrap_or("?").cyan(),
                                value_str.yellow()
                            );
                        }
                    }
                }
            }
        } else {
            println!(
                "  {} {}",
                "Project config:".bold(),
                "none (using defaults)".dimmed()
            );
            println!();
            println!(
                "  {}",
                "Run 'agentic-p config init' to create agentic.yaml".dimmed()
            );
        }

        println!();
        println!("  {}:", "Primitives directory".bold());
        println!(
            "    {}",
            config.paths.primitives.display().to_string().cyan()
        );

        println!();
        println!("  {}:", "Available providers".bold());
        println!("    claude, openai, cursor");
    }

    Ok(())
}

/// List available primitives that can be configured
fn list_primitives(kind_filter: Option<&str>, config: &PrimitivesConfig) -> Result<()> {
    use walkdir::WalkDir;

    println!("{}", "Available Primitives".bold());
    println!("{}", "=".repeat(40));
    println!();
    println!(
        "{}",
        "Use these identifiers in agentic.yaml primitives section:".dimmed()
    );
    println!();

    // New structure (ADR-021): types directly under v1/
    let primitives_dir = &config.paths.primitives;

    // Search for all primitives - walk directory and find ones with .yaml metadata
    for entry in WalkDir::new(primitives_dir)
        .min_depth(2)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }

        // Check if this directory has a primitive (contains {dir_name}.yaml or {dir_name}.meta.yaml)
        let id = path.file_name().and_then(|n| n.to_str()).unwrap_or("?");
        let meta_file = if path.join(format!("{id}.meta.yaml")).exists() {
            path.join(format!("{id}.meta.yaml"))
        } else if path.join(format!("{id}.yaml")).exists() {
            path.join(format!("{id}.yaml"))
        } else {
            continue;
        };

        // Parse the path to extract kind and category
        // Path format (ADR-021): <type>/<category>/<id>
        let relative_path = path.strip_prefix(primitives_dir).unwrap_or(path);
        let components: Vec<_> = relative_path.components().collect();

        let (kind, category) = match components.len() {
            3 => {
                // <type>/<category>/<id>
                let kind = components[0].as_os_str().to_str().unwrap_or("?");
                let cat = components[1].as_os_str().to_str().unwrap_or("?");
                (kind, cat)
            }
            2 => {
                // <type>/<id> (no category, e.g., meta/create-prime)
                let kind = components[0].as_os_str().to_str().unwrap_or("?");
                (kind, "core") // Default category for uncategorized
            }
            _ => continue,
        };

        // Apply kind filter
        if let Some(filter) = kind_filter {
            let filter_plural = if filter.ends_with('s') {
                filter.to_string()
            } else {
                format!("{filter}s")
            };
            let filter_hyphen = filter.replace('_', "-");
            if kind != filter
                && kind != filter_plural
                && kind != filter_hyphen
                && kind != format!("{filter_hyphen}s")
            {
                continue;
            }
        }

        // Get version info from meta file
        let version_info = if let Ok(content) = fs::read_to_string(&meta_file) {
            if let Ok(yaml) = serde_yaml::from_str::<serde_yaml::Value>(&content) {
                let default_v = yaml
                    .get("default_version")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(1);
                let versions_count = yaml
                    .get("versions")
                    .and_then(|v| v.as_sequence())
                    .map(|s| s.len())
                    .unwrap_or(1);
                format!("(v{default_v}, {versions_count} versions)")
            } else {
                String::new()
            }
        } else {
            String::new()
        };

        // Format: [kind] category/id (version info)
        let kind_short = match kind {
            "commands" => "cmd",
            "meta" => "meta",
            "agents" => "agent",
            "skills" => "skill",
            _ => kind,
        };

        println!(
            "  {} {} {}",
            format!("[{kind_short}]").dimmed(),
            format!("{category}/{id}").cyan(),
            version_info.dimmed()
        );
    }

    println!();
    println!("{}:", "Example agentic.yaml".bold());
    println!(
        "{}",
        r#"  primitives:
    qa/review: 1        # Pin to version 1
    qa/pre-commit-qa: latest"#
            .dimmed()
    );

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_init_creates_config_file() {
        let temp_dir = TempDir::new().unwrap();
        let output_path = temp_dir.path().join("agentic.yaml");

        init_config(Some(output_path.to_str().unwrap()), false, false).unwrap();

        assert!(output_path.exists());
        let content = fs::read_to_string(&output_path).unwrap();
        assert!(content.contains("version: \"1.0\""));
        assert!(content.contains("primitives:"));
    }

    #[test]
    fn test_init_with_examples() {
        let temp_dir = TempDir::new().unwrap();
        let output_path = temp_dir.path().join("agentic.yaml");

        init_config(Some(output_path.to_str().unwrap()), false, true).unwrap();

        let content = fs::read_to_string(&output_path).unwrap();
        assert!(content.contains("qa/review: 1"));
        assert!(content.contains("provider: claude"));
    }

    #[test]
    fn test_init_fails_if_exists_without_force() {
        let temp_dir = TempDir::new().unwrap();
        let output_path = temp_dir.path().join("agentic.yaml");

        // Create file
        fs::write(&output_path, "existing").unwrap();

        let result = init_config(Some(output_path.to_str().unwrap()), false, false);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("already exists"));
    }

    #[test]
    fn test_init_with_force_overwrites() {
        let temp_dir = TempDir::new().unwrap();
        let output_path = temp_dir.path().join("agentic.yaml");

        // Create existing file
        fs::write(&output_path, "old content").unwrap();

        init_config(Some(output_path.to_str().unwrap()), true, false).unwrap();

        let content = fs::read_to_string(&output_path).unwrap();
        assert!(content.contains("version: \"1.0\""));
    }

    #[test]
    fn test_generate_config_with_examples_has_values() {
        let content = generate_config_with_examples();
        assert!(content.contains("qa/review: 1"));
        assert!(content.contains("hooks:"));
        assert!(content.contains("enabled: true"));
    }
}
