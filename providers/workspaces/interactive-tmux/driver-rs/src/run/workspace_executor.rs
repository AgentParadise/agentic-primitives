//! The real [`RunExecutor`] backed by a `Workspace`, plus the public
//! [`run`] entry point that wires a recipe spec through the harness-neutral
//! orchestrator.
//!
//! Harness specifics that must NOT leak into `orchestrator.rs` (per R8) live
//! here: mapping the recipe's default agent onto `StartOptions`, materialising
//! per-harness credentials, and the (placeholder) outcome detection.

use std::collections::HashMap;
use std::fs;
use std::io;
use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use crate::adapter::Agent;
use crate::result::AwaitResult;
use crate::run::contract::{AgentRunEvent, AgentRunOutcome, AgentRunResult, AgentRunSpec};
use crate::run::orchestrator::{run_core, CancelToken, RunExecutor};
use crate::run::recipe_loader::{load_execution_plan, RecipeExecutionPlan};
use crate::workspace::{StartOptions, Workspace, DEFAULT_STARTUP_TIMEOUT_S};

/// Default await bound (seconds) when the spec sets no `limits.timeout_s`.
const DEFAULT_AWAIT_TIMEOUT_S: f64 = 300.0;

/// Live workspace handle owned by the orchestrator between Provisioning and
/// Terminalizing.
pub struct WorkspaceHandle {
    workspace: Workspace,
    agent: Agent,
    submit_text: String,
}

/// A [`RunExecutor`] that provisions a real Docker workspace and drives the
/// recipe's default agent through it.
pub struct WorkspaceExecutor {
    name: String,
    image: String,
    plan: RecipeExecutionPlan,
    submit_text: String,
    host_auth: HashMap<Agent, Option<PathBuf>>,
    host_claude_dotjson: Option<PathBuf>,
    startup_timeout_s: f64,
    /// Temp dirs holding credentials materialised from the spec; removed on
    /// teardown so inline credential material never lingers on disk.
    cred_tmp_dirs: Vec<PathBuf>,
}

impl WorkspaceExecutor {
    /// Build an executor from a spec + its loaded plan. Materialises any inline
    /// credentials (contract carries CONTENTS, not paths) into the on-disk
    /// shapes `crate::auth` expects, or falls back to the environment-resolved
    /// host auth (`ITMUX_<AGENT>_HOME` / `$HOME/.<agent>`) when the spec omits
    /// them.
    pub fn new(spec: &AgentRunSpec, plan: &RecipeExecutionPlan, image: &str) -> io::Result<Self> {
        let agent = plan.agent;
        let mut cred_tmp_dirs = Vec::new();
        let mut host_auth: HashMap<Agent, Option<PathBuf>> = HashMap::new();

        let auth_path = materialise_host_auth(spec, agent, &mut cred_tmp_dirs)?;
        host_auth.insert(agent, auth_path);

        Ok(Self {
            name: sanitize_name(&plan.recipe_name),
            image: image.to_string(),
            plan: plan.clone(),
            submit_text: plan.submit_text.clone(),
            host_auth,
            host_claude_dotjson: None,
            startup_timeout_s: DEFAULT_STARTUP_TIMEOUT_S,
            cred_tmp_dirs,
        })
    }
}

impl RunExecutor for WorkspaceExecutor {
    type Handle = WorkspaceHandle;

    fn provision(&mut self) -> io::Result<Self::Handle> {
        // `Workspace::start` is monolithic (provision container + tmux bootstrap
        // + agent launch + wait-for-started) and is itself transactional: on
        // any failure it tears down the container it created, so a failed
        // provision leaks nothing. The orchestrator's Launching phase is a
        // no-op for this executor (see `launch`).
        let mut opts = StartOptions::new(&self.name);
        opts.image = self.image.clone();
        opts.host_auth = self.host_auth.clone();
        opts.host_claude_dotjson = self.host_claude_dotjson.clone();
        opts.claude_plugin_dirs = self.plan.claude_plugin_dirs.clone();
        opts.strict_startup = true;
        opts.startup_timeout_s = self.startup_timeout_s;

        let workspace = Workspace::start(opts)?;
        Ok(WorkspaceHandle {
            workspace,
            agent: self.plan.agent,
            submit_text: self.submit_text.clone(),
        })
    }

