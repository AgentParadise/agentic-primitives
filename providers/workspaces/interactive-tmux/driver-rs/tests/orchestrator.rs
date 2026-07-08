//! Orchestrator state-machine tests (Plan B Task 3, R7).
//!
//! Everything runs against a FAKE `RunExecutor` - no docker, no token. These
//! cover the five Python concurrency defects (orphaned containers on partial
//! startup / cancel / timeout races, duplicate terminalization), now
//! impossible by construction.

use std::cell::RefCell;
use std::io;
use std::path::PathBuf;
use std::rc::Rc;
use std::time::Duration;

use itmux::adapter::Agent;
use itmux::result::AwaitResult;
use itmux::run::contract::{AgentRunEvent, AgentRunEventPayload, AgentRunOutcome};
use itmux::run::orchestrator::{run_core, CancelEscalator, CancelToken, RunExecutor, SignalKind};
use itmux::run::recipe_loader::RecipeExecutionPlan;

// --- fake executor ---------------------------------------------------------

/// Which phase a scripted failure or cancel fires in.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum FakePhase {
    Provision,
    Launch,
    Submit,
    Await,
    Capture,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum CancelKind {
    Graceful,
    Hard,
}

/// Shared, observable record of what the fake executor did.
#[derive(Debug, Default)]
struct Record {
    calls: Vec<FakePhase>,
    teardowns: u32,
    orphan_reaps: u32,
}

struct FakeExecutor {
    record: Rc<RefCell<Record>>,
    cancel: CancelToken,
    /// Phase in which to return an `Err` (adapter error).
    fail_at: Option<FakePhase>,
    /// Trip the cancel token when this phase runs (before its own effect).
    cancel_at: Option<(FakePhase, CancelKind)>,
    /// The await result to return (defaults to ready/success).
    await_timed_out: bool,
    /// Make teardown fail (still must not mask the terminal outcome).
    teardown_fails: bool,
    /// Pane text `capture` returns.
    pane: String,
    /// Deliver N interrupt "signals" through a real `CancelEscalator` when this
    /// phase runs (simulates Ctrl-C: 1 = graceful, 2 = escalate to hard).
    escalate_at: Option<(FakePhase, u32)>,
    escalator: RefCell<CancelEscalator>,
    /// Request a hard cancel BEFORE the run starts (simulates a hard cancel
    /// landing during a blocking provision, before any handle exists).
    pre_cancel_hard: bool,
    observed_events: Vec<AgentRunEventPayload>,
}

impl FakeExecutor {
    fn new(record: Rc<RefCell<Record>>, cancel: CancelToken) -> Self {
        Self {
            record,
            cancel,
            fail_at: None,
            cancel_at: None,
            await_timed_out: false,
            teardown_fails: false,
            pane: "session pane".to_string(),
            escalate_at: None,
            escalator: RefCell::new(CancelEscalator::new()),
            pre_cancel_hard: false,
            observed_events: Vec::new(),
        }
    }

    fn maybe_cancel(&self, phase: FakePhase) {
        if let Some((at, kind)) = self.cancel_at {
            if at == phase {
                match kind {
                    CancelKind::Graceful => self.cancel.cancel_graceful(),
                    CancelKind::Hard => self.cancel.cancel_hard(),
                }
            }
        }
        if let Some((at, count)) = self.escalate_at {
            if at == phase {
                for _ in 0..count {
                    self.escalator
                        .borrow_mut()
                        .on_signal(SignalKind::Interrupt, &self.cancel);
                }
            }
        }
    }

    fn step(&self, phase: FakePhase) -> io::Result<()> {
        self.record.borrow_mut().calls.push(phase);
        self.maybe_cancel(phase);
        if self.fail_at == Some(phase) {
            return Err(io::Error::other(format!("boom in {phase:?}")));
        }
        Ok(())
    }
}

struct FakeHandle;

impl RunExecutor for FakeExecutor {
    type Handle = FakeHandle;

    fn provision(&mut self) -> io::Result<Self::Handle> {
        self.step(FakePhase::Provision)?;
        Ok(FakeHandle)
    }

    fn launch(&mut self, _h: &mut Self::Handle) -> io::Result<()> {
        self.step(FakePhase::Launch)
    }

