//! Per-agent adapters encoding the EXP-01..04 + ANALYTICS.md §4 matrix.
//!
//! Each adapter is a pure module with three responsibilities:
//!
//! * `launch_in_window` — tmux send-keys to start the CLI and walk init gates.
//! * `submit` — encode the per-CLI submit pattern (the part that varies).
//! * `is_ready` / `is_started` — readiness heuristics over a captured pane.
//!
//! Auth-mount preparation lives in `crate::auth` so the readiness logic can
//! be unit-tested without touching the filesystem.

use std::fmt;
use std::sync::OnceLock;
use std::thread;
use std::time::Duration;

use regex::Regex;

use crate::tmux;

/// Agent identifier — restricted to the three CLIs the matrix covers.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Agent {
    Claude,
    Codex,
    Gemini,
}

pub const AGENTS: [Agent; 3] = [Agent::Claude, Agent::Codex, Agent::Gemini];

impl Agent {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Claude => "claude",
            Self::Codex => "codex",
            Self::Gemini => "gemini",
        }
    }

    /// tmux window name (1:1 with the agent name in the Python driver).
    pub const fn window(self) -> &'static str {
        self.as_str()
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "claude" => Some(Self::Claude),
            "codex" => Some(Self::Codex),
            "gemini" => Some(Self::Gemini),
            _ => None,
        }
    }

    /// Per-CLI response marker — the glyph the TUI prefixes onto a model
    /// reply (vs. an echoed user prompt). Used by smoke harnesses to
    /// distinguish the reply from the echo. Matches Python adapter constants.
    pub const fn response_marker(self) -> &'static str {
        match self {
            Self::Claude => "● ",
            Self::Codex => "• ",
            Self::Gemini => "✦ ",
        }
    }
}

impl fmt::Display for Agent {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

// ---------------------------------------------------------------------------
// Readiness predicates (pure — unit-tested with fixture pane captures)

/// Claude empty-prompt line predicate — `^❯\s*$` per Python `_CLAUDE_EMPTY_PROMPT_RE`.
fn claude_empty_prompt_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?m)^❯\s*$").expect("claude empty-prompt regex compiles"))
}

/// EXP-01 FRICTION F-5 three-signal post-turn readiness heuristic:
///
/// 1. `esc to interrupt` absent (no generation in progress)
/// 2. `? for shortcuts` present (steady-state TUI footer, not a modal)
/// 3. `^❯\s*$` matches somewhere (empty prompt line — input box ready)
pub fn claude_is_ready(pane: &str) -> bool {
    !pane.contains("esc to interrupt")
        && pane.contains("? for shortcuts")
        && claude_empty_prompt_re().is_match(pane)
}

/// Looser startup predicate — accepts the welcome screen where `❯ Try …`
/// shows a placeholder instead of an empty prompt. Matches Python
/// `_ClaudeAdapter.is_started`.
pub fn claude_is_started(pane: &str) -> bool {
    !pane.contains("esc to interrupt") && pane.contains("? for shortcuts") && pane.contains('❯')
}

/// EXP-02 codex readiness: NOT `• Working` AND ( `› ` OR `Write tests for` OR `Tip:` ).
/// Mirrors `_CodexAdapter.is_ready` exactly.
pub fn codex_is_ready(pane: &str) -> bool {
    if pane.contains("• Working") {
        return false;
    }
    pane.contains("› ") || pane.contains("Write tests for") || pane.contains("Tip:")
}

pub fn codex_is_started(pane: &str) -> bool {
    codex_is_ready(pane)
}

/// EXP-03 gemini readiness: idle prompt visible AND no `Thinking...` /
/// `esc to cancel` indicators. Mirrors `_GeminiAdapter.is_ready` exactly.
pub fn gemini_is_ready(pane: &str) -> bool {
    if pane.contains("Thinking...") || pane.contains("esc to cancel") {
        return false;
    }
    pane.contains("Type your message")
}

pub fn gemini_is_started(pane: &str) -> bool {
    gemini_is_ready(pane)
}

pub fn is_ready(agent: Agent, pane: &str) -> bool {
    match agent {
        Agent::Claude => claude_is_ready(pane),
        Agent::Codex => codex_is_ready(pane),
        Agent::Gemini => gemini_is_ready(pane),
    }
}

pub fn is_started(agent: Agent, pane: &str) -> bool {
    match agent {
        Agent::Claude => claude_is_started(pane),
        Agent::Codex => codex_is_started(pane),
        Agent::Gemini => gemini_is_started(pane),
    }
}

// ---------------------------------------------------------------------------
// Launch + submit (the per-agent matrix)

