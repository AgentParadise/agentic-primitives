---
title: "ADR-038: Workspace Capability Modules"
status: accepted
created: 2026-08-12
updated: 2026-08-12
author: NeuralEmpowerment
supersedes: ADR-036 (in mechanism)
tags: [workspace, capabilities, contracts, claude-cli, session-store, memory, lifecycle]
---

# ADR-038: Workspace Capability Modules

## Status

**Accepted**

- Created: 2026-08-12
- Updated: 2026-08-12
- Author(s): NeuralEmpowerment
- Supersedes: [ADR-036](036-memory-primitive-and-doctor.md) in *mechanism*.
  ADR-036's reasoning about opt-in and loud failure is retained and still
  binding; only its memory-specific plumbing is replaced by the generic
  module system described here.

## Context

ADR-036 gave the workspace image exactly one pluggable subsystem: memory.
Its shape was good. A host set `AGENTIC_MEMORY_PROVIDER` plus a handful of
`AGENTIC_MEMORY_*` vars, entrypoint section 5.6 sourced a per-provider
`init.sh` that translated those into provider-native env, and section 5.7
ran a doctor that hard-failed the container on any misconfiguration. That
shape was validated in production and nothing about it wants changing.

What wanted changing is that the shape was hard-coded to the word "memory".
Adding session capture (upload every agent transcript to a session store
speaking the APS-V1-0004 standard) under ADR-036's design would have meant
copying sections 5.6 and 5.7 with `MEMORY` replaced by `SESSION_STORE`, and
the next capability after that would copy them again. Three forces made
that unacceptable:

1. **The entrypoint is the single source of truth for workspace
   configuration.** Every capability that edits it makes it a shared
   mutable surface, and the failure mode of a bad edit is a container that
   will not start.
2. **Session capture needs a lifecycle stage memory does not.** Memory is
   fully configured before the agent runs. Session capture needs a *post
   agent* moment to sweep and upload transcripts. That is a new hook, and
   the place to add a new hook is a generic lifecycle, not a second
   bespoke one.
3. **Docker is not the only substrate we expect to run on.** E2B and
   similar sandbox APIs are on the roadmap. A capability whose logic lives
   inside `entrypoint.sh` is a capability that has to be rewritten for
   every substrate that does not run our entrypoint.

Two further constraints came from evidence rather than design taste.

**EXP-07** established that a mistimed sweep silently misattributes
sessions. That made the trigger mechanism a question worth measuring
rather than guessing, which is what
[EXP-08](../../experiments/EXP-08-capability-capture-lifecycle.md) did.
EXP-08 scored 3 of 6 predictions correct, and both wrong predictions would
have shipped as silent data-loss defects. Its findings are load bearing
throughout the Decision below and are cited inline.

**The session store is dependency-injected.** The store server is private;
the exporter that talks to it is a reference client of the public
APS-V1-0004 standard. The image must build, and its capability doctor must
be meaningful, without any credential that would let it vendor a vendor's
binary.

## Decision

We will restructure the workspace image's pluggable subsystems into
**capability modules**: a generic registry plus a generic lifecycle, with
each capability supplying portable shell and a host-side binding.

### 1. A capability has two halves

**The in-container half** is portable shell, baked into the image at
`/opt/agentic/capabilities/<capability>/`:

```
/opt/agentic/capabilities/<capability>/
  doctor                       # generic entry, execs `python -m <pkg>.doctor`
  <provider>/init.sh           # contract -> provider-native env (required)
  <provider>/doctor.sh         # provider-specific checks (optional)
  <provider>/finalize.sh       # post-agent hook (optional)
```

It knows nothing about Docker. It reads an `AGENTIC_<CAP>_*` env contract,
writes provider-native env, checks its own health, and optionally does
post-agent work. Anything it needs from the substrate arrives as an
environment variable or a mounted path.

**The host-side half** is provider-implemented and substrate-specific: how
the contract's env vars actually get into the container, how a spool volume
is provisioned, how the stop grace is set. Today that lives in
`lib/python/agentic_isolation/agentic_isolation/providers/docker.py`. On
E2B it would live somewhere else entirely, and the in-container half would
be unchanged.