    fn submit(&mut self, _h: &mut Self::Handle) -> io::Result<()> {
        self.step(FakePhase::Submit)
    }

    fn await_completion(
        &mut self,
        _h: &mut Self::Handle,
        _timeout: Option<Duration>,
        emit_observed: &mut dyn FnMut(Vec<AgentRunEventPayload>),
    ) -> io::Result<AwaitResult> {
        self.step(FakePhase::Await)?;
        if !self.observed_events.is_empty() {
            emit_observed(std::mem::take(&mut self.observed_events));
        }
        Ok(if self.await_timed_out {
            AwaitResult::timeout_never_ready(10.0, self.pane.clone())
        } else {
            AwaitResult::ready(10.0, 4, self.pane.clone())
        })
    }

    fn capture(&mut self, _h: &mut Self::Handle) -> io::Result<String> {
        self.step(FakePhase::Capture)?;
        Ok(self.pane.clone())
    }

    fn detect_outcome(
        &self,
        _h: &Self::Handle,
        pane: &str,
        _await_result: &AwaitResult,
    ) -> AgentRunOutcome {
        // Mirror the real executor: outcome is derived from the PANE (a fake
        // harness marker here), not from liveness - so an "errored" pane yields
        // success=false through the orchestrator.
        if pane.contains("FAKE_ERROR") {
            AgentRunOutcome {
                success: false,
                summary: "fake harness error detected".to_string(),
            }
        } else {
            AgentRunOutcome {
                success: true,
                summary: "fake outcome".to_string(),
            }
        }
    }

    fn drain_observed_events(
        &mut self,
        _h: &mut Self::Handle,
    ) -> io::Result<Vec<AgentRunEventPayload>> {
        Ok(std::mem::take(&mut self.observed_events))
    }

    fn teardown(&mut self, _h: Self::Handle) -> io::Result<()> {
        self.record.borrow_mut().teardowns += 1;
        if self.teardown_fails {
            Err(io::Error::other("teardown boom"))
        } else {
            Ok(())
        }
    }

    fn teardown_orphans(&mut self) {
        self.record.borrow_mut().orphan_reaps += 1;
    }
}

// --- harness ---------------------------------------------------------------

fn fake_plan() -> RecipeExecutionPlan {
    RecipeExecutionPlan {
        recipe_name: "test-recipe".to_string(),
        agent: Agent::Claude,
        claude_plugin_dirs: vec![PathBuf::from("/skills/x")],
        submit_text: "do the task".to_string(),
        subagents: vec![],
    }
}

struct Run {
    result: itmux::run::contract::AgentRunResult,
    events: Vec<AgentRunEvent>,
    record: Record,
}

fn drive(mut configure: impl FnMut(&mut FakeExecutor)) -> Run {
    let record = Rc::new(RefCell::new(Record::default()));
    let cancel = CancelToken::new();
    let mut executor = FakeExecutor::new(Rc::clone(&record), cancel.clone());
    configure(&mut executor);
    if executor.pre_cancel_hard {
        cancel.cancel_hard();
    }

    let plan = fake_plan();
    let events = Rc::new(RefCell::new(Vec::new()));
    let mut tick = 0u64;
    let mut now = || {
        let ts = format!("2026-07-07T00:00:{tick:02}Z");
        tick += 1;
        ts
    };
    let events_sink = Rc::clone(&events);
    let mut emit = move |event: &AgentRunEvent| events_sink.borrow_mut().push(event.clone());

    let result = run_core(
        "run-test",
        &plan,
        Some(Duration::from_secs(60)),
        &mut executor,
        &cancel,
        &mut now,
        &mut emit,
    );

    // Drop the borrowers that still hold Rc clones (the `move` emit closure and
    // the executor) so the sole remaining strong ref can be unwrapped.
    drop(emit);
    drop(executor);
    let events = Rc::try_unwrap(events).unwrap().into_inner();
    let record = Rc::try_unwrap(record).unwrap().into_inner();
    Run {
        result,
        events,
        record,
    }
}

fn session_end_count(events: &[AgentRunEvent]) -> usize {
    events
        .iter()
        .filter(|e| matches!(e.payload, AgentRunEventPayload::SessionEnd { .. }))
        .count()
}

