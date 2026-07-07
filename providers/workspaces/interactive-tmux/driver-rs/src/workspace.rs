//! Workspace lifecycle: `docker run`, tmux bootstrap, per-agent launch +
//! readiness gating, public primitives (send/await/capture/exec/stop).

use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::io::{Error, ErrorKind, Result};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::thread;
use std::time::{Duration, Instant};

use crate::adapter::{self, Agent};
use crate::auth::{self, AuthContext, PreparedAuth, StagedPath};
use crate::registry::{self, WorkspaceRecord};
use crate::result::AwaitResult;
use crate::run::secret_env;
use crate::tmux;

pub const DEFAULT_IMAGE: &str = "agentic-workspace-interactive-tmux:latest";
pub const DEFAULT_TMUX_COLS: u32 = 200;
pub const DEFAULT_TMUX_ROWS: u32 = 50;
pub const DEFAULT_WORKDIR: &str = "/workspace";
pub const DEFAULT_STARTUP_TIMEOUT_S: f64 = 45.0;

#[derive(Debug, Clone)]
pub struct StartOptions {
    pub name: String,
    pub image: String,
    pub workdir: String,
    pub tmux_size: (u32, u32),
    pub startup_timeout_s: f64,
    pub strict_startup: bool,
    /// Per-agent host source paths. `None` skips the agent.
    pub host_auth: HashMap<Agent, Option<PathBuf>>,
    /// Explicit path to the operator's `~/.claude.json`. When `None`, the
    /// claude adapter falls back to `host_auth[Claude].parent()/.claude.json`,
    /// which is correct outside a container. Inside a container (DooD), the
    /// dotjson may be mounted at an unrelated path; set this so the synthesised
    /// container-side dotjson can carry the host's `oauthAccount` through.
    /// Surfaced as a bug fix for the Syntropic137 integration e2e (PR #202).
    pub host_claude_dotjson: Option<PathBuf>,
    /// Container-side paths to load as Claude Code plugin dirs (one
    /// `claude --plugin-dir <path>` flag per entry). Empty list = bare
    /// `claude` launch (pre-plugin behaviour preserved). Mirrors the
    /// Python `claude_plugin_dirs` kwarg and `ITMUX_CLAUDE_PLUGIN_DIRS`
    /// env var. Surfaced by Syntropic137's workflow-skills bridge
    /// (`docs/plans/workflow-skills.md` §9): settings.json `installedPlugins`
    /// injection is silently ignored by the TUI; the CLI flag is the only
    /// mechanism that actually loads plugins.
    pub claude_plugin_dirs: Vec<PathBuf>,
    /// Non-secret container environment variables, such as the hook sink
    /// location. Secret values use `secret_env`, never Docker argv.
    pub env_vars: Vec<(String, String)>,
    /// Explicit container name. When `None` (the default), `start` generates
    /// `interactive-tmux-<name>-<random>`. Callers that must know the container
    /// name BEFORE `start` returns (e.g. `itmux run` needs a deterministic name
    /// to best-effort reap an orphan on hard-cancel, #248) set this to a
    /// pre-computed unique name. It MUST be unique per workspace.
    pub container_name: Option<String>,
    /// Per-agent secret environment variables (R1/R2). For each agent with a
    /// non-empty map, `start` stages a `0600` env file into the container over
    /// the base64-over-stdin transfer and launches that agent's pane through a
    /// wrapper that `source`s it (see `adapter::launch_command_with_env`). The
    /// values NEVER reach argv. An agent with only `secret_env` (no `host_auth`)
    /// still counts as enabled. Empty by default.
    pub secret_env: HashMap<Agent, BTreeMap<String, String>>,
    /// When `true`, the claude auth staging omits `.credentials.json` and stages
    /// ONLY the seeded `.claude.json` (trust/onboarding). Used by the OAuth env
    /// var path (R1/R8): the token is injected via `secret_env`
    /// (`CLAUDE_CODE_OAUTH_TOKEN`), never synthesized into a `.credentials.json`.
    pub claude_omit_credentials: bool,
}

