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
It is sourced by `/opt/agentic/entrypoint.sh` section 5.6 (ADR-040) and
translates the six `AGENTIC_SESSION_STORE_*` contract vars (`Env` in
`contract.py`) into the env `SeshMagicSessionExporter` reads:

| Contract var                       | Adapter behavior |
|-------------------------------------|-------------------|
| `AGENTIC_SESSION_STORE_PROVIDER`    | selects this adapter (`seshmagic`) |
| `AGENTIC_SESSION_STORE_URL`         | exported as `SESSION_STORE_URL`. Must be an ORIGIN only: `scheme://host[:port]`, no userinfo, path, query or fragment (see below) |
| `AGENTIC_SESSION_STORE_AUTH`        | exported as `SESSIONS_WRITE_TOKEN`, only if set |
| `AGENTIC_SESSION_STORE_TAGS`        | exported as `SESSION_STORE_TAGS`, only if set, and persisted to `.capture-env` (see below) |
| `AGENTIC_SESSION_STORE_SPOOL`       | root of the spool tree (default `/spool`) |
| `AGENTIC_SESSION_STORE_PARTITION`   | subdirectory under the spool, default `$HOSTNAME` |

### Spool layout

Given `$SPOOL` and `$PARTITION`, the adapter creates:

```
$SPOOL/$PARTITION/                       <- TRANSCRIPTS. The operator may own this.
  claude/           <- CLAUDE_PROJECTS_ROOT, symlinked from ~/.claude/projects
  codex/            <- CODEX_SESSIONS_ROOT, symlinked from ~/.codex/sessions

$SPOOL/.agentic-session-store/           <- ADAPTER METADATA. Reserved namespace.
  .owner            <- ownership marker (agentic-session-store-metadata-v1)
  $PARTITION/
    state.json      <- EXPORTER_STATE_FILE (exporter-owned, created on first sweep)
    .capture-env    <- mode 600, DATA not shell (see below), present only when AGENTIC_SESSION_STORE_TAGS was set
```

**Two directories, two owners.** Transcripts must land where the harnesses
write, and that is a path the operator chose: `SPOOL=/workspace
PARTITION=repos` points at an existing mount. The only things this adapter
does to that directory are `mkdir -p` and creating the two subdirectories it
symlinks the harness roots to. It writes no file of its own there and removes
nothing from it.

Adapter metadata goes to the reserved `$SPOOL/.agentic-session-store/`
namespace instead, because its filenames are fixed and would collide with
whatever the operator already had. `init.sh` claims that namespace before
writing into it, and **refuses loudly rather than deleting or overwriting**
when the reserved name is held by a non-directory, when the directory has
contents but no marker, or when the marker holds an id it does not
recognise. A refusal returns non-zero, so no symlink is created, the
`symlinks_correct` doctor check fails, and the workspace stops at preflight
with a named path.

The marker proves the namespace ROOT. It says nothing about
`$PARTITION` below it, which is a multi-component path, so that chain is
built one component at a time with plain `mkdir` (never `mkdir -p`, which
walks a symlinked component silently). `mkdir` creates the component itself
and fails on any existing name without resolving a link at it, so a success
is proof this adapter created a real directory there; an existing name is
classified and a symlink, or anything that is not a directory, is refused
loudly with nothing removed or replaced. The finished path is then resolved
and required to be the marked root plus the partition components.

Inside that path, this adapter does replace and remove its own files (see
`.capture-env` below). That is not the prune coming back: it touches only
files this adapter wrote, at a path whose every component from the marked
root down was proven a real directory when the walk ran, and no transcript
directory lies on it. `.capture-env` and `state.json` are themselves
refused if the name is held by a symlink or by anything else that is not a
regular file, and
`.capture-env` is created with `O_CREAT|O_EXCL` (`set -o noclobber` in the
writing subshell) after the stale copy is removed, so a link planted at
that name between the check and the write fails the write rather than
receiving it.

**What that does not cover**, stated here so nobody plans around a
guarantee the code does not provide. `O_EXCL` constrains the FINAL
component only; the kernel still resolves the directories above it
normally, so a parent swapped for a symlink after the walk and the resolve
is followed, and the write lands wherever it points. `state.json` gets no
`O_EXCL` cover at all: `init.sh` only classifies the name and exports the
path, and the file is opened later by the exporter, in a different process,
after the agent has run, so anything that changes that path in between is
observed by nobody. Both are races against a writer that already has access
to `$SPOOL`. Closing them needs per-component `openat` with `O_NOFOLLOW`,
which shell cannot express, so they are recorded as known limitations of
this adapter rather than half-fixed with more checks.

