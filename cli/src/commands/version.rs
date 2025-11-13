//! Version management commands for primitives

use anyhow::{Context, Result};
use blake3::Hasher;
use chrono::Utc;
use clap::Subcommand;
use colored::Colorize;
use comfy_table::{presets::UTF8_FULL, Cell, Color, ContentArrangement, Table};
use std::fs;
use std::path::{Path, PathBuf};

use crate::config::PrimitivesConfig;
use crate::primitives::prompt::{PromptMeta, VersionEntry};

#[derive(Debug, Subcommand)]
pub enum VersionCommand {
    /// List all versions of a primitive with status, dates, and hashes
    List {
        /// Primitive path (e.g., python/python-pro)
        primitive: String,
    },
    /// Create a new version by copying the current one
    Bump {
        /// Primitive path (e.g., python/python-pro)
        primitive: String,
        /// Notes describing changes in this version
        #[arg(long)]
        notes: String,
        /// Set this version as the default
        #[arg(long)]
        set_default: bool,
    },
    /// Promote a version from draft to active
    Promote {
        /// Primitive path (e.g., python/python-pro)
        primitive: String,
        /// Version number to promote
        version: u32,
        /// Set this version as the default
        #[arg(long)]
        set_default: bool,
    },
    /// Deprecate a version
    Deprecate {
        /// Primitive path (e.g., python/python-pro)
        primitive: String,
        /// Version number to deprecate
        version: u32,
        /// Reason for deprecation
        #[arg(long)]
        reason: Option<String>,
    },
    /// Validate BLAKE3 hashes for content integrity
    Check {
        /// Optional primitive path (checks all if not specified)
        primitive: Option<String>,
    },
}

/// Execute version commands
pub fn execute(command: &VersionCommand, config: &PrimitivesConfig) -> Result<()> {
    match command {
        VersionCommand::List { primitive } => list_versions(primitive, config),
        VersionCommand::Bump {
            primitive,
            notes,
            set_default,
        } => bump_version(primitive, notes, *set_default, config),
        VersionCommand::Promote {
            primitive,
            version,
            set_default,
        } => promote_version(primitive, *version, *set_default, config),
        VersionCommand::Deprecate {
            primitive,
            version,
            reason,
        } => deprecate_version(primitive, *version, reason.as_deref(), config),
        VersionCommand::Check { primitive } => check_hashes(primitive.as_deref(), config),
    }
}

/// List all versions of a primitive
fn list_versions(primitive: &str, config: &PrimitivesConfig) -> Result<()> {
    let primitive_path = resolve_primitive_path(primitive, config)?;
    let meta = load_meta(&primitive_path)?;

    if meta.versions.is_empty() {
        println!("{}", "No versions found for this primitive.".yellow());
        println!("\nThis primitive does not use versioning.");
        println!("Use 'agentic-p version bump' to create the first version.");
        return Ok(());
    }

    // Display header
    println!("\n{}", format!("Versions for {}", primitive).bold());

    // Create table
    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec!["Version", "Status", "Created", "Hash", "Notes"]);

    // Add rows
    for version in &meta.versions {
        let version_str = format!("v{}", version.version);

        // Color-code status
        let status_cell = match version.status.as_str() {
            "active" => Cell::new(&version.status).fg(Color::Green),
            "draft" => Cell::new(&version.status).fg(Color::Yellow),
            "deprecated" => Cell::new(&version.status).fg(Color::Red),
            _ => Cell::new(&version.status),
        };

        // Truncate hash for display
        let hash_short = if version.hash.starts_with("blake3:") {
            &version.hash[7..std::cmp::min(7 + 8, version.hash.len())]
        } else {
            &version.hash[..std::cmp::min(8, version.hash.len())]
        };

        // Add default marker
        let mut notes = version.notes.clone();
        if meta.default_version == Some(version.version) {
            notes.push_str(" ⭐ default");
        }

        table.add_row(vec![
            Cell::new(&version_str),
            status_cell,
            Cell::new(&version.created),
            Cell::new(&format!("blake3:{}", hash_short)),
            Cell::new(&notes),
        ]);
    }

    println!("{table}");
    println!("\nUse --version N with inspect/build to use a specific version.");

    Ok(())
}

