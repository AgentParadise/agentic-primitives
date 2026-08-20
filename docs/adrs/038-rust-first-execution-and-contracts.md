---
title: "ADR-038: Rust-First for Workspace Execution and Contracts"
status: accepted
created: 2026-07-07
updated: 2026-07-07
author: NeuralEmpowerment
tags: [rust, python, workspace, itmux, contracts, language-choice, architecture]
---

# ADR-038: Rust-First for Workspace Execution and Contracts

## Status

**Accepted**

- Created: 2026-07-07
- Updated: 2026-07-07
- Author(s): NeuralEmpowerment

## Context

agentic-primitives began as "Claude Code plugins + Python libraries." The interactive-tmux
workspace (the substrate that runs agents in isolation) was first written as a ~2500-line
Python driver, then ported to a Rust binary (`itmux`) for cold-start and single-binary
reasons. That port surfaced a durable pattern, and this ADR makes the resulting language
policy explicit so future contributors do not re-litigate it per feature.

Forces at play:

- **Cold-start cost.** A per-invocation Python process pays ~120ms interpreter startup;
  the equivalent Rust ELF is ~5ms. The workspace driver and per-hook emitters are invoked
  at high frequency inside every container, where that difference compounds.
- **Single-binary portability.** The workspace must run on the host, in Docker, and over
  SSH (local/docker/ssh). A statically-linked Rust binary ships as one artifact with no
  runtime to provision on the target; a Python package drags a virtualenv, a lockfile, and
  a filesystem-path assumption behind it.
- **Concurrency correctness.** The `RunSpec -> RunResult` orchestrator was first built in
  Python (async + `asyncio.to_thread` + `asyncio.Event` + cancellation). Across three
  independent reviewers (Claude adversarial, codex cross-model, GitHub Copilot) it accrued
  **five** distinct concurrency defects - an orphaned-container race, a dangling event
  stream on failure, lost subprocess JSON, a thread-unsafe `Event.set()`, and an unshielded
  teardown. Every one was an artifact of doing async orchestration *in Python*, not a flaw
  in the contract itself. The orchestrator belongs next to the harness adapters, which are
  already Rust; there the whole bug class does not exist.
- **A working precedent.** event-sourcing-platform already runs a Rust core (event store)
  with a thin Python SDK. "Rust core, thin language glue" is proven in this org.
- **The stated direction.** The end state is one Rust `itmux`, no parallel Python driver,
  and consumers that pass a config and read a result. Growing a second, Python, execution
  surface works against that.

Constraint: the primary consumer today, Syntropic137, is Python. Any decision must keep it
cheap for a Python process to drive a workspace.

**Non-forces (explicitly out of scope):** this ADR is *not* "rewrite every Python package
in Rust." Claude Code hook plugins must be whatever the harness expects; existing Python
libraries (`agentic_logging`, `agentic_events`, `agentic_memory`) stay until there is a
concrete reason to move them.

## Decision

**We will build the workspace execution substrate and its cross-language contracts in Rust,
and expose them to consumers as a language-neutral JSON contract plus thin per-language
clients. Python is retained only as thin consumer glue and for artifacts that must be
Python (Claude hook plugins).**

Concretely:

- The **execution substrate** (`itmux`: launch, tmux drive, credential staging, environments)
  is Rust. There is no parallel Python driver.
- The **`AgentRunSpec -> AgentRunResult` contract and its orchestrator** live in Rust, as an
  `itmux run` subcommand plus `serde` structs. The wire contract is **JSON** (with a
  published schema), which is language-neutral.
- **Recipe loading and validation** (the directory-based agent recipe, ADR/standard TBD) is
  Rust - the loader is `itmux`.
- **Observability tailers / hot-path emitters** (e.g. `syn-observe`) are Rust.
- **Consumers get thin clients.** Syntropic137 shells out to `itmux run` and parses the JSON
  result - tens of lines, not a 600-line contract. A standalone eval runner calls the Rust
  binary directly and needs no Python at all.

**Default going forward:** new execution, contract, recipe, or hot-path tooling is authored
in Rust unless there is a concrete, stated reason it must be Python (a harness plugin, or a
throwaway script). "It's easier to write it in Python right now" is not such a reason - the
concurrency and cold-start costs above are paid repeatedly, not once.

## Alternatives Considered

### Alternative 1: Python contract over the Rust `itmux` binary (the status quo we are leaving)

**Description**: Keep the `AgentRunSpec/AgentRunResult` models and the `run()` orchestrator
in a Python package (`agentic_isolation`) that shells out to `itmux` for the primitive
subcommands.

**Pros**:
- Directly callable from Syntropic137 (Python) with typed Pydantic models.
- Already built and unit-tested; codex proved one end-to-end path works.

**Cons**:
- Reintroduces a Python execution surface, cutting against the delete-the-Python-driver
  direction.
- The async orchestration is a demonstrated, recurring source of concurrency bugs (five
  across three reviewers) that simply do not exist when the orchestrator sits with the
  adapters in Rust.
- A standalone eval (a stated acceptance goal) then needs a Python runtime it should not.
- The contract is Python-shaped rather than language-neutral, coupling every future consumer
  to Python or to re-implementing the models.

**Verdict**: Rejected. Cheapest time to change is now - it is unmerged and nothing depends
on it.

### Alternative 2: Full rewrite of all Python libraries into Rust

**Description**: Treat "Rust-first" as "Rust-only" and port `agentic_logging`,
`agentic_events`, the hook emitters, etc.

**Pros**:
- Maximal consistency.

**Cons**:
- Enormous, low-ROI churn; some artifacts (Claude hook plugins) are constrained to what the
  harness loads and cannot be arbitrary Rust.
- Conflates "the performance-sensitive substrate" with "every utility."

**Verdict**: Rejected. Scope is the execution/contract/hot-path core, not everything.

## Consequences

**Positive**
- One execution surface (Rust `itmux`), single-binary, portable across local/docker/ssh.
- The concurrency-bug class from Python async orchestration is eliminated by construction.
- Standalone (no-Syntropic137) runs are a pure Rust path - stronger acceptance story.
- A JSON contract + schema is consumable by any language; Syntropic137 is a thin client.
- Aligns with the event-sourcing-platform "Rust core, thin SDK" precedent.

**Negative / costs**
- The existing Python contract (`agentic_isolation` `AgentRunSpec`/`run()`) is reworked into
  Rust; the Python models port over, but it is rework.
- Contributors need Rust fluency for substrate/contract work (Python remains fine for glue).
- A JSON/subprocess boundary is slightly less ergonomic than an in-process Python call - paid
  once at the client, worth it for language-neutrality.

**Follow-up**
- Rework the `AgentRunSpec -> AgentRunResult` contract into `itmux run` (Rust) + JSON schema
  + a thin Python client (supersedes the Python-contract execution plan).
- Update `CLAUDE.md` / `AGENTS.md` framing from "Python libraries" to reflect Rust-first for
  the substrate/contracts, Python for glue + Claude plugins.
