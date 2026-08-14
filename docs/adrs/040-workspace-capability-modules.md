---
title: "ADR-040: Workspace Capability Modules"
status: accepted
created: 2026-08-12
updated: 2026-08-14
author: NeuralEmpowerment
supersedes: ADR-036 (in mechanism)
tags: [workspace, capabilities, contracts, claude-cli, session-store, memory, lifecycle]
---

# ADR-040: Workspace Capability Modules

## Status

**Accepted**

- Created: 2026-08-12
- Updated: 2026-08-14
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

### 12. The workspace image contract

Sections 1 through 11 describe what a *capability* must provide. This
section describes the other half: what an *image* must provide in order to
host capabilities. It is the half that makes the harness swappable, because
it is the list a second image has to satisfy and the list is deliberately
short.

An image hosting capability modules must:

1. **Run the shared `workspace/entrypoint.sh` as its `ENTRYPOINT`.** The
   registry loop, the three hooks, and the post-agent wrapper live there.
   An image that runs its own entrypoint is not hosting capabilities; it is
   hosting a fork of them.
2. **Provide `/opt/agentic/capabilities/` populated from the shared
   `workspace/capabilities/` tree.** Populated by *staging*, not by copying
   the tree into the provider directory. `stage_workspace_runtime()` in
   `scripts/build-provider.py` copies `workspace/` into the build context;
   the image's `COPY` reads it from there.
3. **Make every module script executable, at any nesting depth.** The
   lifecycle *sources* `init.sh` but *executes* `doctor` and `finalize.sh`,
   so a non-executable module script is a runtime failure that neither the
   build nor a link check can catch. The claude-cli image does this with a
   depth-unbounded `find /opt/agentic/capabilities -name "*.sh" -exec chmod
   755`, plus a separate pass for the extensionless `doctor` entry. That
   second pass is currently pinned to `-mindepth 2 -maxdepth 2`, which
   matches section 1's layout exactly and nothing deeper. An image is
   satisfying the contract only if its permission pass covers the layout it
   actually ships.
4. **Declare `AGENTIC_CAPABILITIES` as an image `ENV`.** The registry is
   part of what the image *is*, not something a host is expected to know to
   set. A host may narrow it; per section 5 that narrowing is the one
   misconfiguration the system only warns about, which is a further reason
   the default belongs in the image.
5. **Provide the runtime each capability's doctor needs.** Today every
   `doctor` entry execs `python -m <pkg>.doctor`, preferring
   `/opt/venv/bin/python` and falling back to `python3` on `PATH`, so the
   image must ship a Python with the capability packages installed. The
   contract is "a runtime that satisfies the shipped doctor entries"; the
   venv path is this image's binding to it, in the same sense as section 10.

**What the image does not own**, and must not fork per image: the env
contract (section 2), the three-hook lifecycle and its failure semantics
(section 3), and the registry loop with its name validation (section 5). A
second image that reimplements any of these has reintroduced exactly the
duplication Alternative 1 was rejected for, one image at a time instead of
one capability at a time.

#### 12.1 The in-container layout is a contract, not an observation

> **`/opt/agentic/entrypoint.sh` and `/opt/agentic/capabilities/` are
> fixed. Where their sources live in the repository is free to change; where
> they land in the container is not.**

This is the property that made M2 safe, and it is stated here as a rule so
that a reviewer can cite it rather than rediscover it. The mechanical form:
**a commit that relocates the runtime's source files must leave the
destination side of every `COPY` byte-identical.** `git show -M <commit> |
grep '/opt/agentic'` is the check, and only source-side changes may appear
in its output.

The M2 move commit passes that check exactly. Across the whole commit the
only `/opt/agentic` lines are two `COPY` destinations, character for
character unchanged, with only the source side moved:

```
-COPY scripts/entrypoint.sh /opt/agentic/entrypoint.sh
+COPY workspace/entrypoint.sh /opt/agentic/entrypoint.sh
-COPY capabilities/ /opt/agentic/capabilities/
+COPY workspace/capabilities/ /opt/agentic/capabilities/
```

The failure this rule prevents is quiet. A change that rewrote in-container
paths while also moving source files would produce a source tree that looks
correct, documentation that passes a link check, and images that break only
when a container starts. Nothing before runtime would object. The Migration
table above is the precedent for the cost when an in-container path really
must move: it is a breaking change with a major version bump and an
explicit operator action, not something to be carried along inside a
refactor.

**The move produced exactly one breakage, and its shape is the argument for
this rule.** The naming conformance test of section 2, which reads
`entrypoint.sh` from disk and runs the real `__capability_env_prefix` in a
bash subprocess to pin it against `capability_env_name()`, existed in both
`agentic_memory` and `agentic_session_store` and read the pre-move path in
both. The move deleted that path, so both failed with `FileNotFoundError`
and were repaired separately. Nothing inside a container broke, because
`/opt/agentic/**` did not move. **The only thing that broke was a test
reaching into the source tree from outside it, and that asymmetry is the
whole point.** A fixed in-container layout confines a source relocation's
blast radius to things whose coupling is to source paths, which are
findable, rather than to running containers, which are not.