/// Create a new version by copying the current one
fn bump_version(
    primitive: &str,
    notes: &str,
    set_default: bool,
    config: &PrimitivesConfig,
) -> Result<()> {
    let primitive_path = resolve_primitive_path(primitive, config)?;
    let meta_path = primitive_path.join("meta.yaml");
    let mut meta = load_meta(&primitive_path)?;

    // Find highest version number
    let highest = meta.versions.iter().map(|v| v.version).max().unwrap_or(0);
    let new_version = highest + 1;

    // Determine source file
    let source_file = if highest > 0 {
        // Copy from highest version
        let source_entry = meta
            .versions
            .iter()
            .find(|v| v.version == highest)
            .context("Failed to find source version entry")?;
        source_entry.file.clone()
    } else {
        // Copy from unversioned file
        format!("{}.prompt.md", meta.id)
    };

    let source_path = primitive_path.join(&source_file);
    if !source_path.exists() {
        anyhow::bail!("Source file not found: {}", source_path.display());
    }

    // Create new version file
    let new_file = format!("{}.prompt.v{}.md", meta.id, new_version);
    let new_path = primitive_path.join(&new_file);

    fs::copy(&source_path, &new_path).context("Failed to copy version file")?;

    println!(
        "{}",
        format!("✓ Copied {} → {}", source_file, new_file).green()
    );

    // Calculate hash for new version
    let content = fs::read_to_string(&new_path)?;
    let hash = calculate_hash(&content);

    println!(
        "{}",
        format!(
            "✓ Calculated hash: {}...",
            &hash[..std::cmp::min(16, hash.len())]
        )
        .green()
    );

    // Add version entry to meta.yaml
    let version_entry = VersionEntry {
        version: new_version,
        file: new_file.clone(),
        status: "draft".to_string(),
        hash: hash.clone(),
        created: Utc::now().format("%Y-%m-%d").to_string(),
        deprecated: None,
        notes: notes.to_string(),
    };
    meta.versions.push(version_entry);

    // Optionally update default_version
    if set_default {
        meta.default_version = Some(new_version);
    }

    // Save meta.yaml
    save_meta(&meta_path, &meta)?;

    println!(
        "{}",
        format!("\n✓ Created version {} (draft)", new_version)
            .green()
            .bold()
    );
    println!("\nNext steps:");
    println!("  1. Edit {} with your changes", new_file);
    println!(
        "  2. Run: agentic-p version promote {} {}",
        primitive, new_version
    );
    if !set_default {
        println!("     Add --set-default to make it the default version");
    }

    Ok(())
}

/// Promote a version from draft to active
fn promote_version(
    primitive: &str,
    version: u32,
    set_default: bool,
    config: &PrimitivesConfig,
) -> Result<()> {
    let primitive_path = resolve_primitive_path(primitive, config)?;
    let meta_path = primitive_path.join("meta.yaml");
    let mut meta = load_meta(&primitive_path)?;

    // Find version entry
    let version_entry = meta
        .versions
        .iter_mut()
        .find(|v| v.version == version)
        .context(format!("Version {} not found", version))?;

    // Validate current status
    if version_entry.status == "deprecated" {
        anyhow::bail!("Cannot promote a deprecated version. Create a new version instead.");
    }

    // Update status
    version_entry.status = "active".to_string();

    // Optionally set as default
    if set_default {
        meta.default_version = Some(version);
    }

    // Save meta.yaml
    save_meta(&meta_path, &meta)?;

    println!(
        "{}",
        format!("✓ Promoted version {} to active", version)
            .green()
            .bold()
    );

    if set_default {
        println!("{}", format!("✓ Set as default version").green());
    }

    Ok(())
}