**This split is the entire point of the ADR.** It is what admits a second
substrate later without rewriting the capabilities themselves. Anything
that leaks substrate knowledge into the in-container half spends that
option.

### 2. The env contract naming rule

A capability's contract variables are named:

```
AGENTIC_<CAP_UPPER>_<FIELD>
```

where `<CAP_UPPER>` is the capability's registry name uppercased with `-`
replaced by `_`, and `<FIELD>` likewise. So capability `session-store`,
field `partition`, gives `AGENTIC_SESSION_STORE_PARTITION`.

The rule has two implementations that must agree: `__capability_env_prefix`
in `entrypoint.sh` (shell) and `capability_env_name()` in each capability's
`contract.py` (Python). A conformance test pins them together, so a drift
between them is a CI failure rather than a container that quietly reads the
wrong variable.

`AGENTIC_<CAP>_PROVIDER` is reserved by the lifecycle: it selects the
adapter directory and, when unset or `none`, makes the capability a
complete no-op.

Two variables are capability-generic rather than per-capability:

- `AGENTIC_CAPABILITIES`: space-separated registry of capability names the
  lifecycle iterates. Image default is `"memory session-store"`.
- `AGENTIC_CAPABILITY_AUDIT_DIR`: where doctor output is appended, one
  JSON line per run into `YYYY-MM-DD.jsonl`. Defaults per capability to
  `/var/agentic/<capability>-doctor`.

### 3. The three hooks and their failure semantics

| Hook | When | On failure |
|---|---|---|
| `init.sh` | entrypoint 5.6, before the agent | Warn and continue. The doctor in 5.7 is what turns a broken init into a hard stop, with a specific cause rather than a bare non-zero exit. |
| `doctor` | entrypoint 5.7, before the agent | **Hard fail, exit 1.** Opting into a capability is opting into loud failure (ADR-036). Failing here is free because no agent work has happened yet. |
| `finalize.sh` | entrypoint 6, after the agent exits | **Always soft.** Invoked as `"${__fin}" \|\| true`, and the shipped hook itself always exits 0. A failed upload after an hour of successful agent work must never make the phase report as failed. |

`init.sh` is *sourced* into the entrypoint shell so its exports propagate
to later process spawns. `finalize.sh` is *executed* as a subprocess, since
it must not be able to corrupt the wrapper's exit-code handling.

One inherited detail: a successful `init.sh` also causes the lifecycle to
export `AGENTIC_<CAP>_READY=1`. That is ADR-036's pre-existing, tested
memory contract, and generalizing the loop must not silently drop it.

### 4. The invariant that proves the boundary is real

> **Adding a new capability requires ZERO changes to `entrypoint.sh`.**

Write the adapter directory, add the name to `AGENTIC_CAPABILITIES`, done.
If a new capability needs an entrypoint edit, that is not a reason to make
the edit. It is a signal that the contract is wrong, and the fix belongs in
the contract.

This is checkable, not aspirational: `session-store`, the capability this
ADR was written alongside, added zero lines to sections 5.6 and 5.7. The
entrypoint changes on this branch are the *generalization* of those
sections plus the section 6 wrapper, not per-capability plumbing.

### 5. The registry hardening, and the one silent path

The lifecycle loop validates aggressively, because every name it reads
becomes part of a filesystem path or an `eval`'d variable expansion:

- Capability names are `[a-z0-9-]+`. A name containing a `.` would
  uppercase into a prefix like `AGENTIC_A.B` whose `${AGENTIC_A.B_PROVIDER:-}`
  is a bash bad substitution, which under `set -e` kills the whole
  entrypoint. Invalid names are skipped, not fatal.
- Provider names are validated before any path is built, and a rejected
  provider name is **not echoed**: a path-traversal payload would otherwise
  leak its escape target verbatim into the audit stream.
- `finalize` re-validates the provider name. Section 5.6's *hard*-fail path
  exits before CMD, but its init-failure path only warns, so an unsafe
  provider string can still be in scope by the time finalizers run.

