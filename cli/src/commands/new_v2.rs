///! Generate new V2 primitives with templates and validation
use anyhow::{Context, Result};
use clap::Args;
use colored::Colorize;
use dialoguer::{Input, Select};
use handlebars::Handlebars;
use serde_json::json;
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

use crate::validators;

#[derive(Args, Debug)]
pub struct NewCommandArgs {
    /// Primitive type (command, skill, tool)
    #[arg(value_enum)]
    pub primitive_type: PrimitiveType,

    /// Category (e.g., qa, devops, data)
    pub category: String,

    /// Primitive name (kebab-case)
    pub name: String,

    /// Description of the primitive
    #[arg(long)]
    pub description: Option<String>,

    /// Model to use (haiku, sonnet, opus)
    #[arg(long)]
    pub model: Option<String>,

    /// Allowed tools (comma-separated)
    #[arg(long)]
    pub allowed_tools: Option<String>,

    /// Argument hint (for commands)
    #[arg(long)]
    pub argument_hint: Option<String>,

    /// Expertise areas (for skills, comma-separated)
    #[arg(long)]
    pub expertise: Option<String>,

    /// Tags (comma-separated)
    #[arg(long)]
    pub tags: Option<String>,

    /// Skip interactive prompts
    #[arg(long)]
    pub non_interactive: bool,
}

#[derive(Debug, Clone, clap::ValueEnum)]
pub enum PrimitiveType {
    Command,
    Skill,
    Tool,
}

impl PrimitiveType {
    fn subdir(&self) -> &str {
        match self {
            PrimitiveType::Command => "commands",
            PrimitiveType::Skill => "skills",
            PrimitiveType::Tool => "tools",
        }
    }
}

pub fn execute(mut args: NewCommandArgs) -> Result<()> {
    println!("{}", "Creating New V2 Primitive".cyan().bold());
    println!("{}", "═".repeat(50).cyan());
    println!();

    // Validate name format
    validate_name(&args.name)?;

    // Interactive prompts if fields missing
    if !args.non_interactive {
        fill_missing_fields(&mut args)?;
    }

    // Ensure required fields are present
    ensure_required_fields(&args)?;

    // Generate the primitive
    match args.primitive_type {
        PrimitiveType::Command => create_command(&args)?,
        PrimitiveType::Skill => create_skill(&args)?,
        PrimitiveType::Tool => create_tool(&args)?,
    }

    Ok(())
}

/// Validate name format (kebab-case)
fn validate_name(name: &str) -> Result<()> {
    if !name
        .chars()
        .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
    {
        anyhow::bail!(
            "Name must be lowercase alphanumeric with hyphens only (kebab-case): {}",
            name
        );
    }

    if name.starts_with('-') || name.ends_with('-') {
        anyhow::bail!("Name cannot start or end with a hyphen: {}", name);
    }

    Ok(())
}

/// Fill missing fields with interactive prompts
fn fill_missing_fields(args: &mut NewCommandArgs) -> Result<()> {
    // Description
    if args.description.is_none() {
        let desc: String = Input::new()
            .with_prompt("Description (10-200 chars)")
            .interact_text()?;
        args.description = Some(desc);
    }

    // Model
    if args.model.is_none() {
        let models = vec!["haiku", "sonnet", "opus"];
        let selection = Select::new()
            .with_prompt("Model")
            .items(&models)
            .default(1) // sonnet
            .interact()?;
        args.model = Some(models[selection].to_string());
    }

    // Type-specific fields
    match args.primitive_type {
        PrimitiveType::Command => {
            // Argument hint
            if args.argument_hint.is_none() {
                let hint: String = Input::new()
                    .with_prompt("Argument hint (optional, press Enter to skip)")
                    .allow_empty(true)
                    .interact_text()?;
                if !hint.is_empty() {
                    args.argument_hint = Some(hint);
                }
            }
        }
        PrimitiveType::Skill => {
            // Expertise
            if args.expertise.is_none() {
                let expertise: String = Input::new()
                    .with_prompt("Expertise areas (comma-separated, optional)")
                    .allow_empty(true)
                    .interact_text()?;
                if !expertise.is_empty() {
                    args.expertise = Some(expertise);
                }
            }
        }
        PrimitiveType::Tool => {
            // Tools don't need extra interactive fields for now
        }
    }

    // Allowed tools (for all types)
    if args.allowed_tools.is_none() {
        let tools: String = Input::new()
            .with_prompt("Allowed tools (comma-separated, optional)")
            .allow_empty(true)
            .interact_text()?;
        if !tools.is_empty() {
            args.allowed_tools = Some(tools);
        }
    }

    Ok(())
}

