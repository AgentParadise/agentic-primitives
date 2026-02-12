//! Migrate primitives between spec versions

use anyhow::{Context, Result};
use clap::Args;
use colored::Colorize;
use comfy_table::{presets::UTF8_FULL, ContentArrangement, Table};
use serde_yaml::Value;
//use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

use crate::config::PrimitivesConfig;
// V2: SpecVersion not used in v2-only CLI
// use crate::spec_version::SpecVersion;
// V2: Validation updated - old layers system not used
// use crate::validators::{validate_primitive_with_layers, ValidationLayers};

#[derive(Debug, Args)]
pub struct MigrateArgs {
    /// Path to primitive(s) to migrate
    #[arg(value_name = "PATH")]
    pub path: PathBuf,

    /// Target spec version (v2, experimental, etc.)
    #[arg(long)]
    pub to_spec: String,

    /// Show planned changes without applying them
    #[arg(long)]
    pub dry_run: bool,

    /// Automatically fix breaking changes
    #[arg(long)]
    pub auto_fix: bool,
}

#[derive(Debug, Clone)]
struct MigrationReport {
    primitive: PathBuf,
    from_spec: String,
    to_spec: String,
    changes: Vec<String>,
    success: bool,
    error: Option<String>,
}

/// Execute migration command
pub fn execute(args: &MigrateArgs, config: &PrimitivesConfig) -> Result<()> {
    // Parse target spec
    let target_spec = parse_spec_version(&args.to_spec)?;

    // Find primitives to migrate
    let mut primitives = find_primitives(&args.path)?;

    // If no primitives found but the path is a specific directory, try to migrate it anyway
    // (will fail with proper error reporting)
    if primitives.is_empty() && args.path.is_dir() {
        primitives.push(args.path.clone());
    }

    if primitives.is_empty() {
        println!("{}", "No primitives found to migrate.".yellow());
        return Ok(());
    }

    println!(
        "\n{}",
        format!("Found {} primitive(s) to migrate", primitives.len()).bold()
    );

    // Perform migrations
    let mut reports = Vec::new();
    for primitive_path in primitives {
        let report = migrate_primitive(&primitive_path, &target_spec, args, config)?;
        reports.push(report);
    }

    // Display summary
    display_summary(&reports, args.dry_run);

    // Check for failures
    let failures = reports.iter().filter(|r| !r.success).count();
    if failures > 0 {
        println!(); // blank line before error
        println!("{}", format!("{failures} migration(s) failed").red().bold());
        std::process::exit(1);
    }

    if args.dry_run {
        println!("\n{}", "Run without --dry-run to apply changes.".bold());
    } else {
        println!("\n{}", "✓ Migration complete!".green().bold());
    }

    Ok(())
}

/// Migrate a single primitive
fn migrate_primitive(
    primitive_path: &Path,
    target_spec: &str,
    args: &MigrateArgs,
    config: &PrimitivesConfig,
) -> Result<MigrationReport> {
    let meta_path = primitive_path.join("meta.yaml");

    if !meta_path.exists() {
        return Ok(MigrationReport {
            primitive: primitive_path.to_path_buf(),
            from_spec: "unknown".to_string(),
            to_spec: target_spec.to_string(),
            changes: vec![],
            success: false,
            error: Some("meta.yaml not found".to_string()),
        });
    }

    // Load current meta.yaml
    let content = fs::read_to_string(&meta_path).context("Failed to read meta.yaml")?;
    let mut meta: Value = serde_yaml::from_str(&content).context("Failed to parse meta.yaml")?;

    // Determine current spec version
    let from_spec = meta
        .get("spec_version")
        .and_then(|v| v.as_str())
        .unwrap_or("v1")
        .to_string();

    // Get migration plan
    let changes = plan_migration(&from_spec, target_spec, &meta)?;

    if changes.is_empty() {
        return Ok(MigrationReport {
            primitive: primitive_path.to_path_buf(),
            from_spec,
            to_spec: target_spec.to_string(),
            changes: vec!["No changes needed".to_string()],
            success: true,
            error: None,
        });
    }

    // Apply changes if not dry-run
    if !args.dry_run {
        // Apply transformations
        apply_migrations(&mut meta, &from_spec, target_spec, args.auto_fix)?;

        // Save updated meta.yaml
        let updated_yaml = serde_yaml::to_string(&meta).context("Failed to serialize meta.yaml")?;
        fs::write(&meta_path, updated_yaml).context("Failed to write meta.yaml")?;

        // Handle directory moves if needed
        if target_spec == "experimental" && from_spec.starts_with('v') {
            move_to_experimental(primitive_path, config)?;
        }

        // V2: Validation not yet implemented for migrate
        // TODO: Add v2 validation after migration
        // if target_spec == "v1" {
        //     // validate the migrated primitive
        // }
        // Note: Skip validation for v2/experimental as those schemas don't exist yet
    }

    Ok(MigrationReport {
        primitive: primitive_path.to_path_buf(),
        from_spec,
        to_spec: target_spec.to_string(),
        changes,
        success: true,
        error: None,
    })
}