One deliberate softness is worth recording because it conflicts with
ADR-036's "loud failure" posture. Before this ADR, setting
`AGENTIC_MEMORY_PROVIDER` alone activated memory. Now the capability must
*also* be listed in `AGENTIC_CAPABILITIES`. A narrowed registry therefore
drops a capability with no other signal. The lifecycle emits a warning when
a `AGENTIC_*_PROVIDER` var is set for an unregistered capability. It does
not hard fail, because an operator narrowing the registry may be doing it
on purpose. This is the one path in the system where a misconfiguration
produces a warning rather than a stop.

### 6. Post-agent execution: the wrapper, and why it looks the way it does

Section 6 was `exec "$@"`. It is now a wrapper, because `exec` leaves no
moment after the agent for `finalize.sh` to run in. Every detail below is
an EXP-08 finding, not a preference.

**The bounded wait.** A trapped signal makes the first `wait` return >128,
so the naive fix is a second bare `wait` to recover the child's real
status. EXP-08 measured that this is *strictly worse than not trying*: it
blocks on a child that has not died, burns the entire stop grace, gets
SIGKILLed, and never runs finalize at all. `agent_trapped=0` throughout,
because bash defers traps while a foreground child runs, so the agent never
processed TERM in the first place. Wrapper correctness cannot assume prompt
agent signal handling. The shipped form bounds the wait, escalates to
SIGKILL, and only then reaps:

```bash
if [ "${__rc}" -gt 128 ]; then
    __n=0
    while kill -0 "${__child}" 2>/dev/null && [ "${__n}" -lt "${__TERM_GRACE_TICKS}" ]; do
        sleep 0.1; __n=$((__n + 1))
    done
    kill -0 "${__child}" 2>/dev/null && kill -KILL "${__child}" 2>/dev/null
    if wait "${__child}" 2>/dev/null; then __rc=0; else __rc=$?; fi
fi
```

**`set -e` and the guarded wait.** The script runs under `set -e`. A bare
`wait "${__child}"; __rc=$?` is a classic trap: `wait`'s non-zero status is
an unshielded simple command, so the shell exits right there, `__rc` is
never captured, and finalize never fires. That skips capture on exactly the
failing runs most worth capturing. Both waits are therefore wrapped in `if`,
which is exempt from `-e`.

**Signal forwarding, not synthesis.** The trap forwards the signal actually
received rather than always sending TERM. Under `docker run -it` the child
shares PID 1's process group and already receives the tty's SIGINT
directly; synthesizing a SIGTERM would make Ctrl-C, which is how Claude
Code interrupts generation, kill the whole session instead of the current
turn.

**The stop-grace coupling.** `__TERM_GRACE_TICKS` in `entrypoint.sh` must
stay **strictly below** the `docker stop -t` value in
`agentic_isolation/providers/docker.py`, with headroom for finalize's own
work (a real transcript upload, not just process teardown). Currently 1.5s
against a 5s grace, leaving roughly 3.5s. During implementation the two
were effectively tied at 5s and the result was silent: finalize simply
never ran, and the container's exit code became 137. Both files now carry
cross-referencing comments. **Changing either number without the other can
silently disable post-agent capture on every graceful shutdown**, and
nothing in the exit code or the logs says so.

### 7. Production reality: the timing budget is what matters

This is easy to misread. Both production providers start this image with
`sleep infinity` as CMD and run agents via `docker exec`. On that path the
agent is **not** the wrapper's child, and the exit-code preservation above
is never exercised at all. It matters for direct `docker run <image> <agent>`
usage and for the tests, and it is worth keeping correct, but it is not the
production property.

What matters in production is that **finalize fires inside the stop
grace**. The timing budget in section 6 above, not the exit-code plumbing,
is the load-bearing property of this design.

### 8. Scope limit: headless only

`InteractiveTmuxProvider` rejects `environment` and `secrets` outright
(`_unsupported_config_fields` raises `ValueError` when either is set to a
non-default value). The capability contract is delivered entirely through
environment variables, so it **cannot reach interactive-tmux workspaces at
all**. EXP-08 arm A3 confirmed this against the running code.

This is recorded as a known gap, not fixed here. Extending that provider to
accept an environment seam is separate work with its own risk surface.
Until it happens, capability modules are a headless-mode feature.

