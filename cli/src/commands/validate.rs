use anyhow::{Context, Result};
use clap::Args;
use colored::Colorize;
use std::fs;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

use crate::validators;

#[derive(Args, Debug)]
pub struct ValidateArgs {
    /// Path to primitive file or directory to validate
    pub path: Option<PathBuf>,

    /// Validate all v2 primitives
    #[arg(long)]
    pub all: bool,

    /// Primitives version to validate (v1 or v2)
    #[arg(long, default_value = "v2")]
    pub primitives_version: String,

    /// Show detailed output
    #[arg(long, short)]
    pub verbose: bool,
}

pub fn execute(args: ValidateArgs) -> Result<()> {
    if args.all {
        validate_all_primitives(&args)?;
    } else if let Some(path) = args.path {
        validate_single_primitive(&path, args.verbose)?;
    } else {
        anyhow::bail!("Must provide either a path or use --all flag");
    }

    Ok(())
}

/// Validate a single primitive file
fn validate_single_primitive(path: &Path, verbose: bool) -> Result<()> {
    println!("{} {}", "Validating:".cyan().bold(), path.display());
    println!();

    // Determine primitive type from path
    let path_str = path.to_string_lossy();
    let primitive_type = if path_str.contains("/commands/") {
        "command"
    } else if path_str.contains("/skills/") {
        "skill"
    } else if path_str.contains("/tools/") {
        "tool"
    } else {
        anyhow::bail!(
            "Cannot determine primitive type from path: {}",
            path.display()
        );
    };

    // Validate based on type
    match primitive_type {
        "command" | "skill" => {
            // Read file content for markdown-based primitives
            let content = fs::read_to_string(path)
                .with_context(|| format!("Failed to read file: {}", path.display()))?;

            if primitive_type == "command" {
                validate_command_file(&content, path, verbose)?;
            } else {
                validate_skill_file(&content, path, verbose)?;
            }
        }
        "tool" => {
            // Tools are directories, validate directly
            validate_tool_directory(path, verbose)?;
        }
        _ => unreachable!(),
    }

    println!();
    println!("{} Primitive is valid!", "✓".green().bold());

    Ok(())
}

/// Validate all v2 primitives
fn validate_all_primitives(args: &ValidateArgs) -> Result<()> {
    println!("{}", "Validating All V2 Primitives".cyan().bold());
    println!("{}", "═".repeat(50).cyan());
    println!();

    let primitives_base = if args.primitives_version == "v2" {
        PathBuf::from("primitives/v2")
    } else {
        PathBuf::from("primitives/v1")
    };

    if !primitives_base.exists() {
        anyhow::bail!(
            "Primitives directory not found: {}",
            primitives_base.display()
        );
    }

    // Discover all v2 primitives
    let primitives = if args.primitives_version == "v2" {
        discover_v2_primitives(&primitives_base)?
    } else {
        anyhow::bail!("V1 validation not yet implemented");
    };

    let total = primitives.len();
    let mut passed = 0;
    let mut failed = 0;
    let mut errors = Vec::new();

    for primitive_path in primitives {
        let result = validate_single_primitive(&primitive_path, false);

        match result {
            Ok(_) => {
                passed += 1;
                if args.verbose {
                    println!("{} {}", "✓".green(), primitive_path.display());
                }
            }
            Err(e) => {
                failed += 1;
                println!("{} {}", "✗".red(), primitive_path.display());
                errors.push((primitive_path, e));
            }
        }
    }

    println!();
    println!("{}", "═".repeat(50).cyan());
    println!("{}", "Validation Summary".cyan().bold());
    println!("{}", "═".repeat(50).cyan());
    println!("Total:  {}", total);
    println!("Passed: {} {}", passed, "✓".green());
    println!(
        "Failed: {} {}",
        failed,
        if failed > 0 {
            "✗".red()
        } else {
            "✓".green()
        }
    );

    if !errors.is_empty() {
        println!();
        println!("{}", "Errors:".red().bold());
        for (path, error) in errors {
            println!();
            println!("{} {}", "✗".red(), path.display());
            println!("  {}", error.to_string().replace('\n', "\n  "));
        }
        anyhow::bail!("Validation failed for {} primitive(s)", failed);
    }

    Ok(())
}