/// Plan migration changes
fn plan_migration(from_spec: &str, to_spec: &str, meta: &Value) -> Result<Vec<String>> {
    let mut changes = Vec::new();

    match (from_spec, to_spec) {
        ("v1", "v2") => {
            // spec_version update
            changes.push("Update spec_version: \"v1\" → \"v2\"".to_string());

            // Field renames (check under defaults)
            if let Some(Value::Mapping(defaults)) = meta.get("defaults") {
                if defaults
                    .get(Value::String("preferred_models".to_string()))
                    .is_some()
                {
                    changes.push(
                        "Rename field: 'defaults.preferred_models' → 'defaults.model_preferences'"
                            .to_string(),
                    );
                }
            }

            // Add new required fields if missing
            if meta.get("compatibility").is_none() {
                changes.push("Add field: 'compatibility' with target versions".to_string());
            }
        }
        ("v1", "experimental") | ("v2", "experimental") => {
            changes.push(format!(
                "Update spec_version: \"{from_spec}\" → \"experimental\""
            ));
            changes.push("Move to: primitives/experimental/".to_string());
        }
        ("experimental", "v2") => {
            changes.push("Update spec_version: \"experimental\" → \"v2\"".to_string());
            changes.push("Move to: primitives/v2/".to_string());
            changes.push("Rigorous validation will be applied".to_string());
        }
        (from, to) if from == to => {
            // No changes needed
        }
        (from, to) => {
            anyhow::bail!("Unsupported migration path: {from} → {to}");
        }
    }

    Ok(changes)
}

/// Apply migration transformations
fn apply_migrations(
    meta: &mut Value,
    from_spec: &str,
    to_spec: &str,
    auto_fix: bool,
) -> Result<()> {
    match (from_spec, to_spec) {
        ("v1", "v2") => {
            // Update spec_version
            if let Some(obj) = meta.as_mapping_mut() {
                obj.insert(
                    Value::String("spec_version".to_string()),
                    Value::String("v2".to_string()),
                );

                // Rename preferred_models to model_preferences (check under defaults)
                if let Some(Value::Mapping(defaults)) =
                    obj.get_mut(Value::String("defaults".to_string()))
                {
                    if let Some(preferred_models) =
                        defaults.remove(Value::String("preferred_models".to_string()))
                    {
                        defaults.insert(
                            Value::String("model_preferences".to_string()),
                            preferred_models,
                        );
                    }
                }

                // Add compatibility field if missing
                if !obj.contains_key(Value::String("compatibility".to_string())) && auto_fix {
                    let mut compatibility = serde_yaml::Mapping::new();
                    compatibility.insert(
                        Value::String("min_version".to_string()),
                        Value::String("v2".to_string()),
                    );
                    obj.insert(
                        Value::String("compatibility".to_string()),
                        Value::Mapping(compatibility),
                    );
                }
            }
        }
        ("v1", "experimental") | ("v2", "experimental") => {
            // Update spec_version to experimental
            if let Some(obj) = meta.as_mapping_mut() {
                obj.insert(
                    Value::String("spec_version".to_string()),
                    Value::String("experimental".to_string()),
                );
            }
        }
        ("experimental", "v2") => {
            // Promote from experimental to v2
            if let Some(obj) = meta.as_mapping_mut() {
                obj.insert(
                    Value::String("spec_version".to_string()),
                    Value::String("v2".to_string()),
                );
            }
        }
        (from, to) if from == to => {
            // No transformations needed
        }
        _ => {}
    }

    Ok(())
}

