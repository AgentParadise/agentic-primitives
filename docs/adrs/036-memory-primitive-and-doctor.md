---
title: "ADR-036: Memory Primitive and Doctor"
status: draft
created: 2026-05-13
updated: 2026-05-13
author: NeuralEmpowerment
tags: [memory, workspace, contracts, agentic-isolation, claude-cli, hindsight, observability]
---

# ADR-036: Memory Primitive and Doctor

## Status

**Draft**

- Created: 2026-05-13
- Updated: 2026-05-13
- Author(s): NeuralEmpowerment

## Context

Multiple orchestrators want to attach an agentic-memory backend (hindsight
first, lossless-claw or others later) to workspaces spawned from the
`agentic-workspace-claude-cli` image:

- [agentic-domain-runner](https://gitea.neuralempowerment.xyz/HomeLab/agentic-domain-runner)
  wants per-task isolated memory keyed by `agent_task_id`.
- [Syntropic137](https://github.com/AgentParadise/syntropic137) wants
  per-workflow scoped memory keyed by `workflow_id::phase`.
- Standalone Claude Code sessions (on a developer's laptop) want per-project
  banks.
- Hermes Agent — *not in scope* — already has hindsight as a native
  upstream provider via `hermes memory setup` (announced 2026-04-06).

Without a contract, every orchestrator would re-implement its own
hindsight-specific bolt-on: parse identity, derive bank ID, set
`HINDSIGHT_*` env vars, sniff connectivity, decide what to do on failure.
That couples every host to one memory backend and one identity model. The
proven cost of *not* having a contract is visible in ADR-035's "Before"
section — the same drift problem for context staging.

A separate force: memory misconfiguration tends to fail silently. The
hindsight Claude Code plugin's retain hook returns 0 from `read_transcript`
when the JSONL is empty; recall returns 0 facts; the bank stays empty; the
agent runs as if nothing's wrong. Empirical evidence from a recent probe
(`agentic-memory/experiments/.../auto-recall-per-project`) — three procedure
bugs surfaced only after the writeup phase, by inspection, not by failure.
A diagnostic surface that fails loud at the operator layer is the missing
piece.

This ADR proposes both pieces — the contract and the doctor — together,
because their shapes are coupled. The doctor is what makes the contract's
"soft-fail by default" posture safe: things break loudly enough for humans
to notice, without breaking the agent's startup path.

## Decision

We will add a **memory primitive** to the workspace image, structured as
two coordinated extensions of the workspace injection contract (ADR-035):

1. **Memory contract** — three required env vars from the host
   (`AGENTIC_MEMORY_PROVIDER`, `AGENTIC_MEMORY_NAMESPACE`, `AGENTIC_MEMORY_URL`)
   plus three optional (`NAMESPACE_KIND`, `AUTH`, `CONFIG_JSON`).
   Translation logic lives in per-provider adapter scripts at
   `/opt/agentic/memory/<provider>/init.sh`, baked into the image.
   Entrypoint section 5.6 sources the adapter.

2. **Memory doctor** — a CLI at `/opt/agentic/memory/doctor` that validates
   the contract is wired correctly, sniffs the backend's reachability,
   surfaces actionable diagnostics in both human-readable and
   machine-readable form, and optionally auto-corrects client-side issues
   via `--fix`. Entrypoint section 5.7 runs `--quick` automatically at
   container start; soft-fails by default (`AGENTIC_MEMORY_REQUIRED=true`
   opts into hard fail).

Detailed design lives in
[the spec doc](../superpowers/specs/2026-05-13-memory-primitive-and-doctor-design.md).

## Alternatives Considered

### Alternative 1: Provider-specific env vars only (no contract)

**Description**: Each orchestrator sets provider-specific env vars
(`HINDSIGHT_BANK_ID`, `HINDSIGHT_API_URL`, …) directly. The workspace image
passes them through. No adapter layer.

**Pros**:
- Zero new code in the workspace image.
- Lowest friction for the first integration.

**Cons**:
- Couples every orchestrator to one provider. Switching from hindsight to
  lossless-claw means rewriting every host.
- No diagnostic layer. Misconfiguration fails silently.
- Each orchestrator independently re-derives bank IDs from its identity
  model — exact drift we're trying to prevent.

**Reason for rejection**: This is the status-quo-after-first-integration
path. It's where every other agent platform has ended up. We have ADR-035 as
explicit precedent for choosing the contract over the convenience path.

---

### Alternative 2: Memory-as-plugin (load via `AGENTIC_WORKSPACE_PLUGINS`)

**Description**: Memory adapters are plugins. A subagent named
`memory-hindsight` ships in the image, gets loaded via the existing plugin
injection contract from ADR-035.

**Pros**:
- Reuses ADR-035's mechanism. No new entrypoint section.
- Adapters compose like any other plugin.

**Cons**:
- The plugin contract is *for Claude Code plugins* (hooks, slash commands).
  A memory adapter needs to run *before* the plugin starts, to set env vars
  the plugin's hooks then read.
- Env-var translation isn't naturally a plugin concern. Forcing it through
  the plugin shape would require either pre-plugin lifecycle hooks (new
  primitive) or duplicating env-var logic inside each plugin (drift).

**Reason for rejection**: The translation has to happen before the plugin
starts, in shell/env. The plugin layer is too late. The two stages
(translation glue, plugin source) are genuinely different concerns and
benefit from being separate.

---

### Alternative 3: Doctor as a standalone CLI only (no automatic preflight)

**Description**: Add the doctor command, but don't run it at container start.
Operators invoke it manually when they suspect a problem.

**Pros**:
- Zero startup overhead.
- Doctor is unambiguously an operator tool, not part of the agent's path.

**Cons**:
- Misconfiguration still fails silently until the operator notices and
  invokes it. Defeats the headline value.
- Most users won't run it. Doctors that aren't auto-invoked end up as
  break-glass-only tools.

**Reason for rejection**: The whole point of a doctor is to fail loud where
the system would otherwise fail silent. Manual invocation is a "feature
flag for safety" — users skip it.

---

### Alternative 4: Hard-fail on misconfiguration by default

**Description**: If the doctor reports any failure, the entrypoint exits
non-zero and the workspace doesn't start. No `AGENTIC_MEMORY_REQUIRED` flag.

**Pros**:
- Misconfiguration is impossible to ignore.
- Less surprising for production deployments — they want to fail loud.

**Cons**:
- Breaks the "backwards compatible, soft-fail" posture of ADR-035.
- A flaky backend (hindsight container restart, network blip) takes down
  every workspace until the operator intervenes. Bad coupling.
- Development environments often have backend issues that are okay to
  ignore for the moment; this would block them.

**Reason for rejection**: Coupling workspace startup to backend health is
the wrong default. We add `AGENTIC_MEMORY_REQUIRED=true` for hosts that
want to opt into hard fail, but keep soft-fail as the default to match
ADR-035 and prevent backend outages from cascading.

## Consequences

### Positive Consequences

- **Provider swap is a 4-line change in the host**, not a refactor. The
  agentic-domain-runner code stays generic; switching to a future
  lossless-claw adapter only changes one env-var string.
- **Diagnostic surface for memory becomes first-class.** Failures are loud
  enough for humans to notice without breaking the workspace's startup path.
  The doctor JSON output is machine-parseable for orchestrators that want to
  surface diagnostics in their own UIs.
- **The contract matches ADR-035's shape.** Same env-var prefix, same
  entrypoint-section convention, same soft-fail-with-loud-logs default,
  same WorkspaceFiles-style bind-mount pattern. Cognitive overhead for
  orchestrator authors is minimal.
- **Backend ownership stays where it belongs.** The doctor explicitly does
  not mutate the backend. Operators retain authority over bank creation,
  deletion, and policy.

### Negative Consequences

- **Three more env vars in the host contract.** Total grows from 3
  (ADR-035) to 6 (ADR-035 plus 3 from this ADR). Manageable but not free.
- **Per-provider adapters need to be maintained inside the image.** When
  a new provider ships, we need a new adapter script and matching doctor
  checks. The adapter layer is its own surface to keep working.
- **The Python helper library is a new dependency** in the workspace image
  (already has Python; minor weight added). Future cleanup might extract
  the validation logic to a shared package.
- **Soft-fail default means production misconfiguration can run unnoticed
  if operators ignore the doctor's logged warnings.** Mitigated by
  `AGENTIC_MEMORY_REQUIRED=true` opt-in, but the default is still
  "agent runs even when memory is broken."

## Implementation Notes

Phased implementation per the spec doc. Phases 1–2 cover contract + doctor
skeleton + hindsight adapter; phases 3–5 cover host adoption, `--fix` mode,
and second-provider adapter.

ADR-035's "soft-fail by default, loud logs" pattern is mirrored deliberately.
If a future ADR changes ADR-035 to hard-fail, this ADR should be reviewed
to keep them consistent.

`tests/integration/test_entrypoint_memory_*.py` follows the existing test
pattern from `test_entrypoint_workspace_injection.py`.

## References

- [Design spec](../superpowers/specs/2026-05-13-memory-primitive-and-doctor-design.md)
- [ADR-035: Workspace Injection Contract](035-workspace-injection-contract.md)
- [agentic-memory/docs/architecture/memory-contract.md](../../../../agentic-memory/docs/architecture/memory-contract.md) — sibling design doc with consumer-side adapter examples
- [hindsight bank derivation modes probe](../../../../agentic-memory/experiments/2026-05-12--claude-code--hindsight--bank-derivation-modes/results.md) — empirical evidence informing the adapter's env var choices