Two further details are worth keeping, because they are why it was not
caught at review time:

- **It was invisible, not tolerated.** Both packages sat outside CI's matrix
  and outside the local QA runner's package list until the same day, so the
  only test that could have objected was not being executed by anything. The
  move's review saw a green tree because the tree was not being fully run.
- **The recursion.** That test exists specifically to catch drift between
  two implementations of one rule, and its own drift went undetected. A test
  that reads a file by path is coupled to the source tree, so a source-tree
  move can break it silently, and the very property that makes it valuable
  (it reads the real shipped file rather than a copy) is what makes it
  fragile to relocation. Any future move of the runtime must re-point such
  tests in the same commit and run them, precisely because they are the
  tests least likely to be covered by a documentation sweep.

#### 12.2 The neutrality boundary, and the sites still outside it

M2 moved the capability runtime out from under `providers/workspaces/claude-cli/`.
It did **not** make that runtime harness-neutral. Those are different
achievements, and the boundary between them runs through the middle of
`workspace/`, so it is drawn here explicitly rather than left as a caveat.

**Inside the boundary, genuinely neutral and not to be forked per image:**
the env contract (section 2), the three-hook lifecycle (section 3), the
registry loop and its hardening (section 5), and the
`workspace/capabilities/` tree itself. Individual provider adapters do name
harness paths (`~/.claude/projects` and `~/.codex/sessions` in the seshmagic
adapter, `~/.hindsight/claude-code.json` in the hindsight adapter), which is
what an adapter is for: a per-provider binding, not an image-level fork.

**Outside the boundary:** `workspace/entrypoint.sh` is shared in *location*
only. It still carries harness-specific setup, at these sites:

| Site | What it does | Status |
|---|---|---|
| `workspace/entrypoint.sh:33-64` | Section 1 writes `~/.claude/settings.json` unconditionally, with no capability, provider, or harness condition around it. The written document enables three Claude Code plugin identifiers. | Harness-specific. M3. |
| `workspace/entrypoint.sh:66-91` | Section 2 scans `/opt/agentic/plugins/` for `.claude-plugin/plugin.json` and builds `--plugin-dir` flags (built at `:74-88`), which the file describes at `:71-72` as flags "for the orchestrator to append when invoking claude CLI". | Harness-specific. M3. |
| `workspace/entrypoint.sh:113-115` | Comments the first git-hooks source as "owned by the claude-cli provider itself", baked in from `providers/workspaces/claude-cli/scripts/git-hooks/`. | **Accurate, no change needed.** That directory correctly stayed behind in the provider. Evidence of a provider-specific dependency, not a stale path. |

The consequence, stated plainly: **a second image staging this tree today is
handed Claude's configuration whether or not it runs Claude.** Not a
degraded experience, an incorrect one.

Factoring the first two rows out, behind a condition or a per-provider hook,
is **M3's scope**, named here so it is a tracked boundary with two known
sites rather than a debt some later reader discovers. M3 is where the omni
image forces the question. Until then the honest statement is that the
runtime is *shared*, not that it is *neutral*.

#### 12.3 A move commit contains only the move

Recorded here as a reviewability property rather than a style preference.

The check that made M2 verifiable is `git diff --name-status -M` showing
every relocated file at `R100`. That signal is what lets a reviewer confirm
"nothing changed, things moved" without reading the files. Any content edit
inside the same commit, including a reformat or an unrelated tidy, drops
those files below `R100` and the reviewer can no longer distinguish a file
that was relocated from a file that was changed. The whole diff then has to
be read as new code.

The M2 commit satisfied this: ten relocated files, all `R100`, with the
only content changes in the two files that must change for a move to work
at all, `Dockerfile` and `scripts/build-provider.py`. Combined with 12.1,
that is the entire review: the renames are pure, and the two edited files
touch source paths only.

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
- **The doctor pattern generalizes.** Both capabilities emit JSON into the
  same audit directory with the `capability` field in common, so a reader
  can attribute every record. The two payload shapes otherwise still
  differ: memory predates the `capability`/`passed`/`checks` shape
  session-store established and has not been reconciled to it; see
  [docs/workspace-capabilities.md](../workspace-capabilities.md).

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
- **The shared entrypoint is not yet harness-neutral.** It is shared in
  location, and two of its sections still configure Claude specifically, so
  a second image staging the tree today inherits that setup. Two enumerated
  sites, tracked as M3 scope; see section 12.2.

## Migration

This branch moves interfaces that ADR-036 named, so the workspace image
manifest goes **1.3.0 to 2.0.0**. Note for anyone tracing the version line:
the last *released* version is 1.2.0. The intermediate 1.3.0 was set earlier
on this same branch, during the capability-registry refactor, and never
shipped. An operator upgrading is therefore coming from 1.2.0.

Three breaking changes, in the order an operator will hit them:

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
  `workspace/capabilities/<capability>/README.md` so
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
- [session-store module README](../../workspace/capabilities/session-store/README.md)
- [memory module README](../../workspace/capabilities/memory/README.md)