impl StartOptions {
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            image: DEFAULT_IMAGE.to_string(),
            workdir: DEFAULT_WORKDIR.to_string(),
            tmux_size: (DEFAULT_TMUX_COLS, DEFAULT_TMUX_ROWS),
            startup_timeout_s: DEFAULT_STARTUP_TIMEOUT_S,
            strict_startup: true,
            host_auth: HashMap::new(),
            host_claude_dotjson: None,
            claude_plugin_dirs: Vec::new(),
            env_vars: Vec::new(),
            container_name: None,
            secret_env: HashMap::new(),
            claude_omit_credentials: false,
        }
    }
}

#[derive(Debug, Clone)]
pub struct Workspace {
    pub name: String,
    pub container: String,
    pub image: String,
    pub workdir: String,
    pub tmux_size: (u32, u32),
    pub host_throwaway_dir: PathBuf,
    pub enabled_agents: Vec<Agent>,
    pub startup_status: HashMap<Agent, AwaitResult>,
    /// Per-agent CLI extras used at launch time. Today only claude has a
    /// non-default entry (`--plugin-dir` paths). Populated by
    /// `Workspace::start` from `StartOptions::claude_plugin_dirs`;
    /// consumed by `bootstrap_tmux_and_launch`.
    pub claude_plugin_dirs: Vec<PathBuf>,
    /// Per-agent container-side path of the staged `0600` secret env file
    /// (R1/R6). Populated by `Workspace::start` after the file is transferred;
    /// consumed by `bootstrap_tmux_and_launch` to launch the pane through the
    /// source-and-exec wrapper. NEVER contains a secret value - only the path.
    pub secret_env_files: HashMap<Agent, String>,
}

fn random_suffix() -> String {
    // 8 hex chars from a non-crypto seed mix (no `rand` dep). Mirrors the
    // Python `uuid.uuid4().hex[:8]` slot - used only for container naming.
    use std::time::{SystemTime, UNIX_EPOCH};
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    let pid = u128::from(std::process::id());
    let mix = now.as_nanos().wrapping_mul(0x9E37_79B9_7F4A_7C15) ^ (pid << 64);
    #[allow(clippy::cast_possible_truncation)]
    let low = (mix & 0xFFFF_FFFF) as u64;
    format!("{low:08x}")
}

/// Create `path` as a fresh directory with mode `0700` set ATOMICALLY at
/// creation (via `mkdir(mode)`), so it is never briefly world-traversable
/// (`0755`) before a follow-up `chmod`. This matters because the dir holds
/// staged secret material (the `0600` secret env files). Fails if `path`
/// already exists (callers pass a freshly-minted unique path).
pub(crate) fn create_private_dir(path: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        std::fs::DirBuilder::new().mode(0o700).create(path)
    }
    #[cfg(not(unix))]
    {
        std::fs::create_dir(path)
    }
}

/// Create `path` as a fresh file with mode `0600` set ATOMICALLY at creation
/// (via `open(O_CREAT | O_EXCL, 0600)`) and write `contents`, so the file is
/// never briefly world-readable (`0644`) before a follow-up `chmod` - closing
/// the local-read window on secret material (PR #254 review). `create_new`
/// guarantees this process is the creator; callers pass a path inside a fresh
/// `0700` dir, so there is no pre-existing file to clobber.
pub(crate) fn write_private_file(path: &Path, contents: &[u8]) -> Result<()> {
    use std::io::Write;
    let mut file = {
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            std::fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(path)?
        }
        #[cfg(not(unix))]
        {
            std::fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(path)?
        }
    };
    file.write_all(contents)?;
    Ok(())
}

