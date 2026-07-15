//! Recipe-directory loader: turn an [`AgentRunSpec`] (whose `recipe` is a
//! directory path, per contract revision R4) into the concrete `itmux` start
//! arguments and submit text needed to launch the run.
//!
//! The recipe SHAPE is owned by the APSS crate `apss-v1-0005-agent-recipe`
//! (re-exported here as `agent_recipe`): a recipe that validates against that
//! crate is a recipe that runs. This module depends on the crate's
//! [`load_recipe_dir`]/[`Recipe`]/[`AgentManifest`]/[`resolved_system`] rather
//! than re-implementing the shape (plan revision R2).
//!
//! ## What this maps
//!
//! For the recipe's `default_agent` (and ONLY that agent - see R5 below) it
//! produces:
//!
//! * `agent` - the `itmux` harness ([`AgentKind::Claude`] -> [`Agent::Claude`],
//!   [`AgentKind::Codex`] -> [`Agent::Codex`]). `itmux start` receives
//!   `agents = [that one agent]`.
//! * `claude_plugin_dirs` - the agent's `skills`, resolved to plugin-dir paths
//!   in listed order (R3, see [`resolve_skill_plugin_dirs`]). Only meaningful
//!   for claude; empty for codex.
//! * `submit_text` - the resolved system prompt (per `system_instructions`
//!   append/replace against `SYSTEM.md`) prepended to the task (see
//!   [`build_submit_text`]).
//!
//! ## R5 - subagents are validated-only in v1
//!
//! `load_recipe_dir` parses and validates the whole recipe, INCLUDING the
//! `default_agent`'s `subagents` references. But `itmux run` in v1 executes
//! ONLY the `default_agent`; subagents are NOT spawned. This module surfaces
//! the subagent names as metadata ([`RecipeExecutionPlan::subagents`]) but
//! [`RecipeExecutionPlan::start_agents`] returns just the one default agent.
//! Multi-agent / subagent execution is a v0.2 follow-up.
//!
//! ## Host paths vs container paths
//!
//! The skill plugin-dir paths this loader resolves are HOST paths (they point
//! inside the recipe directory on disk). Staging them into the container and
//! rewriting them to container-side `--plugin-dir` paths is the orchestrator's
//! job (Task 3), not the loader's. The loader's contract is purely
//! recipe-directory -> intended start arguments.

use std::error::Error;
use std::fmt;
use std::path::{Path, PathBuf};

use agent_recipe::{
    load_recipe_dir, resolved_system, AgentKind, AgentManifest, Recipe, RecipeLoadError,
};

use crate::adapter::Agent;
use crate::run::contract::AgentRunSpec;

/// A fully resolved plan for launching a recipe's `default_agent` via `itmux`.
///
/// This is the loader's output: the harness-neutral recipe shape (from the
/// APSS crate) mapped onto the concrete `itmux` launch inputs.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RecipeExecutionPlan {
    /// The recipe's `name` (from `recipe.yaml`), for logging / run identity.
    pub recipe_name: String,
    /// The `itmux` harness that runs the `default_agent`.
    pub agent: Agent,
    /// The default agent's `skills`, resolved to plugin-dir paths in listed
    /// order (R3). Empty for a codex default agent. Host paths - the
    /// orchestrator stages these into the container (Task 3).
    pub claude_plugin_dirs: Vec<PathBuf>,
    /// The text to submit to the agent: the resolved system prompt prepended
    /// to the task (see [`build_submit_text`]).
    pub submit_text: String,
    /// The default agent's declared `subagents`, VALIDATED but NOT executed in
    /// v1 (R5). Present here purely as metadata; see [`Self::start_agents`].
    pub subagents: Vec<String>,
}

impl RecipeExecutionPlan {
    /// The agents `itmux start` should launch: exactly the `default_agent`.
    ///
    /// R5 made explicit and testable: even when the recipe declares
    /// `subagents`, v1 launches ONLY the default agent. Subagents never appear
    /// here.
    pub fn start_agents(&self) -> Vec<Agent> {
        vec![self.agent]
    }
}

/// Failure modes of [`load_execution_plan`].
#[derive(Debug)]
pub enum RecipeMapError {
    /// The recipe directory failed to load/validate (missing marker,
    /// malformed YAML, unresolved `default_agent`, duplicate agent, I/O).
    Load(RecipeLoadError),
    /// The recipe loaded, but its `default_agent` did not resolve to a parsed
    /// agent. `load_recipe_dir` normally rejects this before returning, so
    /// this indicates an inconsistent [`Recipe`] value.
    DefaultAgentUnresolved {
        /// The `default_agent` name from `recipe.yaml`.
        default_agent: String,
    },
    /// A skill ref resolved to a BUNDLED skill directory that exists on the
    /// HOST (`<recipe>/skills/<ref>/`). Passing that host path to
    /// `claude --plugin-dir` inside the container would reference a path that
    /// does not exist there. Staging bundled skills into the container
    /// (tar-over-docker-exec) is not implemented yet (#249); fail fast instead
    /// of silently producing a broken `--plugin-dir`.
    BundledSkillStagingUnsupported {
        /// The skill ref from the agent manifest.
        skill_ref: String,
        /// The resolved host path to the bundled skill directory.
        host_path: PathBuf,
    },
}