/// Ensure required fields are present
fn ensure_required_fields(args: &NewCommandArgs) -> Result<()> {
    if args.description.is_none() {
        anyhow::bail!("Description is required (use --description or interactive mode)");
    }

    if args.model.is_none() {
        anyhow::bail!("Model is required (use --model or interactive mode)");
    }

    // Validate description length
    let desc = args.description.as_ref().unwrap();
    if desc.len() < 10 || desc.len() > 200 {
        anyhow::bail!(
            "Description must be between 10 and 200 characters (got {})",
            desc.len()
        );
    }

    // Validate model
    let model = args.model.as_ref().unwrap();
    if !["haiku", "sonnet", "opus"].contains(&model.as_str()) {
        anyhow::bail!("Model must be one of: haiku, sonnet, opus (got: {})", model);
    }

    Ok(())
}

/// Create a command primitive
fn create_command(args: &NewCommandArgs) -> Result<()> {
    let output_dir = PathBuf::from("primitives/v2/commands").join(&args.category);
    fs::create_dir_all(&output_dir)
        .with_context(|| format!("Failed to create directory: {}", output_dir.display()))?;

    let output_file = output_dir.join(format!("{}.md", args.name));

    if output_file.exists() {
        anyhow::bail!("Command already exists: {}", output_file.display());
    }

    // Prepare template data
    let mut data = HashMap::new();
    data.insert("description", args.description.as_ref().unwrap().clone());
    data.insert("model", args.model.as_ref().unwrap().clone());
    data.insert("title", to_title_case(&args.name));
    data.insert("slug", args.name.clone());

    if let Some(hint) = &args.argument_hint {
        data.insert("argument_hint", hint.clone());
    }

    if let Some(tools) = &args.allowed_tools {
        data.insert("allowed_tools", tools.clone());
    }

    // Parse tags if provided
    let tags: Option<Vec<String>> = args
        .tags
        .as_ref()
        .map(|t| t.split(',').map(|s| s.trim().to_string()).collect());

    // Render template
    let template = include_str!("../templates/command.md.hbs");
    let mut hb = Handlebars::new();
    hb.register_template_string("command", template)?;

    let content = hb.render(
        "command",
        &json!({
            "description": data.get("description").unwrap(),
            "argument_hint": data.get("argument_hint"),
            "model": data.get("model").unwrap(),
            "allowed_tools": data.get("allowed_tools"),
            "tags": tags,
            "title": data.get("title").unwrap(),
            "slug": data.get("slug").unwrap(),
        }),
    )?;

    fs::write(&output_file, content)
        .with_context(|| format!("Failed to write file: {}", output_file.display()))?;

    println!(
        "{} Created command: {}",
        "✓".green().bold(),
        output_file.display()
    );

    // Validate the generated file
    validate_generated(&output_file)?;

    Ok(())
}

/// Create a skill primitive
fn create_skill(args: &NewCommandArgs) -> Result<()> {
    let output_dir = PathBuf::from("primitives/v2/skills").join(&args.category);
    fs::create_dir_all(&output_dir)
        .with_context(|| format!("Failed to create directory: {}", output_dir.display()))?;

    let output_file = output_dir.join(format!("{}.md", args.name));

    if output_file.exists() {
        anyhow::bail!("Skill already exists: {}", output_file.display());
    }

    // Prepare template data
    let mut data = HashMap::new();
    data.insert("description", args.description.as_ref().unwrap().clone());
    data.insert("model", args.model.as_ref().unwrap().clone());
    data.insert("title", to_title_case(&args.name));
    data.insert("slug", args.name.clone());

    if let Some(tools) = &args.allowed_tools {
        data.insert("allowed_tools", tools.clone());
    }

    // Parse expertise if provided
    let expertise: Option<Vec<String>> = args
        .expertise
        .as_ref()
        .map(|e| e.split(',').map(|s| s.trim().to_string()).collect());

    // Render template
    let template = include_str!("../templates/skill.md.hbs");
    let mut hb = Handlebars::new();
    hb.register_template_string("skill", template)?;

    let content = hb.render(
        "skill",
        &json!({
            "description": data.get("description").unwrap(),
            "model": data.get("model").unwrap(),
            "allowed_tools": data.get("allowed_tools"),
            "expertise": expertise,
            "title": data.get("title").unwrap(),
            "slug": data.get("slug").unwrap(),
        }),
    )?;

    fs::write(&output_file, content)
        .with_context(|| format!("Failed to write file: {}", output_file.display()))?;

    println!(
        "{} Created skill: {}",
        "✓".green().bold(),
        output_file.display()
    );

    // Validate the generated file
    validate_generated(&output_file)?;

    Ok(())
}

