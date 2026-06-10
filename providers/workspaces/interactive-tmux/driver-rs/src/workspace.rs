//! Workspace lifecycle: `docker run`, tmux bootstrap, per-agent launch +
//! readiness gating, public primitives (send/await/capture/exec/stop).

use std::collections::HashMap;
use std::fs;
use std::io::{Error, ErrorKind, Result};
use std::path::PathBuf;
use std::process::{Command, Output};
use std::thread;
use std::time::{Duration, Instant};

use crate::adapter::{self, Agent};
use crate::auth::{self, AuthContext, Mount};
use crate::registry::{self, WorkspaceRecord};
use crate::result::AwaitResult;
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
}

fn random_suffix() -> String {
    // 8 hex chars from a non-crypto seed mix (no `rand` dep). Mirrors the
    // Python `uuid.uuid4().hex[:8]` slot — used only for container naming.
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

fn run_capture(cmd: &mut Command, what: &str) -> Result<Output> {
    let out = cmd.output()?;
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
        if opts.host_auth.values().all(Option::is_none) {
            return Err(Error::new(
                ErrorKind::InvalidInput,
                "start_workspace called with no enabled agents (host_auth empty)",
            ));
        }

        let container = format!("interactive-tmux-{}-{}", opts.name, random_suffix());
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
            fs::create_dir_all(&path)?;
            path
        };

        let auth_ctx = AuthContext {
            workdir: opts.workdir.clone(),
            throwaway_dir: throwaway.clone(),
            host_claude_dotjson: opts.host_claude_dotjson.clone(),
        };

        let mut enabled: Vec<Agent> = Vec::new();
        let mut mounts: Vec<Mount> = Vec::new();
        for agent in adapter::AGENTS {
            let Some(Some(src)) = opts.host_auth.get(&agent) else {
                continue;
            };
            let prepared = auth::prepare(agent, src, &auth_ctx)?;
            if prepared.is_empty() {
                continue;
            }
            enabled.push(agent);
            mounts.extend(prepared);
        }

        if enabled.is_empty() {
            let _ = fs::remove_dir_all(&throwaway);
            return Err(Error::new(
                ErrorKind::InvalidInput,
                "start_workspace called with no enabled agents (host_auth empty)",
            ));
        }

        // docker run -d --name <c> --workdir <wd> [-v host:container ...] <image> sleep infinity
        let mut run = Command::new("docker");
        run.args([
            "run",
            "-d",
            "--name",
            &container,
            "--workdir",
            &opts.workdir,
        ]);
        for m in &mounts {
            run.arg("-v").arg(m.as_docker_arg());
        }
        run.arg(&opts.image).args(["sleep", "infinity"]);
        run_capture(&mut run, "docker run")?;

        let mut ws = Self {
            name: opts.name.clone(),
            container: container.clone(),
            image: opts.image.clone(),
            workdir: opts.workdir.clone(),
            tmux_size: opts.tmux_size,
            host_throwaway_dir: throwaway,
            enabled_agents: enabled,
            startup_status: HashMap::new(),
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

        for &agent in &self.enabled_agents.clone() {
            adapter::launch_in_window(&self.container, agent)?;
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
            match tmux::capture_pane(&self.container, agent.window()) {
                Ok(p) => {
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
                Err(e) => {
                    let elapsed = start.elapsed().as_secs_f64() * 1000.0;
                    return AwaitResult::error(elapsed, pane, e.to_string());
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
        // would fail forever — any new response token appended changes
        // the buffer, even when the live TUI window has settled.
        // Comparing tails matches the pre-fix "visible window" semantics
        // on the full-history capture introduced by `-S - -E -`.
        let mut last_tail: Option<String> = None;
        let mut consecutive_stable_ready: u32 = 0;
        let mut ever_ready = false;
        let mut pane = String::new();
        while Instant::now() < deadline {
            pane = tmux::capture_pane(&self.container, agent.window())?;
            let tail = tmux::pane_tail(&pane, self.tmux_size.1 as usize);
            if adapter::is_ready(agent, &tail) {
                ever_ready = true;
                if last_tail.as_deref() == Some(&tail) {
                    consecutive_stable_ready += 1;
                    if consecutive_stable_ready >= stable_polls {
                        let elapsed = start.elapsed().as_secs_f64() * 1000.0;
                        return Ok(AwaitResult::ready(elapsed, consecutive_stable_ready, pane));
                    }
                } else {
                    consecutive_stable_ready = 0;
                }
            } else {
                consecutive_stable_ready = 0;
            }
            last_tail = Some(tail);
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
        // `subprocess.run(check=False)` semantics.
        let _ = Command::new("docker")
            .args(["rm", "-f", &self.container])
            .output();
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
