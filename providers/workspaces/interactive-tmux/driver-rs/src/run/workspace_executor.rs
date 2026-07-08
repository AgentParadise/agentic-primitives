//! The real [`RunExecutor`] backed by a `Workspace`, plus the public
//! [`run`] entry point that wires a recipe spec through the harness-neutral
//! orchestrator.
//!
//! Harness specifics that must NOT leak into `orchestrator.rs` (per R8) live
//! here: mapping the recipe's default agent onto `StartOptions`, materialising
//! per-harness credentials, and the (placeholder) outcome detection.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs;
use std::io;
use std::path::PathBuf;
use std::process::Command;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use crate::adapter::Agent;
use crate::result::AwaitResult;
use crate::run::contract::{
    AgentRunEvent, AgentRunEventPayload, AgentRunOutcome, AgentRunResult, AgentRunSpec,
};
use crate::run::harness_observer::{ClaudeTranscriptObserver, HarnessObserver};
use crate::run::observability::ObservabilityFanout;
use crate::run::orchestrator::{run_core, CancelToken, RunExecutor};
use crate::run::recipe_loader::{load_execution_plan, RecipeExecutionPlan};
use crate::run::secret_env::{missing_credentials_message, resolve_agent_secrets};
use crate::tmux;
use crate::workspace::{StartOptions, Workspace, DEFAULT_STARTUP_TIMEOUT_S};

/// Default await bound (seconds) when the spec sets no `limits.timeout_s`.
const DEFAULT_AWAIT_TIMEOUT_S: f64 = 300.0;
const AGENTIC_EVENTS_JSONL_ENV: &str = "AGENTIC_EVENTS_JSONL";
const AGENTIC_EVENTS_JSONL_PATH: &str = "/tmp/agentic-observability/hooks.jsonl";

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
    /// Deterministic, unique container name computed UP FRONT (before
    /// `provision`), so a hard cancel that orphans a container mid-provision can
    /// be reaped precisely by name (see `teardown_orphans`, #248).
    container_name: String,
    image: String,
    plan: RecipeExecutionPlan,
    submit_text: String,
    host_auth: HashMap<Agent, Option<PathBuf>>,
    host_claude_dotjson: Option<PathBuf>,
    /// Per-agent secret env vars (OAuth token / API keys) to inject via the
    /// sourced `0600` env-file launch wrapper (R1/R2). Never in argv.
    secret_env: HashMap<Agent, BTreeMap<String, String>>,
    /// Claude OAuth env-var mode: stage `.claude.json` only, no
    /// `.credentials.json` (R1/R8).
    claude_omit_credentials: bool,
    env_vars: Vec<(String, String)>,
    hook_events_path: Option<String>,
    hook_events_bytes_read: usize,
    transcript_paths: BTreeSet<String>,
    transcript_bytes_read: HashMap<String, usize>,
    transcript_observers: HashMap<String, ClaudeTranscriptObserver>,
    agent_stopped_normal: bool,
    startup_timeout_s: f64,
    /// Temp dirs holding credentials materialised from the spec; removed on
    /// teardown so inline credential material never lingers on disk.
    cred_tmp_dirs: Vec<PathBuf>,
}

