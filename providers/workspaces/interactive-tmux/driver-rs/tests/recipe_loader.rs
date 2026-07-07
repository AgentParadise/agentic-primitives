//! Recipe-directory loader tests (Plan B Task 2).
//!
//! Fixture `tests/fixtures/recipe-pr-reviewer/` is VENDORED verbatim from the
//! APSS crate `apss-v1-0005-agent-recipe`, from
//! `examples/valid/pr-reviewer/` at rev
//! 4819b38745aaf8d2742d74479a9e728283e09271 (the same rev the git dependency
//! in Cargo.toml is pinned to). Re-copy it if that rev's example changes.

use std::path::PathBuf;

use itmux::adapter::Agent;
use itmux::run::contract::AgentRunSpec;
use itmux::run::recipe_loader::{
    build_submit_text, load_execution_plan, resolve_skill_plugin_dirs,
};

fn fixture_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/recipe-pr-reviewer")
}

fn spec_for_fixture(task: &str) -> AgentRunSpec {
    AgentRunSpec {
        recipe: fixture_dir(),
        task: task.to_string(),
        input_artifacts: vec![],
        credentials: Default::default(),
        observability: vec![],
        limits: None,
    }
}

// --- start-arg mapping -----------------------------------------------------

#[test]
fn loads_vendored_recipe_and_maps_default_agent_to_claude() {
    let plan = load_execution_plan(&spec_for_fixture("Review PR #42")).expect("fixture loads");

    assert_eq!(plan.recipe_name, "pr-reviewer");
    // default_agent = main, whose harness is claude.
    assert_eq!(plan.agent, Agent::Claude);
    // Only the default agent is launched (R5), never the codex subagent.
    assert_eq!(plan.start_agents(), vec![Agent::Claude]);
}

#[test]
fn maps_skills_to_plugin_dirs_in_listed_order() {
    let plan = load_execution_plan(&spec_for_fixture("Review PR #42")).expect("fixture loads");

    // main.yaml declares `skills: [code-review]`, and skills/code-review/
    // exists in the recipe, so it resolves to that bundled directory path.
    assert_eq!(
        plan.claude_plugin_dirs,
        vec![fixture_dir().join("skills").join("code-review")]
    );
}

#[test]
fn submit_text_prepends_resolved_system_and_ends_with_task() {
    let task = "Review PR #42";
    let plan = load_execution_plan(&spec_for_fixture(task)).expect("fixture loads");

    // main.yaml has system_instructions.mode = append, so the resolved system
    // is SYSTEM.md + "\n\n" + the agent content; the submit text then prepends
    // that whole system prompt to the task.
    assert!(
        plan.submit_text
            .starts_with("Shared base instructions for the pr-reviewer recipe."),
        "submit text should start with SYSTEM.md base, got:\n{}",
        plan.submit_text
    );
    assert!(
        plan.submit_text
            .contains("Focus exclusively on correctness and security issues."),
        "submit text should carry the agent's appended system content, got:\n{}",
        plan.submit_text
    );
    assert!(
        plan.submit_text.ends_with(task),
        "submit text should end with the task, got:\n{}",
        plan.submit_text
    );
}

// --- R5: subagents validated-only, not executed ----------------------------

#[test]
fn subagents_are_present_but_not_mapped_to_execution() {
    let plan = load_execution_plan(&spec_for_fixture("Review PR #42")).expect("fixture loads");

    // The recipe's default agent declares the `reviewer` subagent (a codex
    // agent). It is validated and surfaced as metadata...
    assert_eq!(plan.subagents, vec!["reviewer".to_string()]);
    // ...but v1 executes ONLY the default agent: the codex subagent is never
    // added to the set of agents itmux starts.
    assert_eq!(plan.start_agents(), vec![Agent::Claude]);
    assert!(
        !plan.start_agents().contains(&Agent::Codex),
        "subagent harness (codex) must not be launched in v1"
    );
}

// --- unit-level mapping helpers --------------------------------------------

#[test]
fn build_submit_text_append_semantics() {
    assert_eq!(
        build_submit_text(Some("You are a reviewer."), "Review PR #42"),
        "You are a reviewer.\n\nReview PR #42"
    );
}

#[test]
fn build_submit_text_without_system_is_task_only() {
    assert_eq!(build_submit_text(None, "Review PR #42"), "Review PR #42");
    assert_eq!(
        build_submit_text(Some(""), "Review PR #42"),
        "Review PR #42"
    );
}

#[test]
fn resolve_skill_plugin_dirs_falls_back_to_ref_when_not_bundled() {
    let recipe_dir = fixture_dir();
    let resolved = resolve_skill_plugin_dirs(
        &recipe_dir,
        &["code-review".to_string(), "external-skill".to_string()],
    );
    assert_eq!(
        resolved,
        vec![
            // bundled: resolves to the on-disk directory
            recipe_dir.join("skills").join("code-review"),
            // not bundled: used verbatim as a path
            PathBuf::from("external-skill"),
        ]
    );
}

#[test]
fn missing_recipe_directory_is_an_error() {
    let spec = AgentRunSpec {
        recipe: PathBuf::from("/nonexistent/recipe/dir"),
        task: "x".to_string(),
        input_artifacts: vec![],
        credentials: Default::default(),
        observability: vec![],
        limits: None,
    };
    assert!(load_execution_plan(&spec).is_err());
}