/// Move primitive to experimental directory
fn move_to_experimental(primitive_path: &Path, _config: &PrimitivesConfig) -> Result<()> {
    // Find the primitive type and name from the path
    // Pattern: .../primitives/v1/{type}/{category}/{name}
    // Target: .../primitives/experimental/{type}/{category}/{name}

    // Find the position of /primitives/ in the path (handle both Unix and Windows separators)
    let path_str = primitive_path.to_string_lossy();
    // Normalize to forward slashes for consistent parsing
    let normalized_path = path_str.replace('\\', "/");
    let primitives_idx = normalized_path
        .rfind("/primitives/")
        .context("Path does not contain /primitives/")?;

    let before_primitives = &normalized_path[..primitives_idx];
    let after_primitives = &normalized_path[primitives_idx + "/primitives/".len()..];

    // Skip the version part (v1, v2, etc.) and get the rest
    let after_version = after_primitives
        .split_once('/')
        .map(|(_, rest)| rest)
        .context("Unexpected path structure")?;

    // Construct target path
    let target_path = PathBuf::from(before_primitives)
        .join("primitives/experimental")
        .join(after_version);

    // Create parent directory
    if let Some(parent) = target_path.parent() {
        fs::create_dir_all(parent).context("Failed to create experimental directory")?;
    }

    // Move the primitive
    fs::rename(primitive_path, &target_path).context("Failed to move primitive to experimental")?;

    println!(
        "  {}",
        format!("→ Moved to {}", target_path.display()).blue()
    );

    Ok(())
}

/// Find all primitives in the given path
fn find_primitives(path: &Path) -> Result<Vec<PathBuf>> {
    let mut primitives = Vec::new();

    if !path.exists() {
        anyhow::bail!("Path does not exist: {}", path.display());
    }

    if path.is_file() {
        // Single meta.yaml file
        if path.file_name() == Some(std::ffi::OsStr::new("meta.yaml")) {
            if let Some(parent) = path.parent() {
                primitives.push(parent.to_path_buf());
            }
        }
    } else {
        // Directory - search for primitives
        for entry in WalkDir::new(path)
            .max_depth(6)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            if entry.file_name() == "meta.yaml" {
                if let Some(primitive_dir) = entry.path().parent() {
                    primitives.push(primitive_dir.to_path_buf());
                }
            }
        }
    }

    Ok(primitives)
}

/// Parse spec version string
fn parse_spec_version(spec: &str) -> Result<String> {
    match spec.to_lowercase().as_str() {
        "v1" => Ok("v1".to_string()),
        "v2" => Ok("v2".to_string()),
        "experimental" => Ok("experimental".to_string()),
        _ => anyhow::bail!("Unknown spec version: {spec}. Valid: v1, v2, experimental"),
    }
}

