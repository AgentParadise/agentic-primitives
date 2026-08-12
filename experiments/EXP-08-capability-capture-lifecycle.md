# EXP-08 — Workspace capability capture lifecycle

**Branch of record:** `feat/workspace-capability-modules`
**Status:** hypothesis frozen, runs pending
**Spec under test:** `docs/superpowers/specs/2026-08-12-workspace-capability-modules-design.md`
**Plan gated on this:** `docs/superpowers/plans/2026-08-12-workspace-capability-modules.md`

## Context (one sentence)

Before implementing the session-store capability, prove empirically which
post-agent trigger mechanism actually fires in this image, because EXP-07 showed
a mistimed sweep misattributes sessions silently and the plan's Task 7 branches
on the answer.

## Question

Does a signal-correct entrypoint wrapper reliably produce a post-agent sweep
moment across this image's execution modes, or must the sweep be triggered from
outside the container by the orchestrator?

This is falsifiable: each arm either produces a complete, correctly-tagged
session set within the container stop grace period, or it does not.

## FOCUS gate

| Gate | Status |
|---|---|
| **F**it | Pass. Gates the capability-modules plan, which gates the whole session-capture goal. |
| **O**rganization pull | Pass. The result selects Task 7A vs 7B. A decision is waiting on it. |
| **C**apability readiness | Pass, after setup. Workspace image `agentic-workspace-claude-cli:latest` built 26h ago; local store healthy at `127.0.0.1:18091`; Linux ARM64 exporter cross-built (`ELF 64-bit LSB pie executable, ARM aarch64`). |
| **U**nderlying data | Pass. Baseline captured before any run: **9 sessions** in the local store (`select count(*) from sessions`). |
| **S**uccess | Pass. Predicted outcomes below, committed before any `runs/` artifact. |

## Setup

- **Store:** the isolated local `exp07` stack on `127.0.0.1:18091`, **not** the
  Mini. Deliberate: this probe writes junk envelopes, and the Mini holds the
  real learning corpus. Read and write tokens are distinct on this stack.
- **Image:** `agentic-workspace-claude-cli:latest`.
- **Exporter:** cross-built in `rust:1.88-bookworm`, mounted into the container.
  Building on the macOS host produces a Mach-O binary that cannot execute in the
  container; this cost a cycle in EXP-07.
- **Spool:** host directory bind-mounted at `/spool`, partitioned
  `<workflow>/<phase>`.
- **Baseline:** 9 sessions, captured above.

## Pre-flight findings (read, not run)

Two facts established by reading `providers/interactive_tmux/__init__.py`
**before** freezing this hypothesis. They reshape the question rather than
answer it.

1. **The interactive-tmux provider runs a fixed `sleep infinity` entrypoint**
   and launches agents into tmux panes via `docker exec` (line 267). The agent
   is therefore never the entrypoint's child. The "background job stdin goes to
   `/dev/null`" hazard I originally predicted is moot in that mode, because the
   agent's stdin never passes through the wrapper at all.

2. **That provider rejects `environment` and `secrets`** as unsupported
   `WorkspaceConfig` fields, raising `ValueError` when either is set to a
   non-default value (`_unsupported_config_fields`). This means the
   `AGENTIC_SESSION_STORE_*` contract **cannot be delivered** to an
   interactive-tmux workspace as that provider stands today.

Finding 2 is the load-bearing one and it is a scope discovery, not a trigger
question. It is recorded as P3 below so it gets scored rather than quietly
absorbed.

## Hypothesis (frozen 2026-08-12 before any probing)

| ID | Prediction | Predicted outcome |
|---|---|---|
| P1 | A trap-based wrapper forwards SIGTERM to the agent child and the sweep completes before Docker's 10s SIGKILL, in headless mode. | **Confirmed.** Expect sweep to finish in under 2s for a small spool. |
| P2 | The wrapper propagates the agent's real exit code. A trapped signal makes the first `wait` return 143, so a second `wait` is required to recover the true status. | **Confirmed**, and the naive single-`wait` version is expected to return 143 instead of the agent's code, demonstrating the bug the double-`wait` fixes. |
| P3 | The session-store capability can be configured in interactive-tmux mode. | **Refuted.** Expect `ValueError` from `_unsupported_config_fields` on any attempt to pass `environment` or `secrets`. Capture is structurally unavailable there until that provider is extended. |
| P4 | An orchestrator-triggered `docker exec` sweep before teardown captures the same session set as the wrapper. | **Confirmed**, byte-identical session IDs between arms. |
| P5 | After `docker kill -9`, the phase-partitioned spool survives on the volume and a later sweep uploads it with the partition's tags rather than the sweeping shell's ambient env. | **Confirmed.** This is the P9-from-EXP-07 fix; if refuted, the phase-encoded spool design is wrong. |
| P6 | Re-sweeping an already-uploaded partition is a clean no-op via `content_hash` dedup. | **Confirmed.** Expect the store's session count to be unchanged after a second identical sweep. |

**Predicted scorecard: 5 confirmed, 1 refuted.** If this comes back 6/6
confirmed, treat that as evidence the hypothesis was written to match what I
already believed rather than to risk anything, and discount it accordingly.

**What would invalidate the whole run:** if the exporter cannot reach the store
from inside the container, every arm fails for a reason unrelated to trigger
timing, and the verdict is `inconclusive` rather than `no-go`.

## Method

Frozen. Each arm writes evidence under `experiments/EXP-08/runs/`.

1. **A1 wrapper, headless.** Build a throwaway image whose entrypoint ends in
   the wrapper under test. Run an agent that writes transcripts and exits 0.
   Record: sweep ran, elapsed `docker stop` to exit, exit code, uploaded count.
2. **A2 wrapper, exit code.** Same, agent exits 7. Record observed exit code.
   Run once with a single `wait` and once with the double `wait` to show the
   difference.
3. **A3 interactive-tmux config.** Attempt to construct a `WorkspaceConfig` with
   `environment` set and pass it to `InteractiveTmuxProvider.create`. Record the
   exception.
4. **A4 docker exec.** Stock entrypoint. Trigger the sweep from the host before
   `docker stop`. Record the same fields as A1 and diff the session set.
5. **A5 crash.** `docker kill -9` mid-session, then sweep the surviving spool
   from the host. Record the tags on the uploaded envelopes.
6. **A6 re-sweep.** Re-run a completed sweep. Record store session count before
   and after.

## Out of scope

- Whether the capability *should* be available in interactive-tmux mode. P3
  establishes that it is not; extending that provider is separate work.
- Syntropic137 integration.
- Performance of the exporter at corpus scale.

## Results

Pending. Populated in the `run` commit.

## Verdict

Pending. Populated in the `run` commit.
