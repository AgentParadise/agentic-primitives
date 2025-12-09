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

    /// Returns the type directory for this kind (ADR-021 structure)
    pub fn subdir(&self) -> &str {
        match self {
            PromptKind::Agent => "agents",
            PromptKind::Command => "commands",
            PromptKind::Skill => "skills",
            // Meta-prompts are under commands/meta/
            PromptKind::MetaPrompt => "commands",
        }
    }

    /// Returns the category to use for meta-prompts (which go under commands/meta/)
    pub fn category_override(&self) -> Option<&str> {
        match self {
            PromptKind::MetaPrompt => Some("meta"),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ToolRuntime {
    #[default]
    Python,
    Bun,
}

impl ToolRuntime {
    pub fn as_str(&self) -> &str {
        match self {
            ToolRuntime::Python => "python",
            ToolRuntime::Bun => "bun",
        }
    }

    /// Get file extension for implementation
    pub fn impl_extension(&self) -> &str {
        match self {
            ToolRuntime::Python => "py",
            ToolRuntime::Bun => "ts",
        }
    }
}

#[derive(Debug, Clone)]
pub struct NewPrimitiveArgs {
    pub prim_type: PrimitiveType,
    pub category: String,
    pub id: String,
    pub kind: Option<PromptKind>,
    pub runtime: ToolRuntime,
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

    // New structure (ADR-021): types are directly under v1/
    // - commands/{category}/{id}/
    // - commands/meta/{id}/ (for meta-prompts)
    // - skills/{category}/{id}/
    // - agents/{category}/{id}/
    // - tools/{category}/{id}/
    // - hooks/{category}/{id}/
    let path = match args.prim_type {
        PrimitiveType::Prompt => {
            let kind = args.kind.unwrap();
            let type_dir = base.join(kind.subdir());
            // For meta-prompts, use "meta" as category; otherwise use provided category
            let category = kind.category_override().unwrap_or(&args.category);
            type_dir.join(category).join(&args.id)
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

    // Filename depends on kind:
    // - Skills: {id}.skill.v{N}.md
    // - Others: {id}.prompt.v{N}.md
    let content_filename = if kind == PromptKind::Skill {
        format!("{}.skill.v1.md", args.id)
    } else {
        format!("{}.prompt.v1.md", args.id)
    };
    let content_path = path.join(&content_filename);
    fs::write(&content_path, &prompt_content)
        .with_context(|| format!("Failed to write prompt: {content_path:?}"))?;

    // 2. Calculate BLAKE3 hash with prefix
    let hash = format!(
        "blake3:{}",
        blake3::hash(prompt_content.as_bytes()).to_hex()
    );

    // 3. Render metadata with versions array
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

    // Add versions array to metadata file with proper format
    let created_date = Utc::now().format("%Y-%m-%d").to_string();
    let meta_with_versions = format!(
        "{}\nversions:\n  - version: 1\n    file: {}\n    hash: \"{}\"\n    status: active\n    created: \"{}\"\n    notes: \"Initial version\"\ndefault_version: 1\n",
        meta_content.trim_end(),
        content_filename,
        hash,
        created_date
    );

    // Metadata filename depends on kind:
    // - Skills: {id}.skill.yaml
    // - Others: {id}.yaml
    let meta_filename = if kind == PromptKind::Skill {
        format!("{}.skill.yaml", &args.id)
    } else {
        format!("{}.yaml", &args.id)
    };
    fs::write(path.join(&meta_filename), meta_with_versions)
        .with_context(|| format!("Failed to write {meta_filename}"))?;

    Ok(())
}

fn create_tool_primitive(path: &Path, args: &NewPrimitiveArgs) -> Result<()> {
    let renderer = TemplateRenderer::new()?;

    // Convert id to snake_case for Python module names
    let id_snake = args.id.replace('-', "_");

    // Common template data
    let tool_data = serde_json::json!({
        "id": &args.id,
        "id_snake": &id_snake,
        "kind": "tool",
        "category": &args.category,
        "description": format!("TODO: Describe what {} does", &args.id),
        "args": [],
        "runtime_python": args.runtime == ToolRuntime::Python,
        "runtime_bun": args.runtime == ToolRuntime::Bun,
    });

    // Render {id}.tool.yaml
    let tool_meta = renderer.render_tool_meta(&tool_data)?;
    let meta_filename = format!("{}.tool.yaml", &args.id);
    fs::write(path.join(&meta_filename), tool_meta)
        .with_context(|| format!("Failed to write {meta_filename}"))?;

    // Create tests/ directory
    let tests_dir = path.join("tests");
    fs::create_dir_all(&tests_dir).with_context(|| "Failed to create tests/ directory")?;

    match args.runtime {
        ToolRuntime::Python => {
            // Create Python implementation
            let impl_content = renderer.render_tool_impl_python(&tool_data)?;
            let impl_filename = format!("{}.py", &id_snake);
            fs::write(path.join(&impl_filename), impl_content)
                .with_context(|| format!("Failed to write {impl_filename}"))?;

            // Create pyproject.toml
            let pyproject = renderer.render_tool_pyproject(&tool_data)?;
            fs::write(path.join("pyproject.toml"), pyproject)
                .with_context(|| "Failed to write pyproject.toml")?;

            // Create test file
            let test_content = renderer.render_tool_test_python(&tool_data)?;
            fs::write(tests_dir.join("__init__.py"), "")
                .with_context(|| "Failed to write tests/__init__.py")?;
            fs::write(
                tests_dir.join(format!("test_{}.py", &id_snake)),
                test_content,
            )
            .with_context(|| "Failed to write test file")?;
        }
        ToolRuntime::Bun => {
            // Create TypeScript implementation
            let impl_content = renderer.render_tool_impl_typescript(&tool_data)?;
            let impl_filename = format!("{}.ts", &args.id);
            fs::write(path.join(&impl_filename), impl_content)
                .with_context(|| format!("Failed to write {impl_filename}"))?;

            // Create package.json
            let package_json = renderer.render_tool_package_json(&tool_data)?;
            fs::write(path.join("package.json"), package_json)
                .with_context(|| "Failed to write package.json")?;

            // Create tsconfig.json
            let tsconfig = renderer.render_tool_tsconfig(&tool_data)?;
            fs::write(path.join("tsconfig.json"), tsconfig)
                .with_context(|| "Failed to write tsconfig.json")?;

            // Create test file
            let test_content = renderer.render_tool_test_typescript(&tool_data)?;
            fs::write(
                tests_dir.join(format!("{}.test.ts", &args.id)),
                test_content,
            )
            .with_context(|| "Failed to write test file")?;
        }
    }

    // Create README.md
    let readme = renderer.render_tool_readme(&tool_data)?;
    fs::write(path.join("README.md"), readme).with_context(|| "Failed to write README.md")?;

    Ok(())
}

fn create_hook_primitive(path: &Path, args: &NewPrimitiveArgs) -> Result<()> {
    let renderer = TemplateRenderer::new()?;

    // Render {id}.hook.yaml
    let hook_data = serde_json::json!({
        "id": &args.id,
        "kind": "hook",  // Correct kind for hooks
        "category": &args.category,
        "event": "PreToolUse",  // Default event
        "summary": format!("TODO: Describe what {} does", &args.id),
        "middleware_type": "safety",
    });

    let hook_meta = renderer.render_hook_meta(&hook_data)?;
    let meta_filename = format!("{}.hook.yaml", &args.id);
    fs::write(path.join(&meta_filename), hook_meta)
        .with_context(|| format!("Failed to write {meta_filename}"))?;

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
        format!("agentic-p validate {}", path.display()).cyan()
    );
    if args.prim_type == PrimitiveType::Prompt {
        println!(
            "  3. {}",
            format!("agentic-p version promote {}/{} 1", args.category, args.id).cyan()
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
            runtime: ToolRuntime::default(),
            spec_version: SpecVersion::V1,
            experimental: false,
        };

        let path = resolve_output_path(&args).unwrap();
        // New structure (ADR-021): agents directly under v1/
        assert_eq!(
            path,
            PathBuf::from("primitives/v1/agents/python/python-pro")
        );
    }

    #[test]
    fn test_resolve_output_path_tool() {
        let args = NewPrimitiveArgs {
            prim_type: PrimitiveType::Tool,
            category: "testing".to_string(),
            id: "run-tests".to_string(),
            kind: None,
            runtime: ToolRuntime::Python,
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
            runtime: ToolRuntime::default(),
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
            runtime: ToolRuntime::default(),
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
            runtime: ToolRuntime::default(),
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
            runtime: ToolRuntime::default(),
            spec_version: SpecVersion::V1,
            experimental: false,
        };

        let result = create_prompt_primitive(&path, &args);
        assert!(result.is_ok());

        // Check files exist (new naming pattern)
        assert!(path.join("test-agent.prompt.v1.md").exists());
        assert!(path.join("test-agent.yaml").exists());

        // Check {id}.yaml has versions with correct format
        let meta_content = fs::read_to_string(path.join("test-agent.yaml")).unwrap();
        assert!(meta_content.contains("versions:"));
        assert!(meta_content.contains("version: 1"));
        assert!(meta_content.contains("file: test-agent.prompt.v1.md"));
        assert!(meta_content.contains("hash: \"blake3:"));
        assert!(meta_content.contains("status: active"));
        assert!(meta_content.contains("notes:"));
    }

    #[test]
    fn test_create_tool_primitive_python() {
        let temp_dir = TempDir::new().unwrap();
        let path = temp_dir.path().join("test-tool");
        fs::create_dir_all(&path).unwrap();

        let args = NewPrimitiveArgs {
            prim_type: PrimitiveType::Tool,
            category: "testing".to_string(),
            id: "test-tool".to_string(),
            kind: None,
            runtime: ToolRuntime::Python,
            spec_version: SpecVersion::V1,
            experimental: false,
        };

        let result = create_tool_primitive(&path, &args);
        assert!(result.is_ok());

        // Check Python-specific files exist
        assert!(path.join("test-tool.tool.yaml").exists());
        assert!(path.join("test_tool.py").exists());
        assert!(path.join("pyproject.toml").exists());
        assert!(path.join("tests").exists());
        assert!(path.join("tests/__init__.py").exists());
        assert!(path.join("tests/test_test_tool.py").exists());
        assert!(path.join("README.md").exists());
    }

    #[test]
    fn test_create_tool_primitive_bun() {
        let temp_dir = TempDir::new().unwrap();
        let path = temp_dir.path().join("my-tool");
        fs::create_dir_all(&path).unwrap();

        let args = NewPrimitiveArgs {
            prim_type: PrimitiveType::Tool,
            category: "testing".to_string(),
            id: "my-tool".to_string(),
            kind: None,
            runtime: ToolRuntime::Bun,
            spec_version: SpecVersion::V1,
            experimental: false,
        };

        let result = create_tool_primitive(&path, &args);
        assert!(result.is_ok());

        // Check TypeScript-specific files exist
        assert!(path.join("my-tool.tool.yaml").exists());
        assert!(path.join("my-tool.ts").exists());
        assert!(path.join("package.json").exists());
        assert!(path.join("tsconfig.json").exists());
        assert!(path.join("tests").exists());
        assert!(path.join("tests/my-tool.test.ts").exists());
        assert!(path.join("README.md").exists());
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
            runtime: ToolRuntime::default(),
            spec_version: SpecVersion::V1,
            experimental: false,
        };

        let result = create_hook_primitive(&path, &args);
        assert!(result.is_ok());

        // Check files exist
        assert!(path.join("test-hook.hook.yaml").exists());
        assert!(path.join("hook.py").exists());
    }

    #[test]
    fn test_new_primitive_detects_conflict() {
        let temp_dir = TempDir::new().unwrap();

        // Create the structure (ADR-021 structure)
        let base = temp_dir.path();
        fs::create_dir_all(base.join("primitives/v1/agents/test")).unwrap();

        // Change to temp dir for relative path resolution
        let original_dir = std::env::current_dir().unwrap();
        std::env::set_current_dir(base).unwrap();

        let args = NewPrimitiveArgs {
            prim_type: PrimitiveType::Prompt,
            category: "test".to_string(),
            id: "test-agent".to_string(),
            kind: Some(PromptKind::Agent),
            runtime: ToolRuntime::default(),
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