/// Display migration summary
fn display_summary(reports: &[MigrationReport], dry_run: bool) {
    println!(
        "\n{}",
        if dry_run {
            "Migration Plan".bold()
        } else {
            "Migration Results".bold()
        }
    );

    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec!["Primitive", "From", "To", "Status", "Changes"]);

    for report in reports {
        let primitive_name = report
            .primitive
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown");

        let status = if report.success {
            if dry_run {
                "Ready".green().to_string()
            } else {
                "✓".green().to_string()
            }
        } else {
            "✗".red().to_string()
        };

        let changes_summary = if report.changes.is_empty() {
            "None".to_string()
        } else {
            format!("{} change(s)", report.changes.len())
        };

        table.add_row(vec![
            primitive_name,
            &report.from_spec,
            &report.to_spec,
            &status,
            &changes_summary,
        ]);
    }

    println!("{table}");

    // Show detailed changes for failed migrations
    for report in reports.iter().filter(|r| !r.success) {
        if let Some(error) = &report.error {
            println!(
                "\n{}",
                format!("✗ {}", report.primitive.display()).red().bold()
            );
            println!("  Error: {error}");
        }
    }

    // Show detailed changes in dry-run mode
    if dry_run {
        println!("\n{}", "Planned Changes:".bold());
        for report in reports
            .iter()
            .filter(|r| r.success && !r.changes.is_empty())
        {
            println!("\n{}", report.primitive.display().to_string().blue().bold());
            for change in &report.changes {
                println!("  ✓ {change}");
            }
        }
    }

    // Summary counts
    let success_count = reports.iter().filter(|r| r.success).count();
    let fail_count = reports.len() - success_count;

    println!();
    if fail_count == 0 {
        if dry_run {
            println!(
                "{}",
                format!("{success_count} primitive(s) ready to migrate")
                    .green()
                    .bold()
            );
        } else {
            println!(
                "{}",
                format!("{success_count} primitive(s) migrated successfully")
                    .green()
                    .bold()
            );
        }
    } else {
        println!(
            "{}",
            format!("{success_count} succeeded, {fail_count} failed")
                .yellow()
                .bold()
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_spec_version() {
        assert_eq!(parse_spec_version("v1").unwrap(), "v1");
        assert_eq!(parse_spec_version("v2").unwrap(), "v2");
        assert_eq!(parse_spec_version("experimental").unwrap(), "experimental");
        assert_eq!(parse_spec_version("V1").unwrap(), "v1");
        assert!(parse_spec_version("v3").is_err());
    }

    #[test]
    fn test_plan_migration_v1_to_v2() {
        let meta_yaml = r#"
spec_version: v1
id: test
kind: agent
category: test
domain: test
summary: test
defaults:
  preferred_models:
    - claude/sonnet
"#;
        let meta: Value = serde_yaml::from_str(meta_yaml).unwrap();
        let changes = plan_migration("v1", "v2", &meta).unwrap();

        assert!(!changes.is_empty());
        assert!(changes.iter().any(|c| c.contains("spec_version")));
        assert!(changes.iter().any(|c| c.contains("preferred_models")));
    }

    #[test]
    fn test_plan_migration_to_experimental() {
        let meta: Value = serde_yaml::from_str("spec_version: v1").unwrap();
        let changes = plan_migration("v1", "experimental", &meta).unwrap();

        assert!(!changes.is_empty());
        assert!(changes.iter().any(|c| c.contains("experimental")));
    }

    #[test]
    fn test_plan_migration_same_version() {
        let meta: Value = serde_yaml::from_str("spec_version: v1").unwrap();
        let changes = plan_migration("v1", "v1", &meta).unwrap();
        assert!(changes.is_empty());
    }

    #[test]
    fn test_apply_migrations_v1_to_v2() {
        let meta_yaml = r#"
spec_version: v1
defaults:
  preferred_models:
    - claude/sonnet
"#;
        let mut meta: Value = serde_yaml::from_str(meta_yaml).unwrap();
        apply_migrations(&mut meta, "v1", "v2", true).unwrap();

        assert_eq!(
            meta.get("spec_version").and_then(|v| v.as_str()),
            Some("v2")
        );
        // Check that the field was renamed under defaults
        if let Some(Value::Mapping(defaults)) = meta.get("defaults") {
            assert!(defaults
                .get(Value::String("model_preferences".to_string()))
                .is_some());
            assert!(defaults
                .get(Value::String("preferred_models".to_string()))
                .is_none());
        } else {
            panic!("defaults section not found");
        }
    }
}
