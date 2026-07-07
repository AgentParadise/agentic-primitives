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
use itmux::run::orchestrator::{run_core, CancelToken, RunExecutor};
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
    ) -> io::Result<AwaitResult> {
        self.step(FakePhase::Await)?;
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
        _pane: &str,
        await_result: &AwaitResult,
    ) -> AgentRunOutcome {
        AgentRunOutcome {
            success: await_result.ready,
            summary: "fake outcome".to_string(),
        }
    }

    fn teardown(&mut self, _h: Self::Handle) -> io::Result<()> {
        self.record.borrow_mut().teardowns += 1;
        if self.teardown_fails {
            Err(io::Error::other("teardown boom"))
        } else {
            Ok(())
        }
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
