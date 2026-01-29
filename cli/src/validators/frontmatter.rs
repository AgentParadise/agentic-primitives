use anyhow::Result;
use super::schema::validate_against_schema;

/// Command frontmatter schema (embedded at compile time)
const COMMAND_SCHEMA: &str =
    include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/schemas/command-frontmatter.v1.json"));

/// Skill frontmatter schema (embedded at compile time)
const SKILL_SCHEMA: &str =
    include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/schemas/skill-frontmatter.v1.json"));

/// Validate command frontmatter against schema
pub fn validate_command_frontmatter(yaml_str: &str) -> Result<()> {
    validate_against_schema(yaml_str, COMMAND_SCHEMA)
        .map_err(|e| anyhow::anyhow!("Command frontmatter validation failed:\n{}", e))
}

/// Validate skill frontmatter against schema
pub fn validate_skill_frontmatter(yaml_str: &str) -> Result<()> {
    validate_against_schema(yaml_str, SKILL_SCHEMA)
        .map_err(|e| anyhow::anyhow!("Skill frontmatter validation failed:\n{}", e))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_valid_command_frontmatter() {
        let yaml = r#"
description: Test command for validation
model: sonnet
"#;
        assert!(validate_command_frontmatter(yaml).is_ok());
    }

    #[test]
    fn test_invalid_command_model() {
        let yaml = r#"
description: Test command
model: invalid-model
"#;
        assert!(validate_command_frontmatter(yaml).is_err());
    }

    #[test]
    fn test_missing_required_field() {
        let yaml = r#"
model: sonnet
"#;
        let result = validate_command_frontmatter(yaml);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("description"));
    }

    #[test]
    fn test_description_too_short() {
        let yaml = r#"
description: Short
model: sonnet
"#;
        assert!(validate_command_frontmatter(yaml).is_err());
    }

    #[test]
    fn test_valid_skill_frontmatter() {
        let yaml = r#"
description: Expert knowledge for testing
model: sonnet
allowed-tools: Read, Grep, Bash
"#;
        assert!(validate_skill_frontmatter(yaml).is_ok());
    }

    #[test]
    fn test_skill_with_expertise() {
        let yaml = r#"
description: Testing expert with specialized knowledge
model: sonnet
expertise:
  - Test-Driven Development
  - Coverage Analysis
"#;
        assert!(validate_skill_frontmatter(yaml).is_ok());
    }
}
