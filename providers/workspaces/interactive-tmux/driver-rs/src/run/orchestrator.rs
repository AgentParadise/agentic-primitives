//! The `itmux run` orchestrator: a crash-safe, orphan-proof state machine that
//! drives a single agent run and emits the R6 event stream.
//!
//! This module is deliberately HARNESS-NEUTRAL (plan R8): it names no specific
//! harness. All harness specifics live behind the [`RunExecutor`] trait, whose
//! real implementation is `crate::run::workspace_executor` and whose test
//! doubles live in the tests. A guard test asserts this file contains no
//! harness-name string literals.
//!
//! ## State machine (plan R7, authoritative)
//!
//! ```text
//! Provisioning -> Launching -> Awaiting -> Capturing -> Terminalizing -> Done
//! ```
//!
//! There is exactly ONE terminalization path ([`terminalize`]): it chooses a
//! single terminal reason (by the precedence below), tears the workspace down
//! EXACTLY ONCE, and emits EXACTLY ONE `session_end`.
//!
//! **Terminal reason precedence** (highest wins):
//! `hard_cancel > adapter_error > timeout > graceful_cancel > success`.
//!
//! **No orphan is possible by construction:** the workspace handle is created
//! at the Provisioning boundary and, once it exists, EVERY exit path (success,
//! error, timeout, cancel) flows through the single [`terminalize`] call, which
//! always tears the handle down. A teardown FAILURE never overrides the primary
//! terminal reason - it is logged to stderr, attached to the session log, and
//! swallowed. This is what makes the five Python concurrency defects (orphaned
//! containers on partial startup / cancel / timeout races) impossible here.

use std::io;
use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::Arc;
use std::time::Duration;

use crate::result::AwaitResult;
use crate::run::contract::{AgentRunEvent, AgentRunEventPayload, AgentRunOutcome, AgentRunResult};
use crate::run::recipe_loader::RecipeExecutionPlan;

/// The side-effecting operations the orchestrator drives, one per lifecycle
/// boundary. The real implementation wraps a `Workspace`; tests supply a fake.
///
/// Split into `provision` (create the workspace) then `launch` (start the agent
/// in it) so the workspace handle exists BEFORE anything that can fail after
/// infrastructure is created - the orchestrator can then always tear it down.
/// This is the structural anti-orphan property (R7).
pub trait RunExecutor {
    /// Owns the live workspace/container. Torn down exactly once via
    /// [`RunExecutor::teardown`].
    type Handle;

    /// Provisioning: create the workspace (container). MUST be transactional -
    /// if it fails, it cleans up its own partial infrastructure and returns
    /// `Err` (no handle escapes, so there is nothing to orphan).
    fn provision(&mut self) -> io::Result<Self::Handle>;

    /// Launching: start the agent inside the provisioned workspace.
    fn launch(&mut self, handle: &mut Self::Handle) -> io::Result<()>;

    /// Submit the task text to the agent (uses the per-harness input-readiness
    /// submit under the hood).
    fn submit(&mut self, handle: &mut Self::Handle) -> io::Result<()>;

    /// Awaiting: block until the agent settles or `timeout` elapses.
    fn await_completion(
        &mut self,
        handle: &mut Self::Handle,
        timeout: Option<Duration>,
    ) -> io::Result<AwaitResult>;

    /// Capturing: return the session log / pane transcript.
    fn capture(&mut self, handle: &mut Self::Handle) -> io::Result<String>;

    /// Harness-aware outcome detection. TODO(#246): today this is a liveness
    /// placeholder; Task 5 replaces it with per-harness success/error markers.
    /// The orchestrator only calls it - the harness logic lives in the adapter.
    fn detect_outcome(
        &self,
        handle: &Self::Handle,
        pane: &str,
        await_result: &AwaitResult,
    ) -> AgentRunOutcome;

    /// Optional harness-specific observed events collected outside the driver
    /// lifecycle itself, already normalized to the shared event payload
    /// vocabulary. Called after capture/outcome detection and before the final
    /// `session_end`, so the terminal event remains last.
    fn drain_observed_events(
        &mut self,
        _handle: &mut Self::Handle,
    ) -> io::Result<Vec<AgentRunEventPayload>> {
        Ok(Vec::new())
    }