/// Build the `docker run` argv for a bare, credential-free container:
/// `docker run -d --name <c> --workdir <wd> <image> sleep infinity`.
///
/// Deliberately carries NO `-v` flags for credentials (docker-out-of-docker
/// fix): a sibling `-v host:container` bind mount is resolved by the OUTER
/// daemon against its own filesystem, which cannot see this driver's own
/// staging dir when the driver itself runs inside a container. Credentials
/// are pushed in afterwards over `docker exec` - see
/// `auth::stage_into_container`. Pure (no I/O) so it can be asserted on
/// without a docker daemon; see `tests/cred_transfer.rs`.
pub fn build_docker_run_argv(
    container: &str,
    workdir: &str,
    image: &str,
    env_vars: &[(String, String)],
) -> Vec<String> {
    let mut argv = vec![
        "run".to_string(),
        "-d".to_string(),
        "--name".to_string(),
        container.to_string(),
        "--workdir".to_string(),
        workdir.to_string(),
    ];
    for (name, value) in env_vars {
        argv.push("-e".to_string());
        argv.push(format!("{name}={value}"));
    }
    argv.extend([
        image.to_string(),
        "sleep".to_string(),
        "infinity".to_string(),
    ]);
    argv
}

/// Substrings docker/tmux emit when the workspace target itself is GONE
/// (OOM-killed, `docker rm`'d, stopped, tmux session vanished) rather than a
/// transient capture hiccup while the container is still alive. Matched
/// case-insensitively against a failed exec's error message so the readiness
/// pollers can break out immediately instead of spinning the full
/// startup/await deadline and then reporting a misleading generic timeout (a
/// "degraded" workspace that actually masks a hard container death).
///
/// Deliberately EXCLUDED: "cannot connect to the Docker daemon" / generic
/// "error connecting to" - those signal a transient daemon or socket outage,
/// NOT a dead container (the container is very likely still running once the
/// daemon recovers). Treating them as death would abort a live workspace on
/// a blip; they stay on the retry path and are bounded by the overall
/// deadline. Mirrors Python's `_CONTAINER_DEAD_STDERR_MARKERS` (PY:1637-1652).
const CONTAINER_DEAD_STDERR_MARKERS: &[&str] = &[
    "no such container",
    "is not running",
    "no server running", // tmux daemon gone
    "no such session",   // tmux session vanished
    "can't find session",
];

/// Return a human-readable reason if `err` indicates the workspace target is
/// GONE, else `None`. Mirrors Python's `_container_death_reason`
/// (PY:1653-1666).
///
/// A timed-out capture (`run_bounded`'s `ErrorKind::TimedOut`, mirroring
/// Python's `TimeoutExpired`) is always treated as transient - the container
/// may just be slow this once. Only a failed exec whose error text names a
/// dead container / tmux server / tmux session counts as death. This lets
/// the readiness pollers distinguish "one failed capture while still alive"
/// (keep retrying) from "the container died" (stop now, surface the real
/// error) instead of blindly polling until the deadline.
fn container_death_reason(err: &Error) -> Option<String> {
    if err.kind() == ErrorKind::TimedOut {
        return None;
    }
    let msg = err.to_string();
    let low = msg.to_lowercase();
    for marker in CONTAINER_DEAD_STDERR_MARKERS {
        if low.contains(marker) {
            let trimmed = msg.trim();
            return Some(if trimmed.is_empty() {
                (*marker).to_string()
            } else {
                trimmed.to_string()
            });
        }
    }
    None
}

/// Outcome of classifying a single poll's pane-capture attempt. Pure (no
/// I/O, no sleeping) so the await/startup poll loops' resilience logic can
/// be unit tested without a docker daemon - see `tests/poll_resilience.rs`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PollStep {
    /// Capture succeeded; caller evaluates readiness against this pane text.
    Captured(String),
    /// Capture failed but looks transient (container still alive) - keep
    /// polling within the overall deadline instead of aborting.
    Retry,
    /// Capture failed because the workspace target itself is gone.
    Dead(String),
}

