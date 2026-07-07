# experiments/

Lab notes and matrices for the interactive-tmux workspace provider (EXP-01..06,
FRICTION-*, ANALYTICS). See `INDEX.md` for the full map.

## Acceptance harness: the Rust `itmux run` live-eval

The acceptance battery that proves the `itmux run` contract end-to-end is the
**Rust live-eval**, not the old Python `standalone_eval.py` (retired - it drove
the superseded Python orchestrator on PR #240).

- Harness: `providers/workspaces/interactive-tmux/driver-rs/tests/live_eval.rs`
- Run it: `just eval-live`
  (= `AGENTIC_LIVE_EVAL=1 cargo test --test live_eval -- --ignored --test-threads=1 --nocapture`)

The live cases (E1-E7) are BOTH `#[ignore]` AND env-gated on `AGENTIC_LIVE_EVAL=1`,
so a plain `cargo test` never touches docker. The harness's plumbing (argv
builder, JSONL event parser, `AgentRunResult` extractor, and the R5
event-contract validator) is unit-tested in that same file with no docker.

### Auth prerequisite (live only)

`itmux` sources host credentials into each workspace:

- Claude: `~/.claude/.credentials.json`
- Codex: `~/.codex/auth.json`

If the claude token has expired, refresh it with `claude setup-token`. Without
valid credentials, E1/E2 fail with an auth banner and the harness correctly
reports `success=false` (the run still terminalizes cleanly with no orphan).

### What the battery proves

| Case | Proves |
|------|--------|
| E1 | claude happy-path: `result.success` + `EXPERIMENT_OK` in `session_log` + R5 contract |
| E2 | codex reaches ready + graceful terminal (task success is a stretch goal) |
| E3 | events arrive incrementally (arrival spread), `tool_start` precedes `session_end` |
| E4 | graceful (1x SIGINT) / hard (2x SIGINT or SIGTERM) cancel at the submit/await boundary maps to the right terminal reason; orphan sweep clean |
| E5b | bad image fails with no container created; orphan sweep clean |
| E6 | short `--timeout` yields a `timeout` terminal reason, `success=false`, no orphan |
| E7 | `--result-file` lands the result JSON in the file AND keeps stdout pure lifecycle events |

E5a (forced startup-timeout orphan guard) is **unit-proven**, not live-proven
(plan R2): `driver-rs/tests/orchestrator.rs` covers the teardown-on-startup-
failure and hard-cancel-no-handle reap paths deterministically without docker
(`start_failure_after_partial_startup_tears_down_and_no_orphan`,
`hard_cancel_before_provision_reaps_orphans_best_effort`). A live forced timeout
would re-test docker, not our logic.

### Known gaps (unproven by this battery, plan R7)

These `itmux run` surfaces are NOT exercised by E1-E7 and remain to be proven
by later work:

- **Inline credential materialization** - the battery uses host credentials
  (`~/.claude`, `~/.codex`); `AgentRunSpec.credentials` inline token/`auth.json`
  contents are not exercised.
- **`--json false`** - only the default JSON event stream is validated; the
  human-summary mode is not.
- **Output artifacts** - `AgentRunResult.output_artifacts` is always empty in
  v1; artifact collection is unproven.
- **Observability** - `AgentRunSpec.observability` exporters and
  `AgentRunResult.observability` are Plan 3 placeholders, untested here.
- **Token usage** - `token_usage` events / `AgentRunLimits.token_budget`
  enforcement are not asserted.
- **Bundled-skill staging failure (#249)** - the fail-fast on host-path skill
  refs is unit-covered, not exercised live.
- **Subagents** - v1 executes only the `default_agent`; declared `subagents`
  are validated-only (R5) and never spawned.