    /// Terminalizing: tear the workspace down. Called EXACTLY once, consuming
    /// the handle. May fail - the orchestrator logs and swallows the error
    /// without letting it mask the run's terminal outcome.
    fn teardown(&mut self, handle: Self::Handle) -> io::Result<()>;

    /// Best-effort reap of a workspace that may have been orphaned by a hard
    /// cancel arriving DURING a blocking provision - i.e. before a handle
    /// existed to tear down. Called by `terminalize` ONLY on the hard-cancel
    /// path when no handle is held. Default no-op (most executors have nothing
    /// to reap). Implementations MUST be idempotent and MUST NOT fail the run
    /// (log and swallow). See workspace_executor + #248.
    fn teardown_orphans(&mut self) {}
}

/// Two-tier cancellation flag, shared with a signal handler (Task 6) or a test.
/// `Graceful` lets the current cycle finish and collect a final capture; `Hard`
/// bails at the next boundary and tears down immediately.
#[derive(Clone, Default)]
pub struct CancelToken(Arc<AtomicU8>);

const CANCEL_NONE: u8 = 0;
const CANCEL_GRACEFUL: u8 = 1;
const CANCEL_HARD: u8 = 2;

/// Observed cancellation level.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CancelLevel {
    None,
    Graceful,
    Hard,
}

impl CancelToken {
    pub fn new() -> Self {
        Self(Arc::new(AtomicU8::new(CANCEL_NONE)))
    }

    /// Request a graceful cancel (monotonic - never downgrades a hard cancel).
    pub fn cancel_graceful(&self) {
        self.0.fetch_max(CANCEL_GRACEFUL, Ordering::SeqCst);
    }

    /// Request a hard cancel (highest level).
    pub fn cancel_hard(&self) {
        self.0.fetch_max(CANCEL_HARD, Ordering::SeqCst);
    }

    pub fn level(&self) -> CancelLevel {
        match self.0.load(Ordering::SeqCst) {
            CANCEL_HARD => CancelLevel::Hard,
            CANCEL_GRACEFUL => CancelLevel::Graceful,
            _ => CancelLevel::None,
        }
    }

    fn is_hard(&self) -> bool {
        self.level() == CancelLevel::Hard
    }
}

/// A cancellation-relevant OS signal, abstracted from the platform so the
/// escalation logic is testable without raising real signals.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SignalKind {
    /// Interactive interrupt (SIGINT / Ctrl-C).
    Interrupt,
    /// Termination request (SIGTERM).
    Terminate,
}

/// Two-tier cancellation escalation (Task 6): the FIRST interrupt requests a
/// GRACEFUL cancel (let the run collect a partial result + emit a terminal
/// `session_end`); a SECOND interrupt, or any terminate, escalates to HARD
/// (immediate teardown). Pure and unit-testable without OS signals.
///
/// Async-signal-safety note: this type does real work (it calls into the
/// `CancelToken`), so it MUST run on a normal thread, NOT inside a signal
/// handler. The CLI drives it from a watcher thread fed by a self-pipe (see
/// `main.rs`), so the async-signal-safe part (writing the pipe) stays in the
/// signal-handling crate and this logic runs in ordinary thread context.
#[derive(Debug, Default)]
pub struct CancelEscalator {
    interrupts: u32,
}

impl CancelEscalator {
    pub fn new() -> Self {
        Self::default()
    }

    /// Fold one observed signal into `token`, escalating per the two-tier rule.
    pub fn on_signal(&mut self, signal: SignalKind, token: &CancelToken) {
        match signal {
            SignalKind::Terminate => token.cancel_hard(),
            SignalKind::Interrupt => {
                self.interrupts = self.interrupts.saturating_add(1);
                if self.interrupts >= 2 {
                    token.cancel_hard();
                } else {
                    token.cancel_graceful();
                }
            }
        }
    }
}

