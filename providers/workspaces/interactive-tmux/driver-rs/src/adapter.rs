//! Per-agent adapters encoding the EXP-01..04 + ANALYTICS.md §4 matrix.
//!
//! Each adapter is a pure module with four responsibilities:
//!
//! * `launch_in_window` — tmux send-keys to start the CLI and walk init gates.
//! * `submit` — encode the per-CLI submit pattern (the part that varies),
//!   including the per-harness input-readiness gate (Gap 1, below).
//! * `is_ready` / `is_started` — readiness heuristics over a captured pane.
//!
//! Auth-mount preparation lives in `crate::auth` so the readiness logic can
//! be unit-tested without touching the filesystem.
//!
//! ## Input-readiness (Gap 1 - the claude send-race)
//!
//! A live standalone eval found that `claude`, launched bare, drops the very
//! first keystrokes its TUI receives: sending the task prompt immediately
//! after launch lands nothing (the captured pane shows an empty prompt).
//! Codex tolerates the same timing because its launch dance
//! (`1`/Enter/Escape) inserts settle-steps; bare `claude` has none. Pane
//! stability ("ready") is NOT the same as the input box being ready to
//! accept keystrokes.
//!
//! The fix is a PER-HARNESS adapter concern, never a special-case in generic
//! `run` code (harness-neutrality, ADR direction / plan R8): `submit`
//! verifies the typed text actually landed in the input line (by capturing
//! the pane and checking) and re-types it (bounded retries) before pressing
//! the harness's submit key. Claude opts into this gate
//! (`needs_submit_verification`); codex/gemini keep their one-shot submit via
//! the SAME interface, so a new harness (pyagent/opencode) plugs in by
//! supplying its own `needs_submit_verification` + `input_reflects_submission`
//! answer with zero changes to callers. The generic protocol runner
//! (`run_submit_protocol`) contains NO harness-name branches beyond calling
//! these per-harness functions - all harness specifics stay in this module.

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
// Outcome detection (Gap 2 - per-harness, harness-neutral)
//
// A live eval found that deriving run success from pane LIVENESS
// (`AwaitResult.ready`) is wrong: a pane going stable only means the TUI
// settled, NOT that the task succeeded, so an idle-or-errored run reads as
// success. Outcome detection is therefore a PER-HARNESS adapter concern (like
// readiness and submit): each harness declares its own hard-error markers, and
// `detect_outcome` reports failure when one is present.
//
// KNOWN LIMIT (documented, by design): true "the task completed successfully"
// detection is NOT possible on an interactive TUI - there is no structured
// completion signal in the pane. This function is a FLOOR, not a ceiling: it
// catches hard errors (auth/API failures) and otherwise treats a clean, ready
// pane with no error markers as success. A real completion sentinel (or an
// observability-hook / JSONL completion signal) is a Plan 3 follow-up. Until
// then, "success" means "the agent settled to a ready state and emitted no
// known hard-error marker".

/// How many bottom-of-pane lines readiness is evaluated over (mirrors the
/// await loop's tail-based readiness; a full-scrollback capture would let old
/// text fool the absence checks).
pub const OUTCOME_TAIL_LINES: usize = 50;

/// A harness-aware run outcome derived from the captured pane.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RunOutcomeSignal {
    pub success: bool,
    pub reason: String,
}

// Error markers are split into two anchored kinds so the agent's OWN reply
// text cannot trigger a false hard-error (PR #247 Fix 5). A bare substring like
// `401` scanned over the whole pane would misread a task that merely DISCUSSES
// HTTP 401 (e.g. "the endpoint returns 401 on bad auth") as an auth failure.
//
// 1. BANNER phrases: distinctive multi-word error banners that indicate a hard
//    failure on their own (low false-positive risk), matched case-insensitively.
// 2. AMBIGUOUS tokens: short/common tokens (`401`, `Invalid API key`, ...) that
//    only count when they appear on a line that ALSO reads as an error line
//    (contains the word "error"), i.e. the harness's actual error-banner
//    context - not the agent's prose.

