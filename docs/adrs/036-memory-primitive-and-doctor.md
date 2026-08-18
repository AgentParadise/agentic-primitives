---
title: "ADR-036: Memory Primitive and Doctor"
status: superseded
created: 2026-05-13
updated: 2026-08-12
author: NeuralEmpowerment
superseded_by: ADR-040 (in mechanism only)
tags: [memory, workspace, contracts, agentic-isolation, claude-cli, hindsight, observability]
---

# ADR-036: Memory Primitive and Doctor

> **Amendment, 2026-08-12: superseded in mechanism by
> [ADR-040](040-workspace-capability-modules.md), retained for its
> reasoning.**
>
> ADR-040 generalizes the memory-only plumbing described below into a
> capability-module system, so this ADR's *mechanism* is no longer the
> shipped one. What remains fully in force is this ADR's **reasoning**, in
> particular the rejection of Alternative 3 (a doctor nobody runs
> automatically is a break-glass tool) and Alternative 4 (opting in IS
> opting into hard fail, and a second env var to ignore the first is a
> workaround for a contract that was not designed sharply). ADR-040 inherits
> both verdicts unchanged and applies them to every capability.
>
> Paths and variable names in this document have been updated in place to
> match what shipped. Three interfaces moved, which is why the workspace
> image went to 2.0.0:
>
> - `/opt/agentic/memory/` is now `/opt/agentic/capabilities/memory/`.
> - `AGENTIC_MEMORY_AUDIT_DIR` is now `AGENTIC_CAPABILITY_AUDIT_DIR`,
>   applying to every capability rather than only memory.
> - `AGENTIC_MEMORY_PROVIDER` alone no longer activates memory; `memory`
>   must also appear in `AGENTIC_CAPABILITIES` (the image default provides
>   it).
>
> See ADR-040's Migration section for the operator-facing version, and
> [`docs/workspace-capabilities.md`](../workspace-capabilities.md) for how
> to author a capability today. Nothing in the original reasoning below has
> been deleted.

## Status

**Superseded in mechanism by ADR-040. Reasoning retained.**

- Created: 2026-05-13
- Updated: 2026-08-12
- Author(s): NeuralEmpowerment
- Superseded by: [ADR-040: Workspace Capability Modules](040-workspace-capability-modules.md) (mechanism only)

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
   `/opt/agentic/capabilities/memory/<provider>/init.sh`, baked into the
   image. Entrypoint section 5.6 sources the adapter.

2. **Memory doctor** — a CLI at `/opt/agentic/capabilities/memory/doctor` that validates
   the contract is wired correctly, sniffs the backend's reachability,
   surfaces actionable diagnostics in both human-readable and
   machine-readable form, and optionally auto-corrects client-side issues
   via `--fix`. Entrypoint section 5.7 runs full preflight automatically
   at container start. **Hard-fail on any failure.** Opting into memory
   (setting `AGENTIC_MEMORY_PROVIDER`) is the user's authorization to
   fail loud on misconfiguration; there is no soft-fail mode and no escape
   hatch.

3. **Audit trail** via host bind-mount at `/var/agentic/memory-doctor/`.
   Doctor appends one JSON line per run to `YYYY-MM-DD.jsonl`. Operators
   can `tail`, `grep`, and dashboard the diagnostics across every container
   start.

Detailed design lived in
`docs/superpowers/specs/2026-05-13-memory-primitive-and-doctor-design.md`,
which is no longer in the repository.

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

### Alternative 4: Soft-fail by default + `AGENTIC_MEMORY_REQUIRED=true` opt-in

**Description**: If the doctor reports any failure, the entrypoint logs the
issue but continues. An `AGENTIC_MEMORY_REQUIRED=true` env var opts into
hard fail.

**Pros**:
- Matches ADR-035's soft-fail-with-loud-logs posture exactly.
- A flaky backend doesn't take down every workspace.
- Development environments tolerate transient backend issues.

**Cons**:
- Two env vars to remember instead of one (`PROVIDER` AND `REQUIRED`).
- Misconfiguration in development looks like working code until the
  agent's memory tools silently no-op mid-session — the exact silent-failure
  pattern we're trying to escape.
- The semantic of "setting `AGENTIC_MEMORY_PROVIDER` but not `REQUIRED`" is
  fundamentally confused — why opt into memory if you don't care whether
  it works?

**Reason for rejection**: The user's reasoning during decision review:
"if you enable memory, you want failure when misconfigured." Adding a
second env var to allow ignoring the first is a workaround for not having
designed the contract sharply. Opting in IS opting into hard fail; if you
don't want hard fail, don't set the provider. The entrypoint then skips
sections 5.6 and 5.7 entirely.

This decision deliberately diverges from ADR-035's soft-fail default
because the failure modes differ. ADR-035 deals with optional content
(plugins, subagents) where missing pieces gracefully degrade. Memory is
binary — either retain/recall works or it doesn't. There is no graceful
degradation.

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
- **Hard-fail couples workspace startup to backend health.** A flaky
  hindsight container takes down every workspace that opts into memory
  until the operator intervenes. Mitigated by the doctor's auto-fix
  capability and clear audit logs; operators with a flaky backend should
  unset `AGENTIC_MEMORY_PROVIDER` temporarily rather than work around the
  doctor.

- **Diverges from ADR-035's soft-fail default.** ADR-035 deals with
  optional content (plugins, subagents); ADR-036 deals with a binary
  feature (memory works or it doesn't). The divergence is intentional but
  worth flagging — future ADRs that extend either contract should be
  explicit about which posture they inherit.

## Implementation Notes

Phased implementation per the spec doc. Phases 1–2 cover contract + doctor
skeleton + hindsight adapter; phases 3–5 cover host adoption, `--fix` mode,
and second-provider adapter.

**Divergence from ADR-035's soft-fail default is intentional.** ADR-035
deals with optional content where missing pieces gracefully degrade.
ADR-036 deals with a binary feature. If a future ADR consolidates the two
postures or revisits one of them, both should be reviewed together.

`tests/integration/test_entrypoint_memory_*.py` follows the existing test
pattern from `test_entrypoint_workspace_injection.py`.

## References

- Design spec: `docs/superpowers/specs/2026-05-13-memory-primitive-and-doctor-design.md` (no longer in the repository)
- [ADR-040: Workspace Capability Modules](040-workspace-capability-modules.md) (supersedes this ADR's mechanism)
- [Authoring guide: workspace capabilities](../workspace-capabilities.md)
- [ADR-035: Workspace Injection Contract](035-workspace-injection-contract.md)
- [agentic-memory/docs/architecture/memory-contract.md](../../../../agentic-memory/docs/architecture/memory-contract.md) — sibling design doc with consumer-side adapter examples
- [hindsight bank derivation modes probe](../../../../agentic-memory/experiments/2026-05-12--claude-code--hindsight--bank-derivation-modes/results.md) — empirical evidence informing the adapter's env var choices