A partition written by an older adapter has `state.json` and `.capture-env`
directly in `$SPOOL/$PARTITION`. `finalize.sh` recognises that layout by the
absence of the reserved segment in `EXPORTER_STATE_FILE` and reads the
partition directory for both, so a spool volume that outlives the image
still recovers its tags.

`$SPOOL` must be an absolute path with no `..` segment, and `$PARTITION` a
relative one with the same restriction; both are validated in `contract.py`
and a bad value fails the workspace at startup.

### The store URL is an origin, and only an origin

`AGENTIC_SESSION_STORE_URL` must be `scheme://host[:port]` with `http` or
`https`, and nothing else: no `user:pass@`, no path, no query, no fragment.
A trailing `/` is accepted because it is the same origin written two ways.

This is an allowlist because the blocklist that preceded it lost twice. It
rejected userinfo, then gained query and fragment, and a review then found
`https://store.example/token/hunter2` (and its percent-encoded twin) passing
through the path, which no entry covered. Each round could only name the
channel just found. Scheme, host and port is everything the store endpoint
needs, so accepting exactly that cannot be outflanked.

The credential goes in `AGENTIC_SESSION_STORE_AUTH`, which is never printed.
A refused URL fails at preflight with a message that names the variable and
never echoes the value, because that message reaches both stderr and the
durable doctor audit file.

The invariant belongs to the type, not to one constructor:
`SessionStoreContract.__post_init__` enforces it, so direct construction and
`dataclasses.replace` cannot bypass it the way they could when the check
lived only in `from_env`.

**A store behind a reverse proxy at a subpath is refused**, deliberately. It
now breaks loudly at preflight instead of a credential in a path travelling
silently into the audit file. Supporting that shape means adding a separate
contract field for the prefix, not widening this one.

### The spool is append-only

**Nothing in this capability deletes a partition.** The store is the durable
copy; the spool is a local cache that only ever grows. A sweep reports what
reached the store and leaves every transcript where it is, whether the sweep
was clean or not.

`finalize.sh` used to prune the partition after a sweep it judged clean, gated
by an `.agentic-partition` ownership marker `init.sh` wrote, a clean-summary
check, and a `.sweep-rejected` sentinel. That whole mechanism is gone. Five
data-loss paths were found on this branch and every one of them reached
destruction through that single `rm -rf`, with four of them introduced by the
fix for the previous one. Removing the delete removes the class.

Unbounded spool growth is the accepted tradeoff. Reclaiming space is an
operator decision, made against a view of the store that a finalize hook does
not have.

Transcript roots live outside `$HOME` and are symlinked in, rather than
bind-mounted under `$HOME` directly — Docker creates a bind-mount root as
root-owned while the container runs as uid 1000 (verified in EXP-07),
which breaks writes.

If `~/.claude/projects` or `~/.codex/sessions` already exists as a **symlink**,
it is replaced only when it is already this adapter's own (it resolves into
`$SPOOL`) or when it dangles. A link resolving anywhere else is the
operator's, and retargeting it silently moves capture away from where they
pointed it, so the adapter refuses and names the path instead.

If `~/.claude/projects` or `~/.codex/sessions` already exists as a real
directory (a persisted `$HOME`, or a prior harness run), `init.sh` **migrates
its contents into the partition** and then symlinks, so those transcripts are
swept and uploaded by this run's finalize instead of being lost. The move uses
`mv -n` and then `rmdir`, neither of which can overwrite or force: if anything
at all survives the move, the adapter leaves the directory untouched and
returns non-zero, and the `symlinks_correct` doctor check then fails the
workspace with a specific error. Refusing to start is recoverable; a deleted
transcript is not.

### Crash-recovery attribution (`.capture-env`)

EXP-08 arm A5 found that a container killed with `SIGKILL` leaves its
partitioned spool on disk, but a later recovery sweep has no
`SESSION_STORE_TAGS` in its environment (that env var died with the
process) — so the recovered session uploads with no tags at all, the
exact misattribution the partitioned spool exists to prevent.

`init.sh` closes this gap by writing the opaque tag string to
`$SPOOL/.agentic-session-store/$PARTITION/.capture-env` whenever
`AGENTIC_SESSION_STORE_TAGS` is set.
The file holds exactly one record, and the value is base64-encoded:

```
SESSION_STORE_TAGS_B64=<base64 of the opaque tag string, exactly as received>
```

