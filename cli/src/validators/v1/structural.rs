//! Layer 1: Structural validation
//! Validates file structure, naming conventions, required files

use anyhow::Result;
use std::path::Path;

pub struct StructuralValidator;

impl StructuralValidator {
    pub fn new() -> Self {
        Self
    }

    pub fn validate(&self, primitive_path: &Path) -> Result<()> {
        // Check if path exists
        if !primitive_path.exists() {
            anyhow::bail!(
                "Primitive path does not exist: {}",
                primitive_path.display()
            );
        }

        // Check if it's a directory
        if !primitive_path.is_dir() {
            anyhow::bail!(
                "Primitive path is not a directory: {}",
                primitive_path.display()
            );
        }

        // Check for meta.yaml file
        let meta_path = primitive_path.join("meta.yaml");
        if !meta_path.exists() {
            anyhow::bail!(
                "Missing required meta.yaml file in: {}",
                primitive_path.display()
            );
        }

        Ok(())
    }
}

impl Default for StructuralValidator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_validate_missing_directory() {
        let validator = StructuralValidator::new();
        let result = validator.validate(Path::new("/nonexistent/path"));
        assert!(result.is_err());
    }

    #[test]
    fn test_validate_missing_meta_yaml() {
        let temp_dir = TempDir::new().unwrap();
        let validator = StructuralValidator::new();
        let result = validator.validate(temp_dir.path());
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("meta.yaml"));
    }

    #[test]
    fn test_validate_valid_structure() {
        let temp_dir = TempDir::new().unwrap();
        fs::write(temp_dir.path().join("meta.yaml"), "id: test").unwrap();
        let validator = StructuralValidator::new();
        let result = validator.validate(temp_dir.path());
        assert!(result.is_ok());
    }
}