/// Classify one `tmux::capture_pane` result into a `PollStep`. Mirrors the
/// try/except branch structure of Python's `_wait_for_started`/
/// `await_completion` (PY:1962-1987, PY:2110-2138): success -> `Captured`,
/// a death marker -> `Dead`, anything else (including a timed-out capture)
/// -> `Retry`.
pub fn classify_poll(capture: Result<String>) -> PollStep {
    match capture {
        Ok(pane) => PollStep::Captured(pane),
        Err(e) => match container_death_reason(&e) {
            Some(reason) => PollStep::Dead(reason),
            None => PollStep::Retry,
        },
    }
}

/// Run `cmd` bounded by `DEFAULT_RUN_TIMEOUT_S` (PY:87) - used for `docker
/// run` / `docker rm -f`, which get a longer bound than the 15s exec/tmux
/// default since image pulls and container teardown can legitimately take
/// longer than a single `docker exec`.
fn run_capture(cmd: Command, what: &str) -> Result<Output> {
    let out = tmux::run_bounded(cmd, Duration::from_secs_f64(tmux::DEFAULT_RUN_TIMEOUT_S))?;
    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr);
        return Err(Error::other(format!(
            "{what} failed (exit {}): {stderr}",
            out.status
        )));
    }
    Ok(out)
}

