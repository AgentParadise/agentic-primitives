//! R8 generic guard: the orchestrator state machine must contain NO
//! harness-name string literals. All harness specifics live in `adapter.rs`
//! (per-harness behaviour) and `workspace_executor.rs` (the concrete executor).
//! A source scan is the cheap, durable enforcement of that boundary.

const ORCHESTRATOR_SRC: &str = include_str!("../src/run/orchestrator.rs");

#[test]
fn orchestrator_contains_no_harness_name_literals() {
    let lowered = ORCHESTRATOR_SRC.to_lowercase();
    for needle in ["claude", "codex", "gemini"] {
        assert!(
            !lowered.contains(needle),
            "orchestrator.rs must stay harness-neutral (R8), but mentions '{needle}'. \
             Move any harness-specific logic into adapter.rs / workspace_executor.rs."
        );
    }
}
