# session-store capability

Opts a workspace image into session export via the APS-V1-0004 standard.
See `doctor` in this directory for the five preflight checks
(`contract_parses`, `spool_writable`, `symlinks_correct`,
`exporter_present`, `store_reachable`) and
`lib/python/agentic_session_store/agentic_session_store/contract.py` for
the env-var contract (`Env` in that module is the single source of truth
for every `AGENTIC_SESSION_STORE_*` variable this capability reads).

## Exporter provisioning contract

The workspace image does **not** ship the `SeshMagicSessionExporter`
binary. The exporter is a reference client of the public APS-V1-0004
standard, not part of the private store server — vendoring one vendor's
binary into the image would break the store being dependency-injected,
and would require build credentials a turnkey user of this image does
not have.

The image defines the contract (`exporter_present` looks for
`SeshMagicSessionExporter` on `PATH` and runs `--version`); deployment
supplies the binary via one of:

1. **Bind-mount at container start** — mount the binary at
   `/usr/local/bin/SeshMagicSessionExporter` (read-only is sufficient).
2. **A derived image** — `FROM` this image and `COPY` the binary in.
3. **A base-layer install** — bake the binary into a custom variant of
   this image before it reaches this capability.

When the exporter becomes public under AgentParadise, provisioning route
1 can be replaced by a `curl` fetch in the Dockerfile; the rest of this
contract (the doctor check, the env vars the adapter exports for the
exporter to read) does not change.

`tests/integration/fixtures/stub-exporter` is a committed test double
satisfying `exporter_present` and emitting the real binary's summary-line
shape, for tests that need the contract satisfied without a real binary
or real uploads. It is not a substitute for end-to-end testing against
the real exporter.

## The `seshmagic` provider adapter

`seshmagic/init.sh` is the adapter for `AGENTIC_SESSION_STORE_PROVIDER=seshmagic`.
It is sourced by `/opt/agentic/entrypoint.sh` section 5.6 (ADR-038) and
translates the six `AGENTIC_SESSION_STORE_*` contract vars (`Env` in
`contract.py`) into the env `SeshMagicSessionExporter` reads:

| Contract var                       | Adapter behavior |
|-------------------------------------|-------------------|
| `AGENTIC_SESSION_STORE_PROVIDER`    | selects this adapter (`seshmagic`) |
| `AGENTIC_SESSION_STORE_URL`         | exported as `SESSION_STORE_URL` |
| `AGENTIC_SESSION_STORE_AUTH`        | exported as `SESSIONS_WRITE_TOKEN`, only if set |
| `AGENTIC_SESSION_STORE_TAGS`        | exported as `SESSION_STORE_TAGS`, only if set, and persisted to `.capture-env` (see below) |
| `AGENTIC_SESSION_STORE_SPOOL`       | root of the spool tree (default `/spool`) |
| `AGENTIC_SESSION_STORE_PARTITION`   | subdirectory under the spool, default `$HOSTNAME` |

### Spool layout

Given `$SPOOL` and `$PARTITION`, the adapter creates:

```
$SPOOL/$PARTITION/
  claude/           <- CLAUDE_PROJECTS_ROOT, symlinked from ~/.claude/projects
  codex/             <- CODEX_SESSIONS_ROOT, symlinked from ~/.codex/sessions
  state.json         <- EXPORTER_STATE_FILE (exporter-owned, created on first sweep)
  .capture-env       <- mode 600, DATA not shell (see below), present only when AGENTIC_SESSION_STORE_TAGS was set
```

Transcript roots live outside `$HOME` and are symlinked in, rather than
bind-mounted under `$HOME` directly — Docker creates a bind-mount root as
root-owned while the container runs as uid 1000 (verified in EXP-07),
which breaks writes.

### Crash-recovery attribution (`.capture-env`)

EXP-08 arm A5 found that a container killed with `SIGKILL` leaves its
partitioned spool on disk, but a later recovery sweep has no
`SESSION_STORE_TAGS` in its environment (that env var died with the
process) — so the recovered session uploads with no tags at all, the
exact misattribution the partitioned spool exists to prevent.

`init.sh` closes this gap by writing the opaque tag string to
`$PART_DIR/.capture-env` whenever `AGENTIC_SESSION_STORE_TAGS` is set:

```
SESSION_STORE_TAGS=<opaque tag string, exactly as received>
```

**`.capture-env` is DATA, never shell — it must be parsed, never
`source`d / `.`d.** Tags originate from the orchestrator as an opaque
string that can contain anything: spaces, `$(...)`, quotes. A consumer
that sources this file executes that string as a child of a process that
may have `SESSIONS_WRITE_TOKEN` in scope — arbitrary command execution at
sweep time. The correct parse is line-oriented and quote-agnostic:

```bash
tags="$(sed -n 's/^SESSION_STORE_TAGS=//p' "${PART_DIR}/.capture-env" | head -1)"
export SESSION_STORE_TAGS="${tags}"
```

`export` is required because the exporter runs as a **child process** of
whatever reads this file; a shell variable alone (from either sourcing or
a bare assignment) never reaches it.

The file is created with `umask 077` (not a post-hoc `chmod`, which would
leave a window where the file is briefly world-readable) so it lands at
mode `600`. A stale `.capture-env` from a previous occupant of the same
partition is removed unconditionally before either writing a new one or
leaving the partition tag-free, so a reused partition never serves a
previous run's tags.

Task 7's `finalize.sh` parses this file (not sources it) when
`SESSION_STORE_TAGS` is unset at sweep time, so a recovery sweep recovers
the same tags the original capture had. This adapter assigns no meaning
to the tag string in either direction — it only persists what it was
given, verbatim.

### What this adapter deliberately does not do

- **It never sets `SESSION_STORE_ORIGIN_HOST`.** The live corpus uses
  `origin_host` for real machine identity, and a separate in-flight
  branch keys per-machine cost attribution on it. Overloading it with
  phase identity would corrupt that telemetry permanently — an earlier
  prototype did exactly this, which is why the tags mechanism exists
  instead.
- **It assigns no meaning to `SESSION_STORE_TAGS`.** The tag string is
  opaque to this layer; the orchestrator (e.g. workflow/phase identifiers)
  decides its structure and semantics.

### Running the doctor by hand

The generic entry point runs every check:

```bash
AGENTIC_SESSION_STORE_PROVIDER=seshmagic \
AGENTIC_SESSION_STORE_URL=http://host.docker.internal:18091 \
AGENTIC_SESSION_STORE_PARTITION=manual-check \
/opt/agentic/capabilities/session-store/doctor --json
```

`seshmagic/doctor.sh` is a narrower, provider-specific check confirming
the exporter's state file is readable/writable and, if present,
well-formed JSON. It is not currently wired into the generic Python
doctor's check list (unlike the memory capability's
`ProviderSpecificCheck`); run it directly, with the adapter's exported
env already in the shell, to exercise it:

```bash
. /opt/agentic/capabilities/session-store/seshmagic/init.sh
/opt/agentic/capabilities/session-store/seshmagic/doctor.sh
```