### 9. `.capture-env` is DATA, parsed, never sourced

The session-store adapter persists its opaque tag string to
`$SPOOL/$PARTITION/.capture-env` at init, so a recovery sweep of a spool
left behind by a SIGKILLed container can still attribute the session.
(EXP-08 arm A5: without this the partition path preserves *location* but
the tags, which live only in the environment, are lost, and the recovered
session uploads with no tags at all. That is the exact misattribution the
partitioned spool exists to prevent.)

The file looks like shell. It is not, and this is a security property, not
a style note:

```
SESSION_STORE_TAGS=<opaque tag string, exactly as received>
```

Tags are **opaque orchestrator input**. Sourcing them is arbitrary code
execution in a process that holds `SESSIONS_WRITE_TOKEN`. This was
demonstrated during the Tasks 5+6 review, not theorized: a tag of
`workflow:$(touch /tmp/PWNED)` executed on source, and any tag containing a
space truncated the value to empty, destroying the very attribution the
file exists to preserve. The correct read is line-oriented and
quote-agnostic:

```bash
SESSION_STORE_TAGS="$(sed -n 's/^SESSION_STORE_TAGS=//p' "${capture_env}" | head -1)"
export SESSION_STORE_TAGS
```

`export` is required: the exporter is a *child process*, and a shell
variable alone never reaches it. The file is written under `umask 077`
rather than a post-hoc `chmod`, which would leave a window where it is
world-readable. EXP-08's verdict text originally recommended sourcing; it
carries a dated in-line correction retracting that instruction. Its
findings are unchanged; only that one implementation instruction was wrong.

### 10. The exporter site is a BINDING, not part of the contract

The image deliberately does **not** vendor `SeshMagicSessionExporter`. The
exporter is a reference client of the public APS-V1-0004 standard, not part
of the private store server. Vendoring one vendor's binary would break the
store being dependency-injected and would require build credentials a
turnkey user of this image does not have.

The image defines the *contract*: the doctor's `exporter_present` check
looks for the binary on `PATH` and runs `--version`. Deployment supplies
the binary by bind-mount, by a derived image, or by a custom base layer.
`tests/integration/fixtures/stub-exporter` is a committed test double that
satisfies the check without a real binary or real uploads.

If the exporter later becomes publicly distributable, the Dockerfile gains
a `curl` fetch step and **nothing else changes**. The exporter's location
is a binding to a particular deployment, not a term of the capability
contract.

### 11. `TranscriptSource` already exists, and is the E2B path

`lib/python/agentic_isolation/agentic_isolation/harnesses/` defines a
provider-abstracted `TranscriptSource` protocol, with plugins for both
`claude` and `codex`, contracted to **never raise** (transport and parse
failures are reported through `TranscriptExtractionResult.errors` so a
harvest can never abort a workspace teardown). `DockerProvider` already
implements `transcript_source()`.

**It has no production caller.** It is unused in v1 for one reason: the
in-container exporter was already validated end to end by EXP-08, and
adding a second capture path would have meant two mechanisms to keep
correct instead of one.

It is nonetheless the natural host-side half of session capture and the
natural path for a non-Docker substrate, where there is no entrypoint to
wrap and no in-container binary to provision. **Anyone adding a substrate
should start there rather than reinventing it.**

## Alternatives Considered

### Alternative 1: Copy ADR-036's sections per capability

**Description**: Leave `entrypoint.sh` capability-specific. For each new
capability, duplicate sections 5.6 and 5.7 with the prefix changed.

**Pros**:
- Zero abstraction. Each capability's plumbing is readable in one place.
- No registry, no name validation, no `eval`.

**Cons**:
- The entrypoint grows without bound and becomes a shared mutable surface
  whose failure mode is a container that will not start.
- Every capability re-derives the same env prefix logic, with the same
  bugs available to be re-introduced independently.
- No place to put a lifecycle stage (like `finalize`) that more than one
  capability wants.

**Reason for rejection**: This is what the branch started from and it does
not survive the second capability. The `eval` and name-validation cost of
the generic loop is real but bounded and tested; the duplication cost is
unbounded.

---

### Alternative 2: Capability logic in the host provider only

