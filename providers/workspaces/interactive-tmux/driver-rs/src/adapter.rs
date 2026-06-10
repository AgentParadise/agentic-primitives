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

/// Launch the agent CLI in its tmux window and walk init gates.
///
/// Per ANALYTICS.md §4:
/// * Claude: `claude` + Enter.
/// * Codex:  `codex --no-alt-screen` + Enter, then `1` Enter (trust banner),
///   then Escape (hooks-review modal).
/// * Gemini: `gemini` + Enter.
pub fn launch_in_window(container: &str, agent: Agent) -> std::io::Result<()> {
    match agent {
        Agent::Claude => {
            tmux::send_keys(container, agent.window(), &["claude", "Enter"])?;
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
