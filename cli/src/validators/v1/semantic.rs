//! Layer 3: Semantic validation
//! Validates cross-references, dependencies, and business logic

use anyhow::Result;
use std::path::Path;

pub struct SemanticValidator;

impl SemanticValidator {
    pub fn new() -> Self {
        Self
    }

    pub fn validate(&self, primitive_path: &Path) -> Result<()> {
        // TODO: Implement semantic validation
        // - Check cross-references between primitives
        // - Validate provider references
        // - Check model configurations
        // - Validate hook dependencies

        // For now, just ensure the path is valid
        if !primitive_path.exists() {
            anyhow::bail!(
                "Primitive path does not exist: {}",
                primitive_path.display()
            );
        }

        Ok(())
    }
}

impl Default for SemanticValidator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_validate_missing_path() {
        let validator = SemanticValidator::new();
        let result = validator.validate(Path::new("/nonexistent/path"));
        assert!(result.is_err());
    }

    #[test]
    fn test_validate_valid_path() {
        let temp_dir = TempDir::new().unwrap();
        let validator = SemanticValidator::new();
        let result = validator.validate(temp_dir.path());
        assert!(result.is_ok());
    }
}