    fn launch(&mut self, _handle: &mut Self::Handle) -> io::Result<()> {
        // No-op: `Workspace::start` already launched the agent and waited for
        // startup readiness during provisioning. The distinct Launching phase
        // exists in the orchestrator for the state-machine boundary and for the
        // fake executor's tests; this executor has nothing left to do here.
        Ok(())
    }

    fn submit(&mut self, handle: &mut Self::Handle) -> io::Result<()> {
        // Uses the per-harness input-readiness submit (Gap 1 fix).
        handle
            .workspace
            .send_message(handle.agent, &handle.submit_text)
    }

    fn await_completion(
        &mut self,
        handle: &mut Self::Handle,
        timeout: Option<Duration>,
    ) -> io::Result<AwaitResult> {
        let secs = timeout.map_or(DEFAULT_AWAIT_TIMEOUT_S, |d| d.as_secs_f64());
        handle
            .workspace
            .await_completion(handle.agent, secs, 4, 0.5, 2.0)
    }

    fn capture(&mut self, handle: &mut Self::Handle) -> io::Result<String> {
        handle.workspace.capture_response(handle.agent)
    }

    fn detect_outcome(
        &self,
        handle: &Self::Handle,
        pane: &str,
        _await_result: &AwaitResult,
    ) -> AgentRunOutcome {
        // Gap 2 (#246): success is derived from HARNESS-AWARE state via the
        // per-harness adapter, NOT from pane liveness. The adapter scans the
        // pane for that harness's hard-error markers and applies the readiness
        // floor. All harness specifics live in the adapter; this executor just
        // maps the adapter's signal onto the contract's outcome type.
        let signal = crate::adapter::detect_outcome(handle.agent, pane);
        AgentRunOutcome {
            success: signal.success,
            summary: signal.reason,
        }
    }

    fn teardown(&mut self, handle: Self::Handle) -> io::Result<()> {
        let result = handle.workspace.stop();
        // Remove any materialised credential temp dirs regardless of stop's
        // result; best-effort, never masks the teardown result.
        for dir in self.cred_tmp_dirs.drain(..) {
            let _ = fs::remove_dir_all(dir);
        }
        result
    }
}

/// Resolve the host-auth path for `agent`: materialise inline spec credentials
/// when present, else fall back to the environment (`ITMUX_<AGENT>_HOME` or
/// `$HOME/.<agent>`), matching the `start` subcommand's resolution.
fn materialise_host_auth(
    spec: &AgentRunSpec,
    agent: Agent,
    cred_tmp_dirs: &mut Vec<PathBuf>,
) -> io::Result<Option<PathBuf>> {
    match agent {
        Agent::Claude => {
            if let Some(claude) = &spec.credentials.claude {
                let dir = fresh_cred_dir("claude")?;
                // `.credentials.json` shape mirrors a Max-plan credentials file
                // (`claudeAiOauth.accessToken`), per the interactive-tmux
                // manifest. The exact schema is validated by the live run
                // (Task 8); the contract supplies the token contents only.
                let creds = serde_json::json!({
                    "claudeAiOauth": { "accessToken": claude.oauth_token }
                });
                fs::write(
                    dir.join(".credentials.json"),
                    serde_json::to_vec_pretty(&creds)?,
                )?;
                cred_tmp_dirs.push(dir.clone());
                Ok(Some(dir))
            } else {
                Ok(env_host_auth("ITMUX_CLAUDE_HOME", ".claude"))
            }
        }
        Agent::Codex => {
            if let Some(codex) = &spec.credentials.codex {
                let dir = fresh_cred_dir("codex")?;
                fs::write(dir.join("auth.json"), codex.auth_json.as_bytes())?;
                cred_tmp_dirs.push(dir.clone());
                Ok(Some(dir))
            } else {
                Ok(env_host_auth("ITMUX_CODEX_HOME", ".codex"))
            }
        }
        Agent::Gemini => Ok(env_host_auth("ITMUX_GEMINI_HOME", ".gemini")),
    }
}

/// Environment-resolved host auth dir: `$<override_env>` if set, else
/// `$HOME/<home_subdir>` if it exists, else `None`.
fn env_host_auth(override_env: &str, home_subdir: &str) -> Option<PathBuf> {
    if let Some(explicit) = std::env::var_os(override_env) {
        return Some(PathBuf::from(explicit));
    }
    let home = std::env::var_os("HOME").map(PathBuf::from)?;
    let candidate = home.join(home_subdir);
    candidate.is_dir().then_some(candidate)
}