/// Deprecate a version
fn deprecate_version(
    primitive: &str,
    version: u32,
    reason: Option<&str>,
    config: &PrimitivesConfig,
) -> Result<()> {
    let primitive_path = resolve_primitive_path(primitive, config)?;
    let meta_path = primitive_path.join("meta.yaml");
    let mut meta = load_meta(&primitive_path)?;

    // Find version entry
    let version_entry = meta
        .versions
        .iter_mut()
        .find(|v| v.version == version)
        .context(format!("Version {} not found", version))?;

    // Update status
    version_entry.status = "deprecated".to_string();

    // Add reason to deprecated field
    if let Some(reason) = reason {
        version_entry.deprecated = Some(reason.to_string());
    }

    // Unset as default if it was
    if meta.default_version == Some(version) {
        // Find highest active version
        let latest_active = meta
            .versions
            .iter()
            .filter(|v| v.status == "active")
            .map(|v| v.version)
            .max();

        meta.default_version = latest_active;

        if let Some(new_default) = latest_active {
            println!(
                "{}",
                format!("→ Default version changed to v{}", new_default).yellow()
            );
        } else {
            println!("{}", "⚠ No active versions remaining!".yellow());
        }
    }

    // Save meta.yaml
    save_meta(&meta_path, &meta)?;

    println!(
        "{}",
        format!("✓ Deprecated version {}", version).yellow().bold()
    );

    if let Some(reason) = reason {
        println!("  Reason: {}", reason);
    }

    Ok(())
}

/// Check BLAKE3 hashes for all versions
fn check_hashes(primitive: Option<&str>, config: &PrimitivesConfig) -> Result<()> {
    let primitives = if let Some(prim) = primitive {
        vec![resolve_primitive_path(prim, config)?]
    } else {
        // Find all primitives with versions
        find_versioned_primitives(config)?
    };

    if primitives.is_empty() {
        println!("{}", "No versioned primitives found.".yellow());
        return Ok(());
    }

    println!("\n{}", "Checking version hashes...".bold());

    let mut valid_count = 0;
    let mut mismatch_count = 0;

    for primitive_path in &primitives {
        let meta = load_meta(primitive_path)?;
        let primitive_name = primitive_path
            .strip_prefix(&config.paths.primitives)
            .or_else(|_| primitive_path.strip_prefix(&config.paths.experimental))
            .unwrap_or(primitive_path)
            .display()
            .to_string();

        for version_entry in &meta.versions {
            let file_path = primitive_path.join(&version_entry.file);

            if !file_path.exists() {
                println!(
                    "{}",
                    format!(
                        "✗ {} v{}: FILE NOT FOUND ({})",
                        primitive_name, version_entry.version, version_entry.file
                    )
                    .red()
                );
                mismatch_count += 1;
                continue;
            }

            let content = fs::read_to_string(&file_path)?;
            let actual_hash = calculate_hash(&content);

            if actual_hash == version_entry.hash {
                println!(
                    "{}",
                    format!(
                        "✓ {} v{}: {} (valid)",
                        primitive_name,
                        version_entry.version,
                        &actual_hash[..std::cmp::min(16, actual_hash.len())]
                    )
                    .green()
                );
                valid_count += 1;
            } else {
                println!(
                    "{}",
                    format!(
                        "✗ {} v{}: HASH MISMATCH!",
                        primitive_name, version_entry.version
                    )
                    .red()
                    .bold()
                );
                println!("  Expected: {}", version_entry.hash);
                println!("  Got:      {}", actual_hash);
                println!(
                    "  {}",
                    "Content has been modified after versioning.".yellow()
                );
                println!("  Run 'agentic-p version bump' to create a new version.");
                mismatch_count += 1;
            }
        }
    }

    println!();
    if mismatch_count == 0 {
        println!(
            "{}",
            format!("✓ All {} versions valid", valid_count)
                .green()
                .bold()
        );
    } else {
        println!(
            "{}",
            format!("{} valid, {} mismatch", valid_count, mismatch_count)
                .yellow()
                .bold()
        );
    }

    if mismatch_count > 0 {
        anyhow::bail!("Hash validation failed");
    }

    Ok(())
}

