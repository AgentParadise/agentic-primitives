use crate::config::PrimitivesConfig;
use crate::manifest::{AgenticManifest, ManifestDiff, MANIFEST_FILENAME};
use anyhow::{anyhow, bail, Context, Result};
use chrono::Local;
use colored::Colorize;
use std::collections::HashSet;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

pub struct InstallArgs {
    pub provider: String,
    pub global: bool,
    pub build_dir: Option<PathBuf>,
    pub backup: bool,
    pub dry_run: bool,
    pub verbose: bool,
}

pub struct InstallResult {
    pub provider: String,
    pub install_location: PathBuf,
    pub files_installed: usize,
    pub files_backed_up: usize,
    pub backup_location: Option<PathBuf>,
    pub errors: Vec<String>,
}

#[allow(dead_code)]
fn resolve_install_location(provider: &str, global: bool) -> Result<PathBuf> {
    if global {
        // Global install - use platform-specific directories
        #[cfg(target_os = "linux")]
        let base_dir = dirs::config_dir()
            .ok_or_else(|| anyhow!("Could not determine config directory"))?
            .join(provider);

        #[cfg(not(target_os = "linux"))]
        let base_dir = dirs::home_dir()
            .ok_or_else(|| anyhow!("Could not determine home directory"))?
            .join(format!(".{provider}"));

        Ok(base_dir)
    } else {
        // Project install - current directory
        Ok(env::current_dir()?.join(format!(".{provider}")))
    }
}

#[allow(dead_code)]
fn validate_build_dir(build_dir: &Path, provider: &str) -> Result<()> {
    // Check directory exists
    if !build_dir.exists() {
        bail!(
            "Build directory not found: {}\n\nRun 'agentic-p build --provider {}' first",
            build_dir.display(),
            provider
        );
    }

    if !build_dir.is_dir() {
        bail!("Build path is not a directory: {}", build_dir.display());
    }

    // Check for provider-specific files
    match provider {
        "claude" => {
            // Claude should have mcp.json or .claude/ directory
            let mcp_file = build_dir.join("mcp.json");
            let claude_dir = build_dir.join(".claude");

            if !mcp_file.exists() && !claude_dir.exists() {
                bail!(
                    "Invalid Claude build directory: missing mcp.json or .claude/\n\
                    Directory: {}",
                    build_dir.display()
                );
            }
        }
        "openai" => {
            // OpenAI should have functions directory or manifest
            let functions_dir = build_dir.join("functions");
            let manifest = build_dir.join("manifest.json");

            if !functions_dir.exists() && !manifest.exists() {
                bail!(
                    "Invalid OpenAI build directory: missing functions/ or manifest.json\n\
                    Directory: {}",
                    build_dir.display()
                );
            }
        }
        _ => {
            // Generic check - directory should have at least one file
            let has_files = fs::read_dir(build_dir)?.next().is_some();

            if !has_files {
                bail!("Build directory is empty: {}", build_dir.display());
            }
        }
    }

    Ok(())
}

#[allow(dead_code)]
fn backup_existing_files(install_location: &Path, skip_backup: bool) -> Result<Option<PathBuf>> {
    if skip_backup || !install_location.exists() {
        return Ok(None);
    }

    // Create backup directory with timestamp
    let timestamp = Local::now().format("%Y%m%d_%H%M%S");
    let backup_dir = PathBuf::from(format!(
        "{}.backup.{}",
        install_location.display(),
        timestamp
    ));

    // Create backup directory
    fs::create_dir_all(&backup_dir).with_context(|| {
        format!(
            "Failed to create backup directory: {}",
            backup_dir.display()
        )
    })?;

    // Copy all existing files
    let mut backed_up = 0;
    for entry in WalkDir::new(install_location)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        let path = entry.path();

        if path.is_file() {
            let relative = path.strip_prefix(install_location)?;
            let backup_path = backup_dir.join(relative);

            if let Some(parent) = backup_path.parent() {
                fs::create_dir_all(parent)?;
            }

            fs::copy(path, &backup_path)
                .with_context(|| format!("Failed to backup {}", path.display()))?;

            backed_up += 1;
        }
    }

    println!(
        "  {} Backed up {} files to {}",
        "ℹ".cyan(),
        backed_up,
        backup_dir.display()
    );

    Ok(Some(backup_dir))
}

