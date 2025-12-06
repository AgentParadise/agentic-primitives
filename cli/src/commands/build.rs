//! Build command - transforms primitives into provider-specific outputs

use anyhow::{bail, Context, Result};
use chrono::Utc;
use colored::Colorize;
use std::fs;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

use crate::config::PrimitivesConfig;
use crate::manifest::{AgenticManifest, ManifestPrimitive, MANIFEST_FILENAME};
use crate::providers::{ClaudeTransformer, OpenAITransformer, ProviderTransformer};

/// Arguments for the build command
#[derive(Debug, Clone)]
pub struct BuildArgs {
    pub provider: String,
    pub output: Option<PathBuf>,
    pub primitive: Option<String>,
    pub type_filter: Option<String>,
    pub kind: Option<String>,
    pub clean: bool,
    pub verbose: bool,
}

/// Result of a build operation
#[derive(Debug)]
pub struct BuildResult {
    pub provider: String,
    pub output_dir: PathBuf,
    pub primitives_built: usize,
    pub files_generated: Vec<PathBuf>,
    pub errors: Vec<String>,
    pub manifest: AgenticManifest,
}

/// Get a transformer for the specified provider
fn get_transformer(provider: &str) -> Result<Box<dyn ProviderTransformer>> {
    match provider {
        "claude" => Ok(Box::new(ClaudeTransformer::new())),
        "openai" => Ok(Box::new(OpenAITransformer::new())),
        _ => bail!("Unknown provider: {provider}. Supported: claude, openai"),
    }
}

/// Discover primitives to build based on arguments and filters
fn discover_primitives(args: &BuildArgs, config: &PrimitivesConfig) -> Result<Vec<PathBuf>> {
    let mut primitives = Vec::new();

    // If single primitive specified, return just that
    if let Some(ref prim_path) = args.primitive {
        let path = PathBuf::from(prim_path);
        if path.exists() {
            return Ok(vec![path]);
        } else {
            bail!("Primitive not found: {prim_path}");
        }
    }

    // Otherwise, walk primitives directory
    let primitives_dir = PathBuf::from(&config.paths.primitives);

    if !primitives_dir.exists() {
        bail!(
            "Primitives directory not found: {}",
            primitives_dir.display()
        );
    }

    for entry in WalkDir::new(&primitives_dir)
        .min_depth(1)
        .max_depth(10)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        let path = entry.path();

        // Check if this directory contains a metadata file
        if path.is_dir() && has_metadata_file(path) {
            // Apply filters
            if should_include_primitive(path, args)? {
                primitives.push(path.to_path_buf());
            }
        }
    }

    Ok(primitives)
}

/// Check if a directory contains a metadata file or is an atomic hooks directory
fn has_metadata_file(path: &Path) -> bool {
    let dir_name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");

    // Check for atomic hooks structure (handlers/ directory)
    if dir_name == "hooks" && path.join("handlers").exists() {
        return true;
    }

    // New convention (ADR-019): {id}.{type}.yaml
    path.join(format!("{dir_name}.meta.yaml")).exists()      // Prompts (new)
        || path.join(format!("{dir_name}.tool.yaml")).exists() // Tools
        || path.join(format!("{dir_name}.hook.yaml")).exists() // Hooks
        // Legacy fallbacks (for backward compatibility)
        || path.join(format!("{dir_name}.yaml")).exists()
        || path.join("meta.yaml").exists()
}

/// Check if a primitive should be included based on filters
fn should_include_primitive(path: &Path, args: &BuildArgs) -> Result<bool> {
    // Type filter (prompt, tool, hook)
    // New structure (ADR-021): prompts are under commands/, skills/, agents/
    if let Some(ref type_filter) = args.type_filter {
        let has_component = path.components().any(|c| {
            let name = c.as_os_str().to_string_lossy();
            match type_filter.as_str() {
                // Prompts include commands, skills, agents (new structure)
                "prompt" => name == "commands" || name == "skills" || name == "agents",
                "tool" => name == "tools",
                "hook" => name == "hooks",
                _ => false,
            }
        });

        if !has_component {
            if !matches!(type_filter.as_str(), "prompt" | "tool" | "hook") {
                bail!("Invalid type filter: {type_filter}. Use: prompt, tool, hook");
            }
            return Ok(false);
        }
    }

    // Kind filter (agent, command, skill, etc.)
    if let Some(ref kind_filter) = args.kind {
        let kind_plural = format!("{kind_filter}s");
        let has_kind = path
            .components()
            .any(|c| c.as_os_str().to_string_lossy() == kind_plural);

        if !has_kind {
            return Ok(false);
        }
    }

    Ok(true)
}

