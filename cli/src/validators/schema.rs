use anyhow::{Context, Result};
use jsonschema::JSONSchema;
use serde_json::Value;

/// Validate YAML content against a JSON Schema
pub fn validate_against_schema(yaml_str: &str, schema_json: &str) -> Result<()> {
    // Parse YAML to JSON Value
    let yaml_value: Value = serde_yaml::from_str(yaml_str)
        .context("Failed to parse YAML")?;

    // Parse schema
    let schema_value: Value = serde_json::from_str(schema_json)
        .context("Failed to parse JSON Schema")?;

    // Compile schema
    let compiled_schema = JSONSchema::compile(&schema_value)
        .map_err(|e| anyhow::anyhow!("Failed to compile schema: {}", e))?;

    // Validate
    if let Err(errors) = compiled_schema.validate(&yaml_value) {
        let error_messages: Vec<String> = errors
            .map(|e| format!("  - {}: {}", e.instance_path, e))
            .collect();

        anyhow::bail!(
            "Validation errors:\n{}",
            error_messages.join("\n")
        );
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_valid_schema() {
        let schema = r#"{
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": { "type": "string" }
            }
        }"#;

        let yaml = "name: test";

        assert!(validate_against_schema(yaml, schema).is_ok());
    }

    #[test]
    fn test_invalid_schema() {
        let schema = r#"{
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": { "type": "string" }
            }
        }"#;

        let yaml = "age: 25";

        assert!(validate_against_schema(yaml, schema).is_err());
    }
}
