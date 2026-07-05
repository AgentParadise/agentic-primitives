//! Structured result mirroring `agentic_isolation.ExecuteResult` (Python
//! driver's `AwaitResult`). Field names and serde keys match the Python
//! `to_dict()` output so the CLI surface stays interchangeable.

use serde::{Deserialize, Serialize};

/// Result of waiting for an agent pane to reach a ready/idle state.
///
/// Mirrors the Python `AwaitResult` dataclass so the CLI's JSON output is
/// byte-identical to the Python `driver/interactive_tmux.py` output (modulo
/// floating-point timing). The `reason` enum is encoded as the same string
/// literals the Python emits (`"ready"`, `"timeout_never_ready"`,
/// `"timeout_unstable"`, `"error"`) to keep parity strict.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AwaitResult {
    pub ready: bool,
    pub timed_out: bool,
    pub reason: String,
    pub duration_ms: f64,
    pub stable_polls_observed: u32,
    #[serde(default)]
    pub pane: String,
    #[serde(default)]
    pub error: Option<String>,
}

impl AwaitResult {
    pub fn ready(duration_ms: f64, stable: u32, pane: String) -> Self {
        Self {
            ready: true,
            timed_out: false,
            reason: "ready".to_string(),
            duration_ms,
            stable_polls_observed: stable,
            pane,
            error: None,
        }
    }

    pub fn timeout_never_ready(duration_ms: f64, pane: String) -> Self {
        Self {
            ready: false,
            timed_out: true,
            reason: "timeout_never_ready".to_string(),
            duration_ms,
            stable_polls_observed: 0,
            pane,
            error: None,
        }
    }

    pub fn timeout_unstable(duration_ms: f64, stable: u32, pane: String) -> Self {
        Self {
            ready: false,
            timed_out: true,
            reason: "timeout_unstable".to_string(),
            duration_ms,
            stable_polls_observed: stable,
            pane,
            error: None,
        }
    }

    pub fn error(duration_ms: f64, pane: String, err: impl Into<String>) -> Self {
        Self {
            ready: false,
            timed_out: false,
            reason: "error".to_string(),
            duration_ms,
            stable_polls_observed: 0,
            pane,
            error: Some(err.into()),
        }
    }

    /// The workspace target itself is GONE (dead container, vanished tmux
    /// session/server) rather than a transient capture hiccup. Mirrors the
    /// Python driver's `AwaitResult(reason="container_dead", ...)`
    /// constructed in `_wait_for_started`/`await_completion` (PY:1962-1987,
    /// PY:2110-2138) once `_container_death_reason` finds a death marker.
    pub fn container_dead(
        duration_ms: f64,
        stable: u32,
        pane: String,
        err: impl Into<String>,
    ) -> Self {
        Self {
            ready: false,
            timed_out: false,
            reason: "container_dead".to_string(),
            duration_ms,
            stable_polls_observed: stable,
            pane,
            error: Some(err.into()),
        }
    }

    /// Convenience for CLI `await` exit codes (mirrors Python: 0 if ready, 2 if not).
    pub const fn cli_exit_code(&self) -> i32 {
        if self.ready {
            0
        } else {
            2
        }
    }
}