impl Workspace {
    #[allow(clippy::needless_pass_by_value)]
    pub fn start(opts: StartOptions) -> Result<Self> {
        let has_any_secret_env = opts.secret_env.values().any(|m| !m.is_empty());
        if opts.host_auth.values().all(Option::is_none) && !has_any_secret_env {
            return Err(Error::new(
                ErrorKind::InvalidInput,
                "start_workspace called with no enabled agents (no host_auth and no secret_env)",
            ));
        }

        let container = opts
            .container_name
            .clone()
            .unwrap_or_else(|| format!("interactive-tmux-{}-{}", opts.name, random_suffix()));
        let throwaway = {
            let base = std::env::temp_dir();
            let mut path = base.join(format!(
                "interactive-tmux-{}-{}",
                opts.name,
                random_suffix()
            ));
            // Make sure we don't collide: if it exists (extremely unlikely),
            // append more entropy until we get a fresh dir.
            while path.exists() {
                path = base.join(format!(
                    "interactive-tmux-{}-{}",
                    opts.name,
                    random_suffix()
                ));
            }
            // Create the throwaway dir 0700 at creation (it holds the staged
            // 0600 secret env files) - no brief world-traversable window.
            create_private_dir(&path)?;
            path
        };

        let auth_ctx = AuthContext {
            workdir: opts.workdir.clone(),
            throwaway_dir: throwaway.clone(),
            host_claude_dotjson: opts.host_claude_dotjson.clone(),
            claude_omit_credentials: opts.claude_omit_credentials,
        };

        // Everything between creating `throwaway` and the Workspace taking
        // ownership of it (the `Self { .. }` below, whose stop() removes it)
        // must clean up the staged credential copies on failure; otherwise
        // a failed `docker run` (or a bad host auth dir) leaks auth
        // material under the temp dir.
        let provision = (|| -> Result<(Vec<Agent>, HashMap<Agent, String>)> {
            let mut enabled: Vec<Agent> = Vec::new();
            let mut prepared_by_agent: Vec<PreparedAuth> = Vec::new();
            for agent in adapter::AGENTS {
                let host_src = opts.host_auth.get(&agent).cloned().flatten();
                let has_secret_env = opts.secret_env.get(&agent).is_some_and(|m| !m.is_empty());
                let prepared = match host_src.as_ref() {
                    Some(src) => auth::prepare(agent, src, &auth_ctx)?,
                    None => PreparedAuth::default(),
                };
                // An agent is enabled if it has staged credential files OR a
                // non-empty secret env (the OAuth/API-key env-var path, R1/R2).
                if prepared.is_empty() && !has_secret_env {
                    continue;
                }
                enabled.push(agent);
                if !prepared.is_empty() {
                    prepared_by_agent.push(prepared);
                }
            }

            if enabled.is_empty() {
                return Err(Error::new(
                    ErrorKind::InvalidInput,
                    "start_workspace called with no enabled agents (no host_auth and no secret_env)",
                ));
            }

            // Provision a bare, credential-free container (docker-out-of-
            // docker fix - see `build_docker_run_argv` and module docs on
            // `auth::stage_into_container`).
            let argv =
                build_docker_run_argv(&container, &opts.workdir, &opts.image, &opts.env_vars);
            let mut run = Command::new("docker");
            run.args(&argv);
            run_capture(run, "docker run")?;

            // Container is up; push each agent's staged credentials into it
            // over `docker exec` and lock down ownership/permissions
            // in-container (PY:1850-1869, PY:1566-1583).
            for prepared in &prepared_by_agent {
                auth::stage_into_container(&container, prepared)?;
            }

            // Stage per-agent secret env files (R1). Each is created 0600 at
            // creation (atomic, no brief 0644 window) and transferred via the
            // SAME base64-over-stdin path as credentials - the values never
            // touch argv. The in-container file is re-secured to 0600 by
            // `secure_path_plan`. Record the container path so the launch step
            // sources it.
            let mut secret_env_files: HashMap<Agent, String> = HashMap::new();
            for &agent in &enabled {
                let Some(env) = opts.secret_env.get(&agent).filter(|m| !m.is_empty()) else {
                    continue;
                };
                let container_path = format!("/home/agent/.itmux-secret-env-{}", agent.as_str());
                let host_file = throwaway.join(format!("secret-env-{}", agent.as_str()));
                write_private_file(&host_file, secret_env::render_env_file(env).as_bytes())?;
                let staged = PreparedAuth(vec![StagedPath {
                    host: host_file.clone(),
                    container: container_path.clone(),
                }]);
                auth::stage_into_container(&container, &staged)?;
                // Secret hygiene: the container now holds its own 0600 copy, so
                // remove the host copy immediately rather than waiting for
                // teardown - the plaintext secret should linger on the host for
                // the shortest possible time. Best-effort; teardown's
                // `remove_dir_all(throwaway)` is the fallback.
                let _ = fs::remove_file(&host_file);
                secret_env_files.insert(agent, container_path);
            }
            Ok((enabled, secret_env_files))
        })();
        let (enabled, secret_env_files) = match provision {
            Ok(result) => result,
            Err(e) => {
                // Best-effort: `docker run -d` (or the credential transfer
                // that follows it) can fail after the container is
                // created, so remove it too. Bounded by
                // `DEFAULT_RUN_TIMEOUT_S` like every other docker/tmux
                // shell-out - cleanup must not be able to hang forever.
                let mut rm = Command::new("docker");
                rm.args(["rm", "-f", &container]);
                let _ = tmux::run_bounded(rm, Duration::from_secs_f64(tmux::DEFAULT_RUN_TIMEOUT_S));
                let _ = fs::remove_dir_all(&throwaway);
                return Err(e);
            }
        };

        let mut ws = Self {
            name: opts.name.clone(),
            container: container.clone(),
            image: opts.image.clone(),
            workdir: opts.workdir.clone(),
            tmux_size: opts.tmux_size,
            host_throwaway_dir: throwaway,
            enabled_agents: enabled,
            startup_status: HashMap::new(),
            claude_plugin_dirs: opts.claude_plugin_dirs.clone(),
            secret_env_files,
        };
        if let Err(e) = ws.bootstrap_tmux_and_launch(opts.startup_timeout_s, opts.strict_startup) {
            let _ = ws.stop();
            return Err(e);
        }
        Ok(ws)
    }