/// The single terminal reason chosen at the one terminalization point.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TerminalReason {
    Success,
    GracefulCancel,
    Timeout,
    AdapterError(String),
    HardCancel,
}

impl TerminalReason {
    /// Precedence rank (higher wins): hard_cancel > adapter_error > timeout >
    /// graceful_cancel > success. Exposed for the precedence guarantee tests.
    pub const fn rank(&self) -> u8 {
        match self {
            Self::Success => 0,
            Self::GracefulCancel => 1,
            Self::Timeout => 2,
            Self::AdapterError(_) => 3,
            Self::HardCancel => 4,
        }
    }
}

/// The lifecycle phases surfaced as `tool_start`/`tool_end` event pairs. The
/// labels are generic orchestration phase names (never harness names), so they
/// keep this module harness-neutral (R8).
#[derive(Debug, Clone, Copy)]
enum Phase {
    Provision,
    Launch,
    Submit,
    Await,
    Capture,
}

impl Phase {
    const fn label(self) -> &'static str {
        match self {
            Self::Provision => "provision",
            Self::Launch => "launch",
            Self::Submit => "submit",
            Self::Await => "await",
            Self::Capture => "capture",
        }
    }
}

/// R6 event stream: assigns the shared `run_id`, a monotonic `seq` from 0 with
/// no gaps, and an RFC3339 `ts` (from the injected clock) to every event.
struct EventStream<'a> {
    run_id: String,
    seq: u64,
    now: &'a mut dyn FnMut() -> String,
    emit: &'a mut dyn FnMut(&AgentRunEvent),
}

impl EventStream<'_> {
    fn push(&mut self, payload: AgentRunEventPayload) {
        let event = AgentRunEvent {
            run_id: self.run_id.clone(),
            seq: self.seq,
            ts: (self.now)(),
            payload,
        };
        (self.emit)(&event);
        self.seq += 1;
    }

    fn phase_start(&mut self, phase: Phase) {
        self.push(AgentRunEventPayload::ToolStart {
            tool_name: phase.label().to_string(),
            tool_input: serde_json::Value::Null,
        });
    }

    fn phase_end(&mut self, phase: Phase, success: bool, summary: Option<String>) {
        self.push(AgentRunEventPayload::ToolEnd {
            tool_name: phase.label().to_string(),
            success,
            output_summary: summary,
        });
    }

    fn session_end(&mut self, outcome: AgentRunOutcome) {
        self.push(AgentRunEventPayload::SessionEnd { outcome });
    }

    fn observed_events(&mut self, payloads: Vec<AgentRunEventPayload>) {
        for payload in payloads {
            self.push(payload);
        }
    }
}

/// Build the outcome for a terminal reason. Only `Success` uses the (Task 5)
/// detected outcome; every failure reason yields `success = false` with a
/// reason-specific summary.
fn outcome_for(reason: &TerminalReason, detected: Option<AgentRunOutcome>) -> AgentRunOutcome {
    match reason {
        TerminalReason::Success => detected.unwrap_or(AgentRunOutcome {
            success: true,
            summary: "run completed".to_string(),
        }),
        TerminalReason::Timeout => AgentRunOutcome {
            success: false,
            summary: "run timed out awaiting agent completion".to_string(),
        },
        TerminalReason::AdapterError(msg) => AgentRunOutcome {
            success: false,
            summary: format!("run failed: {msg}"),
        },
        TerminalReason::GracefulCancel => AgentRunOutcome {
            success: false,
            summary: "run cancelled (graceful)".to_string(),
        },
        TerminalReason::HardCancel => AgentRunOutcome {
            success: false,
            summary: "run cancelled (hard)".to_string(),
        },
    }
}