/// Prepare output directory, optionally cleaning it first
fn prepare_output_dir(args: &BuildArgs) -> Result<PathBuf> {
    let output_dir = args
        .output
        .clone()
        .unwrap_or_else(|| PathBuf::from(format!("./build/{}", args.provider)));

    // Clean directory if requested
    if args.clean && output_dir.exists() {
        fs::remove_dir_all(&output_dir)
            .with_context(|| format!("Failed to clean directory: {}", output_dir.display()))?;
    }

    // Create directory structure
    fs::create_dir_all(&output_dir)
        .with_context(|| format!("Failed to create directory: {}", output_dir.display()))?;

    Ok(output_dir)
}

/// Transform primitives using the provider transformer
fn transform_primitives(
    primitives: Vec<PathBuf>,
    transformer: &dyn ProviderTransformer,
    output_dir: &Path,
    verbose: bool,
) -> Result<(Vec<PathBuf>, Vec<String>, Vec<ManifestPrimitive>)> {
    // Canonicalize output_dir for consistent path comparison
    let output_dir_canonical = output_dir
        .canonicalize()
        .unwrap_or_else(|_| output_dir.to_path_buf());
    let mut generated_files = Vec::new();
    let mut errors = Vec::new();
    let mut manifest_primitives = Vec::new();

    for (idx, primitive_path) in primitives.iter().enumerate() {
        if verbose {
            println!(
                "[{}/{}] Transforming: {}",
                idx + 1,
                primitives.len(),
                primitive_path.display()
            );
        }

        // Transform primitive (continue on error)
        match transformer.transform_primitive(primitive_path, output_dir) {
            Ok(result) => {
                // Convert output files from Strings to PathBufs
                let files: Vec<PathBuf> = result.output_files.iter().map(PathBuf::from).collect();

                if verbose {
                    println!("  {} Generated {} files", "✓".green(), files.len());
                }

                // Create manifest entry for this primitive
                if let Some(manifest_prim) = create_manifest_primitive(
                    primitive_path,
                    &result.output_files,
                    &output_dir_canonical,
                ) {
                    manifest_primitives.push(manifest_prim);
                }

                generated_files.extend(files);
            }
            Err(e) => {
                let error_msg = format!("Failed to transform {}: {}", primitive_path.display(), e);
                eprintln!("  {} {}", "✗".red(), error_msg);
                errors.push(error_msg);
            }
        }
    }

    Ok((generated_files, errors, manifest_primitives))
}