    fn bootstrap_tmux_and_launch(
        &mut self,
        startup_timeout_s: f64,
        strict_startup: bool,
    ) -> Result<()> {
        let (cols, rows) = self.tmux_size;
        let first = self.enabled_agents[0];
        tmux::new_session(&self.container, first.window(), cols, rows)?;
        for &agent in self.enabled_agents.iter().skip(1) {
            tmux::new_window(&self.container, agent.window())?;
        }

        let plugin_dirs = self.claude_plugin_dirs.clone();
        for &agent in &self.enabled_agents.clone() {
            let secret_env_file = self.secret_env_files.get(&agent).map(String::as_str);
            adapter::launch_in_window(&self.container, agent, &plugin_dirs, secret_env_file)?;
            let result = self.wait_for_started(agent, startup_timeout_s);
            self.startup_status.insert(agent, result);
        }

        let failed: Vec<Agent> = self
            .startup_status
            .iter()
            .filter(|(_, r)| !r.ready)
            .map(|(a, _)| *a)
            .collect();
        if !failed.is_empty() && strict_startup {
            return Err(Error::new(
                ErrorKind::TimedOut,
                format!(
                    "start_workspace: per-agent readiness failed for {:?}",
                    failed.iter().map(|a| a.as_str()).collect::<Vec<_>>()
                ),
            ));
        }
        Ok(())
    }

    fn wait_for_started(&self, agent: Agent, timeout_s: f64) -> AwaitResult {
        let start = Instant::now();
        let deadline = start + Duration::from_secs_f64(timeout_s);
        let mut pane = String::new();
        while Instant::now() < deadline {
            match classify_poll(tmux::capture_pane(&self.container, agent.window())) {
                PollStep::Captured(p) => {
                    // D-block-2 fix (Syntropic137 stress): predicate runs
                    // against the bottom-of-pane tail so historical text
                    // in the now-included scrollback can't fool absence
                    // checks like `"esc to interrupt" not in pane`.
                    let tail = tmux::pane_tail(&p, self.tmux_size.1 as usize);
                    if adapter::is_started(agent, &tail) {
                        let elapsed = start.elapsed().as_secs_f64() * 1000.0;
                        return AwaitResult::ready(elapsed, 1, p);
                    }
                    pane = p;
                }
                PollStep::Dead(reason) => {
                    let elapsed = start.elapsed().as_secs_f64() * 1000.0;
                    return AwaitResult::container_dead(elapsed, 0, pane, reason);
                }
                PollStep::Retry => {
                    // Phase 3 (PY:1962-1987): a single wedged/failed capture
                    // while the container is still alive must not abort the
                    // whole wait - keep polling until the overall deadline.
                }
            }
            thread::sleep(Duration::from_millis(500));
        }
        let elapsed = start.elapsed().as_secs_f64() * 1000.0;
        AwaitResult::timeout_never_ready(elapsed, pane)
    }

    // -----------------------------------------------------------------------
    // Public primitives

    pub fn check_agent(&self, agent: Agent) -> Result<()> {
        if self.enabled_agents.contains(&agent) {
            Ok(())
        } else {
            Err(Error::new(
                ErrorKind::InvalidInput,
                format!(
                    "agent {:?} not enabled (enabled: {:?})",
                    agent.as_str(),
                    self.enabled_agents
                        .iter()
                        .map(|a| a.as_str())
                        .collect::<Vec<_>>()
                ),
            ))
        }
    }

    pub fn send_message(&self, agent: Agent, text: &str) -> Result<()> {
        self.check_agent(agent)?;
        adapter::submit(&self.container, agent, text)
    }