/// Validate command file content
fn validate_command_file(content: &str, path: &Path, verbose: bool) -> Result<()> {
    // Parse frontmatter
    let (frontmatter_str, body) = parse_frontmatter(content, path)?;

    if verbose {
        println!("  {} Frontmatter found", "→".blue());
    }

    // Validate frontmatter against schema
    validators::validate_command_frontmatter(&frontmatter_str)
        .context("Frontmatter validation failed")?;

    if verbose {
        println!("  {} Frontmatter valid", "✓".green());
    }

    // Basic content checks
    if body.trim().is_empty() {
        anyhow::bail!("Command body is empty");
    }

    if verbose {
        println!("  {} Content present", "✓".green());
    }

    // Check for title
    if !body.contains("# ") {
        println!("  {} Warning: No H1 heading found", "⚠".yellow());
    }

    Ok(())
}

/// Validate skill file content
fn validate_skill_file(content: &str, path: &Path, verbose: bool) -> Result<()> {
    // Parse frontmatter
    let (frontmatter_str, body) = parse_frontmatter(content, path)?;

    if verbose {
        println!("  {} Frontmatter found", "→".blue());
    }

    // Validate frontmatter against schema
    validators::validate_skill_frontmatter(&frontmatter_str)
        .context("Frontmatter validation failed")?;

    if verbose {
        println!("  {} Frontmatter valid", "✓".green());
    }

    // Basic content checks
    if body.trim().is_empty() {
        anyhow::bail!("Skill body is empty");
    }

    if verbose {
        println!("  {} Content present", "✓".green());
    }

    Ok(())
}

/// Validate tool directory
fn validate_tool_directory(path: &Path, verbose: bool) -> Result<()> {
    // Check for tool.yaml
    let tool_yaml = path.join("tool.yaml");
    if !tool_yaml.exists() {
        anyhow::bail!("tool.yaml not found in {}", path.display());
    }

    if verbose {
        println!("  {} tool.yaml found", "✓".green());
    }

    // Read and validate tool.yaml (using existing tool spec validation)
    let content = fs::read_to_string(&tool_yaml)?;
    let _: serde_yaml::Value =
        serde_yaml::from_str(&content).context("Failed to parse tool.yaml")?;

    if verbose {
        println!("  {} tool.yaml is valid YAML", "✓".green());
    }

    // Check for impl.py
    if path.join("impl.py").exists() && verbose {
        println!("  {} impl.py found", "✓".green());
    }

    Ok(())
}

/// Parse frontmatter from markdown content
fn parse_frontmatter(content: &str, path: &Path) -> Result<(String, String)> {
    let trimmed = content.trim_start();

    if !trimmed.starts_with("---") {
        anyhow::bail!(
            "No frontmatter found in {}. Expected file to start with '---'",
            path.display()
        );
    }

    let after_open = &trimmed[3..];
    let end_idx = after_open
        .find("\n---")
        .with_context(|| format!("Frontmatter not closed in {}", path.display()))?;

    let frontmatter = after_open[..end_idx].trim().to_string();
    let body = after_open[end_idx + 4..].trim().to_string();

    Ok((frontmatter, body))
}

/// Discover v2 primitives (similar to build_v2 logic)
fn discover_v2_primitives(primitives_base: &Path) -> Result<Vec<PathBuf>> {
    let mut primitives = Vec::new();

    // Commands
    for entry in WalkDir::new(primitives_base.join("commands"))
        .min_depth(2)
        .max_depth(2)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        let path = entry.path();
        if path.is_file() && path.extension().is_some_and(|ext| ext == "md") {
            primitives.push(path.to_path_buf());
        }
    }

    // Skills
    for entry in WalkDir::new(primitives_base.join("skills"))
        .min_depth(2)
        .max_depth(2)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        let path = entry.path();
        if path.is_file() && path.extension().is_some_and(|ext| ext == "md") {
            primitives.push(path.to_path_buf());
        }
    }

    // Tools
    for entry in WalkDir::new(primitives_base.join("tools"))
        .min_depth(2)
        .max_depth(2)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        let path = entry.path();
        if path.is_dir() && path.join("tool.yaml").exists() {
            primitives.push(path.to_path_buf());
        }
    }

    Ok(primitives)
}
