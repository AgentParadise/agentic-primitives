# Authoring a workspace capability

How to add a pluggable subsystem to the workspace image, end to end.

The decision record is [ADR-040](adrs/040-workspace-capability-modules.md).
This document is the procedure. Read the ADR when you want to know *why*
something is shaped the way it is; read this when you want to build one.

The worked example throughout is `session-store`, the capability that
uploads agent transcripts to a session store speaking APS-V1-0004. Every
file referenced below exists and can be read alongside this guide.

---

## The one invariant

> **Adding a capability requires ZERO changes to `entrypoint.sh`.**

If you find yourself editing `providers/workspaces/claude-cli/scripts/entrypoint.sh`
to make your capability work, stop. That is not a task, it is a signal:
the contract is wrong, and the fix belongs in the contract. The generic
lifecycle in sections 5.6, 5.7, and 6 is capability-agnostic on purpose,
and every per-capability line added to it costs the next author.

Verify the invariant on your own branch before you open the PR:

```bash
git diff main -- providers/workspaces/claude-cli/scripts/entrypoint.sh
```

That should be empty.

---

## The two halves

A capability has an **in-container half** (portable shell plus a Python
contract library, baked into the image) and a **host-side half** (how the
contract's env vars, mounts, and timings actually reach the container).

You are almost always writing the in-container half. It must not know it is
running in Docker. Anything it needs from the substrate arrives as an env
var or a mounted path. That discipline is what lets the same adapter run
unchanged on a future E2B binding.

---

## Step 1: Pick the name

The registry name is lowercase letters, digits, and hyphens only
(`[a-z0-9-]+`). This is enforced by `__capability_name_safe` in the
entrypoint, and the charset is narrower than the provider charset for a
concrete reason: a name containing `.` uppercases into a prefix like
`AGENTIC_A.B`, whose expansion is a bash bad substitution that kills the
whole entrypoint under `set -e`.

The name determines your env prefix by the ADR-040 rule:

```
AGENTIC_<CAP_UPPER>_<FIELD>      uppercase, '-' -> '_'
```

So `session-store` + `partition` gives `AGENTIC_SESSION_STORE_PARTITION`.

`AGENTIC_<CAP>_PROVIDER` is reserved by the lifecycle. It selects your
adapter directory, and when unset or set to `none` your capability is a
complete no-op.

---

## Step 2: Write the contract library

Create `lib/python/agentic_<name>/` with a `contract.py`. Two rules:

**Every env var name is declared exactly once, in an `Env` StrEnum.**
Nothing in the package, its doctor, or its tests may spell one as a string
literal. A renamed variable must break at import, not at runtime inside a
container three deploys later.

**Ship `capability_env_name()`.** It is the Python half of the naming rule;
`__capability_env_prefix` in the entrypoint is the shell half. A conformance
test pins the two together so drift is a CI failure.

From `agentic_session_store/contract.py`:

```python
CAPABILITY = "session-store"

class Env(StrEnum):
    PROVIDER  = "AGENTIC_SESSION_STORE_PROVIDER"
    URL       = "AGENTIC_SESSION_STORE_URL"
    AUTH      = "AGENTIC_SESSION_STORE_AUTH"
    TAGS      = "AGENTIC_SESSION_STORE_TAGS"
    SPOOL     = "AGENTIC_SESSION_STORE_SPOOL"
    PARTITION = "AGENTIC_SESSION_STORE_PARTITION"
```

Members are `str`, so they pass straight to `env.get()`,
`monkeypatch.setenv()`, and f-strings with no `.value`. Member *names* are
the field half of the naming rule, which is what the conformance test
checks.

Then a frozen dataclass with a `from_env(env: Mapping[str, str])`
classmethod obeying two behaviors:

- **Not opted in returns `None`.** Provider unset or `none`, no exception,
  no checks, no side effects.
- **Opted in but misconfigured raises `ValueError`.** Opting in is opting
  into loud failure (ADR-036, still binding).

Validate anything that will become a path. `session-store` rejects a
provider name outside `[a-zA-Z0-9][a-zA-Z0-9._-]*` or containing `..`, and
rejects an absolute or `..`-containing partition. Do the same for your own
fields. If a value ends up in a filesystem path, it is untrusted input.

If your capability *exports* provider-native vars, name those in a second
enum (`ExporterEnv` in the example) so the doctor can assert on them
without restating literals.

---

## Step 3: Write the doctor

Create `doctor.py` in the same package with a `main(argv)` that:

- returns **0 and prints nothing** when `from_env()` returns `None`,
- runs every check even after one fails, so one invocation gives the
  operator the whole picture,
- writes a pretty summary to **stderr** and, under `--json`, one JSON
  object to **stdout**,
- returns 0 when all checks pass, 1 otherwise.

Follow the `session-store` payload shape for new capabilities:

```json
{"capability": "...", "passed": true, "checks": [{"name": "...", "passed": true, "detail": "..."}]}
```

`memory` predates this shape (`doctor_version`, `timestamp`, `provider`,
`namespace`, `status`, `checks: [{name, status, message, details,
duration_ms}]`, `exit_code`) and has not been reconciled to it. That
reconciliation is a deliberate follow-up, not something to replicate in a
new capability. The only field guaranteed present in both today is
`capability`, which is what lets a reader attribute a record in a shared
audit directory; do not assume any further overlap.

**A doctor must never crash.** `run_checks` wraps each check in an outer
`try/except` that converts an unanticipated exception into a failed
`CheckResult`. Individual checks additionally catch their own *expected*
failure modes so the detail string is specific rather than a generic
"raised: ...". A doctor that dies on a malformed URL takes the other four
checks down with it and tells the operator nothing.

`session-store` ships five checks, and their shape is a reasonable
template: `contract_parses`, `spool_writable`, `symlinks_correct`,
`exporter_present`, `store_reachable`. Memory ships eight, including a
`ProviderSpecificCheck` that shells out to the adapter's own `doctor.sh`.

Add the bash entry point at
`providers/workspaces/claude-cli/capabilities/<name>/doctor`. It is a thin
wrapper, copied from either existing capability, that execs the Python
module and passes flags through:

```bash
if [ -x "/opt/venv/bin/python" ]; then
  exec /opt/venv/bin/python -m agentic_<name>.doctor "$@"
fi
exec python3 -m agentic_<name>.doctor "$@"
```

---

## Step 4: Write the adapter hooks

Adapters live at
`providers/workspaces/claude-cli/capabilities/<name>/<provider>/`.
`scripts/build-provider.py`'s `stage_capabilities()` copies the whole tree
into the build context and the Dockerfile `COPY`s it to
`/opt/agentic/capabilities/`. You do not touch either file.

### `init.sh` (required)

**Sourced** by entrypoint 5.6, so its `export`s propagate to every later
process spawn. Its whole job is translating your `AGENTIC_<CAP>_*` contract
into whatever the underlying tool actually reads.

On success the lifecycle also exports `AGENTIC_<CAP>_READY=1`. On failure
it warns and continues, and section 5.7's doctor is what turns the failure
into a hard stop with a specific cause.

Keep it portable shell. No `docker`, no host paths, no substrate
assumptions.

Two hazards `session-store` hit that are worth knowing before you hit them:

- **Symlinks, not bind-mounts, under `$HOME`.** Docker creates a bind-mount
  root as root-owned while the container runs as uid 1000 (verified in
  EXP-07), which breaks writes. Put the real directory outside `$HOME` and
  symlink it in.
- **Migrate a pre-existing real directory; never delete it.** If
  `~/.claude/projects` already exists as a directory, `ln -sfn` nests the
  link *inside* it rather than replacing it, and your doctor then hard-fails
  the workspace with a confusing error. The obvious fix, `rm -rf` the
  directory first, is a data-loss bug, and shipped as one: on a persisted
  `$HOME`, or any workspace where the harness already ran, it destroys
  un-uploaded transcripts at startup, before the exporter has ever run.
  Instead move the contents into the partition so this run's finalize sweeps
  and uploads them, then symlink. Use `mv -n` (never overwrite) followed by
  `rmdir` (refuses a non-empty directory) so that anything the move could not
  place leaves the source intact and the adapter returns non-zero rather than
  guessing. Leave an existing symlink or a missing path alone; `ln -sfn`
  handles those correctly. A workspace that refuses to start is recoverable;
  a deleted transcript is not.

### `doctor.sh` (optional)

Provider-specific checks that do not belong in the generic Python doctor.
Emit JSON on stdout, exit 0 for pass and 1 for fail.

You can wire it into the Python doctor's check list, as memory does with
`ProviderSpecificCheck`, or leave it as a hand-run tool, as `session-store`
does today. If you leave it unwired, say so in the module README so nobody
assumes it runs at startup.

### `finalize.sh` (optional)

**Executed** (not sourced) by entrypoint section 6 after the agent exits.
This is the hook for post-agent work: sweeping, uploading, flushing.

Four rules, each of which cost something to learn:

1. **Always exit 0.** The lifecycle already calls it as `|| true`, but the
   hook itself must also be soft. A failed upload after an hour of
   successful agent work must never make the phase report as failed.
2. **Never write to stdout.** Under the old `exec "$@"`, container stdout
   was exclusively the agent's. Finalize now runs after the agent, so
   chatter on stdout corrupts anything parsing it (an agent CMD invoked
   with a structured `--output-format`, for instance). Send both streams to
   stderr with `>&2 2>&1`, in that order.
3. **Assume it may run standalone.** A recovery sweep of a spool left by a
   SIGKILLed container has none of `init.sh`'s exported env. Guard every
   variable you read (`${VAR:-}`), because a bare expansion under `set -u`
   aborts the script and breaks the "always exit 0" contract on exactly the
   failure path recovery exists to handle.
4. **Be fast.** You are inside the container stop grace. See the timing
   budget below.

### The timing budget

`__TERM_GRACE_TICKS` in `entrypoint.sh` (currently 15 ticks of 0.1s, so
1.5s) must stay **strictly below** the `docker stop -t` value in
`lib/python/agentic_isolation/agentic_isolation/providers/docker.py`
(currently 5s), with the remaining headroom (about 3.5s) available for your
finalize hook's real work.

During implementation the two were effectively tied and finalize silently
never ran, with the container's exit code becoming 137 and nothing in the
logs saying why. Both files carry cross-referencing comments. If your
finalize needs more than the headroom, raise the `docker stop` grace, not
the ticks.

#### `AGENTIC_FINALIZE_BUDGET_S`

Your finalizer receives a per-run budget in seconds through this variable.

**Read it, never set it.** It is not user-facing configuration and is not part
of the capability contract's public surface. It is an internal call parameter
between `entrypoint.sh` and the finalizers, travelling by environment because
that is how you pass a value to a child process. Do not document it to
operators as a knob, and do not add it to a `.env.example`.

Treat an absent, non-numeric, or **zero** value as "use your own default":

```sh
case "${AGENTIC_FINALIZE_BUDGET_S:-}" in
    "" | *[!0-9]* | 0) __TIMEOUT_S="${__TIMEOUT_DEFAULT_S}" ;;
    *) __TIMEOUT_S="${AGENTIC_FINALIZE_BUDGET_S}" ;;
esac
```

Zero matters as much as empty. GNU `timeout 0` means *no timeout at all*, so a
guard that only tested for empty or non-numeric would leave `0` as a silent way
to disable the bound entirely, which is the exact failure the budget exists to
prevent.

**The budget is asymmetric, because the deadline only exists on one path.**
`__run_finalizers` is called on both exits, but the SIGKILL escalation window
only runs when the agent's status is `>128`, the signal path. Your finalizer
cannot tell which path it is on; only the entrypoint knows, which is why the
value is passed in rather than decided locally.

| Constant | Value | Path |
|---|---|---|
| `__FINALIZE_BUDGET_SIGNAL_S` | 2 | Signal. `docker stop -t 5` is already ticking. |
| `__FINALIZE_BUDGET_CLEAN_S` | 120 | Clean exit. Nothing is waiting; the bound only stops a wedged finalizer hanging the run forever. |

Measured 2026-08-14 through the real entrypoint: escalation completes at ~1.66s
for a stubborn agent and ~0.22s for a cooperative one, leaving ~3.3s of the
stop grace. A 2s budget finishes at ~3.66s, a 1.3s margin; 3s would leave 0.34s,
too thin.

**The 120 is bounded, not derived.** Nobody has measured a real sweep against a
large migrated transcript history. It may be short for a heavy first sweep,
which is also the case where failing to complete hurts most, because a capability
that never finishes its work never prunes. Treat it as a ceiling that has not yet
been tested against the workload that would falsify it.

A single tight bound applied to both paths was the tempting simplification and
is wrong: it kills a legitimate multi-second sweep on every normal run, so the
capability never completes its work, which for a heavy user is permanent.

**One invariant to preserve.** `entrypoint.sh` assigns the value
unconditionally:

```sh
AGENTIC_FINALIZE_BUDGET_S="${1}"
```

There is deliberately no `:-` fallback. That is what stops
`docker run -e AGENTIC_FINALIZE_BUDGET_S=99999` from reaching your finalizer:
the outer value is always overwritten before export. A refactor to
`"${AGENTIC_FINALIZE_BUDGET_S:-$1}"` reads as a harmless defensive tidy and
silently reopens it.

---

## Step 5: Handle untrusted values correctly

If your capability persists an orchestrator-supplied value to disk for a
later process to read, that file is **data, and must be parsed, never
sourced**.

`session-store` writes tags to `$SPOOL/$PARTITION/.capture-env`:

```
SESSION_STORE_TAGS=<opaque tag string, exactly as received>
```

It looks like shell. Sourcing it is arbitrary code execution in a process
holding the store write token. Demonstrated during review, not theorized: a
tag of `workflow:$(touch /tmp/PWNED)` executed on source, and any tag
containing a space truncated the value to empty, destroying the very
attribution the file exists to preserve.

The correct read is line-oriented and quote-agnostic:

```bash
SESSION_STORE_TAGS="$(sed -n 's/^SESSION_STORE_TAGS=//p' "${capture_env}" | head -1)"
export SESSION_STORE_TAGS
```

`export` is required because the consumer is a child process; a bare shell
variable never reaches it.

Write such files under `umask 077` in a subshell, not with a post-hoc
`chmod`, which leaves a window where the file is world-readable. Remove any
stale copy unconditionally before writing, so a reused partition never
serves a previous run's values.

---

## Step 6: Register it

Add the name to `AGENTIC_CAPABILITIES` in the Dockerfile's `ENV` block:

```dockerfile
AGENTIC_CAPABILITIES="memory session-store" \
```

Space-separated. The lifecycle iterates this list in both 5.6 and 5.7, and
a listed capability with no `AGENTIC_<CAP>_PROVIDER` set is a silent no-op,
so listing a capability costs nothing at runtime.

Operators can override the list, and this is the one place a
misconfiguration only warns: setting `AGENTIC_<CAP>_PROVIDER` for a
capability *not* in the registry produces a stderr warning at startup and
otherwise does nothing. That is deliberate (an operator may be disabling a
capability on purpose), but it means an override that forgets a name
silently disables it.

Then bump `providers/workspaces/claude-cli/manifest.yaml`. A new capability
is a minor bump. Moving or renaming an interface that an ADR names is a
major bump, as the 1.3.0 to 2.0.0 move on this branch was (1.2.0 was the
last released version; the intermediate 1.3.0 never shipped).

---

## Step 7: Test it

Add to `tests/integration/test_entrypoint_capabilities.py`. The existing
tests are the checklist. Cover at minimum:

**Registry hardening**, which is generic and mostly already covered:
unknown capability name is skipped rather than fatal, a provider name
cannot escape the capabilities directory, an invalid capability name is
skipped, an unregistered provider warns without failing.

**Your adapter**: that `init.sh` translates the contract and creates
whatever it is supposed to create, and that it is idempotent across a
re-run.

**Your doctor**: at least one specific failure (`exporter_present` when the
binary is absent) and one full pass against a real dependency.

**Your finalize**, if you have one: that it never changes the agent's exit
code (on both success and failure paths), that a missing hook is a silent
skip, that it survives its own env being unset, and that it parses rather
than sources any persisted data. Use hostile fixtures for that last one,
not friendly strings.

**The timing arms**, if you have a finalize: a `docker stop` against a
cooperative agent (exits with its own code, finalize runs) and against a
stubborn one (killed, finalize still runs). These are the tests that catch
a broken stop-grace coupling, and nothing else will.

If you need a dependency you cannot ship, commit a test double.
`tests/integration/fixtures/stub-exporter` satisfies `exporter_present` and
emits the real binary's summary-line shape. It is not a substitute for an
end-to-end run against the real thing.

---

## Step 8: Document it

Write `providers/workspaces/claude-cli/capabilities/<name>/README.md`, so
the module is comprehensible standalone. The two existing READMEs are the
template: contract table, on-disk layout, what the adapter deliberately
does *not* do, and how to run the doctor by hand.

If your capability requires something the image does not ship, say so
explicitly and give the provisioning routes. See the session-store README's
exporter provisioning contract.

---

## Known limits

- **Headless only.** `InteractiveTmuxProvider` rejects `environment` and
  `secrets` outright, so the capability contract cannot reach
  interactive-tmux workspaces at all. Extending that provider is separate
  work.
- **Docker only, today.** The in-container half is substrate-neutral by
  construction, but the only host-side binding that exists is
  `DockerProvider`.
- **Section 6 is a wrapper, not `exec`.** PID 1 is the wrapper. Exit codes
  are preserved explicitly. Note that both production providers run the
  image with `sleep infinity` as CMD and launch agents via `docker exec`,
  so on that path the agent is not the wrapper's child and the exit-code
  handling is never exercised. What matters in production is that finalize
  fires inside the stop grace.

## Adding a substrate

Do not start from `entrypoint.sh`.

`lib/python/agentic_isolation/agentic_isolation/harnesses/` already defines
a provider-abstracted `TranscriptSource` protocol, with `claude` and
`codex` plugins, contracted never to raise (failures come back through
`TranscriptExtractionResult.errors` so a harvest can never abort a
teardown). `DockerProvider` already implements `transcript_source()`. It
has **no production caller** only because the in-container exporter was
already validated end to end by EXP-08 and a second live capture path would
have meant two mechanisms to keep correct.

For a substrate with no entrypoint of ours to wrap, that protocol is the
natural host-side half. Start there.

## References

- [ADR-040: Workspace Capability Modules](adrs/040-workspace-capability-modules.md)
- [ADR-036: Memory Primitive and Doctor](adrs/036-memory-primitive-and-doctor.md)
- [ADR-035: Workspace Injection Contract](adrs/035-workspace-injection-contract.md)
- [EXP-08: Workspace capability capture lifecycle](../experiments/EXP-08-capability-capture-lifecycle.md)
- [session-store module README](../providers/workspaces/claude-cli/capabilities/session-store/README.md)
- [memory module README](../providers/workspaces/claude-cli/capabilities/memory/README.md)