/// Create a fresh 0700 temp dir under the system temp dir for credential
/// materialisation.
fn fresh_cred_dir(agent: &str) -> io::Result<PathBuf> {
    let base = std::env::temp_dir();
    let mut path = base.join(format!("itmux-run-cred-{agent}-{}", unique_suffix()));
    while path.exists() {
        path = base.join(format!("itmux-run-cred-{agent}-{}", unique_suffix()));
    }
    fs::create_dir_all(&path)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(&path, fs::Permissions::from_mode(0o700));
    }
    Ok(path)
}

fn unique_suffix() -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    let pid = u128::from(std::process::id());
    let mix = now.as_nanos().wrapping_mul(0x9E37_79B9_7F4A_7C15) ^ (pid << 64);
    #[allow(clippy::cast_possible_truncation)]
    let low = (mix & 0xFFFF_FFFF) as u64;
    format!("{low:08x}")
}

/// Sanitise a recipe name into a docker-safe workspace label.
fn sanitize_name(recipe_name: &str) -> String {
    let cleaned: String = recipe_name
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '-' || c == '_' {
                c
            } else {
                '-'
            }
        })
        .collect();
    let trimmed = cleaned.trim_matches('-');
    if trimmed.is_empty() {
        "recipe".to_string()
    } else {
        trimmed.to_string()
    }
}

/// A run identifier for the event stream. Derived from time + pid; opaque.
pub fn generate_run_id() -> String {
    format!("run-{}", unique_suffix())
}

/// Format the current time as an RFC3339 UTC timestamp (second precision), with
/// no external date dependency.
pub fn now_rfc3339() -> String {
    let dur = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    format_rfc3339_utc(dur.as_secs())
}

fn format_rfc3339_utc(unix_secs: u64) -> String {
    let days = (unix_secs / 86_400) as i64;
    let secs_of_day = unix_secs % 86_400;
    let (hh, mm, ss) = (
        secs_of_day / 3_600,
        (secs_of_day % 3_600) / 60,
        secs_of_day % 60,
    );
    let (year, month, day) = civil_from_days(days);
    format!("{year:04}-{month:02}-{day:02}T{hh:02}:{mm:02}:{ss:02}Z")
}

/// Convert days-since-Unix-epoch to a (year, month, day) civil date
/// (Howard Hinnant's algorithm). No dependency, no `unsafe`.
fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let month = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    let year = if month <= 2 { y + 1 } else { y };
    (year, month, day)
}

/// Public entry point: load the recipe named by `spec.recipe`, then drive the
/// run through the harness-neutral orchestrator, emitting the R6 event stream.
///
/// Returns `Err` only when the recipe fails to load (a precondition, before any
/// workspace is provisioned); once the state machine starts, all failures are
/// reported as a terminal [`AgentRunResult`] with a `session_end` event.
pub fn run(
    spec: &AgentRunSpec,
    image: &str,
    run_id: &str,
    cancel: &CancelToken,
    emit: &mut dyn FnMut(&AgentRunEvent),
) -> io::Result<AgentRunResult> {
    let plan = load_execution_plan(spec).map_err(|e| io::Error::other(e.to_string()))?;
    let timeout = spec
        .limits
        .as_ref()
        .and_then(|l| l.timeout_s)
        .map(Duration::from_secs_f64);
    let mut executor = WorkspaceExecutor::new(spec, &plan, image)?;
    let mut now = now_rfc3339;
    Ok(run_core(
        run_id,
        &plan,
        timeout,
        &mut executor,
        cancel,
        &mut now,
        emit,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rfc3339_formats_known_epochs() {
        assert_eq!(format_rfc3339_utc(0), "1970-01-01T00:00:00Z");
        // 2026-07-07T00:00:00Z = 1783382400 unix seconds.
        assert_eq!(format_rfc3339_utc(1_783_382_400), "2026-07-07T00:00:00Z");
        // A within-day time: +13:45:30.
        assert_eq!(
            format_rfc3339_utc(1_783_382_400 + 13 * 3600 + 45 * 60 + 30),
            "2026-07-07T13:45:30Z"
        );
    }

    #[test]
    fn sanitize_name_replaces_unsafe_chars() {
        assert_eq!(sanitize_name("pr-reviewer"), "pr-reviewer");
        assert_eq!(sanitize_name("my recipe!"), "my-recipe");
        assert_eq!(sanitize_name("///"), "recipe");
    }
}
