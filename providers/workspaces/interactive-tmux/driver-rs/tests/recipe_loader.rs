//! Recipe-directory loader tests (Plan B Task 2 + PR #247 Fix 3).
//!
//! Fixture `tests/fixtures/recipe-pr-reviewer/` is VENDORED verbatim from the
//! APSS crate `apss-v1-0005-agent-recipe`, from `examples/valid/pr-reviewer/`
//! at rev 4819b38745aaf8d2742d74479a9e728283e09271. It BUNDLES a skill
//! (`skills/code-review/`), so it now exercises the bundled-skill fail-fast
//! guard. The success-path mapping tests use `recipe-plain/` (a local fixture
//! with a container-relative skill ref and no bundled skills dir).
//!
//! Re-copy the vendored fixture if that rev's example changes.

use std::path::PathBuf;

use itmux::adapter::Agent;
use itmux::run::contract::AgentRunSpec;
use itmux::run::recipe_loader::{
    build_submit_text, load_execution_plan, resolve_skill_plugin_dirs, RecipeMapError,
};

fn fixtures_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures")
}

/// Vendored recipe that BUNDLES a skill (`skills/code-review/`).
fn bundled_fixture_dir() -> PathBuf {
    fixtures_root().join("recipe-pr-reviewer")
}

/// Local recipe with a container-relative skill ref and NO bundled skills dir.
fn plain_fixture_dir() -> PathBuf {
    fixtures_root().join("recipe-plain")
}

fn spec_for(dir: PathBuf, task: &str) -> AgentRunSpec {
    AgentRunSpec {
        recipe: dir,
        task: task.to_string(),
        input_artifacts: vec![],
        credentials: Default::default(),
        observability: vec![],
        limits: None,
    }
}

// --- start-arg mapping (plain fixture, container-relative skill) ------------

#[test]
fn loads_recipe_and_maps_default_agent_to_claude() {
    let plan = load_execution_plan(&spec_for(plain_fixture_dir(), "Review PR #42"))
        .expect("plain fixture loads");

    assert_eq!(plan.recipe_name, "plain-recipe");
    // default_agent = main, whose harness is claude.
    assert_eq!(plan.agent, Agent::Claude);
    // Only the default agent is launched (R5), never the codex subagent.
    assert_eq!(plan.start_agents(), vec![Agent::Claude]);
}

#[test]
fn maps_container_relative_skill_ref_in_listed_order() {
    let plan = load_execution_plan(&spec_for(plain_fixture_dir(), "Review PR #42"))
        .expect("plain fixture loads");

    // main.yaml declares `skills: [container-skill]`, which is NOT bundled on
    // the host, so it passes through verbatim as a container-relative path.
    assert_eq!(
        plan.claude_plugin_dirs,
        vec![PathBuf::from("container-skill")]
    );
}

#[test]
fn submit_text_prepends_resolved_system_and_ends_with_task() {
    let task = "Review PR #42";
    let plan =
        load_execution_plan(&spec_for(plain_fixture_dir(), task)).expect("plain fixture loads");

    // main.yaml has system_instructions.mode = append, so the resolved system
    // is SYSTEM.md + "\n\n" + the agent content; the submit text then prepends
    // that whole system prompt to the task.
    assert!(
        plan.submit_text
            .starts_with("Shared base instructions for the plain recipe."),
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
    let plan = load_execution_plan(&spec_for(plain_fixture_dir(), "Review PR #42"))
        .expect("plain fixture loads");

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

// --- Fix 3: bundled skill host-path guard ----------------------------------

#[test]
fn bundled_skill_is_rejected_pending_staging() {
    // The vendored pr-reviewer recipe bundles `skills/code-review/` on the host.
    // Passing that host path to `claude --plugin-dir` in-container would be
    // broken, so the loader fails fast (#249) instead.
    let err = load_execution_plan(&spec_for(bundled_fixture_dir(), "Review PR #42"))
        .expect_err("bundled skill must be rejected");
    match &err {
        RecipeMapError::BundledSkillStagingUnsupported { skill_ref, .. } => {
            assert_eq!(skill_ref, "code-review");
        }
        other => panic!("expected BundledSkillStagingUnsupported, got {other:?}"),
    }
    assert!(err.to_string().contains("#249"), "err: {err}");
}

#[test]
fn resolve_skill_plugin_dirs_passes_container_relative_and_rejects_bundled() {
    let recipe_dir = bundled_fixture_dir();

    // A container-relative ref (not bundled on the host) passes through verbatim.
    let ok = resolve_skill_plugin_dirs(&recipe_dir, &["external-skill".to_string()])
        .expect("container-relative ref resolves");
    assert_eq!(ok, vec![PathBuf::from("external-skill")]);

    // A bundled ref (skills/code-review/ exists on the host) is rejected.
    let err = resolve_skill_plugin_dirs(&recipe_dir, &["code-review".to_string()])
        .expect_err("bundled ref must be rejected");
    assert!(matches!(
        err,
        RecipeMapError::BundledSkillStagingUnsupported { .. }
    ));
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
fn missing_recipe_directory_is_an_error() {
    let spec = spec_for(PathBuf::from("/nonexistent/recipe/dir"), "x");
    assert!(load_execution_plan(&spec).is_err());
}
