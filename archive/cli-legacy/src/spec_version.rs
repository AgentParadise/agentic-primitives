use anyhow::{anyhow, Result};
use std::fmt;
use std::path::PathBuf;
use std::str::FromStr;

/// System-level specification version
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SpecVersion {
    /// v1 specification (stable)
    V1,
    /// Experimental workspace (unstable)
    Experimental,
}

impl SpecVersion {
    /// Get the current version from config or default to V1
    pub fn get_current_version() -> Result<Self> {
        // For now, always return V1 (will read from config later)
        Ok(SpecVersion::V1)
    }

    /// Resolve path to spec directory for this version
    pub fn resolve_spec_path(&self) -> PathBuf {
        match self {
            SpecVersion::V1 => PathBuf::from("specs/v1"),
            SpecVersion::Experimental => PathBuf::from("specs/experimental"),
        }
    }

    /// Resolve path to primitives directory for this version
    pub fn resolve_primitives_path(&self) -> PathBuf {
        match self {
            SpecVersion::V1 => PathBuf::from("primitives/v1"),
            SpecVersion::Experimental => PathBuf::from("primitives/experimental"),
        }
    }

    /// Get schema path for a specific schema name
    pub fn schema_path(&self, schema_name: &str) -> PathBuf {
        self.resolve_spec_path()
            .join(format!("{schema_name}.schema.json"))
    }
}

impl FromStr for SpecVersion {
    type Err = anyhow::Error;

    fn from_str(s: &str) -> Result<Self> {
        match s.to_lowercase().as_str() {
            "v1" | "1" => Ok(SpecVersion::V1),
            "experimental" | "exp" => Ok(SpecVersion::Experimental),
            _ => Err(anyhow!(
                "Unknown spec version: {s}. Valid: v1, experimental"
            )),
        }
    }
}

impl fmt::Display for SpecVersion {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SpecVersion::V1 => write!(f, "v1"),
            SpecVersion::Experimental => write!(f, "experimental"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_version() {
        assert_eq!("v1".parse::<SpecVersion>().unwrap(), SpecVersion::V1);
        assert_eq!("V1".parse::<SpecVersion>().unwrap(), SpecVersion::V1);
        assert_eq!("1".parse::<SpecVersion>().unwrap(), SpecVersion::V1);
        assert_eq!(
            "experimental".parse::<SpecVersion>().unwrap(),
            SpecVersion::Experimental
        );
        assert!("v2".parse::<SpecVersion>().is_err());
    }

    #[test]
    fn test_resolve_paths() {
        let v1 = SpecVersion::V1;
        assert_eq!(v1.resolve_spec_path(), PathBuf::from("specs/v1"));
        assert_eq!(v1.resolve_primitives_path(), PathBuf::from("primitives/v1"));

        let exp = SpecVersion::Experimental;
        assert_eq!(
            exp.resolve_primitives_path(),
            PathBuf::from("primitives/experimental")
        );
    }

    #[test]
    fn test_schema_path() {
        let v1 = SpecVersion::V1;
        assert_eq!(
            v1.schema_path("prompt-meta"),
            PathBuf::from("specs/v1/prompt-meta.schema.json")
        );
    }
}