/// Build the shell command this driver sends to tmux to launch `claude`.
///
/// `plugin_dirs` is a list of container-side paths to load as Claude Code
/// plugin dirs (one `--plugin-dir` flag per entry). Paths are shell-quoted
/// with `shell_quote` below so directory names with spaces survive the
/// tmux send-keys path. When the list is empty, returns the bare `"claude"`
/// — identical to the pre-plugins behaviour.
///
/// Exposed for unit tests so they can assert the flags land verbatim
/// without spawning a container. Mirrors `launch_in_window`'s string
/// construction one-to-one.
///
/// Surfaced by Syntropic137's workflow-skills bridge experiment
/// (`docs/plans/workflow-skills.md` §9): `~/.claude.json`
/// `installedPlugins` injection is silently ignored by the TUI; only
/// `--plugin-dir` is honoured.
pub fn claude_launch_command(plugin_dirs: &[std::path::PathBuf]) -> String {
    if plugin_dirs.is_empty() {
        return "claude".to_string();
    }
    let mut parts: Vec<String> = vec!["claude".to_string()];
    for p in plugin_dirs {
        parts.push("--plugin-dir".to_string());
        parts.push(shell_quote(&p.display().to_string()));
    }
    parts.join(" ")
}

/// Single-quote `s` if it contains characters that need shell escaping.
/// Empty strings are quoted as `''`. Mirrors Python's `shlex.quote`
/// behaviour for the small set of characters this driver actually emits.
fn shell_quote(s: &str) -> String {
    if s.is_empty() {
        return "''".to_string();
    }
    let safe = s
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || matches!(c, '/' | '_' | '-' | '.' | ':' | '@' | ','));
    if safe {
        s.to_string()
    } else {
        // Escape embedded single quotes by closing/escaping/reopening.
        let escaped = s.replace('\'', "'\\''");
        format!("'{escaped}'")
    }
}

/// Launch the agent CLI in its tmux window and walk init gates.
///
/// Per ANALYTICS.md §4:
/// * Claude: `claude` + Enter (with optional `--plugin-dir <path>` flags).
/// * Codex:  `codex --no-alt-screen` + Enter, then `1` Enter (trust banner),
///   then Escape (hooks-review modal).
/// * Gemini: `gemini` + Enter.
///
/// `claude_plugin_dirs` only affects the claude window; codex/gemini ignore
/// it (no equivalent `--plugin-dir` flag).
pub fn launch_in_window(
    container: &str,
    agent: Agent,
    claude_plugin_dirs: &[std::path::PathBuf],
) -> std::io::Result<()> {
    match agent {
        Agent::Claude => {
            let cmd = claude_launch_command(claude_plugin_dirs);
            if claude_plugin_dirs.is_empty() {
                // Bare `claude` + Enter — preserves the pre-plugins keystroke
                // sequence exactly so the smoke fixtures stay byte-equal.
                tmux::send_keys(container, agent.window(), &["claude", "Enter"])?;
            } else {
                // `claude --plugin-dir P1 --plugin-dir P2 ...` — sent literal
                // so the spaces survive tmux's argument tokenizer; then Enter.
                tmux::send_literal(container, agent.window(), &cmd)?;
                tmux::send_keys(container, agent.window(), &["Enter"])?;
            }
        }
        Agent::Codex => {
            tmux::send_keys(
                container,
                agent.window(),
                &["codex --no-alt-screen", "Enter"],
            )?;
            thread::sleep(Duration::from_secs(2));
            tmux::send_keys(container, agent.window(), &["1", "Enter"])?;
            thread::sleep(Duration::from_secs(1));
            tmux::send_keys(container, agent.window(), &["Escape"])?;
            thread::sleep(Duration::from_secs(1));
        }
        Agent::Gemini => {
            tmux::send_keys(container, agent.window(), &["gemini", "Enter"])?;
            thread::sleep(Duration::from_secs(1));
        }
    }
    Ok(())
}

/// Submit `text` using the per-agent matrix.
///
/// Per ANALYTICS.md §4:
/// * Claude: `send-keys -l <text>` then `send-keys Enter` (two-step Enter).
/// * Codex:  `send-keys -l <text>` then `send-keys C-j C-m` (first-send gotcha).
/// * Gemini: `send-keys -l <text>` then `send-keys Enter` — NEVER `C-m`.
pub fn submit(container: &str, agent: Agent, text: &str) -> std::io::Result<()> {
    let window = agent.window();
    tmux::send_literal(container, window, text)?;
    match agent {
        Agent::Claude | Agent::Gemini => tmux::send_keys(container, window, &["Enter"]),
        Agent::Codex => tmux::send_keys(container, window, &["C-j", "C-m"]),
    }
}