#[allow(dead_code)]
fn install_files(
    build_dir: &Path,
    install_location: &Path,
    dry_run: bool,
    verbose: bool,
) -> Result<Vec<PathBuf>> {
    let mut installed_files = Vec::new();

    // Ensure install location exists
    if !dry_run {
        fs::create_dir_all(install_location).with_context(|| {
            format!(
                "Failed to create install directory: {}",
                install_location.display()
            )
        })?;
    }

    // Walk build directory and copy files
    for entry in WalkDir::new(build_dir).into_iter().filter_map(|e| e.ok()) {
        let src_path = entry.path();

        if src_path.is_file() {
            let relative = src_path.strip_prefix(build_dir)?;
            let dest_path = install_location.join(relative);

            if verbose || dry_run {
                let action = if dry_run {
                    "Would install"
                } else {
                    "Installing"
                };
                println!(
                    "  {} {} -> {}",
                    action.cyan(),
                    relative.display(),
                    dest_path.display()
                );
            }

            if !dry_run {
                // Create parent directories
                if let Some(parent) = dest_path.parent() {
                    fs::create_dir_all(parent).with_context(|| {
                        format!("Failed to create directory: {}", parent.display())
                    })?;
                }

                // Copy file
                fs::copy(src_path, &dest_path).with_context(|| {
                    format!(
                        "Failed to copy {} to {}",
                        src_path.display(),
                        dest_path.display()
                    )
                })?;

                installed_files.push(dest_path);
            }
        }
    }

    Ok(installed_files)
}

#[allow(dead_code)]
fn print_install_summary(result: &InstallResult) {
    println!("\n{}", "═══════════════════════════════════════".cyan());
    println!("{}", "  Install Summary".bold().cyan());
    println!("{}", "═══════════════════════════════════════".cyan());
    println!("  Provider:     {}", result.provider.bold());
    println!("  Location:     {}", result.install_location.display());
    println!(
        "  Files:        {}",
        result.files_installed.to_string().green()
    );

    if let Some(ref backup) = result.backup_location {
        println!("  Backup:       {}", backup.display().to_string().yellow());
    }

    if !result.errors.is_empty() {
        println!("\n  {}", "Errors:".bold().red());
        for error in &result.errors {
            println!("    • {error}");
        }
    } else {
        println!(
            "\n  {}",
            "✓ Installation completed successfully!".green().bold()
        );
    }

    // Show next steps
    println!("\n  {} To use installed primitives:", "Next steps:".bold());
    match result.provider.as_str() {
        "claude" => {
            println!("    claude --agent <agent-name>");
            println!("    claude --command <command-name>");
        }
        "openai" => {
            println!("    # Configure your OpenAI client to use:");
            println!("    # {}", result.install_location.display());
        }
        _ => {}
    }

    println!("{}\n", "═══════════════════════════════════════".cyan());
}

pub fn execute(args: &InstallArgs, _config: &PrimitivesConfig) -> Result<()> {
    // 1. Resolve install location
    let install_location = resolve_install_location(&args.provider, args.global)?;

    if args.verbose {
        println!("Install location: {}", install_location.display());
    }

    // 2. Resolve build directory
    let build_dir = args
        .build_dir
        .clone()
        .unwrap_or_else(|| PathBuf::from(format!("./build/{}", args.provider)));

    // 3. Validate build directory
    validate_build_dir(&build_dir, &args.provider)?;

    // 4. Load manifests for smart sync
    let source_manifest =
        AgenticManifest::load(&build_dir).context("Failed to load build manifest")?;
    let target_manifest =
        AgenticManifest::load(&install_location).context("Failed to load existing manifest")?;

    // 5. Calculate diff and show what will change
    if let Some(ref source) = source_manifest {
        let diff = ManifestDiff::compare(source, target_manifest.as_ref());

        if args.verbose || args.dry_run {
            print_sync_preview(&diff, &target_manifest);
        }

        // 6. Smart sync - only install managed files
        let files_to_install = diff.files_to_install();
        let managed_files: HashSet<String> = source.managed_files().into_iter().collect();

        // Backup only managed files that will be overwritten
        let backup_location = if !args.dry_run && args.backup && !diff.updated.is_empty() {
            backup_managed_files(&install_location, &diff, args.verbose)?
        } else {
            None
        };

        let files_backed_up = backup_location
            .as_ref()
            .map(|b| count_files(b))
            .unwrap_or(0);

        // Install only the files that changed
        let installed_files = install_managed_files(
            &build_dir,
            &install_location,
            &files_to_install,
            args.dry_run,
            args.verbose,
        )?;

        // Copy manifest to install location
        if !args.dry_run {
            source
                .save(&install_location)
                .context("Failed to save manifest to install location")?;
        }

        // Show preserved local files
        if args.verbose {
            show_preserved_files(&install_location, &managed_files)?;
        }

        // Build result
        let result = InstallResult {
            provider: args.provider.clone(),
            install_location,
            files_installed: installed_files.len(),
            files_backed_up,
            backup_location,
            errors: Vec::new(),
        };

        if !args.dry_run {
            print_install_summary(&result);
        } else {
            println!(
                "\n{} Dry-run complete. No files were installed.",
                "ℹ".cyan()
            );
        }
    } else {
        // No manifest in build - fall back to legacy install (all files)
        println!(
            "{} No manifest found in build directory. Using legacy install (all files).",
            "⚠".yellow()
        );

        let backup_location = if !args.dry_run {
            backup_existing_files(&install_location, !args.backup)?
        } else {
            None
        };

        let files_backed_up = backup_location
            .as_ref()
            .map(|b| count_files(b))
            .unwrap_or(0);

        let installed_files =
            install_files(&build_dir, &install_location, args.dry_run, args.verbose)?;

        let result = InstallResult {
            provider: args.provider.clone(),
            install_location,
            files_installed: installed_files.len(),
            files_backed_up,
            backup_location,
            errors: Vec::new(),
        };

        if !args.dry_run {
            print_install_summary(&result);
        } else {
            println!(
                "\n{} Dry-run complete. No files were installed.",
                "ℹ".cyan()
            );
        }
    }

    Ok(())
}