/// Create a manifest primitive entry from a primitive path and its generated files
fn create_manifest_primitive(
    primitive_path: &Path,
    output_files: &[String],
    output_dir: &Path,
) -> Option<ManifestPrimitive> {
    // Extract primitive ID from path (e.g., "qa/review" from ".../commands/qa/review/")
    let components: Vec<_> = primitive_path.components().collect();

    // Find the index of type directory (commands, skills, agents, tools, hooks)
    // New structure (ADR-021): types are directly under v1/
    let type_idx = components.iter().position(|c| {
        let name = c.as_os_str().to_string_lossy();
        name == "commands"
            || name == "skills"
            || name == "agents"
            || name == "tools"
            || name == "hooks"
    })?;

    // Extract kind from the type directory name
    let kind = components[type_idx]
        .as_os_str()
        .to_string_lossy()
        .to_string();

    // Build the ID from remaining path components (category/id)
    let id_parts: Vec<String> = components[type_idx + 1..]
        .iter()
        .map(|c| c.as_os_str().to_string_lossy().to_string())
        .collect();

    if id_parts.is_empty() {
        return None;
    }

    let id = id_parts.join("/");

    // Try to read metadata for version and hash
    // Check for new convention first ({id}.meta.yaml), then legacy patterns
    let dir_name = primitive_path.file_name()?.to_str()?;
    let meta_path = if primitive_path
        .join(format!("{dir_name}.meta.yaml"))
        .exists()
    {
        primitive_path.join(format!("{dir_name}.meta.yaml"))
    } else if primitive_path.join(format!("{dir_name}.yaml")).exists() {
        primitive_path.join(format!("{dir_name}.yaml"))
    } else {
        primitive_path.join("meta.yaml")
    };

    let (version, hash) = if meta_path.exists() {
        if let Ok(content) = fs::read_to_string(&meta_path) {
            if let Ok(yaml) = serde_yaml::from_str::<serde_yaml::Value>(&content) {
                let default_version = yaml
                    .get("default_version")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(1) as u32;

                // Get hash for the default version
                let hash = yaml
                    .get("versions")
                    .and_then(|v| v.as_sequence())
                    .and_then(|versions| {
                        versions.iter().find(|v| {
                            v.get("version")
                                .and_then(|ver| ver.as_u64())
                                .map(|ver| ver as u32 == default_version)
                                .unwrap_or(false)
                        })
                    })
                    .and_then(|v| v.get("hash"))
                    .and_then(|h| h.as_str())
                    .unwrap_or("unknown")
                    .to_string();

                (default_version, hash)
            } else {
                (1, "unknown".to_string())
            }
        } else {
            (1, "unknown".to_string())
        }
    } else {
        (1, "unknown".to_string())
    };

    // Convert paths to relative paths within output_dir
    let output_dir_str = output_dir.to_string_lossy().to_string();
    let relative_files: Vec<String> = output_files
        .iter()
        .map(|f| {
            let path = Path::new(f);
            // Try strip_prefix first (for canonical paths)
            if let Ok(relative) = path.strip_prefix(output_dir) {
                return relative.to_string_lossy().to_string();
            }
            // Try string manipulation for relative paths like ./build/claude/commands/...
            let f_clean = f.trim_start_matches("./");
            let output_clean = output_dir_str
                .trim_start_matches("./")
                .trim_end_matches('/');
            if let Some(relative) = f_clean.strip_prefix(output_clean) {
                return relative.trim_start_matches('/').to_string();
            }
            // Check if f already contains subdirectory structure
            if f.contains('/') {
                // Extract the path after output_dir pattern (e.g., "commands/review.md")
                if let Some(idx) = f.rfind("commands/") {
                    return f[idx..].to_string();
                }
                if let Some(idx) = f.rfind("custom_prompts/") {
                    return f[idx..].to_string();
                }
                if let Some(idx) = f.rfind("hooks/") {
                    return f[idx..].to_string();
                }
            }
            // Fall back to original
            f.clone()
        })
        .collect();

    Some(ManifestPrimitive {
        id,
        kind,
        version,
        hash,
        files: relative_files,
    })
}

/// Print a summary of the build result
fn print_build_summary(result: &BuildResult) {
    println!("\n{}", "═══════════════════════════════════════".cyan());
    println!("{}", "  Build Summary".bold().cyan());
    println!("{}", "═══════════════════════════════════════".cyan());
    println!("  Provider:     {}", result.provider.bold());
    println!("  Output:       {}", result.output_dir.display());
    println!(
        "  Primitives:   {}",
        result.primitives_built.to_string().green()
    );
    println!(
        "  Files:        {}",
        result.files_generated.len().to_string().green()
    );

    if !result.errors.is_empty() {
        println!("\n  {}", "Errors:".bold().red());
        for error in &result.errors {
            println!("    • {error}");
        }
    } else {
        println!("\n  {}", "✓ Build completed successfully!".green().bold());
    }

    println!("{}\n", "═══════════════════════════════════════".cyan());
}