Base64 is what makes a tag containing a **newline** survive. The record is
line-oriented and the tag string is opaque, so before this a tag of
`workflow:w1\nphase:p2` was written raw, read one line back, and silently
truncated to `workflow:w1`, losing the attribution this file exists to
preserve, with no error anywhere. The encoded value is a single line of
`[A-Za-z0-9+/=]` by construction, so the record stays line-oriented and the
parse stays trivial. It also cannot reintroduce shell interpretation: no
character in the base64 alphabet means anything to a shell.

**`.capture-env` is DATA, never shell — it must be parsed, never
`source`d / `.`d.** Tags originate from the orchestrator as an opaque
string that can contain anything: spaces, `$(...)`, quotes, newlines. A
consumer that sources this file executes that string as a child of a
process that may have `SESSIONS_WRITE_TOKEN` in scope: arbitrary command
execution at sweep time, confirmed by reproduction, not theorized. The
base64 encoding is a truncation fix and is **not** the thing that makes
this safe; parsing instead of sourcing is. The correct parse:

```bash
tags="$(sed -n 's/^SESSION_STORE_TAGS_B64=//p' "${META_DIR}/.capture-env" \
    | head -1 | base64 -d)"
export SESSION_STORE_TAGS="${tags}"
```

`export` is required because the exporter runs as a **child process** of
whatever reads this file; a shell variable alone (from either sourcing or
a bare assignment) never reaches it.

The snippet above loses a tag's *trailing* newlines, because `$(...)`
strips them. `finalize.sh` therefore uses the byte-exact form instead,
which reads to a NUL delimiter (a value out of the environment can never
contain one):

```bash
IFS= read -r -d '' SESSION_STORE_TAGS < <(printf '%s' "${b64}" | base64 -d) || true
export SESSION_STORE_TAGS
```

`read` returns non-zero at EOF without finding the delimiter and still
assigns, which is why the `|| true` is correct rather than a swallowed
error. It needs `bash`; the `$(...)` form above is the portable
approximation.

#### Legacy records: a migration affordance, not a supported format

`finalize.sh` falls back to a bare `SESSION_STORE_TAGS=<value>` line when no
`_B64` record is present.

**Nothing writes that form any more.** It is not a second supported
encoding and must not be treated as one: do not add a writer for it, and do
not extend it. It exists for exactly one reason, and it has a removal
condition.

*Why it exists.* The spool volume outlives the image and is rebuilt
independently of it, so a partition written by an older `init.sh` and
orphaned by a `SIGKILL`ed container can be swept by a newer `finalize.sh`.
Without the fallback those sessions upload unattributed, which is the exact
failure this file exists to prevent. Refusing to read data this capability
itself wrote one image build ago would be choosing a cleaner code path over
the data.

*When it can be deleted.* When a scan of every spool volume still in use
finds no `.capture-env` lacking a `_B64` record. Run this against each
volume's mount point:

```bash
find /spool -name .capture-env -type f -print0 \
    | xargs -0 -r grep -L '^SESSION_STORE_TAGS_B64='
```

`grep -L` lists the files that do **not** contain the current record, so
empty output means that volume is drained. When every volume comes back
empty, the `legacy` branch in `finalize.sh` and this subsection can go
together.

**Do not use the absence of the runtime notice as the signal.** `finalize.sh`
does log a `[finalize] NOTE: ... uses the legacy pre-base64
SESSION_STORE_TAGS record` line whenever the fallback fires, and seeing it is
positive proof that a legacy partition is still in circulation. But an
orphaned partition only emits that line when a sweep actually reaches it, and
it can sit unswept indefinitely. Silence over any window is not evidence of
absence, and deleting the branch on that basis would strand exactly the parked
partition the branch exists for. The notice tells you when you are **not**
done; only the scan above tells you when you are.

The fallback is the same parse-never-source read as before, so it adds a
format to read, not a mechanism. It carries the same truncation limitation
those records were written with.

The file is created with `umask 077` (not a post-hoc `chmod`, which would
leave a window where the file is briefly world-readable) so it lands at
mode `600`. When this run has tags, the record is written over any stale
copy; when it has none, the stale copy is removed, so a reused partition
never serves a previous run's tags. Both writes happen inside the reserved
namespace, after the ownership claim above has succeeded, so neither can
reach a file the adapter did not write.

`finalize.sh` parses this file (never sources it) when
`SESSION_STORE_TAGS` is unset at sweep time, so a recovery sweep recovers
the same tags the original capture had, byte for byte. This adapter
assigns no meaning to the tag string in either direction; it only
persists what it was given, verbatim.

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
