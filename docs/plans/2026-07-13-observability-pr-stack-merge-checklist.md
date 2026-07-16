# Observability PR Stack Merge Checklist

**Owner:** `okrs-51p.14`  
**North star:** merge a stable Agentic Primitives foundation, then use the
central LangFuse evidence layer for benchmarked evaluation and learning loops.

## Scope

This checklist covers the currently open workspace/observability PR chain:

| PR | Base | Role |
| --- | --- | --- |
| #240 | `main` | Workspace contract foundation |
| #243 | `main` | Production parity for Claude and Codex |
| #247 | #243 | Rust `AgentRunSpec` / `AgentRunResult` run contract |
| #250 | #247 | Python `agentic_isolation` client |
| #252 | #247 | Live acceptance battery |
| #254 | #247 | Credential loading |
| #256 | #247 | Observability package, LangFuse query/MCP, docs, and local fanout |

PRs #244 and #255 are independent ADR/documentation work. Reconcile them
against the final implementation before merging; do not treat either as an
implementation dependency.

## Priority 0: Review and CI Gates

- [ ] Resolve #240 Copilot: hard cancellation while workspace start is in
      flight can orphan a workspace.
- [ ] Resolve #240 Copilot: cross-thread `CancelToken.request()` uses
      `asyncio.Event.set()` unsafely; wake the owning event loop safely.
- [ ] Resolve #240 Copilot: preserve `stdout` in unexpected `await_ready()`
      errors. (Two review threads report this same issue.)
- [ ] Resolve #243 Copilot: `wait_bounded` timeout cleanup must not reintroduce
      an unbounded wait through `Command::output()`.
- [ ] Obtain an independent final review for #247 and #256 after their final
      rebases. #256 has prior Claude Code review evidence, but needs a review
      of the merge-ready head.
- [ ] Ensure each PR has a green latest-head CI run. Do not use a previously
      green run after a rebase or follow-up fix as merge evidence.
- [ ] Verify no PR is draft at the point it becomes merge candidate.
- [ ] Check the diff against the actual base branch after each rebase; confirm
      there are no accidental changes from a stacked ancestor.

## Priority 1: Merge the Runtime Foundation

- [ ] Merge #240 after its Copilot threads and CI are clean.
- [ ] Rebase/update #243 on the current `main`, resolve any overlap with #240,
      rerun CI, and merge it.
- [ ] Rebase #247 on the merged production-parity baseline, rerun its Rust,
      Python, consumer-contract, and workspace-image checks, and merge it.

The exact rebase command depends on the resulting GitHub base branches. Prefer
GitHub's update branch action only when it produces a clean, reviewable diff;
otherwise rebase locally and force-push only with explicit operator approval.

## Priority 2: Merge the #247 Dependents

- [ ] Rebase #250, #252, and #254 on the merged #247/main baseline.
- [ ] Confirm each PR has a focused acceptance criterion and does not duplicate
      a sibling's changes.
- [ ] Merge them in the order required by their actual file/API dependencies;
      rerun CI after each merge when later PRs are rebased.

## Priority 3: Merge Observability

- [ ] Rebase #256 on the final merged #247/main baseline.
- [ ] Verify ADR-039, the runbook, setup guide, plugin README, and PR body all
      state the canonical architecture correctly: official Claude/Codex plugins
      write rich LangFuse traces; Agentic Primitives owns local JSONL/Syntropic
      fanout and LangFuse query/score/MCP tools.
- [ ] Verify observability plugin versioning and `uv run --script` MCP launch.
- [ ] Rerun MCP self-test, focused `itmux` tests, plugin validation, and the
      latest-head GitHub CI suite.
- [ ] Mark #256 ready, obtain final independent review, merge it, and verify
      the marketplace installation path from the merged branch.

## Priority 4: Post-Merge Operational Acceptance

- [ ] Run `scripts/langfuse-observability-doctor.sh` from the merged checkout.
- [ ] Verify one real Claude and one real Codex trace from MacBook and Flywheel
      VPS retain the expected environment, harness, and host tags.
- [ ] Exercise one isolated Docker workspace with runtime-injected credentials.
- [ ] Query traces through the merged `agentic-langfuse` MCP server and write
      then read one score.
- [ ] Update `okrs-51p.9`, `.10`, `.11`, `.12`, `.14`, and `u6s.1/.2` to
      reflect the merged architecture and evidence. Close only items whose
      stated acceptance criteria are met.

## Evaluation Follow-Through

Once this stack is stable, start the evaluation layer rather than expanding
observability indefinitely:

- `okrs-05k`: evaluation standard and cookbook
- `okrs-imy`: reliable docker-exec backend
- `okrs-n3y`: AgentRunSpec cost-quality sweep runner
- `okrs-51p.5`: evaluation target
- `okrs-u6s.5`: LangFuse datasets/evaluators/trace-linked feedback bridge
