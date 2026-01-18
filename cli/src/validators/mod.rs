//! Validators with version routing
//
// Note: V1 validators removed - use cli/v1/ for V1 validation
// V2 validators are in cli/v2/src/validators/

use crate::spec_version::SpecVersion;
use anyhow::Result;
use std::path::Path;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum ValidationError {
    #[error("Validation failed: {0}")]
    Failed(String),

    #[error("Unknown validation layer: {0}")]
    UnknownLayer(String),
}

/// Validation layers that can be selectively enabled
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ValidationLayers {
    /// All layers (structural, schema, semantic)
    All,
    /// Only structural validation
    Structural,
    /// Only schema validation
    Schema,
    /// Only semantic validation
    Semantic,
}

impl ValidationLayers {
    pub fn parse(s: &str) -> Result<Self> {
        match s.to_lowercase().as_str() {
            "all" => Ok(ValidationLayers::All),
            "structural" => Ok(ValidationLayers::Structural),
            "schema" => Ok(ValidationLayers::Schema),
            "semantic" => Ok(ValidationLayers::Semantic),
            _ => Err(ValidationError::UnknownLayer(s.to_string()).into()),
        }
    }

    pub fn includes_structural(&self) -> bool {
        matches!(self, ValidationLayers::All | ValidationLayers::Structural)
    }

    pub fn includes_schema(&self) -> bool {
        matches!(self, ValidationLayers::All | ValidationLayers::Schema)
    }

    pub fn includes_semantic(&self) -> bool {
        matches!(self, ValidationLayers::All | ValidationLayers::Semantic)
    }
}

/// Validation report containing results from all layers
#[derive(Debug)]
pub struct ValidationReport {
    pub spec_version: SpecVersion,
    pub structural_passed: bool,
    pub schema_passed: bool,
    pub semantic_passed: bool,
    pub errors: Vec<String>,
}

impl ValidationReport {
    pub fn new(spec_version: SpecVersion) -> Self {
        Self {
            spec_version,
            structural_passed: false,
            schema_passed: false,
            semantic_passed: false,
            errors: Vec::new(),
        }
    }

    pub fn experimental(primitive_path: &Path) -> Self {
        Self {
            spec_version: SpecVersion::Experimental,
            structural_passed: true,
            schema_passed: false,
            semantic_passed: false,
            errors: vec![format!(
                "⚠️  Experimental primitive: {}\n    Schema and semantic validation skipped",
                primitive_path.display()
            )],
        }
    }

    pub fn is_valid(&self) -> bool {
        self.errors.is_empty()
    }

    pub fn add_error(&mut self, error: String) {
        self.errors.push(error);
    }
}

/// Route validation to appropriate version validator with selective layers
pub fn validate_primitive_with_layers(
    version: SpecVersion,
    _primitive_path: &Path,
    _layers: ValidationLayers,
) -> Result<ValidationReport> {
    // Note: This is a transitional CLI state
    // Use cli/v1/ for V1 validation or cli/v2/ for V2 validation
    match version {
        SpecVersion::V1 | SpecVersion::Experimental => {
            anyhow::bail!(
                "V1/Experimental validation not supported in transitional CLI.\n\
                 Use: cd cli/v1 && cargo run -- validate <primitive>"
            );
        }
    }
}