/// Claude error-banner phrases (see the note above). `401 Unauthorized` is the
/// adjacent HTTP status phrase (an auth banner), distinct from a bare `401`.
const CLAUDE_ERROR_BANNERS: [&str; 4] = [
    "API Error",
    "authentication_error",
    "Please run /login",
    "401 Unauthorized",
];

/// Claude ambiguous tokens - only a hard error when on an error line.
const CLAUDE_AMBIGUOUS_TOKENS: [&str; 2] = ["401", "Invalid API key"];

/// Codex error-banner phrases. Deliberately CONSERVATIVE and auth-focused: a
/// healthy codex launch prints benign warnings like `⚠ MCP client ... error:
/// ...` / `error: HTTP request failed` (observed in `runs/smoke-codex.txt`), so
/// a bare `error`/`failed` marker would false-positive. See report note (g):
/// codex's exact error vocabulary is less certain than claude's; widen once the
/// live codex-error pane is captured (Task 8).
const CODEX_ERROR_BANNERS: [&str; 4] = [
    "not logged in",
    "Not authenticated",
    "codex login",
    "401 Unauthorized",
];

/// Codex ambiguous tokens - only a hard error when on an error line.
const CODEX_AMBIGUOUS_TOKENS: [&str; 2] = ["401", "Invalid API key"];

/// Gemini is not a Task 5 target; no hard-error markers yet, so its outcome
/// rests purely on the readiness floor.
const GEMINI_ERROR_BANNERS: [&str; 0] = [];
const GEMINI_AMBIGUOUS_TOKENS: [&str; 0] = [];

/// The per-harness error-banner phrases. All harness specifics stay here.
pub fn error_banners(agent: Agent) -> &'static [&'static str] {
    match agent {
        Agent::Claude => &CLAUDE_ERROR_BANNERS,
        Agent::Codex => &CODEX_ERROR_BANNERS,
        Agent::Gemini => &GEMINI_ERROR_BANNERS,
    }
}

/// The per-harness ambiguous tokens (only count on an error line).
pub fn ambiguous_error_tokens(agent: Agent) -> &'static [&'static str] {
    match agent {
        Agent::Claude => &CLAUDE_AMBIGUOUS_TOKENS,
        Agent::Codex => &CODEX_AMBIGUOUS_TOKENS,
        Agent::Gemini => &GEMINI_AMBIGUOUS_TOKENS,
    }
}

/// The union of a harness's banner phrases and ambiguous tokens, for callers
/// that want the full marker vocabulary (e.g. collision guards).
pub fn error_markers(agent: Agent) -> Vec<&'static str> {
    error_banners(agent)
        .iter()
        .chain(ambiguous_error_tokens(agent))
        .copied()
        .collect()
}

/// Does `line` read as an error-banner line? The harness error banners are
/// rendered with the word "error" (claude "API Error", codex "stream error:",
/// "error: ..."), so requiring it anchors the ambiguous tokens to real banners
/// and away from the agent's prose.
fn is_error_line(line: &str) -> bool {
    line.to_lowercase().contains("error")
}

/// The first anchored hard-error marker for `agent` in `pane`, if any.
///
/// A BANNER phrase matched anywhere (case-insensitive) is a hard error; an
/// AMBIGUOUS token counts only when it appears on an error line (Fix 5).
fn first_error_marker(agent: Agent, pane: &str) -> Option<String> {
    let lower_pane = pane.to_lowercase();
    for banner in error_banners(agent) {
        if lower_pane.contains(&banner.to_lowercase()) {
            return Some(format!("error banner {banner:?}"));
        }
    }
    let tokens = ambiguous_error_tokens(agent);
    if !tokens.is_empty() {
        for line in pane.lines() {
            if !is_error_line(line) {
                continue;
            }
            let lower_line = line.to_lowercase();
            for token in tokens {
                if lower_line.contains(&token.to_lowercase()) {
                    return Some(format!("error-line token {token:?}"));
                }
            }
        }
    }
    None
}