fn terminal_outcome(events: &[AgentRunEvent]) -> AgentRunOutcome {
    events
        .iter()
        .rev()
        .find_map(|e| match &e.payload {
            AgentRunEventPayload::SessionEnd { outcome } => Some(outcome.clone()),
            _ => None,
        })
        .expect("a session_end event must exist")
}

fn assert_seq_monotonic_from_zero(events: &[AgentRunEvent]) {
    for (i, event) in events.iter().enumerate() {
        assert_eq!(event.seq, i as u64, "seq must be monotonic from 0, no gaps");
        assert_eq!(event.run_id, "run-test");
        assert!(!event.ts.is_empty(), "every event carries an RFC3339 ts");
    }
}

// --- happy path ------------------------------------------------------------

#[test]
fn happy_path_runs_phases_in_order_and_emits_terminal_session_end() {
    let run = drive(|_| {});

    assert_eq!(
        run.record.calls,
        vec![
            FakePhase::Provision,
            FakePhase::Launch,
            FakePhase::Submit,
            FakePhase::Await,
            FakePhase::Capture,
        ],
        "start -> submit -> await -> capture in order"
    );
    assert_eq!(run.record.teardowns, 1, "torn down exactly once");
    assert_eq!(session_end_count(&run.events), 1, "exactly one session_end");
    assert_seq_monotonic_from_zero(&run.events);

    // The last event is the session_end; the phase pairs precede it.
    assert!(matches!(
        run.events.last().unwrap().payload,
        AgentRunEventPayload::SessionEnd { .. }
    ));
    assert!(run.result.result.success);
    assert_eq!(run.result.session_log, "session pane");
    assert!(terminal_outcome(&run.events).success);
}

#[test]
fn observed_events_are_emitted_before_terminal_session_end() {
    let run = drive(|executor| {
        executor
            .observed_events
            .push(AgentRunEventPayload::HookEvent {
                provider: "fake".to_string(),
                event_type: "session_started".to_string(),
                event: serde_json::json!({"event_type": "session_started"}),
            });
    });

    assert_seq_monotonic_from_zero(&run.events);
    assert!(run
        .events
        .iter()
        .any(|event| matches!(event.payload, AgentRunEventPayload::HookEvent { .. })));
    let await_start = run
        .events
        .iter()
        .position(|event| {
            matches!(
                event.payload,
                AgentRunEventPayload::ToolStart { ref tool_name, .. } if tool_name == "await"
            )
        })
        .expect("await starts");
    let await_end = run
        .events
        .iter()
        .position(|event| {
            matches!(
                event.payload,
                AgentRunEventPayload::ToolEnd { ref tool_name, .. } if tool_name == "await"
            )
        })
        .expect("await ends");
    let observed = run
        .events
        .iter()
        .position(|event| matches!(event.payload, AgentRunEventPayload::HookEvent { .. }))
        .expect("observed event emitted");
    assert!(
        await_start < observed && observed < await_end,
        "observed event should stream during await, not wait for terminal drain"
    );
    assert!(matches!(
        run.events[run.events.len() - 1].payload,
        AgentRunEventPayload::SessionEnd { .. }
    ));
}

#[test]
fn success_flows_from_detect_outcome_not_liveness() {
    // The run reaches a clean, ready await (liveness would say success), but
    // the captured pane carries a harness error marker - detect_outcome must
    // drive the terminal outcome to failure. This is the Gap 2 fix.
    let run = drive(|e| e.pane = "session pane\nFAKE_ERROR: auth failed".to_string());

    assert!(
        run.record.calls.contains(&FakePhase::Capture),
        "the run completed the await + capture cycle"
    );
    assert_eq!(run.record.teardowns, 1);
    assert_eq!(session_end_count(&run.events), 1);
    assert!(
        !run.result.result.success,
        "an errored pane must yield success=false even though the pane was 'ready'"
    );
    assert!(!terminal_outcome(&run.events).success);
}

// --- adapter error (partial-startup no-orphan) -----------------------------