**Description**: No in-container adapters. `DockerProvider` computes every
provider-native env var and injects it. `TranscriptSource` does the
post-agent harvest from the host.

**Pros**:
- No entrypoint changes at all. No shell, no `eval`, no signal handling.
- Typed, testable Python instead of portable shell.
- `TranscriptSource` already exists and already does the hard part.

**Cons**:
- Requires the host to know each provider's native env schema, which is
  exactly the coupling ADR-036 removed.
- Capture only happens when an orchestrator is driving. A workspace run
  directly, with no host process attached, captures nothing.
- EXP-08 validated the in-container path end to end; this one was not
  validated at the time of the decision.

**Reason for rejection**: The "no orchestrator" case matters. The goal is
to capture agent work whether or not a host orchestrator is present.
Rejected for v1, **not rejected in principle**: this is precisely the shape
section 11 above recommends for a second substrate, and the two are
complementary rather than exclusive.

---

### Alternative 3: Orchestrator-triggered sweep via `docker exec`

**Description**: Keep `exec "$@"`. The orchestrator runs the sweep with
`docker exec` before teardown. This was EXP-08 arm A4 and the plan's Task
7B.

**Pros**:
- Measured working, cleanly: 3/3 captured, tags correct, `origin_host`
  untouched. Strictly simpler than the wrapper.
- No signal handling, no stop-grace coupling, no `set -e` traps.

**Cons**:
- Same "no orchestrator, no capture" hole as Alternative 2.
- Puts a lifecycle responsibility in every host that wants capture, which
  is drift waiting to happen across orchestrators.

**Reason for rejection**: Viability was never the question; both arms
worked. The wrapper was chosen because it is the only option that captures
sessions when nothing is driving the container. Task 7B remains a valid
fallback if the wrapper's timing coupling ever proves too fragile.

---

### Alternative 4: Vendor the exporter into the image

**Description**: `COPY` or `curl` the exporter binary at build time so the
capability is turnkey.

**Pros**:
- `exporter_present` passes out of the box. No deployment step.
- One fewer way for an operator to get it wrong.

**Cons**:
- Requires build credentials for a private artifact, so the image could no
  longer be built by anyone who does not have them.
- Bakes one vendor's client into a generic image, contradicting the store
  being dependency-injected.

**Reason for rejection**: The credential requirement is disqualifying on
its own. See section 10: the exporter site is a binding, and bindings do
not belong in the image.

## Consequences

### Positive Consequences

- **A new capability is a directory plus a registry entry.** No entrypoint
  edit, which means no risk of a bad edit bricking container startup for
  capabilities that had nothing to do with the change.
- **The substrate seam is real and cheap to exercise.** The in-container
  half has no Docker knowledge. An E2B binding can reuse every adapter
  unchanged, or skip them entirely in favor of `TranscriptSource`.
- **Session capture survives a crash with attribution intact.** The
  partitioned spool plus `.capture-env` means a SIGKILLed container's
  transcripts can still be swept later and land correctly tagged. Verified
  in EXP-08 arm A5 after the original design was proven wrong.
- **Re-sweeping is safe.** The store dedups on `content_hash`, so a
  recovery sweep of an already-uploaded partition is a no-op through both
  the fingerprint gate and the content-hash gate (EXP-08 arm A6).
- **The doctor pattern generalizes.** Both capabilities emit the same JSON
  shape into the same audit directory, so one log parser covers all of
  them.

### Negative Consequences

- **The lifecycle uses `eval` on a derived variable name.** Necessary in
  bash to read `${AGENTIC_<CAP>_PROVIDER}` from a computed prefix. Mitigated
  by strict charset validation before any prefix is built, and by
  integration tests covering traversal payloads and malformed names, but it
  is genuinely the sharpest edge in the design.
- **A cross-file timing coupling now exists** between `entrypoint.sh` and
  `providers/docker.py`, enforced only by comments and a test. Breaking it
  silently disables post-agent capture. See section 6.
- **A misconfiguration path that only warns.** The unregistered-provider
  case in section 5 is the one place a capability can be silently inactive.