/// Print a preview of what will be synced
fn print_sync_preview(diff: &ManifestDiff, existing: &Option<AgenticManifest>) {
    println!("\n{}", "Sync Preview".bold().cyan());
    println!("{}", "─".repeat(40));

    if !diff.added.is_empty() {
        println!("  {} New primitives:", "+".green().bold());
        for prim in &diff.added {
            println!("    {} {} (v{})", "+".green(), prim.id, prim.version);
        }
    }

    if !diff.updated.is_empty() {
        println!("  {} Updated primitives:", "↑".yellow().bold());
        for (old, new) in &diff.updated {
            println!(
                "    {} {} (v{} → v{})",
                "↑".yellow(),
                new.id,
                old.version,
                new.version
            );
        }
    }

    if !diff.removed.is_empty() {
        println!("  {} Removed primitives:", "-".red().bold());
        for prim in &diff.removed {
            println!("    {} {} (v{})", "-".red(), prim.id, prim.version);
        }
    }

    if !diff.unchanged.is_empty() {
        println!(
            "  {} {} unchanged primitives",
            "•".dimmed(),
            diff.unchanged.len()
        );
    }

    // Show local files that will be preserved
    if existing.is_some() {
        println!("\n  {} Local files will be preserved", "✓".green());
    }

    println!();
}

/// Backup only managed files that will be overwritten
fn backup_managed_files(
    install_location: &Path,
    diff: &ManifestDiff,
    verbose: bool,
) -> Result<Option<PathBuf>> {
    let files_to_backup: Vec<String> = diff
        .updated
        .iter()
        .flat_map(|(old, _)| old.files.iter().cloned())
        .collect();

    if files_to_backup.is_empty() {
        return Ok(None);
    }

    let timestamp = Local::now().format("%Y%m%d_%H%M%S");
    let backup_dir = PathBuf::from(format!(
        "{}.backup.{}",
        install_location.display(),
        timestamp
    ));

    fs::create_dir_all(&backup_dir)?;

    let mut backed_up = 0;
    for file in &files_to_backup {
        let src = install_location.join(file);
        if src.exists() {
            let dest = backup_dir.join(file);
            if let Some(parent) = dest.parent() {
                fs::create_dir_all(parent)?;
            }
            fs::copy(&src, &dest)?;
            backed_up += 1;
        }
    }

    if verbose && backed_up > 0 {
        println!(
            "  {} Backed up {} managed files to {}",
            "ℹ".cyan(),
            backed_up,
            backup_dir.display()
        );
    }

    Ok(Some(backup_dir))
}