#[test]
fn start_failure_after_partial_startup_tears_down_and_no_orphan() {
    // Provision succeeds (infra exists), launch fails: the handle already
    // exists, so the single terminalization tears it down. This is the exact
    // Python orphan bug, now impossible.
    let run = drive(|e| e.fail_at = Some(FakePhase::Launch));

    assert_eq!(
        run.record.calls,
        vec![FakePhase::Provision, FakePhase::Launch],
        "stops after the failed launch; no submit/await/capture"
    );
    assert_eq!(run.record.teardowns, 1, "provisioned infra is torn down");
    assert_eq!(session_end_count(&run.events), 1);
    assert!(!run.result.result.success);
    assert!(
        run.result.result.summary.contains("boom in Launch"),
        "summary carries the adapter error: {}",
        run.result.result.summary
    );
}

#[test]
fn provision_failure_reports_error_with_nothing_to_tear_down() {
    // Provision is transactional: on failure no handle escapes, so there is
    // nothing for the orchestrator to orphan or tear down.
    let run = drive(|e| e.fail_at = Some(FakePhase::Provision));

    assert_eq!(run.record.calls, vec![FakePhase::Provision]);
    assert_eq!(run.record.teardowns, 0, "no handle existed to tear down");
    assert_eq!(session_end_count(&run.events), 1);
    assert!(!run.result.result.success);
}

// --- cancellation ----------------------------------------------------------

#[test]
fn cancel_during_await_collects_partial_result_and_reports_graceful() {
    // Graceful cancel trips during await; the run still does a final capture
    // and terminalizes graceful (success=false) with no orphan.
    let run = drive(|e| e.cancel_at = Some((FakePhase::Await, CancelKind::Graceful)));

    assert!(
        run.record.calls.contains(&FakePhase::Capture),
        "graceful cancel still collects a final capture"
    );
    assert_eq!(run.record.teardowns, 1);
    assert_eq!(session_end_count(&run.events), 1);
    assert!(!run.result.result.success);
    assert!(
        run.result.result.summary.contains("graceful"),
        "summary: {}",
        run.result.result.summary
    );
    assert_eq!(
        run.result.session_log, "session pane",
        "partial log captured"
    );
}

#[test]
fn timeout_during_cancel_prefers_timeout_over_graceful() {
    // Both a graceful cancel AND a timeout apply; precedence timeout > graceful
    // means the terminal reason is timeout.
    let run = drive(|e| {
        e.cancel_at = Some((FakePhase::Await, CancelKind::Graceful));
        e.await_timed_out = true;
    });

    assert_eq!(run.record.teardowns, 1);
    assert_eq!(session_end_count(&run.events), 1);
    assert!(!run.result.result.success);
    assert!(
        run.result.result.summary.contains("timed out"),
        "timeout wins over graceful cancel: {}",
        run.result.result.summary
    );
}

#[test]
fn hard_cancel_while_launch_in_flight_bails_and_tears_down_no_orphan() {
    // A hard cancel arrives during launch: the run bails at the next boundary,
    // never submits/awaits/captures, and tears the workspace down.
    let run = drive(|e| e.cancel_at = Some((FakePhase::Launch, CancelKind::Hard)));

    assert_eq!(
        run.record.calls,
        vec![FakePhase::Provision, FakePhase::Launch],
        "no submit/await/capture after a hard cancel in launch"
    );
    assert_eq!(run.record.teardowns, 1, "no orphan: torn down exactly once");
    assert_eq!(session_end_count(&run.events), 1);
    assert!(!run.result.result.success);
    assert!(
        run.result.result.summary.contains("hard"),
        "summary: {}",
        run.result.result.summary
    );
}

#[test]
fn hard_cancel_before_provision_reaps_orphans_best_effort() {
    // Simulates a hard cancel that lands during a blocking provision, before any
    // handle exists (#248). The orchestrator bails at the first boundary with no
    // handle, and terminalize invokes the best-effort orphan reap so the window
    // can't silently leak a container.
    let run = drive(|e| e.pre_cancel_hard = true);

    assert!(
        run.record.calls.is_empty(),
        "provision never ran (bailed on the pre-provision hard-cancel check)"
    );
    assert_eq!(run.record.teardowns, 0, "no handle to tear down");
    assert_eq!(
        run.record.orphan_reaps, 1,
        "best-effort orphan reap invoked exactly once on the hard-cancel-no-handle path"
    );
    assert_eq!(session_end_count(&run.events), 1);
    assert!(!run.result.result.success);
    assert!(run.result.result.summary.contains("hard"));
}