/// Harness-aware outcome for a captured `pane` (Gap 2 floor - see the section
/// note above). A hard-error marker means failure; otherwise a pane that has
/// settled to a ready state with no error markers is treated as success.
pub fn detect_outcome(agent: Agent, pane: &str) -> RunOutcomeSignal {
    if let Some(marker) = first_error_marker(agent, pane) {
        return RunOutcomeSignal {
            success: false,
            reason: format!("harness hard-error detected ({marker})"),
        };
    }
    let tail = tmux::pane_tail(pane, OUTCOME_TAIL_LINES);
    if is_ready(agent, &tail) {
        RunOutcomeSignal {
            success: true,
            reason: "agent settled to a ready state with no error markers (liveness floor; \
                     true task-completion detection is a known interactive-TUI limit)"
                .to_string(),
        }
    } else {
        RunOutcomeSignal {
            success: false,
            reason: "agent did not settle to a ready state".to_string(),
        }
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

// ---------------------------------------------------------------------------
// Submit input-readiness (Gap 1 - per-harness, see module docs)

/// Max times claude re-types the prompt trying to land it before proceeding
/// anyway. Small: the send-race is a startup one-shot, so a healthy launch
/// lands on the first attempt and a wedged one is unlikely to recover past a
/// couple of retries.
pub const CLAUDE_SUBMIT_MAX_ATTEMPTS: u32 = 3;

/// Pause between typing the prompt and capturing the pane to check it landed,
/// giving the TUI a beat to render the keystrokes into its input box.
pub const SUBMIT_VERIFY_DELAY: Duration = Duration::from_millis(350);

/// Does this harness need its submit verified (typed text confirmed present)
/// before pressing the submit key?
///
/// PER-HARNESS by design (harness-neutrality): claude drops its first
/// keystrokes after a bare launch, so it verifies + retries. Codex settles
/// during its `1`/Enter/Escape launch dance and gemini has no observed
/// send-race, so both submit in one shot. A future harness answers this for
/// itself; no caller changes.
pub const fn needs_submit_verification(agent: Agent) -> bool {
    match agent {
        Agent::Claude => true,
        Agent::Codex | Agent::Gemini => false,
    }
}

/// The tmux `send-keys` argument(s) that submit the typed prompt, per harness.
///
/// Per ANALYTICS.md §4: claude/gemini press `Enter`; codex needs `C-j C-m`
/// (its first-send gotcha) and must NEVER get a bare `Enter`.
const fn finalize_keys(agent: Agent) -> &'static [&'static str] {
    match agent {
        Agent::Claude | Agent::Gemini => &["Enter"],
        Agent::Codex => &["C-j", "C-m"],
    }
}

/// Collapse all runs of whitespace (including newlines) to single spaces and
/// trim. The TUI wraps a long prompt across lines and pads its input box with
/// spaces, so comparing whitespace-normalised strings lets the "did it land"
/// check survive wrapping/padding without a brittle exact-layout match.
fn collapse_whitespace(s: &str) -> String {
    s.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// A distinctive, whitespace-normalised fragment of `text` used to detect
/// that the prompt landed in the input line. Uses the first non-empty line
/// (capped) so a multi-line prompt still has a stable needle, and normalises
/// whitespace so the TUI's line-wrapping of that needle does not defeat the
/// match.
///
/// Heuristic, by necessity - see the module note and the deviation write-up:
/// there is no structured "current input line" in a raw pane capture, so we
/// look for the typed text itself. Capped at 60 chars to stay well inside one
/// wrapped fragment.
pub fn submit_fragment(text: &str) -> String {
    let first_line = text.trim().lines().next().unwrap_or("").trim();
    let base = if first_line.is_empty() {
        text.trim()
    } else {
        first_line
    };
    collapse_whitespace(base).chars().take(60).collect()
}

/// Per-harness: does the captured `pane` show `text` as landed input?
///
/// PER-HARNESS seam (all specifics stay in this module): today every harness
/// answers the same way - the whitespace-normalised prompt fragment appears
/// in the whitespace-normalised pane - but routing through the agent match
/// lets a future harness override the detection (e.g. a harness whose input
/// box echoes differently) without touching `run_submit_protocol`.
///
/// An empty fragment (empty/whitespace-only prompt) is treated as trivially
/// landed - there is nothing to type, so nothing can be dropped.
pub fn input_reflects_submission(agent: Agent, pane: &str, text: &str) -> bool {
    let fragment = submit_fragment(text);
    if fragment.is_empty() {
        return true;
    }
    let haystack = collapse_whitespace(pane);
    match agent {
        Agent::Claude | Agent::Codex | Agent::Gemini => haystack.contains(&fragment),
    }
}

/// Result of running the submit protocol: how many type attempts were made
/// and whether the input was confirmed landed. For a no-verification harness
/// `verified` is always true (it does not drop keys, so there is nothing to
/// confirm) and `attempts` is 1.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SubmitOutcome {
    pub attempts: u32,
    pub verified: bool,
}

/// Generic submit protocol - the harness-NEUTRAL runner. It calls the
/// per-harness functions (`needs_submit_verification`,
/// `input_reflects_submission`) and the injected side-effect closures, but
/// contains no harness-name branches of its own, so it is fully unit-testable
/// with fakes (no docker, no tmux, no live token - keystroke landing is
/// auth-independent).
///
/// Verifying harness (claude): type -> wait -> capture -> if the prompt
/// landed, stop; else retype (bounded) - then submit. Non-verifying harness
/// (codex/gemini): type once, then submit (their existing one-shot behaviour,
/// byte-for-byte). `send` receives the 0-based attempt index so a real caller
/// can clear the input line before a RE-type without clearing on the first,
/// healthy attempt.
#[allow(clippy::too_many_arguments)]
pub fn run_submit_protocol(
    agent: Agent,
    text: &str,
    max_attempts: u32,
    verify_delay: Duration,
    mut send: impl FnMut(u32) -> std::io::Result<()>,
    mut capture: impl FnMut() -> std::io::Result<String>,
    mut finalize: impl FnMut() -> std::io::Result<()>,
    mut sleep: impl FnMut(Duration),
) -> std::io::Result<SubmitOutcome> {
    let mut attempts = 0u32;
    let mut verified = false;

    if needs_submit_verification(agent) {
        while attempts < max_attempts {
            send(attempts)?;
            attempts += 1;
            sleep(verify_delay);
            let pane = capture()?;
            if input_reflects_submission(agent, &pane, text) {
                verified = true;
                break;
            }
        }
    } else {
        // One-shot harnesses: type once and submit, no capture round-trip -
        // exactly the pre-Gap-1 behaviour.
        send(0)?;
        attempts = 1;
        verified = true;
    }

    finalize()?;
    Ok(SubmitOutcome { attempts, verified })
}

/// Submit `text` using the per-agent matrix, gated by the per-harness
/// input-readiness protocol (Gap 1).
///
/// Per ANALYTICS.md §4 the raw keystrokes are: claude/gemini
/// `send-keys -l <text>` then `Enter`; codex `send-keys -l <text>` then
/// `C-j C-m`. On top of that, claude verifies the text landed and re-types it
/// (clearing the input line with `C-u` before each RE-type so a partial land
/// never duplicates) up to `CLAUDE_SUBMIT_MAX_ATTEMPTS` times before pressing
/// Enter. A healthy claude launch lands on the first attempt, so the extra
/// cost is one capture; codex/gemini are unchanged.
pub fn submit(container: &str, agent: Agent, text: &str) -> std::io::Result<()> {
    let window = agent.window();
    let keys = finalize_keys(agent);
    run_submit_protocol(
        agent,
        text,
        CLAUDE_SUBMIT_MAX_ATTEMPTS,
        SUBMIT_VERIFY_DELAY,
        |attempt| {
            if attempt > 0 {
                // RE-type: clear the (possibly partially-landed) input line
                // first so a re-send never duplicates text. `C-u` is a no-op
                // on an empty line, but we only reach here on a retry anyway;
                // the first, healthy attempt types verbatim as before.
                tmux::send_keys(container, window, &["C-u"])?;
            }
            tmux::send_literal(container, window, text)
        },
        || tmux::capture_pane(container, window),
        || tmux::send_keys(container, window, keys),
        thread::sleep,
    )?;
    Ok(())
}