    pub fn await_completion(
        &self,
        agent: Agent,
        timeout: f64,
        stable_polls: u32,
        poll_interval: f64,
        warmup: f64,
    ) -> Result<AwaitResult> {
        self.check_agent(agent)?;
        let start = Instant::now();
        let deadline = start + Duration::from_secs_f64(timeout);
        thread::sleep(Duration::from_secs_f64(warmup));
        // D-block-2 + D-block-3 fix (Syntropic137 stress): the readiness
        // predicate AND the stability comparison both operate on the
        // bottom-of-pane tail. Stability on the full scrollback buffer
        // would fail forever - any new response token appended changes
        // the buffer, even when the live TUI window has settled.
        // Comparing tails matches the pre-fix "visible window" semantics
        // on the full-history capture introduced by `-S - -E -`.
        let mut last_tail: Option<String> = None;
        let mut consecutive_stable_ready: u32 = 0;
        let mut ever_ready = false;
        let mut pane = String::new();
        while Instant::now() < deadline {
            match classify_poll(tmux::capture_pane(&self.container, agent.window())) {
                PollStep::Captured(p) => {
                    pane = p;
                    let tail = tmux::pane_tail(&pane, self.tmux_size.1 as usize);
                    if adapter::is_ready(agent, &tail) {
                        ever_ready = true;
                        if last_tail.as_deref() == Some(&tail) {
                            consecutive_stable_ready += 1;
                            if consecutive_stable_ready >= stable_polls {
                                let elapsed = start.elapsed().as_secs_f64() * 1000.0;
                                return Ok(AwaitResult::ready(
                                    elapsed,
                                    consecutive_stable_ready,
                                    pane,
                                ));
                            }
                        } else {
                            consecutive_stable_ready = 0;
                        }
                    } else {
                        consecutive_stable_ready = 0;
                    }
                    last_tail = Some(tail);
                }
                PollStep::Dead(reason) => {
                    let elapsed = start.elapsed().as_secs_f64() * 1000.0;
                    return Ok(AwaitResult::container_dead(
                        elapsed,
                        consecutive_stable_ready,
                        pane,
                        reason,
                    ));
                }
                PollStep::Retry => {
                    // Phase 3 (PY:2110-2138): a single failed/wedged poll
                    // (container still alive) must not abort the whole
                    // await - treat it as "not ready this round" and keep
                    // polling until the overall deadline above.
                    consecutive_stable_ready = 0;
                    last_tail = None;
                }
            }
            thread::sleep(Duration::from_secs_f64(poll_interval));
        }
        let elapsed = start.elapsed().as_secs_f64() * 1000.0;
        Ok(if ever_ready {
            AwaitResult::timeout_unstable(elapsed, consecutive_stable_ready, pane)
        } else {
            AwaitResult::timeout_never_ready(elapsed, pane)
        })
    }

    pub fn capture_response(&self, agent: Agent) -> Result<String> {
        self.check_agent(agent)?;
        tmux::capture_pane(&self.container, agent.window())
    }

    /// Shell out to `docker exec <container> <argv...>`. Not in the Python
    /// driver's public API but useful for the smoke harness (verifying the
    /// container is alive without going through tmux).
    pub fn exec(&self, argv: &[&str]) -> Result<Output> {
        if argv.is_empty() {
            return Err(Error::new(
                ErrorKind::InvalidInput,
                "exec called with empty argv",
            ));
        }
        tmux::docker_exec(&self.container, argv)
    }

    pub fn stop(&self) -> Result<()> {
        // Best-effort `docker rm -f` + rm of throwaway dir. Matches Python's
        // `subprocess.run(check=False)` semantics, bounded by
        // `DEFAULT_RUN_TIMEOUT_S` like every other docker/tmux shell-out.
        let mut rm = Command::new("docker");
        rm.args(["rm", "-f", &self.container]);
        let _ = tmux::run_bounded(rm, Duration::from_secs_f64(tmux::DEFAULT_RUN_TIMEOUT_S));
        let _ = fs::remove_dir_all(&self.host_throwaway_dir);
        Ok(())
    }