#[test]
fn happy_path_does_not_reap_orphans() {
    let run = drive(|_| {});
    assert_eq!(
        run.record.orphan_reaps, 0,
        "normal completion tears down via the handle, never the orphan reaper"
    );
}

#[test]
fn hard_cancel_outranks_adapter_error_on_err_path() {
    // A hard cancel is pending AND the executor returns Err from the same phase
    // (a blocking call that returned an error after the cancel was requested).
    // Precedence hard_cancel > adapter_error must win: the terminal reason is
    // HardCancel, still torn down once with one session_end.
    let run = drive(|e| {
        e.fail_at = Some(FakePhase::Await);
        e.cancel_at = Some((FakePhase::Await, CancelKind::Hard));
    });

    assert_eq!(run.record.teardowns, 1, "torn down exactly once, no orphan");
    assert_eq!(session_end_count(&run.events), 1);
    assert!(!run.result.result.success);
    assert!(
        run.result.result.summary.contains("hard"),
        "hard_cancel must outrank the adapter_error: {}",
        run.result.result.summary
    );
}

#[test]
fn graceful_then_hard_signals_terminalize_once_with_hard_reason() {
    // Two Ctrl-C during await, driven through the real CancelEscalator: the
    // first requests graceful, the second escalates to hard. Precedence means
    // the terminal reason is hard, terminalized exactly once, torn down once.
    let run = drive(|e| e.escalate_at = Some((FakePhase::Await, 2)));

    assert_eq!(run.record.teardowns, 1, "torn down exactly once, no orphan");
    assert_eq!(session_end_count(&run.events), 1, "exactly one session_end");
    assert!(!run.result.result.success);
    assert!(
        run.result.result.summary.contains("hard"),
        "escalated to hard reason: {}",
        run.result.result.summary
    );
}

// --- teardown failure does not mask outcome --------------------------------

#[test]
fn teardown_failure_does_not_mask_a_successful_outcome() {
    let run = drive(|e| e.teardown_fails = true);

    assert_eq!(run.record.teardowns, 1, "teardown attempted exactly once");
    assert_eq!(session_end_count(&run.events), 1);
    // The primary outcome (success) is preserved despite the teardown failure.
    assert!(
        run.result.result.success,
        "teardown failure must not flip the terminal outcome"
    );
    assert!(terminal_outcome(&run.events).success);
    assert!(
        run.result.session_log.contains("teardown warning"),
        "teardown failure is attached to the session log, not the outcome: {}",
        run.result.session_log
    );
}

// --- no duplicate session_end across every scenario ------------------------

type Scenario = Box<dyn Fn(&mut FakeExecutor)>;

#[test]
fn exactly_one_session_end_in_every_scenario() {
    let scenarios: Vec<Scenario> = vec![
        Box::new(|_e: &mut FakeExecutor| {}),
        Box::new(|e: &mut FakeExecutor| e.fail_at = Some(FakePhase::Provision)),
        Box::new(|e: &mut FakeExecutor| e.fail_at = Some(FakePhase::Launch)),
        Box::new(|e: &mut FakeExecutor| e.fail_at = Some(FakePhase::Submit)),
        Box::new(|e: &mut FakeExecutor| e.fail_at = Some(FakePhase::Await)),
        Box::new(|e: &mut FakeExecutor| e.fail_at = Some(FakePhase::Capture)),
        Box::new(|e: &mut FakeExecutor| e.await_timed_out = true),
        Box::new(|e: &mut FakeExecutor| e.teardown_fails = true),
        Box::new(|e: &mut FakeExecutor| {
            e.cancel_at = Some((FakePhase::Await, CancelKind::Graceful))
        }),
        Box::new(|e: &mut FakeExecutor| e.cancel_at = Some((FakePhase::Launch, CancelKind::Hard))),
    ];

    for (i, configure) in scenarios.iter().enumerate() {
        let run = drive(|e| configure(e));
        assert_eq!(
            session_end_count(&run.events),
            1,
            "scenario {i} must emit exactly one session_end"
        );
        assert_seq_monotonic_from_zero(&run.events);
        // Teardown is never called more than once in any scenario.
        assert!(
            run.record.teardowns <= 1,
            "scenario {i} tore down more than once"
        );
    }
}