/// Install only specific managed files
fn install_managed_files(
    build_dir: &Path,
    install_location: &Path,
    files_to_install: &[String],
    dry_run: bool,
    verbose: bool,
) -> Result<Vec<PathBuf>> {
    let mut installed = Vec::new();

    if !dry_run {
        fs::create_dir_all(install_location)?;
    }

    // Get the provider directory name (e.g., ".claude")
    let provider_prefix = install_location
        .file_name()
        .map(|n| format!("{}/", n.to_string_lossy()))
        .unwrap_or_default();

    for file in files_to_install {
        let src = build_dir.join(file);
        
        // Strip provider prefix from file path if present to avoid double-nesting
        // e.g., ".claude/hooks/..." -> "hooks/..." when install_location is ".claude"
        let relative_file = if file.starts_with(&provider_prefix) {
            &file[provider_prefix.len()..]
        } else {
            file.as_str()
        };
        
        let dest = install_location.join(relative_file);

        if !src.exists() {
            if verbose {
                eprintln!("  {} Source file not found: {}", "⚠".yellow(), file);
            }
            continue;
        }

        if verbose || dry_run {
            let action = if dry_run {
                "Would install"
            } else {
                "Installing"
            };
            println!("  {} {}", action.cyan(), file);
        }

        if !dry_run {
            if let Some(parent) = dest.parent() {
                fs::create_dir_all(parent)?;
            }
            fs::copy(&src, &dest)?;
            installed.push(dest);
        }
    }

    Ok(installed)
}

/// Show local files that are preserved (not managed)
fn show_preserved_files(install_location: &Path, managed_files: &HashSet<String>) -> Result<()> {
    let mut local_files = Vec::new();

    if install_location.exists() {
        for entry in WalkDir::new(install_location)
            .min_depth(1)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            let path = entry.path();
            if path.is_file() {
                let relative = path
                    .strip_prefix(install_location)
                    .map(|p| p.to_string_lossy().to_string())
                    .unwrap_or_default();

                // Skip manifest file
                if relative == MANIFEST_FILENAME {
                    continue;
                }

                if !managed_files.contains(&relative) {
                    local_files.push(relative);
                }
            }
        }
    }

    if !local_files.is_empty() {
        println!("\n  {} Preserved local files:", "✓".green());
        for file in &local_files {
            println!("    {} {}", "•".dimmed(), file);
        }
    }

    Ok(())
}