impl fmt::Display for RecipeMapError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Load(source) => write!(f, "failed to load recipe: {source}"),
            Self::DefaultAgentUnresolved { default_agent } => write!(
                f,
                "recipe default_agent '{default_agent}' did not resolve to a parsed agent"
            ),
            Self::BundledSkillStagingUnsupported {
                skill_ref,
                host_path,
            } => write!(
                f,
                "bundled skill '{skill_ref}' resolves to a host path ({}) that does not exist \
                 in the container; bundled skill staging is not yet supported (#249) - use a \
                 container-relative skill ref instead",
                host_path.display()
            ),
        }
    }
}

impl Error for RecipeMapError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Load(source) => Some(source),
            Self::DefaultAgentUnresolved { .. } => None,
            Self::BundledSkillStagingUnsupported { .. } => None,
        }
    }
}

impl From<RecipeLoadError> for RecipeMapError {
    fn from(value: RecipeLoadError) -> Self {
        Self::Load(value)
    }
}

/// Map the APSS harness kind onto the `itmux` [`Agent`]. Total: [`AgentKind`]
/// is a closed enum of exactly the harnesses `itmux` supports as recipe
/// defaults.
pub const fn map_agent_kind(kind: AgentKind) -> Agent {
    match kind {
        AgentKind::Claude => Agent::Claude,
        AgentKind::Codex => Agent::Codex,
    }
}

/// Resolve an agent's `skills` refs to plugin-dir paths, in listed order (R3).
///
/// For each ref: if `<recipe_dir>/skills/<ref>/` is an existing directory, the
/// ref is a BUNDLED skill on the host. Staging it into the container is not yet
/// implemented (#249), and passing the host path to `claude --plugin-dir` would
/// reference a non-existent in-container path, so this returns
/// [`RecipeMapError::BundledSkillStagingUnsupported`] (PR #247 Fix 3, fail-fast
/// instead of a silently-broken `--plugin-dir`).
///
/// Otherwise the ref is used verbatim as a (container-relative) path - an
/// external skill the container resolves. Order is preserved exactly.
pub fn resolve_skill_plugin_dirs(
    recipe_dir: &Path,
    skills: &[String],
) -> Result<Vec<PathBuf>, RecipeMapError> {
    skills
        .iter()
        .map(|skill_ref| {
            let bundled = recipe_dir.join("skills").join(skill_ref);
            if bundled.is_dir() {
                Err(RecipeMapError::BundledSkillStagingUnsupported {
                    skill_ref: skill_ref.clone(),
                    host_path: bundled,
                })
            } else {
                Ok(PathBuf::from(skill_ref))
            }
        })
        .collect()
}

/// Combine the resolved system prompt with the task into the single text
/// submitted to an interactive agent.
///
/// Interactive harnesses (claude/codex TUIs driven over tmux) have no separate
/// "system" channel, so the resolved system prompt is prepended to the task as
/// a preamble: `system + "\n\n" + task`. When there is no system prompt at all,
/// the submit text is just the task. The append-vs-replace merge of
/// `system_instructions` against `SYSTEM.md` has already happened inside
/// [`resolved_system`]; this function only joins that result to the task.
pub fn build_submit_text(system: Option<&str>, task: &str) -> String {
    match system {
        Some(system) if !system.is_empty() => format!("{system}\n\n{task}"),
        _ => task.to_string(),
    }
}

/// Build a [`RecipeExecutionPlan`] from an already-loaded [`Recipe`] and a
/// task. Split out from [`load_execution_plan`] so it can be unit-tested
/// against an in-memory [`Recipe`] without touching the filesystem, and reused
/// by the orchestrator.
pub fn plan_from_recipe(
    recipe: &Recipe,
    recipe_dir: &Path,
    task: &str,
) -> Result<RecipeExecutionPlan, RecipeMapError> {
    let default_agent: &AgentManifest =
        recipe
            .default_agent()
            .ok_or_else(|| RecipeMapError::DefaultAgentUnresolved {
                default_agent: recipe.manifest.default_agent.clone(),
            })?;

    let agent = map_agent_kind(default_agent.agent);
    let claude_plugin_dirs = resolve_skill_plugin_dirs(recipe_dir, &default_agent.skills)?;
    let system = resolved_system(default_agent, recipe.system_md.as_deref());
    let submit_text = build_submit_text(system.as_deref(), task);

    Ok(RecipeExecutionPlan {
        recipe_name: recipe.manifest.name.clone(),
        agent,
        claude_plugin_dirs,
        submit_text,
        subagents: default_agent.subagents.clone(),
    })
}

/// Load the recipe directory named by `spec.recipe` and map it to a
/// [`RecipeExecutionPlan`] for `spec.task`.
///
/// This is the loader's public entry point: it consumes the APSS
/// [`load_recipe_dir`] (so a recipe that validates is a recipe that runs) and
/// maps the `default_agent` onto `itmux` start arguments + submit text.
pub fn load_execution_plan(spec: &AgentRunSpec) -> Result<RecipeExecutionPlan, RecipeMapError> {
    let recipe = load_recipe_dir(&spec.recipe)?;
    plan_from_recipe(&recipe, &spec.recipe, &spec.task)
}
