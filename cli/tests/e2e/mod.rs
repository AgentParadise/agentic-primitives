use assert_cmd::Command;
use std::fs;
use std::path::{Path, PathBuf};
use tempfile::TempDir;

/// Test helper: Setup test repository with primitives.config.yaml
pub fn setup_test_repo() -> TempDir {
    let temp_dir = TempDir::new().unwrap();

    // Create directory structure
    fs::create_dir_all(temp_dir.path().join("primitives/v1/prompts/agents")).unwrap();
    fs::create_dir_all(temp_dir.path().join("primitives/v1/prompts/commands")).unwrap();
    fs::create_dir_all(temp_dir.path().join("primitives/v1/prompts/skills")).unwrap();
    fs::create_dir_all(temp_dir.path().join("primitives/v1/tools")).unwrap();
    fs::create_dir_all(temp_dir.path().join("primitives/v1/hooks")).unwrap();
    fs::create_dir_all(temp_dir.path().join("specs/v1")).unwrap();

    // Copy schemas from the project root
    let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap();
    let project_root = Path::new(&manifest_dir).parent().unwrap();
    let schema_src = project_root.join("specs/v1");

    if schema_src.exists() {
        for entry in fs::read_dir(schema_src).unwrap() {
            let entry = entry.unwrap();
            let dest = temp_dir.path().join("specs/v1").join(entry.file_name());
            fs::copy(entry.path(), dest).unwrap();
        }
    }

    // Create primitives.config.yaml
    let config_content = r#"version: "1.0"
spec_version: "v1"

paths:
  specs: "specs/v1"
  primitives: "primitives/v1"
  experimental: "primitives/experimental"
  providers: "providers"
  cli: "cli"
  docs: "docs"

validation:
  structural: true
  schema: true
  semantic: true
  strict: false
  hash_algorithm: "blake3"
  verify_hashes: false

versioning:
  default_status: "draft"

naming:
  id_case: "kebab-case"
  id_pattern: "^[a-z0-9]+(-[a-z0-9]+)*$"
  max_id_length: 64
"#;

    fs::write(
        temp_dir.path().join("primitives.config.yaml"),
        config_content,
    )
    .unwrap();

    temp_dir
}

/// Test helper: Run CLI command
pub fn run_cli_command(args: &[&str], working_dir: Option<&Path>) -> assert_cmd::assert::Assert {
    let mut cmd = Command::cargo_bin("agentic-p").unwrap();

    if let Some(dir) = working_dir {
        cmd.current_dir(dir);
    }

    cmd.args(args).assert()
}

/// Test helper: Assert primitive exists with correct structure
pub fn assert_primitive_exists(
    repo_path: &Path,
    prim_type: &str,
    category: &str,
    id: &str,
) -> PathBuf {
    let prim_path = repo_path
        .join("primitives/v1")
        .join(prim_type)
        .join(category)
        .join(id);

    assert!(
        prim_path.exists(),
        "Primitive directory should exist: {}",
        prim_path.display()
    );

    // Check for metadata file
    let meta_patterns = match prim_type {
        "prompts" => vec![format!("{}.yaml", id), "meta.yaml".to_string()],
        "tools" => vec![format!("{}.tool.yaml", id), "tool.meta.yaml".to_string()],
        "hooks" => vec![format!("{}.hook.yaml", id), "hook.meta.yaml".to_string()],
        _ => vec![],
    };

    let has_meta = meta_patterns
        .iter()
        .any(|pattern| prim_path.join(pattern).exists());

    assert!(has_meta, "Primitive should have metadata file");

    prim_path
}

/// Test helper: Assert build output exists
pub fn assert_build_output(repo_path: &Path, provider: &str) -> PathBuf {
    let build_path = repo_path.join("build").join(provider);
    assert!(
        build_path.exists(),
        "Build directory should exist: {}",
        build_path.display()
    );
    build_path
}

/// Test helper: Create test primitive manually
pub fn create_test_primitive(
    repo_path: &Path,
    prim_type: &str,
    category: &str,
    id: &str,
    content: &str,
) {
    let prim_path = repo_path
        .join("primitives/v1")
        .join(prim_type)
        .join(category)
        .join(id);

    fs::create_dir_all(&prim_path).unwrap();

    // Create metadata based on type
    match prim_type {
        "prompts" => {
            // Extract the leaf category (last segment of path)
            let leaf_category = category.split('/').next_back().unwrap_or(category);
            let meta = format!(
                r#"id: {id}
kind: agent
category: {leaf_category}
summary: Test primitive for E2E tests
model_ref: claude/sonnet
version: 1
status: active
"#
            );
            fs::write(prim_path.join(format!("{id}.yaml")), meta).unwrap();
            fs::write(prim_path.join(format!("{id}.v1.md")), content).unwrap();
        }
        "tools" => {
            let leaf_category = category.split('/').next_back().unwrap_or(category);
            let meta = format!(
                r#"id: {}
kind: {}
category: {}
description: Test tool for E2E tests
args: []
"#,
                id, "shell", leaf_category
            );
            fs::write(prim_path.join(format!("{id}.tool.yaml")), meta).unwrap();
        }
        "hooks" => {
            let leaf_category = category.split('/').next_back().unwrap_or(category);
            let meta = format!(
                r#"id: {id}
kind: hook
category: {leaf_category}
event: PreToolUse
summary: Test hook for E2E tests
execution:
  strategy: pipeline
"#
            );
            fs::write(prim_path.join(format!("{id}.hook.yaml")), meta).unwrap();
        }
        _ => {}
    }
}