/// Arbitrate a candidate terminal reason against the current cancel state,
/// returning whichever has the higher precedence by [`TerminalReason::rank`].
///
/// This is the SINGLE place terminal-reason precedence is enforced, so the code
/// and the documented table (hard_cancel > adapter_error > timeout >
/// graceful_cancel > success) agree by construction. In particular, an
/// `adapter_error` raised on any `Err` path can never beat a pending
/// `hard_cancel` - the arbitration re-checks the cancel state at the moment the
/// reason is chosen, closing the gap where a blocking call returned `Err` after
/// a hard cancel had already been requested.
fn arbitrate(candidate: TerminalReason, cancel: &CancelToken) -> TerminalReason {
    let from_cancel = match cancel.level() {
        CancelLevel::Hard => Some(TerminalReason::HardCancel),
        CancelLevel::Graceful => Some(TerminalReason::GracefulCancel),
        CancelLevel::None => None,
    };
    match from_cancel {
        Some(reason) if reason.rank() > candidate.rank() => reason,
        _ => candidate,
    }
}

/// The SINGLE terminalization path (R7). Tears the handle down exactly once,
/// emits exactly one `session_end`, and returns the final result. A teardown
/// failure is logged + attached to the session log but never changes the
/// terminal outcome.
#[allow(clippy::too_many_arguments)]
fn terminalize<E: RunExecutor>(
    reason: TerminalReason,
    handle: Option<E::Handle>,
    mut session_log: String,
    detected: Option<AgentRunOutcome>,
    executor: &mut E,
    events: &mut EventStream<'_>,
) -> AgentRunResult {
    // Teardown exactly once: the handle is consumed here and nowhere else.
    if let Some(handle) = handle {
        if let Err(err) = executor.teardown(handle) {
            // Human log to stderr (R6: stderr is never parsed); attach a note
            // to the session log; do NOT let it mask the primary outcome.
            eprintln!("[itmux run] teardown failed: {err}");
            session_log.push_str(&format!("\n[itmux run] teardown warning: {err}\n"));
        }
    } else if matches!(reason, TerminalReason::HardCancel) {
        // Hard cancel with NO handle held: the cancel may have arrived during a
        // blocking provision that created a container before failing/returning.
        // Best-effort reap so that window can't silently orphan a container
        // (#248). Idempotent and non-failing by contract.
        executor.teardown_orphans();
    }

    let outcome = outcome_for(&reason, detected);
    events.session_end(outcome.clone());

    AgentRunResult {
        result: outcome,
        output_artifacts: Vec::new(),
        session_log,
        observability: None,
    }
}