/// Route validation to appropriate version validator (all layers)
pub fn validate_primitive(version: SpecVersion, primitive_path: &Path) -> Result<()> {
    validate_primitive_with_layers(version, primitive_path, ValidationLayers::All)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;
    use tempfile::TempDir;

    fn create_valid_test_primitive(temp_dir: &Path) -> PathBuf {
        let primitive_path = temp_dir.join("test-agent");
        fs::create_dir_all(&primitive_path).unwrap();

        // Filename must match ID (test-agent.v1.md, not prompt.v1.md)
        let meta = r#"
id: test-agent
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
    file: test-agent.v1.md
    status: active
    created: "2025-01-01"
default_version: 1
"#;
        fs::write(primitive_path.join("meta.yaml"), meta).unwrap();
        fs::write(primitive_path.join("test-agent.v1.md"), "# Test").unwrap();

        primitive_path
    }

    #[test]
    fn test_validation_layers_parse() {
        assert_eq!(
            ValidationLayers::parse("all").unwrap(),
            ValidationLayers::All
        );
        assert_eq!(
            ValidationLayers::parse("structural").unwrap(),
            ValidationLayers::Structural
        );
        assert_eq!(
            ValidationLayers::parse("schema").unwrap(),
            ValidationLayers::Schema
        );
        assert_eq!(
            ValidationLayers::parse("semantic").unwrap(),
            ValidationLayers::Semantic
        );
        assert!(ValidationLayers::parse("invalid").is_err());
    }

    #[test]
    fn test_validation_layers_includes() {
        let all = ValidationLayers::All;
        assert!(all.includes_structural());
        assert!(all.includes_schema());
        assert!(all.includes_semantic());

        let structural = ValidationLayers::Structural;
        assert!(structural.includes_structural());
        assert!(!structural.includes_schema());
        assert!(!structural.includes_semantic());

        let schema = ValidationLayers::Schema;
        assert!(!schema.includes_structural());
        assert!(schema.includes_schema());
        assert!(!schema.includes_semantic());

        let semantic = ValidationLayers::Semantic;
        assert!(!semantic.includes_structural());
        assert!(!semantic.includes_schema());
        assert!(semantic.includes_semantic());
    }

    #[test]
    fn test_validate_v1_primitive_all_layers() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = create_valid_test_primitive(temp_dir.path());

        let result = validate_primitive(SpecVersion::V1, &primitive_path);
        // V1 validation not supported in transitional CLI - expect error
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("V1/Experimental validation not supported"));
    }

    #[test]
    fn test_validate_v1_primitive_structural_only() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = create_valid_test_primitive(temp_dir.path());

        let result = validate_primitive_with_layers(
            SpecVersion::V1,
            &primitive_path,
            ValidationLayers::Structural,
        );
        // V1 validation not supported in transitional CLI - expect error
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("V1/Experimental validation not supported"));
    }

    #[test]
    fn test_validate_v1_primitive_schema_only() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = create_valid_test_primitive(temp_dir.path());

        let result = validate_primitive_with_layers(
            SpecVersion::V1,
            &primitive_path,
            ValidationLayers::Schema,
        );
        // V1 validation not supported in transitional CLI - expect error
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("V1/Experimental validation not supported"));
    }

    #[test]
    fn test_validate_v1_primitive_semantic_only() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = create_valid_test_primitive(temp_dir.path());

        let result = validate_primitive_with_layers(
            SpecVersion::V1,
            &primitive_path,
            ValidationLayers::Semantic,
        );
        // V1 validation not supported in transitional CLI - expect error
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("V1/Experimental validation not supported"));
    }

    #[test]
    fn test_validate_experimental_primitive() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test-exp");
        fs::create_dir_all(&primitive_path).unwrap();
        fs::write(
            primitive_path.join("meta.yaml"),
            "id: test-exp\nkind: agent\nsummary: test\ncategory: test",
        )
        .unwrap();
        // Create version file since kind is agent (must match ID)
        fs::write(primitive_path.join("test-exp.v1.md"), "# Test").unwrap();

        let result = validate_primitive(SpecVersion::Experimental, &primitive_path);
        // Experimental validation not supported in transitional CLI - expect error
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("V1/Experimental validation not supported"));
    }

    #[test]
    fn test_validate_v1_invalid_structural() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("InvalidName");
        fs::create_dir_all(&primitive_path).unwrap();
        fs::write(
            primitive_path.join("meta.yaml"),
            "id: invalid-name\nkind: agent",
        )
        .unwrap();

        let result = validate_primitive(SpecVersion::V1, &primitive_path);
        // V1 validation not supported in transitional CLI - expect error (not structural validation error)
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("V1/Experimental validation not supported"));
    }

    #[test]
    fn test_validation_report_is_valid() {
        let mut report = ValidationReport::new(SpecVersion::V1);
        assert!(report.is_valid());

        report.add_error("Test error".to_string());
        assert!(!report.is_valid());
    }

    #[test]
    fn test_validation_report_experimental() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = temp_dir.path().join("test");
        fs::create_dir_all(&primitive_path).unwrap();

        let report = ValidationReport::experimental(&primitive_path);
        assert_eq!(report.spec_version, SpecVersion::Experimental);
        assert!(report.structural_passed);
        assert!(!report.schema_passed);
        assert!(!report.semantic_passed);
        assert!(!report.errors.is_empty());
    }

    #[test]
    fn test_validate_with_layers_all() {
        let temp_dir = TempDir::new().unwrap();
        let primitive_path = create_valid_test_primitive(temp_dir.path());

        let result =
            validate_primitive_with_layers(SpecVersion::V1, &primitive_path, ValidationLayers::All);
        // V1 validation not supported in transitional CLI - expect error
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("V1/Experimental validation not supported"));
    }
}