/// Create a tool primitive
fn create_tool(args: &NewCommandArgs) -> Result<()> {
    let output_dir = PathBuf::from("primitives/v2/tools")
        .join(&args.category)
        .join(&args.name);

    fs::create_dir_all(&output_dir)
        .with_context(|| format!("Failed to create directory: {}", output_dir.display()))?;

    // Check if tool already exists
    if output_dir.join("tool.yaml").exists() {
        anyhow::bail!("Tool already exists: {}", output_dir.display());
    }

    // Prepare template data
    let tool_id = format!("{}/{}", args.category, args.name);
    let function_name = args.name.replace('-', "_");
    let package_name = args.name.clone();

    let mut hb = Handlebars::new();

    // Render tool.yaml
    let tool_yaml_template = include_str!("../templates/tool/tool.yaml.hbs");
    hb.register_template_string("tool_yaml", tool_yaml_template)?;
    let tool_yaml_content = hb.render(
        "tool_yaml",
        &json!({
            "tool_id": tool_id,
            "name": to_title_case(&args.name),
            "description": args.description.as_ref().unwrap(),
            "function_name": function_name,
            "package_name": package_name,
        }),
    )?;
    fs::write(output_dir.join("tool.yaml"), tool_yaml_content)?;

    // Render impl.py
    let impl_template = include_str!("../templates/tool/impl.py.hbs");
    hb.register_template_string("impl", impl_template)?;
    let impl_content = hb.render(
        "impl",
        &json!({
            "description": args.description.as_ref().unwrap(),
            "function_name": function_name,
        }),
    )?;
    fs::write(output_dir.join("impl.py"), impl_content)?;

    // Render pyproject.toml
    let pyproject_template = include_str!("../templates/tool/pyproject.toml.hbs");
    hb.register_template_string("pyproject", pyproject_template)?;
    let pyproject_content = hb.render(
        "pyproject",
        &json!({
            "package_name": package_name,
            "description": args.description.as_ref().unwrap(),
        }),
    )?;
    fs::write(output_dir.join("pyproject.toml"), pyproject_content)?;

    // Render README.md
    let readme_template = include_str!("../templates/tool/README.md.hbs");
    hb.register_template_string("readme", readme_template)?;
    let readme_content = hb.render(
        "readme",
        &json!({
            "name": to_title_case(&args.name),
            "description": args.description.as_ref().unwrap(),
            "category": args.category,
            "slug": args.name,
            "function_name": function_name,
        }),
    )?;
    fs::write(output_dir.join("README.md"), readme_content)?;

    println!(
        "{} Created tool: {}",
        "✓".green().bold(),
        output_dir.display()
    );
    println!("  {} tool.yaml", "→".blue());
    println!("  {} impl.py", "→".blue());
    println!("  {} pyproject.toml", "→".blue());
    println!("  {} README.md", "→".blue());

    // Validate the generated tool
    validate_generated(&output_dir)?;

    Ok(())
}

/// Validate a generated primitive
fn validate_generated(path: &Path) -> Result<()> {
    println!();
    println!("{} Validating generated primitive...", "→".blue());

    // Determine type from path
    let path_str = path.to_string_lossy();

    if path_str.contains("/commands/") {
        let content = fs::read_to_string(path)?;
        let (fm, _) = parse_frontmatter(&content, path)?;
        validators::validate_command_frontmatter(&fm)?;
        println!("{} Command frontmatter is valid", "✓".green());
    } else if path_str.contains("/skills/") {
        let content = fs::read_to_string(path)?;
        let (fm, _) = parse_frontmatter(&content, path)?;
        validators::validate_skill_frontmatter(&fm)?;
        println!("{} Skill frontmatter is valid", "✓".green());
    } else if path_str.contains("/tools/") {
        // For tools, check tool.yaml exists and is valid YAML
        let tool_yaml = path.join("tool.yaml");
        if !tool_yaml.exists() {
            anyhow::bail!("tool.yaml not found");
        }
        let content = fs::read_to_string(&tool_yaml)?;
        let _: serde_yaml::Value = serde_yaml::from_str(&content)?;
        println!("{} Tool specification is valid", "✓".green());
    }

    println!();
    println!("{} Primitive created successfully!", "✓".green().bold());

    Ok(())
}

/// Parse frontmatter from markdown content
fn parse_frontmatter(content: &str, path: &Path) -> Result<(String, String)> {
    let trimmed = content.trim_start();

    if !trimmed.starts_with("---") {
        anyhow::bail!(
            "No frontmatter found in {}. Expected file to start with '---'",
            path.display()
        );
    }

    let after_open = &trimmed[3..];
    let end_idx = after_open
        .find("\n---")
        .with_context(|| format!("Frontmatter not closed in {}", path.display()))?;

    let frontmatter = after_open[..end_idx].trim().to_string();
    let body = after_open[end_idx + 4..].trim().to_string();

    Ok((frontmatter, body))
}

/// Convert kebab-case to Title Case
fn to_title_case(s: &str) -> String {
    s.split('-')
        .map(|word| {
            let mut chars = word.chars();
            match chars.next() {
                None => String::new(),
                Some(first) => first.to_uppercase().chain(chars).collect(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate_name() {
        assert!(validate_name("test-command").is_ok());
        assert!(validate_name("test123").is_ok());
        assert!(validate_name("TestCommand").is_err());
        assert!(validate_name("test_command").is_err());
        assert!(validate_name("-test").is_err());
        assert!(validate_name("test-").is_err());
    }

    #[test]
    fn test_to_title_case() {
        assert_eq!(to_title_case("test-command"), "Test Command");
        assert_eq!(to_title_case("api-client"), "Api Client");
        assert_eq!(to_title_case("single"), "Single");
    }
}