// Helper functions

/// Calculate BLAKE3 hash with blake3: prefix
fn calculate_hash(content: &str) -> String {
    let mut hasher = Hasher::new();
    hasher.update(content.as_bytes());
    format!("blake3:{}", hasher.finalize().to_hex())
}

/// Resolve primitive path from relative identifier
fn resolve_primitive_path(primitive: &str, config: &PrimitivesConfig) -> Result<PathBuf> {
    // Try different locations for prompts
    let primitives_dir = &config.paths.primitives;
    let experimental_dir = &config.paths.experimental;
    
    let candidates = vec![
        primitives_dir.join("prompts/agents").join(primitive),
        primitives_dir.join("prompts/commands").join(primitive),
        primitives_dir.join("prompts/skills").join(primitive),
        primitives_dir.join("prompts/meta-prompts").join(primitive),
        experimental_dir.join("prompts/agents").join(primitive),
        experimental_dir.join("prompts/commands").join(primitive),
        experimental_dir.join("prompts/skills").join(primitive),
        experimental_dir.join("prompts/meta-prompts").join(primitive),
    ];

    for candidate in candidates {
        if candidate.exists() {
            return Ok(candidate);
        }
    }

    anyhow::bail!("Primitive not found: {}", primitive)
}

/// Load meta.yaml from primitive directory
fn load_meta(primitive_path: &Path) -> Result<PromptMeta> {
    let meta_path = primitive_path.join("meta.yaml");
    if !meta_path.exists() {
        anyhow::bail!("meta.yaml not found in {}", primitive_path.display());
    }

    let content = fs::read_to_string(&meta_path).context("Failed to read meta.yaml")?;
    let meta: PromptMeta = serde_yaml::from_str(&content).context("Failed to parse meta.yaml")?;

    Ok(meta)
}

/// Save meta.yaml to primitive directory
fn save_meta(meta_path: &Path, meta: &PromptMeta) -> Result<()> {
    let yaml = serde_yaml::to_string(meta).context("Failed to serialize meta.yaml")?;
    fs::write(meta_path, yaml).context("Failed to write meta.yaml")?;
    Ok(())
}

/// Find all primitives with versions
fn find_versioned_primitives(config: &PrimitivesConfig) -> Result<Vec<PathBuf>> {
    use walkdir::WalkDir;

    let mut primitives = Vec::new();

    // Search both primitives and experimental directories
    let search_dirs = vec![&config.paths.primitives, &config.paths.experimental];

    for search_dir in search_dirs {
        if !search_dir.exists() {
            continue;
        }
        
        for entry in WalkDir::new(search_dir)
            .max_depth(6)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            if entry.file_name() == "meta.yaml" {
                if let Some(primitive_dir) = entry.path().parent() {
                    // Check if it has versions
                    if let Ok(meta) = load_meta(primitive_dir) {
                        if !meta.versions.is_empty() {
                            primitives.push(primitive_dir.to_path_buf());
                        }
                    }
                }
            }
        }
    }

    Ok(primitives)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_calculate_hash() {
        let content = "test content";
        let hash = calculate_hash(content);
        assert!(hash.starts_with("blake3:"));
        assert_eq!(hash.len(), 71); // "blake3:" + 64 hex chars
    }

    #[test]
    fn test_calculate_hash_consistency() {
        let content = "test content";
        let hash1 = calculate_hash(content);
        let hash2 = calculate_hash(content);
        assert_eq!(hash1, hash2);
    }

    #[test]
    fn test_calculate_hash_different_content() {
        let hash1 = calculate_hash("content1");
        let hash2 = calculate_hash("content2");
        assert_ne!(hash1, hash2);
    }
}