    pub fn to_record(&self) -> WorkspaceRecord {
        WorkspaceRecord {
            name: self.name.clone(),
            container: self.container.clone(),
            image: self.image.clone(),
            workdir: self.workdir.clone(),
            tmux_size: [self.tmux_size.0, self.tmux_size.1],
            host_throwaway_dir: self.host_throwaway_dir.to_string_lossy().into_owned(),
            enabled_agents: self
                .enabled_agents
                .iter()
                .map(|a| a.as_str().to_string())
                .collect(),
        }
    }

    pub fn from_record(record: &WorkspaceRecord) -> Result<Self> {
        let mut enabled = Vec::with_capacity(record.enabled_agents.len());
        for a in &record.enabled_agents {
            let agent = Agent::parse(a)
                .ok_or_else(|| Error::new(ErrorKind::InvalidData, format!("unknown agent: {a}")))?;
            enabled.push(agent);
        }
        Ok(Self {
            name: record.name.clone(),
            container: record.container.clone(),
            image: record.image.clone(),
            workdir: record.workdir.clone(),
            tmux_size: (record.tmux_size[0], record.tmux_size[1]),
            host_throwaway_dir: PathBuf::from(&record.host_throwaway_dir),
            enabled_agents: enabled,
            startup_status: HashMap::new(),
            // `claude_plugin_dirs` lives on the in-memory `StartOptions` /
            // `Workspace`; it's not persisted in the registry (the launch
            // already happened by the time we save). Restored as empty so
            // re-launches via load_from_registry don't accidentally drop
            // or duplicate plugin flags.
            claude_plugin_dirs: Vec::new(),
            // Secret env files are staged at start time and not persisted in
            // the registry (the launch already happened by the time we save).
            secret_env_files: HashMap::new(),
        })
    }

    pub fn save_to_registry(&self) -> Result<()> {
        registry::save(&self.to_record())
    }

    pub fn load_from_registry(name: &str) -> Result<Self> {
        let rec = registry::load(name)?;
        Self::from_record(&rec)
    }
}

#[cfg(all(test, unix))]
mod secret_mode_tests {
    //! PR #254 review: the mode guarantee on host-side secret files/dirs must
    //! be load-bearing. These drive the REAL creation helpers used by
    //! `Workspace::start` (factored out so they are testable without docker)
    //! and assert the mode is restrictive AT creation.

    use super::{create_private_dir, write_private_file};
    use std::os::unix::fs::PermissionsExt;

    fn unique_base(tag: &str) -> std::path::PathBuf {
        std::env::temp_dir().join(format!(
            "itmux-secret-mode-{tag}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    #[test]
    fn private_dir_is_0700_and_private_file_is_0600() {
        let dir = unique_base("dir");
        create_private_dir(&dir).expect("create 0700 dir");
        let dir_mode = std::fs::metadata(&dir).unwrap().permissions().mode() & 0o777;
        assert_eq!(dir_mode, 0o700, "throwaway dir must be 0700 at creation");

        // A staged secret env file inside it - the exact path shape
        // `Workspace::start` uses.
        let file = dir.join("secret-env-claude");
        write_private_file(&file, b"CLAUDE_CODE_OAUTH_TOKEN='tok'\n").expect("write 0600 file");
        let file_mode = std::fs::metadata(&file).unwrap().permissions().mode() & 0o777;
        assert_eq!(file_mode, 0o600, "secret env file must be 0600 at creation");
        assert_eq!(
            std::fs::read_to_string(&file).unwrap(),
            "CLAUDE_CODE_OAUTH_TOKEN='tok'\n"
        );

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn write_private_file_refuses_to_clobber_existing() {
        let dir = unique_base("clobber");
        create_private_dir(&dir).unwrap();
        let file = dir.join("secret");
        write_private_file(&file, b"first").unwrap();
        // create_new(true): a second create must fail rather than truncate a
        // file whose mode we did not set.
        let err = write_private_file(&file, b"second").unwrap_err();
        assert_eq!(err.kind(), std::io::ErrorKind::AlreadyExists);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