/// Drive one agent run to completion, emitting the R6 event stream via `emit`
/// and returning the terminal [`AgentRunResult`].
///
/// Generic over [`RunExecutor`] so the whole state machine is exercised in
/// tests with a fake executor (no docker, no token). `now` injects the RFC3339
/// clock (deterministic in tests). `cancel` is checked at each boundary.
#[allow(clippy::too_many_arguments)]
pub fn run_core<E: RunExecutor>(
    run_id: impl Into<String>,
    plan: &RecipeExecutionPlan,
    timeout: Option<Duration>,
    executor: &mut E,
    cancel: &CancelToken,
    now: &mut dyn FnMut() -> String,
    emit: &mut dyn FnMut(&AgentRunEvent),
) -> AgentRunResult {
    // `plan` is accepted so the real executor's inputs and the orchestrator
    // share one source of truth; the orchestrator itself stays harness-neutral
    // and does not branch on it.
    let _ = plan;

    let mut events = EventStream {
        run_id: run_id.into(),
        seq: 0,
        now,
        emit,
    };

    let mut handle: Option<E::Handle> = None;
    let mut session_log = String::new();
    let mut detected: Option<AgentRunOutcome> = None;

    // The drive block computes exactly one terminal reason and never tears
    // down or emits session_end - that is the single terminalization path
    // below. Every early exit `break`s with its reason.
    let reason: TerminalReason = 'drive: {
        // ---- Provisioning ----
        if cancel.is_hard() {
            break 'drive TerminalReason::HardCancel;
        }
        events.phase_start(Phase::Provision);
        match executor.provision() {
            Ok(h) => {
                handle = Some(h);
                events.phase_end(Phase::Provision, true, None);
            }
            Err(err) => {
                // No handle escaped: provision is transactional, so there is
                // nothing to orphan. Report the error.
                let msg = err.to_string();
                events.phase_end(Phase::Provision, false, Some(msg.clone()));
                break 'drive arbitrate(TerminalReason::AdapterError(msg), cancel);
            }
        }

        // ---- Launching ----
        if cancel.is_hard() {
            break 'drive TerminalReason::HardCancel;
        }
        events.phase_start(Phase::Launch);
        {
            let h = handle.as_mut().expect("handle set by provisioning");
            if let Err(err) = executor.launch(h) {
                let msg = err.to_string();
                events.phase_end(Phase::Launch, false, Some(msg.clone()));
                break 'drive arbitrate(TerminalReason::AdapterError(msg), cancel);
            }
        }
        events.phase_end(Phase::Launch, true, None);
        // Hard-cancel-while-launch-in-flight: a signal that arrived during
        // launch bails here, before any submit/await - and still tears down.
        if cancel.is_hard() {
            break 'drive TerminalReason::HardCancel;
        }

        // ---- Submitting ----
        events.phase_start(Phase::Submit);
        {
            let h = handle.as_mut().expect("handle set by provisioning");
            if let Err(err) = executor.submit(h) {
                let msg = err.to_string();
                events.phase_end(Phase::Submit, false, Some(msg.clone()));
                break 'drive arbitrate(TerminalReason::AdapterError(msg), cancel);
            }
        }
        events.phase_end(Phase::Submit, true, None);
        if cancel.is_hard() {
            break 'drive TerminalReason::HardCancel;
        }

        // ---- Awaiting ----
        events.phase_start(Phase::Await);
        let await_result = {
            let h = handle.as_mut().expect("handle set by provisioning");
            match executor.await_completion(h, timeout) {
                Ok(ar) => ar,
                Err(err) => {
                    let msg = err.to_string();
                    events.phase_end(Phase::Await, false, Some(msg.clone()));
                    break 'drive arbitrate(TerminalReason::AdapterError(msg), cancel);
                }
            }
        };
        events.phase_end(Phase::Await, !await_result.timed_out, None);
        if cancel.is_hard() {
            break 'drive TerminalReason::HardCancel;
        }

        // ---- Capturing ---- (always, so timeout/graceful-cancel still yield a
        // partial session log - R7's "graceful collects a final capture").
        events.phase_start(Phase::Capture);
        {
            let h = handle.as_mut().expect("handle set by provisioning");
            match executor.capture(h) {
                Ok(pane) => {
                    session_log = pane;
                    events.phase_end(Phase::Capture, true, None);
                }
                Err(err) => {
                    let msg = err.to_string();
                    events.phase_end(Phase::Capture, false, Some(msg.clone()));
                    break 'drive arbitrate(TerminalReason::AdapterError(msg), cancel);
                }
            }
        }

        // Task 5 hook - harness-aware outcome (placeholder for now).
        {
            let h = handle.as_ref().expect("handle set by provisioning");
            detected = Some(executor.detect_outcome(h, &session_log, &await_result));
        }

        // Harness-specific observers may collect events that are not visible
        // through the pane transcript (for example hook sidecar JSONL). Emit
        // them before terminalization so `session_end` stays the last lifecycle
        // event.
        {
            let h = handle.as_mut().expect("handle set by provisioning");
            match executor.drain_observed_events(h) {
                Ok(payloads) => events.observed_events(payloads),
                Err(err) => {
                    eprintln!("[itmux run] failed to drain observed events: {err}");
                }
            }
        }

        // Route the terminal reason through the SAME arbitration helper the Err
        // paths use, so precedence is enforced in one place: the candidate is
        // timeout (if the await timed out) or success, arbitrated against any
        // pending cancel (graceful/hard). timeout outranks graceful_cancel;
        // hard_cancel outranks both. (adapter_error already short-circuited.)
        let candidate = if await_result.timed_out {
            TerminalReason::Timeout
        } else {
            TerminalReason::Success
        };
        arbitrate(candidate, cancel)
    };

    terminalize(reason, handle, session_log, detected, executor, &mut events)
}