impl WorkspaceExecutor {
    /// Build an executor from a spec + its loaded plan.
    ///
    /// Resolves the default agent's credentials (R1-R3): secrets from
    /// `spec.credentials` (populated by the `.env`/process-env loader) are
    /// routed to the harness as env vars (OAuth token / API key) injected via a
    /// sourced `0600` env file, or - for codex - an `auth.json` staged file.
    /// When the agent has NO credentials and `allow_host_fallback` is false,
    /// this FAILS FAST with an actionable error (R3); with the flag it falls
    /// back to the host `$HOME/.<agent>` dir (warned, path only - never token
    /// contents).
    pub fn new(
        spec: &AgentRunSpec,
        plan: &RecipeExecutionPlan,
        image: &str,
        allow_host_fallback: bool,
    ) -> io::Result<Self> {
        let agent = plan.agent;
        let mut cred_tmp_dirs = Vec::new();

        let wiring =
            resolve_launch_credentials(spec, agent, allow_host_fallback, &mut cred_tmp_dirs)?;

        let mut host_auth: HashMap<Agent, Option<PathBuf>> = HashMap::new();
        host_auth.insert(agent, wiring.host_auth);
        let mut secret_env: HashMap<Agent, BTreeMap<String, String>> = HashMap::new();
        if !wiring.secret_env.is_empty() {
            secret_env.insert(agent, wiring.secret_env);
        }

        let name = sanitize_name(&plan.recipe_name);
        let container_name = format!("interactive-tmux-{name}-{}", unique_suffix());

        Ok(Self {
            name,
            container_name,
            image: image.to_string(),
            plan: plan.clone(),
            submit_text: plan.submit_text.clone(),
            host_auth,
            host_claude_dotjson: resolve_host_claude_dotjson(),
            secret_env,
            claude_omit_credentials: wiring.claude_omit_credentials,
            env_vars: hook_sink_env(agent),
            hook_events_path: hook_events_path(agent),
            hook_events_bytes_read: 0,
            transcript_paths: BTreeSet::new(),
            transcript_bytes_read: HashMap::new(),
            transcript_observers: HashMap::new(),
            agent_stopped_normal: false,
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
        //
        // TODO(#248): `Workspace::start` is BLOCKING and does not observe the
        // orchestrator's `CancelToken`. A hard cancel that arrives while this
        // call is in flight only takes effect once `start` returns - then the
        // orchestrator tears down the returned handle (no orphan for catchable
        // signals). The residual gap: a SIGKILL (uncatchable) or a wedged
        // blocking call in that window can orphan a container. As a defense we
        // pin a deterministic `container_name` up front so `teardown_orphans`
        // can reap it by exact name on the hard-cancel path; a fully
        // cancellable start is #248.
        let mut opts = StartOptions::new(&self.name);
        opts.image = self.image.clone();
        opts.container_name = Some(self.container_name.clone());
        opts.host_auth = self.host_auth.clone();
        opts.host_claude_dotjson = self.host_claude_dotjson.clone();
        opts.claude_plugin_dirs = self.plan.claude_plugin_dirs.clone();
        opts.secret_env = self.secret_env.clone();
        opts.claude_omit_credentials = self.claude_omit_credentials;
        opts.env_vars = self.env_vars.clone();
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
        emit_observed: &mut dyn FnMut(Vec<AgentRunEventPayload>),
    ) -> io::Result<AwaitResult> {
        // TODO(#248): like `provision`, `await_completion` is a BLOCKING bounded
        // poll loop that does not observe the `CancelToken` mid-poll. A hard
        // cancel takes effect only once this returns (bounded by `secs`); the
        // orchestrator then tears down the handle. Making the poll loop
        // cancel-aware (so a hard cancel returns promptly) is part of #248.
        let secs = timeout.map_or(DEFAULT_AWAIT_TIMEOUT_S, |d| d.as_secs_f64());
        handle.workspace.await_completion_with_poll_callback(
            handle.agent,
            secs,
            4,
            0.5,
            2.0,
            &mut |workspace, pane, elapsed_ms, stable_polls_observed| {
                match self.drain_observed_event_deltas(workspace) {
                    Ok(payloads) if !payloads.is_empty() => emit_observed(payloads),
                    Ok(_) => {}
                    Err(err) => eprintln!("[itmux run] failed to drain observed events: {err}"),
                }
                if self.agent_stopped_normal {
                    return Some(AwaitResult::ready(
                        elapsed_ms,
                        stable_polls_observed,
                        pane.to_string(),
                    ));
                }
                None
            },
        )
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

    fn drain_observed_events(
        &mut self,
        handle: &mut Self::Handle,
    ) -> io::Result<Vec<AgentRunEventPayload>> {
        self.drain_observed_event_deltas(&handle.workspace)
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

    fn teardown_orphans(&mut self) {
        // Best-effort orphan reap for the hard-cancel-during-blocking-provision
        // window (#248): the container name was pinned deterministically before
        // `provision`, so we can `docker rm -f` it by EXACT name (never a
        // prefix - so a concurrent run of the same recipe is never touched).
        // Idempotent: if no such container exists (the common case), the removal
        // is a harmless no-op. Never fails the run; we only log.
        eprintln!(
            "[itmux run] hard cancel with no live handle - best-effort reap of container {} (#248)",
            self.container_name
        );
        let mut cmd = Command::new("docker");
        cmd.args(["rm", "-f", &self.container_name]);
        let _ = tmux::run_bounded(cmd, Duration::from_secs_f64(tmux::DEFAULT_RUN_TIMEOUT_S));
        for dir in self.cred_tmp_dirs.drain(..) {
            let _ = fs::remove_dir_all(dir);
        }
    }
}

/// How the executor wires one agent's credentials into `StartOptions`.
struct CredentialWiring {
    /// Host auth dir to stage (claude trust `.claude.json`, codex `auth.json`),
    /// or `None` when the agent is enabled purely via `secret_env`.
    host_auth: Option<PathBuf>,
    /// Secret env vars (OAuth token / API key) to source at launch.
    secret_env: BTreeMap<String, String>,
    /// Claude OAuth env-var mode: stage `.claude.json` only (R1/R8).
    claude_omit_credentials: bool,
}

impl WorkspaceExecutor {
    fn drain_observed_event_deltas(
        &mut self,
        workspace: &Workspace,
    ) -> io::Result<Vec<AgentRunEventPayload>> {
        let Some(path) = self.hook_events_path.clone() else {
            return Ok(Vec::new());
        };
        let (stdout, bytes_read) =
            read_workspace_file_delta_if_present(workspace, &path, self.hook_events_bytes_read)?;
        self.hook_events_bytes_read = bytes_read;
        let parsed = parse_hook_events(&stdout);
        self.agent_stopped_normal |= parsed.agent_stopped_normal;
        let mut payloads = parsed.payloads;
        for transcript_path in parsed.transcript_paths {
            self.transcript_paths.insert(transcript_path);
        }
        let transcript_paths = self.transcript_paths.iter().cloned().collect::<Vec<_>>();
        for transcript_path in transcript_paths {
            let offset = self
                .transcript_bytes_read
                .get(&transcript_path)
                .copied()
                .unwrap_or_default();
            let (transcript_delta, bytes_read) =
                read_workspace_file_delta_if_present(workspace, &transcript_path, offset)?;
            self.transcript_bytes_read
                .insert(transcript_path.clone(), bytes_read);
            payloads.extend(
                self.parse_claude_transcript_event_deltas(&transcript_path, &transcript_delta),
            );
        }
        Ok(payloads)
    }

    fn parse_claude_transcript_event_deltas(
        &mut self,
        transcript_path: &str,
        raw: &str,
    ) -> Vec<AgentRunEventPayload> {
        let observer = self
            .transcript_observers
            .entry(transcript_path.to_string())
            .or_insert_with(|| ClaudeTranscriptObserver::new().with_message_usage(true));
        parse_claude_transcript_events_with_observer(observer, raw)
    }
}

/// Resolve credentials for `agent` from `spec` (R1-R3).
///
/// Precedence (per user + R8): env-var/file secrets from `spec.credentials`
/// (populated by the `.env`/process-env loader) are preferred. When the agent
/// has NO credentials: with `allow_host_fallback` we fall back to the host
/// `$HOME/.<agent>` dir (warned to stderr - PATH only, never token contents);
/// without it we fail fast with an actionable error naming the missing var.
fn resolve_launch_credentials(
    spec: &AgentRunSpec,
    agent: Agent,
    allow_host_fallback: bool,
    cred_tmp_dirs: &mut Vec<PathBuf>,
) -> io::Result<CredentialWiring> {
    let secrets = resolve_agent_secrets(agent, &spec.credentials);

    if secrets.is_empty() {
        if allow_host_fallback {
            let (override_env, subdir) = match agent {
                Agent::Claude => ("ITMUX_CLAUDE_HOME", ".claude"),
                Agent::Codex => ("ITMUX_CODEX_HOME", ".codex"),
                Agent::Gemini => ("ITMUX_GEMINI_HOME", ".gemini"),
            };
            let host = env_host_auth(override_env, subdir);
            match &host {
                Some(path) => eprintln!(
                    "[itmux run] --allow-host-auth-fallback: using host auth dir {} for {} \
                     (may be stale -> 401)",
                    path.display(),
                    agent.as_str()
                ),
                None => eprintln!(
                    "[itmux run] --allow-host-auth-fallback: no host auth dir found for {}",
                    agent.as_str()
                ),
            }
            return Ok(CredentialWiring {
                host_auth: host,
                secret_env: BTreeMap::new(),
                claude_omit_credentials: false,
            });
        }
        return Err(io::Error::new(
            io::ErrorKind::NotFound,
            missing_credentials_message(agent),
        ));
    }

    match agent {
        Agent::Claude => {
            // OAuth env-var mode (R1): stage the seeded `.claude.json` for
            // trust/onboarding, but NO `.credentials.json`. Use the real host
            // `.claude` dir when it exists (so `oauthAccount` can pass through);
            // otherwise a fresh empty dir so `.claude.json` is still synthesized.
            let host = match env_host_auth("ITMUX_CLAUDE_HOME", ".claude") {
                Some(path) => path,
                None => {
                    let dir = fresh_cred_dir("claude-trust")?;
                    cred_tmp_dirs.push(dir.clone());
                    dir
                }
            };
            Ok(CredentialWiring {
                host_auth: Some(host),
                secret_env: secrets.env,
                claude_omit_credentials: true,
            })
        }
        Agent::Codex => {
            // Preferred: stage `auth.json` (from CODEX_AUTH_FILE / legacy field).
            // Fallback: `OPENAI_API_KEY` sourced as an env var (no file).
            let host_auth = if let Some(auth_json) = secrets.codex_auth_json {
                let dir = fresh_cred_dir("codex")?;
                // Create the auth.json 0600 at creation (atomic, no brief 0644
                // window) - it carries the codex token (PR #254 review).
                crate::workspace::write_private_file(&dir.join("auth.json"), auth_json.as_bytes())?;
                cred_tmp_dirs.push(dir.clone());
                Some(dir)
            } else {
                None
            };
            Ok(CredentialWiring {
                host_auth,
                secret_env: secrets.env,
                claude_omit_credentials: false,
            })
        }
        Agent::Gemini => Ok(CredentialWiring {
            host_auth: env_host_auth("ITMUX_GEMINI_HOME", ".gemini"),
            secret_env: secrets.env,
            claude_omit_credentials: false,
        }),
    }
}

/// Resolve `~/.claude.json` for the trust/onboarding synthesis, honoring
/// `ITMUX_CLAUDE_JSON` first, then `$HOME/.claude.json`. Mirrors the `start`
/// subcommand's `default_host_claude_dotjson`.
fn resolve_host_claude_dotjson() -> Option<PathBuf> {
    if let Some(explicit) = std::env::var_os("ITMUX_CLAUDE_JSON") {
        let path = PathBuf::from(explicit);
        return path.is_file().then_some(path);
    }
    let home = std::env::var_os("HOME").map(PathBuf::from)?;
    let path = home.join(".claude.json");
    path.is_file().then_some(path)
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

fn hook_events_path(agent: Agent) -> Option<String> {
    (agent == Agent::Claude).then(|| AGENTIC_EVENTS_JSONL_PATH.to_string())
}

fn hook_sink_env(agent: Agent) -> Vec<(String, String)> {
    hook_events_path(agent)
        .map(|path| vec![(AGENTIC_EVENTS_JSONL_ENV.to_string(), path)])
        .unwrap_or_default()
}

#[derive(Debug, Default)]
struct ParsedHookEvents {
    payloads: Vec<AgentRunEventPayload>,
    transcript_paths: BTreeSet<String>,
    agent_stopped_normal: bool,
}

fn parse_hook_events(raw: &str) -> ParsedHookEvents {
    let mut parsed = ParsedHookEvents::default();
    for line in raw.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let Ok(event) = serde_json::from_str::<serde_json::Value>(trimmed) else {
            continue;
        };
        if let Some(path) = transcript_path_from_hook_event(&event) {
            parsed.transcript_paths.insert(path.to_string());
        }
        if is_normal_agent_stopped_hook_event(&event) {
            parsed.agent_stopped_normal = true;
        }
        let Some(event_type) = event.get("event_type").and_then(serde_json::Value::as_str) else {
            continue;
        };
        let provider = event
            .get("provider")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("unknown")
            .to_string();
        parsed.payloads.push(AgentRunEventPayload::HookEvent {
            provider,
            event_type: event_type.to_string(),
            event: sanitize_hook_event(event),
        });
    }
    parsed
}

fn is_normal_agent_stopped_hook_event(event: &serde_json::Value) -> bool {
    event
        .get("event_type")
        .and_then(serde_json::Value::as_str)
        .is_some_and(|event_type| event_type == "agent_stopped")
        && event
            .pointer("/context/reason")
            .and_then(serde_json::Value::as_str)
            .is_some_and(|reason| reason == "normal")
}

fn sanitize_hook_event(mut event: serde_json::Value) -> serde_json::Value {
    let mut redacted = false;
    if let Some(context) = event
        .get_mut("context")
        .and_then(serde_json::Value::as_object_mut)
    {
        for key in [
            "input_preview",
            "output_preview",
            "prompt_preview",
            "message",
            "error",
        ] {
            if context.remove(key).is_some() {
                redacted = true;
            }
        }
    }
    if let Some(metadata) = event
        .get_mut("metadata")
        .and_then(serde_json::Value::as_object_mut)
    {
        for key in ["prompt", "tool_input", "tool_result"] {
            if metadata.remove(key).is_some() {
                redacted = true;
            }
        }
    }
    if redacted {
        event["redacted"] = serde_json::Value::Bool(true);
    }
    event
}

fn transcript_path_from_hook_event(event: &serde_json::Value) -> Option<&str> {
    event
        .pointer("/metadata/transcript_path")
        .or_else(|| event.get("transcript_path"))
        .and_then(serde_json::Value::as_str)
        .filter(|path| !path.trim().is_empty())
}

fn read_workspace_file_if_present(workspace: &Workspace, path: &str) -> io::Result<String> {
    let quoted = sh_single_quote(path);
    let output = workspace.exec(&[
        "sh",
        "-lc",
        &format!("if [ -f {quoted} ]; then cat {quoted}; fi"),
    ])?;
    if !output.status.success() {
        return Err(io::Error::other(format!(
            "read observed transcript failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

fn read_workspace_file_delta_if_present(
    workspace: &Workspace,
    path: &str,
    offset: usize,
) -> io::Result<(String, usize)> {
    let raw = read_workspace_file_if_present(workspace, path)?;
    if raw.len() <= offset {
        return Ok((String::new(), raw.len()));
    }
    Ok((raw[offset..].to_string(), raw.len()))
}

#[cfg(test)]
fn parse_claude_transcript_events(raw: &str) -> Vec<AgentRunEventPayload> {
    let mut observer = ClaudeTranscriptObserver::new().with_message_usage(true);
    parse_claude_transcript_events_with_observer(&mut observer, raw)
}

fn parse_claude_transcript_events_with_observer(
    observer: &mut ClaudeTranscriptObserver,
    raw: &str,
) -> Vec<AgentRunEventPayload> {
    let mut payloads = Vec::new();
    for line in raw.lines() {
        match observer.observe_jsonl_line(line) {
            Ok(events) => payloads.extend(events.into_iter().map(|event| event.payload)),
            Err(_) => payloads.push(AgentRunEventPayload::ToolEnd {
                tool_name: "claude_transcript.parse".to_string(),
                success: false,
                output_summary: Some("invalid claude transcript JSONL line".to_string()),
            }),
        }
    }
    payloads
}

fn sh_single_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\\''"))
}

/// Create a fresh temp dir under the system temp dir for credential
/// materialisation, with mode 0700 set ATOMICALLY at creation (no brief 0755
/// window) - it holds staged secret files (PR #254 review).
fn fresh_cred_dir(agent: &str) -> io::Result<PathBuf> {
    let base = std::env::temp_dir();
    let mut path = base.join(format!("itmux-run-cred-{agent}-{}", unique_suffix()));
    while path.exists() {
        path = base.join(format!("itmux-run-cred-{agent}-{}", unique_suffix()));
    }
    crate::workspace::create_private_dir(&path)?;
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
    allow_host_fallback: bool,
    emit: &mut dyn FnMut(&AgentRunEvent),
) -> io::Result<AgentRunResult> {
    let plan = load_execution_plan(spec).map_err(|e| io::Error::other(e.to_string()))?;
    run_with_plan(
        spec,
        &plan,
        image,
        run_id,
        cancel,
        allow_host_fallback,
        emit,
    )
}

/// Drive a run with a plan the caller has already loaded.
///
/// This keeps the public [`run`] entry point convenient while allowing CLI
/// code that must inspect the plan for dispatch decisions to avoid loading the
/// same recipe twice.
pub fn run_with_plan(
    spec: &AgentRunSpec,
    plan: &RecipeExecutionPlan,
    image: &str,
    run_id: &str,
    cancel: &CancelToken,
    allow_host_fallback: bool,
    emit: &mut dyn FnMut(&AgentRunEvent),
) -> io::Result<AgentRunResult> {
    let timeout = spec
        .limits
        .as_ref()
        .and_then(|l| l.timeout_s)
        .map(Duration::from_secs_f64);
    let mut executor = WorkspaceExecutor::new(spec, plan, image, allow_host_fallback)?;
    let mut now = now_rfc3339;
    let mut fanout = ObservabilityFanout::new(&spec.observability);
    let mut fanout_emit = |event: &AgentRunEvent| {
        fanout.emit(event);
        emit(event);
    };
    let mut result = run_core(
        run_id,
        plan,
        timeout,
        &mut executor,
        cancel,
        &mut now,
        &mut fanout_emit,
    );
    result.observability = fanout.finish();
    Ok(result)
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

    #[test]
    fn hook_events_include_payloads_and_transcript_paths() {
        let parsed = parse_hook_events(
            r#"{"event_type":"session_started","provider":"claude","metadata":{"transcript_path":"/tmp/claude/session.jsonl"}}"#,
        );

        assert_eq!(parsed.payloads.len(), 1);
        assert!(parsed
            .transcript_paths
            .contains("/tmp/claude/session.jsonl"));
        assert!(matches!(
            parsed.payloads[0],
            AgentRunEventPayload::HookEvent {
                ref provider,
                ref event_type,
                ..
            } if provider == "claude" && event_type == "session_started"
        ));
    }

    #[test]
    fn hook_events_redact_preview_fields() {
        let parsed = parse_hook_events(
            r#"{"event_type":"tool_execution_started","provider":"claude","context":{"tool_name":"Bash","tool_use_id":"toolu_1","input_preview":"echo sk-ant-secret"}}"#,
        );

        assert_eq!(parsed.payloads.len(), 1);
        let serialized = serde_json::to_string(&parsed.payloads[0]).expect("payload json");
        assert!(serialized.contains("\"redacted\":true"), "{serialized}");
        assert!(
            serialized.contains("\"tool_name\":\"Bash\""),
            "{serialized}"
        );
        assert!(!serialized.contains("sk-ant-secret"), "{serialized}");
        assert!(!serialized.contains("input_preview"), "{serialized}");
    }

    #[test]
    fn hook_events_detect_normal_agent_stop() {
        let parsed = parse_hook_events(
            r#"{"event_type":"agent_stopped","provider":"claude","context":{"reason":"normal"}}"#,
        );

        assert!(parsed.agent_stopped_normal);
        assert_eq!(parsed.payloads.len(), 1);
    }

    #[test]
    fn hook_events_ignore_non_normal_agent_stop_for_completion() {
        let parsed = parse_hook_events(
            r#"{"event_type":"agent_stopped","provider":"claude","context":{"reason":"error"}}"#,
        );

        assert!(!parsed.agent_stopped_normal);
        assert_eq!(parsed.payloads.len(), 1);
    }

    #[test]
    fn claude_transcript_events_are_normalized_for_workspace_run() {
        let payloads = parse_claude_transcript_events(
            r#"{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_1","name":"Bash","input":{"command":"echo sk-ant-secret"}}]}}"#,
        );

        assert_eq!(payloads.len(), 1);
        let serialized = serde_json::to_string(&payloads[0]).expect("payload json");
        assert!(serialized.contains("\"redacted\":true"), "{serialized}");
        assert!(!serialized.contains("sk-ant-secret"), "{serialized}");
    }

    #[test]
    fn claude_transcript_usage_is_available_to_workspace_run() {
        let payloads = parse_claude_transcript_events(
            r#"{"type":"result","modelUsage":{"claude-sonnet-4-5-20250929":{"inputTokens":3,"outputTokens":5,"cacheReadInputTokens":7,"cacheCreationInputTokens":11,"costUSD":0.02}}}"#,
        );

        assert_eq!(payloads.len(), 1);
        assert!(matches!(
            payloads[0],
            AgentRunEventPayload::TokenUsage {
                input_tokens: 3,
                output_tokens: 5,
                cached_input_tokens: Some(18),
                cost_usd: Some(0.02),
                ref harness,
                ref provider,
                ref model,
                ..
            } if harness.as_deref() == Some("claude")
                && provider.as_deref() == Some("anthropic")
                && model.as_deref() == Some("claude-sonnet-4-5-20250929")
        ));
    }
}
