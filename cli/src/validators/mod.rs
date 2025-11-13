//! Validators with version routing

pub mod v1;

use crate::spec_version::SpecVersion;
use anyhow::Result;
use std::path::Path;

/// Route validation to appropriate version validator
pub fn validate_primitive(version: SpecVersion, primitive_path: &Path) -> Result<()> {
    match version {
        SpecVersion::V1 => {
            // Use v1 validators
            v1::StructuralValidator::new().validate(primitive_path)?;
            v1::SchemaValidator::new()?.validate(primitive_path)?;
            v1::SemanticValidator::new().validate(primitive_path)?;
            Ok(())
        }
        SpecVersion::Experimental => {
            // More lenient validation for experimental
            // For now, just structural
            v1::StructuralValidator::new().validate(primitive_path)?;
            println!("⚠️  Experimental primitive - schema and semantic validation skipped");
            Ok(())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_validate_v1_primitive() {
        let temp_dir = TempDir::new().unwrap();
        fs::write(temp_dir.path().join("meta.yaml"), "id: test\nkind: prompt").unwrap();

        let result = validate_primitive(SpecVersion::V1, temp_dir.path());
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_experimental_primitive() {
        let temp_dir = TempDir::new().unwrap();
        fs::write(temp_dir.path().join("meta.yaml"), "id: test").unwrap();

        let result = validate_primitive(SpecVersion::Experimental, temp_dir.path());
        assert!(result.is_ok());
    }
}