/// Execute the build command
pub fn execute(args: &BuildArgs, config: &PrimitivesConfig) -> Result<()> {
    // 1. Instantiate provider transformer
    let transformer = get_transformer(&args.provider)?;

    // 2. Prepare output directory
    let output_dir = prepare_output_dir(args)?;

    // 3. Discover primitives
    let primitives = discover_primitives(args, config)?;

    if primitives.is_empty() {
        println!("{}", "No primitives found matching filters".yellow());
        return Ok(());
    }

    if args.verbose {
        println!("\n{} primitives to build", primitives.len());
    }

    // 4. Transform primitives
    let (files_generated, errors, manifest_primitives) = transform_primitives(
        primitives.clone(),
        transformer.as_ref(),
        &output_dir,
        args.verbose,
    )?;

    // 5. Create and save manifest
    let mut manifest = AgenticManifest::new(&args.provider);
    manifest.source = Some("agentic-primitives".to_string());
    manifest.updated_at = Utc::now();
    for prim in manifest_primitives {
        manifest.upsert_primitive(prim);
    }

    // Save manifest to output directory
    if let Err(e) = manifest.save(&output_dir) {
        eprintln!("  {} Failed to save manifest: {}", "⚠".yellow(), e);
    } else if args.verbose {
        println!("  {} Saved {}", "✓".green(), MANIFEST_FILENAME);
    }

    // 6. Build result
    let result = BuildResult {
        provider: args.provider.clone(),
        output_dir,
        primitives_built: primitives.len(),
        files_generated,
        errors,
        manifest,
    };

    // 7. Print summary
    print_build_summary(&result);

    // Return error if there were any errors
    if !result.errors.is_empty() {
        bail!("Build completed with {} error(s)", result.errors.len());
    }

    Ok(())
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_transformer_claude() {
        let transformer = get_transformer("claude");
        assert!(transformer.is_ok());
        assert_eq!(transformer.unwrap().provider_name(), "claude");
    }

    #[test]
    fn test_get_transformer_openai() {
        let transformer = get_transformer("openai");
        assert!(transformer.is_ok());
        assert_eq!(transformer.unwrap().provider_name(), "openai");
    }

    #[test]
    fn test_get_transformer_unknown() {
        match get_transformer("unknown") {
            Ok(_) => panic!("Expected error for unknown provider"),
            Err(e) => assert!(e.to_string().contains("Unknown provider")),
        }
    }

    #[test]
    fn test_should_include_primitive_no_filter() {
        let path = Path::new("/primitives/agents/python/my-agent");
        let args = BuildArgs {
            provider: "claude".to_string(),
            output: None,
            primitive: None,
            type_filter: None,
            kind: None,
            clean: false,
            verbose: false,
        };
        assert!(should_include_primitive(path, &args).unwrap());
    }

    #[test]
    fn test_should_include_primitive_type_filter_match() {
        let path = Path::new("/primitives/agents/python/my-agent");
        let args = BuildArgs {
            provider: "claude".to_string(),
            output: None,
            primitive: None,
            type_filter: Some("prompt".to_string()),
            kind: None,
            clean: false,
            verbose: false,
        };
        assert!(should_include_primitive(path, &args).unwrap());
    }

    #[test]
    fn test_should_include_primitive_type_filter_no_match() {
        let path = Path::new("/primitives/agents/python/my-agent");
        let args = BuildArgs {
            provider: "claude".to_string(),
            output: None,
            primitive: None,
            type_filter: Some("tool".to_string()),
            kind: None,
            clean: false,
            verbose: false,
        };
        assert!(!should_include_primitive(path, &args).unwrap());
    }

    #[test]
    fn test_should_include_primitive_kind_filter_match() {
        let path = Path::new("/primitives/agents/python/my-agent");
        let args = BuildArgs {
            provider: "claude".to_string(),
            output: None,
            primitive: None,
            type_filter: None,
            kind: Some("agent".to_string()),
            clean: false,
            verbose: false,
        };
        assert!(should_include_primitive(path, &args).unwrap());
    }

    #[test]
    fn test_should_include_primitive_kind_filter_no_match() {
        let path = Path::new("/primitives/agents/python/my-agent");
        let args = BuildArgs {
            provider: "claude".to_string(),
            output: None,
            primitive: None,
            type_filter: None,
            kind: Some("command".to_string()),
            clean: false,
            verbose: false,
        };
        assert!(!should_include_primitive(path, &args).unwrap());
    }

    #[test]
    fn test_should_include_primitive_invalid_type_filter() {
        let path = Path::new("/primitives/agents/python/my-agent");
        let args = BuildArgs {
            provider: "claude".to_string(),
            output: None,
            primitive: None,
            type_filter: Some("invalid".to_string()),
            kind: None,
            clean: false,
            verbose: false,
        };
        assert!(should_include_primitive(path, &args).is_err());
    }
}