/// Count files in a directory
fn count_files(dir: &Path) -> usize {
    WalkDir::new(dir)
        .into_iter()
        .filter(|e| e.as_ref().map(|e| e.path().is_file()).unwrap_or(false))
        .count()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resolve_install_location_project() {
        let path = resolve_install_location("claude", false).unwrap();
        assert!(path.ends_with(".claude"));
    }

    #[test]
    fn test_resolve_install_location_global() {
        let path = resolve_install_location("claude", true).unwrap();
        // Should contain .claude or config/claude
        let path_str = path.to_string_lossy();
        assert!(
            path_str.contains(".claude") || path_str.contains("config/claude"),
            "Path should contain .claude or config/claude, got: {path_str}"
        );
    }

    #[test]
    #[cfg(target_os = "linux")]
    fn test_resolve_install_location_linux_xdg() {
        let path = resolve_install_location("claude", true).unwrap();
        assert!(path.to_string_lossy().contains("config/claude"));
    }

    #[test]
    #[cfg(not(target_os = "linux"))]
    fn test_resolve_install_location_macos_windows() {
        let path = resolve_install_location("claude", true).unwrap();
        assert!(path.to_string_lossy().contains(".claude"));
    }

    #[test]
    fn test_validate_build_dir_not_exists() {
        let result = validate_build_dir(Path::new("/nonexistent"), "claude");
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("not found"));
    }

    #[test]
    fn test_validate_build_dir_claude_valid() {
        use tempfile::TempDir;

        // Create temp directory with mcp.json
        let temp_dir = TempDir::new().unwrap();
        let mcp_file = temp_dir.path().join("mcp.json");
        fs::write(&mcp_file, "{}").unwrap();

        let result = validate_build_dir(temp_dir.path(), "claude");
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_build_dir_openai_valid() {
        use tempfile::TempDir;

        // Create temp directory with functions directory
        let temp_dir = TempDir::new().unwrap();
        let functions_dir = temp_dir.path().join("functions");
        fs::create_dir(&functions_dir).unwrap();

        let result = validate_build_dir(temp_dir.path(), "openai");
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_build_dir_empty() {
        use tempfile::TempDir;

        // Create empty temp directory
        let temp_dir = TempDir::new().unwrap();

        let result = validate_build_dir(temp_dir.path(), "unknown_provider");
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("empty"));
    }

    #[test]
    fn test_backup_existing_files_creates_backup() {
        use tempfile::TempDir;

        // Create temp directory with some files
        let temp_dir = TempDir::new().unwrap();
        let install_location = temp_dir.path().join("install");
        fs::create_dir(&install_location).unwrap();
        fs::write(install_location.join("file1.txt"), "content1").unwrap();
        fs::write(install_location.join("file2.txt"), "content2").unwrap();

        let result = backup_existing_files(&install_location, false);
        assert!(result.is_ok());
        let backup_dir = result.unwrap();
        assert!(backup_dir.is_some());

        // Verify backup directory exists and has files
        let backup_dir = backup_dir.unwrap();
        assert!(backup_dir.exists());
        assert!(backup_dir.join("file1.txt").exists());
        assert!(backup_dir.join("file2.txt").exists());
    }

    #[test]
    fn test_backup_skip_when_no_backup_flag() {
        use tempfile::TempDir;

        // Create temp directory with some files
        let temp_dir = TempDir::new().unwrap();
        let install_location = temp_dir.path().join("install");
        fs::create_dir(&install_location).unwrap();
        fs::write(install_location.join("file1.txt"), "content1").unwrap();

        let result = backup_existing_files(&install_location, true);
        assert!(result.is_ok());
        assert!(result.unwrap().is_none());
    }

    #[test]
    fn test_backup_skip_when_no_existing_files() {
        use tempfile::TempDir;

        // Use non-existent directory
        let temp_dir = TempDir::new().unwrap();
        let install_location = temp_dir.path().join("nonexistent");

        let result = backup_existing_files(&install_location, false);
        assert!(result.is_ok());
        assert!(result.unwrap().is_none());
    }

    #[test]
    fn test_install_files_copies_correctly() {
        use tempfile::TempDir;

        // Create build directory with files
        let temp_dir = TempDir::new().unwrap();
        let build_dir = temp_dir.path().join("build");
        fs::create_dir(&build_dir).unwrap();
        fs::write(build_dir.join("file1.txt"), "content1").unwrap();
        let subdir = build_dir.join("subdir");
        fs::create_dir(&subdir).unwrap();
        fs::write(subdir.join("file2.txt"), "content2").unwrap();

        // Install to a different location
        let install_location = temp_dir.path().join("install");

        let result = install_files(&build_dir, &install_location, false, false);
        assert!(result.is_ok());
        let installed_files = result.unwrap();
        assert_eq!(installed_files.len(), 2);

        // Verify files copied
        assert!(install_location.join("file1.txt").exists());
        assert!(install_location.join("subdir/file2.txt").exists());
        assert_eq!(
            fs::read_to_string(install_location.join("file1.txt")).unwrap(),
            "content1"
        );
        assert_eq!(
            fs::read_to_string(install_location.join("subdir/file2.txt")).unwrap(),
            "content2"
        );
    }

    #[test]
    fn test_install_files_dry_run() {
        use tempfile::TempDir;

        // Create build directory with files
        let temp_dir = TempDir::new().unwrap();
        let build_dir = temp_dir.path().join("build");
        fs::create_dir(&build_dir).unwrap();
        fs::write(build_dir.join("file1.txt"), "content1").unwrap();

        // Install to a different location (dry-run)
        let install_location = temp_dir.path().join("install");

        let result = install_files(&build_dir, &install_location, true, false);
        assert!(result.is_ok());
        let installed_files = result.unwrap();
        assert_eq!(installed_files.len(), 0); // No files actually installed in dry-run

        // Verify files NOT copied
        assert!(!install_location.exists());
    }

    #[test]
    fn test_install_files_preserves_structure() {
        use tempfile::TempDir;

        // Create build directory with nested structure
        let temp_dir = TempDir::new().unwrap();
        let build_dir = temp_dir.path().join("build");
        fs::create_dir_all(build_dir.join("a/b/c")).unwrap();
        fs::write(build_dir.join("a/file1.txt"), "content1").unwrap();
        fs::write(build_dir.join("a/b/file2.txt"), "content2").unwrap();
        fs::write(build_dir.join("a/b/c/file3.txt"), "content3").unwrap();

        // Install to a different location
        let install_location = temp_dir.path().join("install");

        let result = install_files(&build_dir, &install_location, false, false);
        assert!(result.is_ok());

        // Verify directory structure preserved
        assert!(install_location.join("a/file1.txt").exists());
        assert!(install_location.join("a/b/file2.txt").exists());
        assert!(install_location.join("a/b/c/file3.txt").exists());
    }
}
