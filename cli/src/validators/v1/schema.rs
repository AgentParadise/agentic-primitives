//! Layer 2: Schema validation
//! Validates meta.yaml against JSON schemas

use crate::spec_version::SpecVersion;
use anyhow::{Context, Result};
use std::path::Path;

pub struct SchemaValidator {
    spec_version: SpecVersion,
}

impl SchemaValidator {
    pub fn new() -> Result<Self> {
        Self::new_with_version(SpecVersion::V1)
    }

    pub fn new_with_version(spec_version: SpecVersion) -> Result<Self> {
        Ok(Self { spec_version })
    }

    pub fn validate(&self, primitive_path: &Path) -> Result<()> {
        // TODO: Implement JSON schema validation
        // For now, just check that meta.yaml can be read
        let meta_path = primitive_path.join("meta.yaml");
        if !meta_path.exists() {
            anyhow::bail!("Missing meta.yaml file");
        }

        // Try to read the file
        std::fs::read_to_string(&meta_path)
            .with_context(|| format!("Failed to read meta.yaml from {}", meta_path.display()))?;

        Ok(())
    }

    pub fn spec_version(&self) -> SpecVersion {
        self.spec_version
    }
}

impl Default for SchemaValidator {
    fn default() -> Self {
        Self::new().expect("Failed to create default SchemaValidator")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_validate_missing_meta_yaml() {
        let temp_dir = TempDir::new().unwrap();
        let validator = SchemaValidator::new().unwrap();
        let result = validator.validate(temp_dir.path());
        assert!(result.is_err());
    }

    #[test]
    fn test_validate_valid_meta_yaml() {
        let temp_dir = TempDir::new().unwrap();
        fs::write(temp_dir.path().join("meta.yaml"), "id: test\nkind: prompt").unwrap();
        let validator = SchemaValidator::new().unwrap();
        let result = validator.validate(temp_dir.path());
        assert!(result.is_ok());
    }
}
