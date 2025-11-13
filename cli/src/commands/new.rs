//! Scaffold new primitives with validation

use anyhow::{Context, Result};
use blake3;
use chrono::Utc;
use colored::Colorize;
use std::fs;
use std::path::{Path, PathBuf};

use crate::spec_version::SpecVersion;
use crate::templates::render::TemplateRenderer;
use crate::validators::{validate_primitive_with_layers, ValidationLayers};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PrimitiveType {
    Prompt,
    Tool,
    Hook,
}

impl PrimitiveType {
    pub fn parse(s: &str) -> Result<Self> {
        match s.to_lowercase().as_str() {
            "prompt" => Ok(PrimitiveType::Prompt),
            "tool" => Ok(PrimitiveType::Tool),
            "hook" => Ok(PrimitiveType::Hook),
            _ => anyhow::bail!("Unknown primitive type: {s}. Valid: prompt, tool, hook"),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PromptKind {
    Agent,
    Command,
    Skill,
    MetaPrompt,
}

impl PromptKind {
    pub fn parse(s: &str) -> Result<Self> {
        match s.to_lowercase().as_str() {
            "agent" => Ok(PromptKind::Agent),
            "command" => Ok(PromptKind::Command),
            "skill" => Ok(PromptKind::Skill),
            "meta-prompt" | "metaprompt" => Ok(PromptKind::MetaPrompt),
            _ => {
                anyhow::bail!("Unknown prompt kind: {s}. Valid: agent, command, skill, meta-prompt")
            }
        }
    }

    pub fn as_str(&self) -> &str {
        match self {
            PromptKind::Agent => "agent",
            PromptKind::Command => "command",
            PromptKind::Skill => "skill",
            PromptKind::MetaPrompt => "meta-prompt",
        }
    }

    pub fn subdir(&self) -> &str {
        match self {
            PromptKind::Agent => "agents",
            PromptKind::Command => "commands",
            PromptKind::Skill => "skills",
            PromptKind::MetaPrompt => "meta-prompts",
        }
    }
}

#[derive(Debug, Clone)]
pub struct NewPrimitiveArgs {
    pub prim_type: PrimitiveType,
    pub category: String,
    pub id: String,
    pub kind: Option<PromptKind>,
    pub spec_version: SpecVersion,
    pub experimental: bool,
}

/// Create a new primitive
pub fn new_primitive(args: NewPrimitiveArgs) -> Result<()> {
    // 1. Validate inputs
    validate_inputs(&args)?;

    // 2. Resolve output path
    let output_path = resolve_output_path(&args)?;

    // 3. Check for conflicts
    if output_path.exists() {
        anyhow::bail!(
            "Primitive already exists at {output_path:?}. Use a different ID or category."
        );
    }

    // 4. Create directory
    fs::create_dir_all(&output_path)
        .with_context(|| format!("Failed to create directory: {output_path:?}"))?;

    // 5. Create primitive based on type
    match args.prim_type {
        PrimitiveType::Prompt => create_prompt_primitive(&output_path, &args)?,
        PrimitiveType::Tool => create_tool_primitive(&output_path, &args)?,
        PrimitiveType::Hook => create_hook_primitive(&output_path, &args)?,
    }

    // 6. Run structural validation (skip full validation for experimental)
    if !args.experimental {
        let report = validate_primitive_with_layers(
            args.spec_version,
            &output_path,
            ValidationLayers::Structural,
        )?;

        if !report.is_valid() {
            anyhow::bail!("Created primitive failed validation: {:?}", report.errors);
        }
    }

    // 7. Print success message
    print_success_message(&output_path, &args)?;

    Ok(())
}

fn validate_inputs(args: &NewPrimitiveArgs) -> Result<()> {
    // Check kebab-case
    if !is_kebab_case(&args.category) {
        anyhow::bail!(
            "Category must be kebab-case (lowercase with hyphens): {}",
            args.category
        );
    }
    if !is_kebab_case(&args.id) {
        anyhow::bail!(
            "ID must be kebab-case (lowercase with hyphens): {}",
            args.id
        );
    }

    // Check kind required for prompts
    if args.prim_type == PrimitiveType::Prompt && args.kind.is_none() {
        anyhow::bail!("--kind required for prompts (agent|command|skill|meta-prompt)");
    }

    Ok(())
}

fn is_kebab_case(s: &str) -> bool {
    // Must be lowercase alphanumeric with hyphens, no leading/trailing hyphens, no double hyphens
    if s.is_empty() {
        return false;
    }
    let chars: Vec<char> = s.chars().collect();
    if chars[0] == '-' || chars[chars.len() - 1] == '-' {
        return false;
    }
    // Check for double hyphens
    if s.contains("--") {
        return false;
    }
    // Must start with lowercase letter
    if !chars[0].is_ascii_lowercase() {
        return false;
    }
    s.chars()
        .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
}

fn resolve_output_path(args: &NewPrimitiveArgs) -> Result<PathBuf> {
    let base = if args.experimental {
        PathBuf::from("primitives/experimental")
    } else {
        args.spec_version.resolve_primitives_path()
    };

    let path = match args.prim_type {
        PrimitiveType::Prompt => {
            let kind = args.kind.unwrap();
            base.join("prompts")
                .join(kind.subdir())
                .join(&args.category)
                .join(&args.id)
        }
        PrimitiveType::Tool => base.join("tools").join(&args.category).join(&args.id),
        PrimitiveType::Hook => base.join("hooks").join(&args.category).join(&args.id),
    };

    Ok(path)
}

fn create_prompt_primitive(path: &Path, args: &NewPrimitiveArgs) -> Result<()> {
    let kind = args.kind.unwrap();
    let renderer = TemplateRenderer::new()?;

    // 1. Render prompt content
    let prompt_data = serde_json::json!({
        "title": format_title(&args.id),
        "kind": kind.as_str(),
        "domain": &args.category,
    });

    let prompt_content = renderer.render_prompt_content(&prompt_data)?;
    let prompt_path = path.join("prompt.v1.md");
    fs::write(&prompt_path, &prompt_content)
        .with_context(|| format!("Failed to write prompt: {prompt_path:?}"))?;

    // 2. Calculate BLAKE3 hash
    let hash = blake3::hash(prompt_content.as_bytes()).to_hex().to_string();

    // 3. Render meta.yaml with versions array
    let meta_data = serde_json::json!({
        "id": &args.id,
        "category": &args.category,
        "summary": format!("TODO: Add a concise summary of this {}", kind.as_str()),
        "domain": &args.category,
    });

    let meta_content = match kind {
        PromptKind::Agent => renderer.render_agent_meta(&meta_data)?,
        PromptKind::Command => renderer.render_command_meta(&meta_data)?,
        PromptKind::Skill => renderer.render_skill_meta(&meta_data)?,
        PromptKind::MetaPrompt => renderer.render_meta_prompt_meta(&meta_data)?,
    };

    // Add versions array to meta.yaml
    let meta_with_versions = format!(
        "{}\nversions:\n  - version: 1\n    file: prompt.v1.md\n    hash: \"{}\"\n    status: draft\n    created: \"{}\"\ndefault_version: 1\n",
        meta_content.trim_end(),
        hash,
        Utc::now().to_rfc3339()
    );

    fs::write(path.join("meta.yaml"), meta_with_versions)
        .with_context(|| "Failed to write meta.yaml")?;

    Ok(())
}

fn create_tool_primitive(path: &Path, args: &NewPrimitiveArgs) -> Result<()> {
    let renderer = TemplateRenderer::new()?;

    // Render tool.meta.yaml
    let tool_data = serde_json::json!({
        "id": &args.id,
        "kind": "shell",  // Default kind
        "category": &args.category,
        "description": format!("TODO: Describe what {} does", &args.id),
    });

    let tool_meta = renderer.render_tool_meta(&tool_data)?;
    fs::write(path.join("tool.meta.yaml"), tool_meta)
        .with_context(|| "Failed to write tool.meta.yaml")?;

    // Create stub implementation files
    fs::write(
        path.join("impl.claude.yaml"),
        "# Claude MCP tool implementation\n# TODO: Add Claude-specific tool definition\n",
    )
    .with_context(|| "Failed to write impl.claude.yaml")?;

    fs::write(
        path.join("impl.openai.json"),
        "{\n  \"// TODO\": \"Add OpenAI function calling definition\"\n}\n",
    )
    .with_context(|| "Failed to write impl.openai.json")?;

    Ok(())
}

fn create_hook_primitive(path: &Path, args: &NewPrimitiveArgs) -> Result<()> {
    let renderer = TemplateRenderer::new()?;

    // Render hook.meta.yaml
    let hook_data = serde_json::json!({
        "id": &args.id,
        "kind": "safety",  // Default kind
        "category": &args.category,
        "event": "PreToolUse",  // Default event
        "summary": format!("TODO: Describe what {} does", &args.id),
        "middleware_type": "safety",
    });

    let hook_meta = renderer.render_hook_meta(&hook_data)?;
    fs::write(path.join("hook.meta.yaml"), hook_meta)
        .with_context(|| "Failed to write hook.meta.yaml")?;

    // Create Python middleware stub
    let middleware_data = serde_json::json!({
        "description": format!("Hook middleware for {}", &args.id),
        "event": "PreToolUse",
        "middleware_type": "safety",
    });

    let hook_py = renderer.render_middleware_python(&middleware_data)?;
    fs::write(path.join("hook.py"), hook_py).with_context(|| "Failed to write hook.py")?;

    // Make it executable
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = fs::metadata(path.join("hook.py"))?.permissions();
        perms.set_mode(0o755);
        fs::set_permissions(path.join("hook.py"), perms)?;
    }

    Ok(())
}

fn format_title(id: &str) -> String {
    id.split('-')
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

fn print_success_message(path: &Path, args: &NewPrimitiveArgs) -> Result<()> {
    let kind_str = if let Some(k) = args.kind {
        k.as_str().to_string()
    } else {
        match args.prim_type {
            PrimitiveType::Tool => "shell".to_string(),
            PrimitiveType::Hook => "safety".to_string(),
            _ => "".to_string(),
        }
    };

    println!(
        "{} {}",
        "✨ Created".green().bold(),
        format!(
            "{} {}: {}/{}",
            match args.prim_type {
                PrimitiveType::Prompt => "prompt",
                PrimitiveType::Tool => "tool",
                PrimitiveType::Hook => "hook",
            },
            kind_str,
            args.category,
            args.id
        )
        .cyan()
    );
    println!();
    println!("{}", "📁 Files created:".bold());
    println!("  {}", path.display().to_string().dimmed());

    // List files
    if let Ok(entries) = fs::read_dir(path) {
        for entry in entries.flatten() {
            if let Ok(file_name) = entry.file_name().into_string() {
                println!("  ├── {file_name}");
            }
        }
    }

    println!();
    println!("{}", "✅ Structural validation passed".green());
    println!();
    println!("{}", "🚀 Next steps:".bold());
    println!(
        "  1. {}",
        format!("Edit files in {}", path.display()).cyan()
    );
    println!(
        "  2. {}",
        format!("agentic validate {}", path.display()).cyan()
    );
    if args.prim_type == PrimitiveType::Prompt {
        println!(
            "  3. {}",
            format!("agentic version promote {}/{} 1", args.category, args.id).cyan()
        );
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_is_kebab_case() {
        assert!(is_kebab_case("hello"));
        assert!(is_kebab_case("hello-world"));
        assert!(is_kebab_case("hello-world-123"));
        assert!(is_kebab_case("test-1"));

        assert!(!is_kebab_case(""));
        assert!(!is_kebab_case("Hello"));
        assert!(!is_kebab_case("hello_world"));
        assert!(!is_kebab_case("hello world"));
        assert!(!is_kebab_case("-hello"));
        assert!(!is_kebab_case("hello-"));
        assert!(!is_kebab_case("hello--world"));
    }

    #[test]
    fn test_format_title() {
        assert_eq!(format_title("hello"), "Hello");
        assert_eq!(format_title("hello-world"), "Hello World");
        assert_eq!(format_title("test-agent-123"), "Test Agent 123");
    }

    #[test]
    fn test_primitive_type_parse() {
        assert_eq!(
            PrimitiveType::parse("prompt").unwrap(),
            PrimitiveType::Prompt
        );
        assert_eq!(PrimitiveType::parse("tool").unwrap(), PrimitiveType::Tool);
        assert_eq!(PrimitiveType::parse("hook").unwrap(), PrimitiveType::Hook);
        assert!(PrimitiveType::parse("invalid").is_err());
    }

    #[test]
    fn test_prompt_kind_parse() {
        assert_eq!(PromptKind::parse("agent").unwrap(), PromptKind::Agent);
        assert_eq!(PromptKind::parse("command").unwrap(), PromptKind::Command);
        assert_eq!(PromptKind::parse("skill").unwrap(), PromptKind::Skill);
        assert_eq!(
            PromptKind::parse("meta-prompt").unwrap(),
            PromptKind::MetaPrompt
        );
        assert!(PromptKind::parse("invalid").is_err());
    }

    #[test]
    fn test_resolve_output_path_prompt() {
        let args = NewPrimitiveArgs {
            prim_type: PrimitiveType::Prompt,
            category: "python".to_string(),
            id: "python-pro".to_string(),
            kind: Some(PromptKind::Agent),
            spec_version: SpecVersion::V1,
            experimental: false,
        };

        let path = resolve_output_path(&args).unwrap();
        assert_eq!(
            path,
            PathBuf::from("primitives/v1/prompts/agents/python/python-pro")
        );
    }

    #[test]
    fn test_resolve_output_path_tool() {
        let args = NewPrimitiveArgs {
            prim_type: PrimitiveType::Tool,
            category: "testing".to_string(),
            id: "run-tests".to_string(),
            kind: None,
            spec_version: SpecVersion::V1,
            experimental: false,
        };

        let path = resolve_output_path(&args).unwrap();
        assert_eq!(path, PathBuf::from("primitives/v1/tools/testing/run-tests"));
    }

    #[test]
    fn test_resolve_output_path_experimental() {
        let args = NewPrimitiveArgs {
            prim_type: PrimitiveType::Prompt,
            category: "test".to_string(),
            id: "test-agent".to_string(),
            kind: Some(PromptKind::Agent),
            spec_version: SpecVersion::V1,
            experimental: true,
        };

        let path = resolve_output_path(&args).unwrap();
        assert!(path.starts_with("primitives/experimental"));
    }

    #[test]
    fn test_validate_inputs_kebab_case() {
        let args = NewPrimitiveArgs {
            prim_type: PrimitiveType::Prompt,
            category: "InvalidCategory".to_string(),
            id: "test".to_string(),
            kind: Some(PromptKind::Agent),
            spec_version: SpecVersion::V1,
            experimental: false,
        };

        let result = validate_inputs(&args);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("kebab-case"));
    }

    #[test]
    fn test_validate_inputs_kind_required() {
        let args = NewPrimitiveArgs {
            prim_type: PrimitiveType::Prompt,
            category: "test".to_string(),
            id: "test".to_string(),
            kind: None,
            spec_version: SpecVersion::V1,
            experimental: false,
        };

        let result = validate_inputs(&args);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("--kind required"));
    }

    #[test]
    fn test_create_prompt_primitive() {
        let temp_dir = TempDir::new().unwrap();
        let path = temp_dir.path().join("test-agent");
        fs::create_dir_all(&path).unwrap();

        let args = NewPrimitiveArgs {
            prim_type: PrimitiveType::Prompt,
            category: "testing".to_string(),
            id: "test-agent".to_string(),
            kind: Some(PromptKind::Agent),
            spec_version: SpecVersion::V1,
            experimental: false,
        };

        let result = create_prompt_primitive(&path, &args);
        assert!(result.is_ok());

        // Check files exist
        assert!(path.join("prompt.v1.md").exists());
        assert!(path.join("meta.yaml").exists());

        // Check meta.yaml has versions
        let meta_content = fs::read_to_string(path.join("meta.yaml")).unwrap();
        assert!(meta_content.contains("versions:"));
        assert!(meta_content.contains("version: 1"));
        assert!(meta_content.contains("file: prompt.v1.md"));
        assert!(meta_content.contains("hash:"));
        assert!(meta_content.contains("status: draft"));
    }

    #[test]
    fn test_create_tool_primitive() {
        let temp_dir = TempDir::new().unwrap();
        let path = temp_dir.path().join("test-tool");
        fs::create_dir_all(&path).unwrap();

        let args = NewPrimitiveArgs {
            prim_type: PrimitiveType::Tool,
            category: "testing".to_string(),
            id: "test-tool".to_string(),
            kind: None,
            spec_version: SpecVersion::V1,
            experimental: false,
        };

        let result = create_tool_primitive(&path, &args);
        assert!(result.is_ok());

        // Check files exist
        assert!(path.join("tool.meta.yaml").exists());
        assert!(path.join("impl.claude.yaml").exists());
        assert!(path.join("impl.openai.json").exists());
    }

    #[test]
    fn test_create_hook_primitive() {
        let temp_dir = TempDir::new().unwrap();
        let path = temp_dir.path().join("test-hook");
        fs::create_dir_all(&path).unwrap();

        let args = NewPrimitiveArgs {
            prim_type: PrimitiveType::Hook,
            category: "testing".to_string(),
            id: "test-hook".to_string(),
            kind: None,
            spec_version: SpecVersion::V1,
            experimental: false,
        };

        let result = create_hook_primitive(&path, &args);
        assert!(result.is_ok());

        // Check files exist
        assert!(path.join("hook.meta.yaml").exists());
        assert!(path.join("hook.py").exists());
    }

    #[test]
    fn test_new_primitive_detects_conflict() {
        let temp_dir = TempDir::new().unwrap();

        // Create the structure
        let base = temp_dir.path();
        fs::create_dir_all(base.join("primitives/v1/prompts/agents/test")).unwrap();

        // Change to temp dir for relative path resolution
        let original_dir = std::env::current_dir().unwrap();
        std::env::set_current_dir(&base).unwrap();

        let args = NewPrimitiveArgs {
            prim_type: PrimitiveType::Prompt,
            category: "test".to_string(),
            id: "test-agent".to_string(),
            kind: Some(PromptKind::Agent),
            spec_version: SpecVersion::V1,
            experimental: true, // Use experimental to skip full validation
        };

        // Create once
        new_primitive(args.clone()).unwrap();

        // Try to create again - should fail
        let result = new_primitive(args);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("already exists"));

        // Restore original directory
        std::env::set_current_dir(&original_dir).unwrap();
    }
}
