//! Validate primitives with pretty output

use anyhow::{Context, Result};
use colored::*;
use comfy_table::{modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Table};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

use crate::spec_version::SpecVersion;
use crate::validators::{validate_primitive_with_layers, ValidationLayers, ValidationReport};

#[derive(Debug)]
pub struct ValidateArgs {
    pub path: PathBuf,
    pub spec_version: Option<SpecVersion>,
    pub layer: ValidationLayers,
    pub json: bool,
}

#[derive(Serialize, Deserialize)]
struct ValidateOutput {
    total: usize,
    valid: usize,
    invalid: usize,
    results: Vec<ValidationResult>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct ValidationResult {
    path: String,
    prim_type: String,
    kind: Option<String>,
    valid: bool,
    errors: Vec<ValidationError>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
struct ValidationError {
    layer: String,
    message: String,
}

/// Validate primitives
pub fn validate(args: ValidateArgs) -> Result<()> {
    // 1. Find all primitives to validate
    let primitives = find_primitives(&args.path)?;

    if primitives.is_empty() {
        anyhow::bail!("No primitives found at {:?}", args.path);
    }

    // 2. Validate each primitive
    let mut results = Vec::new();
    let mut valid_count = 0;
    let mut invalid_count = 0;

    for primitive_path in &primitives {
        // Auto-detect or use specified spec version
        let spec_version = if let Some(v) = &args.spec_version {
            *v
        } else {
            detect_spec_version(primitive_path)?
        };

        // Run validation
        let report = validate_primitive_with_layers(spec_version, primitive_path, args.layer);

        let result = match report {
            Ok(r) => {
                if r.is_valid() {
                    valid_count += 1;
                } else {
                    invalid_count += 1;
                }
                create_result(primitive_path, r)?
            }
            Err(e) => {
                invalid_count += 1;
                ValidationResult {
                    path: primitive_path.display().to_string(),
                    prim_type: detect_type(primitive_path)?,
                    kind: detect_kind(primitive_path).ok(),
                    valid: false,
                    errors: vec![ValidationError {
                        layer: "system".to_string(),
                        message: e.to_string(),
                    }],
                }
            }
        };

        results.push(result);
    }

    // 3. Output results
    if args.json {
        output_json(&results, valid_count, invalid_count)?;
    } else {
        output_pretty(&results, &args)?;
    }

    // 4. Exit with appropriate code
    if invalid_count > 0 {
        std::process::exit(1);
    }

    Ok(())
}

fn find_primitives(path: &Path) -> Result<Vec<PathBuf>> {
    let mut primitives = Vec::new();

    if !path.exists() {
        anyhow::bail!("Path does not exist: {path:?}");
    }

    if path.is_file() {
        // Single primitive (meta.yaml file)
        if let Some(parent) = path.parent() {
            primitives.push(parent.to_path_buf());
        }
    } else if path.is_dir() {
        // Recursively find all primitives (directories with metadata files)
        // Supports both new ({id}.yaml, {id}.tool.yaml, {id}.hook.yaml) and legacy formats
        for entry in WalkDir::new(path)
            .min_depth(1)
            .max_depth(10)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            let file_name = entry.file_name().to_string_lossy();

            // Check for metadata files in both new (ADR-019) and legacy formats
            let is_meta_file = file_name == "meta.yaml"
                || file_name == "tool.meta.yaml"
                || file_name == "hook.meta.yaml"
                || file_name.ends_with(".meta.yaml") // ADR-019: {id}.meta.yaml
                || (file_name.ends_with(".yaml")
                    && !file_name.starts_with('.')
                    && (file_name.ends_with(".tool.yaml")
                        || file_name.ends_with(".hook.yaml")
                        || (!file_name.contains(".tool.")
                            && !file_name.contains(".hook.")
                            && !file_name.contains(".meta.")
                            && !file_name.contains(".v"))));

            if is_meta_file {
                if let Some(parent) = entry.path().parent() {
                    primitives.push(parent.to_path_buf());
                }
            }
        }
    }

    // Deduplicate
    primitives.sort();
    primitives.dedup();

    Ok(primitives)
}

fn detect_spec_version(primitive_path: &Path) -> Result<SpecVersion> {
    let path_str = primitive_path.display().to_string();
    if path_str.contains("primitives/v1") || path_str.contains("primitives\\v1") {
        Ok(SpecVersion::V1)
    } else if path_str.contains("experimental") {
        Ok(SpecVersion::Experimental)
    } else {
        // Default to V1
        Ok(SpecVersion::V1)
    }
}

fn detect_type(primitive_path: &Path) -> Result<String> {
    // Check for meta file to determine type
    // Get directory name for new naming convention (ADR-019)
    let dir_name = primitive_path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("");

    // Check for prompt metadata (new convention first, then legacy)
    if primitive_path
        .join(format!("{dir_name}.meta.yaml"))
        .exists()
        || primitive_path.join(format!("{dir_name}.yaml")).exists()
        || primitive_path.join("meta.yaml").exists()
    {
        Ok("prompt".to_string())
    } else if primitive_path
        .join(format!("{dir_name}.tool.yaml"))
        .exists()
        || primitive_path.join("tool.meta.yaml").exists()
    {
        Ok("tool".to_string())
    } else if primitive_path
        .join(format!("{dir_name}.hook.yaml"))
        .exists()
        || primitive_path.join("hook.meta.yaml").exists()
    {
        Ok("hook".to_string())
    } else {
        Ok("unknown".to_string())
    }
}

fn detect_kind(primitive_path: &Path) -> Result<String> {
    // Get directory name for new naming convention (ADR-019)
    let dir_name = primitive_path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("");

    // For prompts, read metadata to get kind - try new convention first
    let meta_candidates = [
        primitive_path.join(format!("{dir_name}.meta.yaml")), // ADR-019
        primitive_path.join(format!("{dir_name}.yaml")),      // Legacy
        primitive_path.join("meta.yaml"),                     // Legacy
    ];

    for meta_path in meta_candidates {
        if meta_path.exists() {
            let content = fs::read_to_string(&meta_path)
                .with_context(|| format!("Failed to read metadata: {meta_path:?}"))?;
            let meta: serde_yaml::Value =
                serde_yaml::from_str(&content).with_context(|| "Failed to parse metadata")?;

            if let Some(kind) = meta.get("kind") {
                if let Some(kind_str) = kind.as_str() {
                    return Ok(kind_str.to_string());
                }
            }
        }
    }

    // For tools/hooks, check path
    let path_str = primitive_path.display().to_string();
    if path_str.contains("/tools/") || path_str.contains("\\tools\\") {
        Ok("shell".to_string())
    } else if path_str.contains("/hooks/") || path_str.contains("\\hooks\\") {
        Ok("safety".to_string())
    } else {
        anyhow::bail!("Could not detect kind for primitive")
    }
}

fn create_result(primitive_path: &Path, report: ValidationReport) -> Result<ValidationResult> {
    let prim_type = detect_type(primitive_path)?;
    let kind = detect_kind(primitive_path).ok();
    let is_valid = report.is_valid();

    let errors = report
        .errors
        .into_iter()
        .map(|e| {
            let (layer, message) = if let Some(pos) = e.find(':') {
                let layer = e[..pos].trim().to_string();
                let message = e[pos + 1..].trim().to_string();
                (layer, message)
            } else {
                ("validation".to_string(), e)
            };
            ValidationError { layer, message }
        })
        .collect();

    Ok(ValidationResult {
        path: primitive_path.display().to_string(),
        prim_type,
        kind,
        valid: is_valid,
        errors,
    })
}

fn output_pretty(results: &[ValidationResult], args: &ValidateArgs) -> Result<()> {
    println!(
        "\n🔍 {} {:?}\n",
        "Validating primitives in:".bold(),
        args.path
    );

    // Create table
    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .apply_modifier(UTF8_ROUND_CORNERS)
        .set_header(vec!["Path", "Type", "Kind", "Status"]);

    for result in results {
        let status = if result.valid {
            "✅ Valid".green().to_string()
        } else {
            "❌ Error".red().to_string()
        };

        // Shorten path for display
        let display_path = result.path.replace("primitives/v1/", "").replace("\\", "/");

        table.add_row(vec![
            display_path,
            result.prim_type.clone(),
            result.kind.clone().unwrap_or_else(|| "-".to_string()),
            status,
        ]);
    }

    println!("{table}\n");

    // Summary
    let total = results.len();
    let valid = results.iter().filter(|r| r.valid).count();
    let invalid = total - valid;

    if invalid == 0 {
        println!(
            "✅ {} {total} primitives passed validation\n",
            "All".green().bold()
        );
    } else {
        println!(
            "❌ {} primitives failed validation\n",
            format!("{invalid} of {total}").red().bold()
        );

        // Print detailed errors
        println!("{}\n", "Errors:".red().bold());
        for result in results.iter().filter(|r| !r.valid) {
            println!("{}:", result.path.yellow());
            for error in &result.errors {
                println!(
                    "  {} {}",
                    format!("[{}]", error.layer).cyan(),
                    error.message
                );
            }
            println!();
        }
    }

    // Footer
    println!(
        "{} {}",
        "Layers checked:".dimmed(),
        format_layers(&args.layer)
    );
    if let Some(v) = &args.spec_version {
        println!("{} {}", "Spec version:".dimmed(), v);
    } else {
        println!("{} auto-detected", "Spec version:".dimmed());
    }
    println!();

    Ok(())
}

fn output_json(results: &[ValidationResult], valid: usize, invalid: usize) -> Result<()> {
    let output = ValidateOutput {
        total: results.len(),
        valid,
        invalid,
        results: results.to_vec(),
    };

    println!("{}", serde_json::to_string_pretty(&output)?);
    Ok(())
}

fn format_layers(layers: &ValidationLayers) -> String {
    match layers {
        ValidationLayers::All => "structural, schema, semantic".to_string(),
        ValidationLayers::Structural => "structural".to_string(),
        ValidationLayers::Schema => "schema".to_string(),
        ValidationLayers::Semantic => "semantic".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn create_valid_prompt(base: &Path, category: &str, id: &str) -> PathBuf {
        // New structure (ADR-021): agents directly under v1/
        let path = base.join("primitives/v1/agents").join(category).join(id);
        fs::create_dir_all(&path).unwrap();

        // Filename must match ID
        let version_file = format!("{id}.v1.md");
        let meta = format!(
            r#"
id: {id}
kind: agent
category: testing
domain: test
summary: Test agent
context_usage:
  as_system: true
  as_user: false
  as_overlay: false
versions:
  - version: 1
    file: {version_file}
    status: active
    created: "2025-01-01"
default_version: 1
"#
        );
        fs::write(path.join("meta.yaml"), meta).unwrap();
        fs::write(path.join(&version_file), "# Test").unwrap();

        path
    }

    #[test]
    fn test_find_primitives_single_file() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = create_valid_prompt(temp_dir.path(), "test", "test-agent");
        let meta_path = primitive_path.join("meta.yaml");

        let result = find_primitives(&meta_path).unwrap();
        assert_eq!(result.len(), 1);
        assert_eq!(result[0], primitive_path);
    }

    #[test]
    fn test_find_primitives_directory() {
        let temp_dir = TempDir::new().unwrap();
        create_valid_prompt(temp_dir.path(), "test", "agent1");
        create_valid_prompt(temp_dir.path(), "test", "agent2");

        let result = find_primitives(&temp_dir.path().join("primitives/v1")).unwrap();
        assert_eq!(result.len(), 2);
    }

    #[test]
    fn test_find_primitives_nonexistent() {
        let temp_dir = TempDir::new().unwrap();
        let nonexistent = temp_dir.path().join("nonexistent");

        let result = find_primitives(&nonexistent);
        assert!(result.is_err());
    }

    #[test]
    fn test_detect_spec_version() {
        // New structure (ADR-021)
        let v1_path = PathBuf::from("primitives/v1/agents/test/test-agent");
        assert_eq!(detect_spec_version(&v1_path).unwrap(), SpecVersion::V1);

        let exp_path = PathBuf::from("primitives/experimental/test/test-agent");
        assert_eq!(
            detect_spec_version(&exp_path).unwrap(),
            SpecVersion::Experimental
        );
    }

    #[test]
    fn test_detect_type() {
        let temp_dir = TempDir::new().unwrap();
        let path = temp_dir.path();

        // Prompt
        fs::write(path.join("meta.yaml"), "id: test").unwrap();
        assert_eq!(detect_type(path).unwrap(), "prompt");

        // Tool
        fs::remove_file(path.join("meta.yaml")).unwrap();
        fs::write(path.join("tool.meta.yaml"), "id: test").unwrap();
        assert_eq!(detect_type(path).unwrap(), "tool");

        // Hook
        fs::remove_file(path.join("tool.meta.yaml")).unwrap();
        fs::write(path.join("hook.meta.yaml"), "id: test").unwrap();
        assert_eq!(detect_type(path).unwrap(), "hook");
    }

    #[test]
    fn test_detect_kind_from_meta() {
        let temp_dir = TempDir::new().unwrap();
        let path = temp_dir.path();

        fs::write(path.join("meta.yaml"), "id: test\nkind: agent").unwrap();
        assert_eq!(detect_kind(path).unwrap(), "agent");

        fs::write(path.join("meta.yaml"), "id: test\nkind: command").unwrap();
        assert_eq!(detect_kind(path).unwrap(), "command");
    }

    #[test]
    fn test_format_layers() {
        assert_eq!(
            format_layers(&ValidationLayers::All),
            "structural, schema, semantic"
        );
        assert_eq!(format_layers(&ValidationLayers::Structural), "structural");
        assert_eq!(format_layers(&ValidationLayers::Schema), "schema");
        assert_eq!(format_layers(&ValidationLayers::Semantic), "semantic");
    }

    #[test]
    fn test_validate_with_valid_primitive() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = create_valid_prompt(temp_dir.path(), "test", "test-agent");

        // Test the underlying validation logic directly instead of the validate() function
        // which calls std::process::exit(1) and would kill the test process
        let result = validate_primitive_with_layers(
            SpecVersion::V1,
            &primitive_path,
            ValidationLayers::Structural
        );
        
        // V1 validation not supported in transitional CLI - expect error
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("V1/Experimental validation not supported"));
    }

    #[test]
    fn test_validate_nonexistent_path() {
        let temp_dir = TempDir::new().unwrap();
        let nonexistent = temp_dir.path().join("nonexistent");

        let args = ValidateArgs {
            path: nonexistent,
            spec_version: Some(SpecVersion::V1),
            layer: ValidationLayers::All,
            json: false,
        };

        let result = validate(args);
        assert!(result.is_err());
    }

    #[test]
    fn test_json_output_format() {
        let results = vec![
            ValidationResult {
                path: "test/agent".to_string(),
                prim_type: "prompt".to_string(),
                kind: Some("agent".to_string()),
                valid: true,
                errors: vec![],
            },
            ValidationResult {
                path: "test/bad".to_string(),
                prim_type: "prompt".to_string(),
                kind: Some("agent".to_string()),
                valid: false,
                errors: vec![ValidationError {
                    layer: "structural".to_string(),
                    message: "Invalid structure".to_string(),
                }],
            },
        ];

        let result = output_json(&results, 1, 1);
        assert!(result.is_ok());
    }
}