- **Interactive-tmux workspaces cannot use capabilities at all.** Section 8.
- **Section 6 is no longer `exec`**, so PID 1 is the wrapper rather than
  the agent. Exit codes are preserved explicitly, but this is a behavior
  change for anyone who was relying on process-tree shape.
- **The image is not turnkey for session-store.** Deployment must provide
  the exporter. Accepted deliberately; see section 10.

## Migration

This branch moves interfaces that ADR-036 named, so the workspace image
manifest goes **1.2.0 to 2.0.0**. Three breaking changes, in the order an
operator will hit them:

| # | Was | Is | What the operator must do |
|---|---|---|---|
| 1 | `/opt/agentic/memory/doctor` | `/opt/agentic/capabilities/memory/doctor` | Update any script, healthcheck, or runbook that invokes the memory doctor by path. Same for adapter paths: `/opt/agentic/memory/<provider>/init.sh` moves to `/opt/agentic/capabilities/memory/<provider>/init.sh`. |
| 2 | `AGENTIC_MEMORY_AUDIT_DIR` | `AGENTIC_CAPABILITY_AUDIT_DIR` | Rename the variable wherever it is set. It is now capability-generic: it overrides the audit directory for **every** capability, not just memory. The per-capability default is still `/var/agentic/<capability>-doctor`, so hosts that only bind-mount the default path need no change. |
| 3 | `AGENTIC_MEMORY_PROVIDER` alone activated memory | Memory must **also** appear in `AGENTIC_CAPABILITIES` | No action if you accept the image default (`AGENTIC_CAPABILITIES="memory session-store"`). If you set `AGENTIC_CAPABILITIES` explicitly, include `memory` or memory silently stops running. The entrypoint warns on this exact case, on stderr, at startup. |

Nothing else in the memory contract changed. `AGENTIC_MEMORY_PROVIDER`,
`_NAMESPACE`, `_NAMESPACE_KIND`, `_URL`, `_AUTH`, and `_CONFIG_JSON` keep
their names and meanings, and `AGENTIC_MEMORY_READY=1` is still exported on
a successful init.

Accompanying library versions: `agentic_memory` goes 0.1.0 to 0.2.0 (it
gained the public `Env` and `CAPABILITY` symbols and the
`capability_env_name()` helper). `agentic_session_store` is new at 0.1.0.

## Implementation Notes

- **The authoring guide** at [`docs/workspace-capabilities.md`](../workspace-capabilities.md)
  walks through adding a capability end to end, using session-store as the
  worked example. Read that before writing an adapter; read this ADR to
  understand why it is shaped that way.
- **Per-module READMEs** live at
  `providers/workspaces/claude-cli/capabilities/<capability>/README.md` so
  each module is comprehensible standalone.
- **Tests**: `tests/integration/test_entrypoint_capabilities.py` covers the
  registry hardening, the adapter's env translation and symlinks, the
  `.capture-env` parse-never-source property (with malicious tag fixtures),
  finalize's exit-code neutrality, and the two `docker stop` timing arms
  (cooperative and stubborn agents).
- **Unverified claim carried forward.** EXP-08's A5 repair sub-arm ran
  against a store server build predating the reconcile-on-duplicate fix, so
  it says nothing about whether metadata reconciliation works on a
  duplicate content hash. Code reading says it does. Re-verify against a
  current store build before relying on the repair path.

## References

- [ADR-036: Memory Primitive and Doctor](036-memory-primitive-and-doctor.md) - superseded in mechanism, retained for reasoning
- [ADR-035: Workspace Injection Contract](035-workspace-injection-contract.md) - the env-var and entrypoint-section conventions this ADR extends
- [ADR-033: Plugin-Native Workspace Images](033-plugin-native-workspace-images.md)
- [ADR-027: Provider-Based Workspace Images](027-provider-workspace-images.md)
- [EXP-08: Workspace capability capture lifecycle](../../experiments/EXP-08-capability-capture-lifecycle.md) - the empirical basis for sections 6, 8, and 9
- [Authoring guide: workspace capabilities](../workspace-capabilities.md)
- [session-store module README](../../providers/workspaces/claude-cli/capabilities/session-store/README.md)
- [memory module README](../../providers/workspaces/claude-cli/capabilities/memory/README.md)
