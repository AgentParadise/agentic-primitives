# Native child capture hook contract

Research checkpoint for Syntropic137 #1398, 2026-09-22. Implementation and
supported-launch acceptance remain incomplete.

## Codex 0.156.1

Repository: `openai/codex`, pinned tag `rust-v0.156.1`, matching the workspace
image. The pinned source, rather than current documentation, establishes these
interfaces:

| Event | Correlation | Meaning |
| --- | --- | --- |
| PreToolUse, `spawn_agent` (alias `Agent`) | Parent session, turn and tool-use IDs | Runs before the executor; explicit denial can prevent the spawn |
| PostToolUse | Same tool-use ID plus response `agent_id` | Binds the precise launch intent to the returned child |
| SubagentStart | Child identity and parent context | Context-only notification; cannot prevent execution |
| SubagentStop | Child and parent transcript paths | Child turn completion, not permanent child termination |
| SessionEnd | Root only | Cannot certify descendant settlement |

Sources:

- [Pre-execution hook boundary](https://github.com/openai/codex/blob/rust-v0.156.1/codex-rs/core/src/tools/registry.rs#L588)
- [Tool matcher names](https://github.com/openai/codex/blob/rust-v0.156.1/codex-rs/core/src/tools/hook_names.rs#L41)
- [PreToolUse payload](https://github.com/openai/codex/blob/rust-v0.156.1/codex-rs/hooks/src/events/pre_tool_use.rs#L24)
- [Spawn and returned identity](https://github.com/openai/codex/blob/rust-v0.156.1/codex-rs/core/src/tools/handlers/multi_agents/spawn.rs#L109)
- [PostToolUse payload](https://github.com/openai/codex/blob/rust-v0.156.1/codex-rs/hooks/src/events/post_tool_use.rs#L150)
- [Child hook dispatch and stop semantics](https://github.com/openai/codex/blob/rust-v0.156.1/codex-rs/core/src/hook_runtime.rs#L126)

The [failure handling](https://github.com/openai/codex/blob/rust-v0.156.1/codex-rs/hooks/src/events/pre_tool_use.rs#L193)
defaults to allowing execution. Hook launch errors, malformed JSON and several
exit paths do not block. Exit 2 requires nonempty stderr and enabled control
effects. A durable hook can reject known persistence failures, but a hook that
cannot run cannot establish mandatory registration. Strict launch guarantees
therefore require an enforced acknowledgement at the pinned runtime boundary,
or must remain explicitly unproven. Do not convert hook installation into a
claim of complete capture.

Changes between 0.150.1 and 0.156.1 in the cited sources, checked by diffing
both tags: the hook payloads, failure defaults, spawn identity, hook schema,
`hooks` feature gate and trust-hash function are unchanged. Three additive
changes exist. The tool registry gained a `tool_policy` that can keep a tool
from registering at all, which also means no hook fires for it. `SubagentStart`
now also fires for forked subagents, not only fresh ones. `SessionMeta` gained
`forked_from_ordinal_exclusive` and `runtime_workspace_roots`. None of these
alter the capture contract below.

## Claude Code

Workspace pin: 2.1.281. Current official
[hook reference](https://code.claude.com/docs/en/hooks) documents `agent_id` for
SubagentStop, distinct from the parent `session_id`. The workspace stop handler
now preserves this field, with the old `subagent_id` adapter spelling as a
fallback. SubagentStart cannot block creation. Current documentation is not proof
of every field's behavior in the pinned binary; a pinned-version integration
fixture remains required before enabling a supported-launch claim.

## Implementation contract

1. Persist a launch intent synchronously, keyed by the invocation context,
   parent native identity and tool-use ID. Fsync before success acknowledgement.
2. Reject known persistence failures with an explicit denial and generic error.
3. Bind only the matching post-tool result's child ID. Missing results remain
   unbound; arrival order and timestamps never supply a binding.
4. Keep lifecycle observations separate from launch intent and body receipts.
   A child stop does not seal a resumed or background descendant.
5. Recover missing bindings from archived native evidence with provenance.
6. Test concurrent children, depth three, interrupted hooks, failed persistence,
   resume and late descendants against the pinned harnesses. Test hook-launch
   failure separately from a hook that successfully reports a storage failure.

This contract does not replace Syntropic137's central resolver or assign workflow
membership from a shared native root ID. The eight passing stop-handler tests
prove emitted identity behavior only, not durable registration or settlement.

## Durable journal implementation checkpoint

`agentic_session_store.child_journal.ChildJournal` now provides a SQLite journal
for a caller-owned retained partition. Registration commits with synchronous FULL
before returning. Its unique key includes top-level invocation, attempt, harness,
immediate parent native identity and tool-call ID. Repeated registration returns
the same child invocation ID. Binding requires prior registration and rejects a
conflicting child identity under an immediate transaction.

Nine focused tests exercise separate concurrent connections, restart with missing
results, reverse completion order, attempt/parent isolation, storage failure and
competing bindings. This module is not yet wired into installed hooks or the host
recovery reader. It does not provide launch enforcement, session settlement or a
capture-completeness claim. The next change must wire both hook production and
host ingestion before claiming this journal contributes discovered sessions.

## Codex hook entry point checkpoint

`python -m agentic_session_store.child_hook` now accepts the pinned Codex
`spawn_agent` PreToolUse/PostToolUse payloads. It uses the retained capability
partition, reads at most 1 MiB plus one overflow byte, rejects duplicate JSON
fields, and stores only identity fields. The post-tool response is decoded from
the JSON string emitted by Codex's FunctionCallOutput body. Unknown or conflicting
bindings fail without replacing the saved intent. Enabled capture requires both
per-attempt context IDs. Disabled capture performs no journal writes.

Failures return exit 2 with a generic nonempty stderr message. Successful writes
emit no model context. Seven actual subprocess cases plus nine journal tests pass;
focused Ruff and Pyright pass. No real pinned Codex process has exercised this
entry point yet. Installation, Claude adaptation, host ingestion and strict
launch enforcement remain outstanding. This extends the implementation above;
it does not change the pinned harness's fail-open behavior when hooks cannot run.

## Incremental recovery checkpoint

The journal now appends immutable change records transactionally for registration
and binding. A reader that consumed an unbound intent can discover its later
binding using a newer change cursor. Repeated registration or identical binding
adds no change. Bounded pages (maximum 500) retain an explicit watermark, so
concurrent hook writes cannot alter an in-progress traversal. Historical pages
retain the binding state at that change, not the mutable current row.

The 24 hook/journal cases now include late binding after cursor advancement,
concurrent writes during pagination, invalid cursor bounds and rollback of the
binding when its change record cannot be appended. Focused Ruff and Pyright pass.
Host transport/ingestion still needs wiring to this paging interface.

## Read-only recovery transport checkpoint

`python -m agentic_session_store.child_export JOURNAL --after N --watermark W
--limit L` exposes the bounded change page as a versioned JSON document. SQLite
opens with `mode=ro`; it neither creates a missing journal nor initializes an
empty or corrupt one. Failures return nonzero with generic stderr and no page.
The path is URI-encoded, including spaces, question marks and fragment characters.

All 29 journal/hook/export tests pass. New subprocess tests verify unchanged file
bytes, exact Unicode IDs, late-binding recovery and explicit missing/invalid
journal failure. A read-only handle also rejects mutation. Focused Ruff/Pyright
pass. The host adapter still needs to invoke and validate this transport and
persist the evidence before advancing its checkpoint.

## Workspace reader checkpoint

`agentic_isolation.child_journal.WorkspaceChildJournalReader` invokes the export
through the existing workspace execution protocol. It validates a strict versioned
response, bounded identities, ordered unique change sequences, the pinned
watermark and advancing continuation. Missing or truncated pages cannot be
accepted as completed traversal. The location is host-supplied and shell-quoted
by the existing `exec_argv` transport.

Eight reader tests pass, including a real exporter subprocess round trip with
quoted paths, Unicode identities and late binding. Focused Ruff/Pyright pass.
The remaining integration boundary is Syntropic137's durable evidence ingestion
and checkpoint update; the reader itself does not assign workflow membership.

## Installation research checkpoint

The pinned `rust-v0.150.1` `codex-rs/core/config.schema.json` defines
`hooks.PreToolUse` and `hooks.PostToolUse` as arrays of matcher groups containing
command handlers. Hook event names retain PascalCase. Spawn output arrives as a
serialized FunctionCallOutput body, already handled by the adapter.

Installation must merge with existing hook arrays. Blindly assigning either
array through a CLI override would replace user hooks. Appending TOML array tables
is also unsafe when the existing configuration uses inline arrays. A validated,
atomic merge or a separately composed supported plugin remains necessary before
enabling the capability. Source snapshots used for this check are under
`/private/tmp/1398-codex-hooks/`; the pinned upstream schema is
https://github.com/openai/codex/blob/rust-v0.150.1/codex-rs/core/config.schema.json.

`codex_hook_config.merge_capture_hooks` now composes the two synchronous capture
handlers using tomlkit and verifies the output with stdlib tomllib. Seven tests
cover empty configuration, inline tables/arrays, arrays of tables, preservation
of existing hooks/comments/model settings, idempotence and invalid TOML rejection.
The package now declares tomlkit>=0.13.3,<1; these tests ran with 0.13.3 through
an isolated uv environment. Atomic file installation and entrypoint activation
remain the next steps; the merge function alone does not install hooks.

`python -m agentic_session_store.install_child_hooks CONFIG` now installs the
validated merge using an advisory lock, a same-directory temporary file, file
fsync, atomic replacement and directory fsync. Invalid, oversized, nonregular or
symlink config targets fail without replacing the original. Existing file modes
are preserved; new configs default to 0600. An unchanged config keeps its inode
and modification time. Thirteen merge/installation tests pass, including
concurrent installers and simulated replacement failure. This command is not yet
called by capability startup. Real Codex loading and feature-gate behavior remain
unverified; successful file installation alone is not capture enforcement.

## Local startup activation

Local-provider startup now initializes `children.sqlite` and invokes the atomic
Codex hook installer before `.init-complete`. Remote-provider startup is unchanged.
The pinned feature source (`codex-rs/features/src/lib.rs`, rust-v0.150.1) marks
`hooks` stable and enabled by default. Explicit `features.hooks=false` or its
legacy `codex_hooks` spelling is rejected without changing the configuration.

Twenty-two combined installation/merge/local-capture tests passed, followed by
all eight local-capture tests after adding a disabled-hook readiness regression.
The shell startup test verifies actual database/config creation. No live pinned
Codex model run has validated hook firing yet; Claude capture hooks, remote-provider
activation and fail-closed runtime enforcement remain incomplete.

## Package and exporter validation

The entire session-store suite passes against a freshly built package installed
by uv with its declared dependencies: 145 passed and one exporter integration
initially skipped. That remaining integration then passed with the locally built
`implementation/agentic-session-exporter/target/debug/apss-session-exporter`,
including real local startup, hook installation, capture and exact-byte retrieval.
This validates package inclusion of the new modules and tomlkit dependency.
Log: `/private/tmp/1398-session-store-installed.log`. The first uninstalled-source
run had subprocess import failures and is not counted as passing evidence.

Checkpoint validation: all 47 focused isolation tests passed. Main Syntropic137
repository-wide Pyright passed with zero errors and 16 missing optional-dependency
warnings. The session-store dependency lock now includes tomlkit. Full AP `just qa`
is not green: after bypassing parent-workspace auto-sync with `UV_NO_SYNC=1`, its
lock gate reports stale locks in agentic_events, agentic_isolation, agentic_logging
and agentic_memory. These unrelated locks were not regenerated for this checkpoint.

Hosted CI follow-up: declared agentic-session-store as an isolation development
dependency for the real export round-trip test, regenerated portable locks without
user-level uv config, and corrected SubagentStop formatting. Full isolated
agentic_isolation tests now pass 577 cases with locked all-extras dependencies.
The existing registry round-trip test now restores its original plugin instead
of leaking a fake into later evidence tests. The locked session-store suite also
passes (real exporter case remains an explicit opt-in, validated separately).
Main QA now passes topology fitness but fails its default-branch submodule
reachability gate until this upstream draft is merged; that gate remains intact.

## Pinned runtime trust conformance

The real workspace image `omni-agent-workspace:2.1.250` reports Codex 0.150.1
and Claude Code 2.1.250. An offline Codex app-server probe found that capture
handlers installed without `hooks.state` are enabled but **untrusted**, so the
runtime excludes them from execution. Feature enablement alone was insufficient.

The installer now records the pinned runtime's normalized hashes for only the
exact capture handlers it adds or finds, using their actual configuration path
and group index. Existing unrelated trust entries remain unchanged; explicitly
disabled capture handlers fail installation. No global hook-trust bypass is used.
Hashes are tied to the exact command, matcher, event and timeout. Changing those
fields or the supported Codex version requires rerunning real-binary conformance.

`tests/test_pinned_codex_hooks.py` in the session-store package runs directly with
Python when `CODEX_NATIVE_TEST_BINARY` points to the pinned Codex binary. In an offline,
disposable pinned-image container it verified both capture handlers are trusted,
an unrelated handler stays untrusted, and installation is idempotent. No model
requests, credentials or user configuration were used. This proves runtime hook
activation eligibility only; real child spawning, binding and capture, and
fail-closed launch enforcement remain open acceptance work.

## Real v2 child identity observation

The offline pinned Codex 0.150.1 fixture successfully spawned a native child
through `collaboration.spawn_agent`. Its hook-facing name was
`collaborationspawn_agent`; its response contained `task_name`, not `agent_id`.
The existing `spawn_agent` matcher therefore did not record that launch.
That observation drove the v2 binding fix described below.

The child's first session_meta had distinct `id` (child thread) and `session_id`
(shared root), plus `multi_agent_version: "v2"`, its immediate parent ID and
agent_path. Native evidence and transcript extraction now retain the child `id`
for explicitly marked v2 headers, preserving the shared root separately. A
fixture-derived nested-child regression passes alongside all 30 focused native
evidence and Codex transcript tests. Legacy header interpretation is unchanged.


## Live native child demonstration, 2026-09-23 UTC

Pinned Codex 0.150.1 now records `collaborationspawn_agent` as well as legacy
`spawn_agent`. The v2 hook reads the canonical parent header from the runtime's
`transcript_path`, then resolves the returned task path against child headers
with that exact immediate parent. It never treats the shared root session ID as
a nested parent's native identity. Scans are bounded to 4096 directory entries
and 1 MiB per header. Missing, conflicting, or ambiguous evidence leaves the
registered intent unbound and reports hook failure. No timestamp matching.

The updated matcher has new hashes obtained from the pinned `hooks/list` API.
The offline `test_pinned_codex_child.py` uses the real binary and a loopback
Responses fixture inside a network-disabled container. It verifies registration
before binding and distinct parent/child native IDs. The separate real-binary
trust test also passes. Subprocess regressions cover direct and nested parent
identities plus ambiguous task paths.

A real Syntropic137 workflow, `exec-2349a316ec77`, completed in the isolated
stack with SeshMagic disabled. Its durable child journal bound the child;
its live API served both exact transcript archives and their spawn relationship.
Parent: `01a0cbd8-694c-7cb1-9b10-31b352994c3f`.
Child: `01a0cbd8-8210-7333-918f-8c9346742e28`.
This supersedes the earlier statements that native child capture was unverified.
Universal closed coverage, launch-time fail-closed enforcement, and the broader
cross-harness acceptance matrix remain separate work.


## Claude native child capture (proven at 2.1.250, re-verified at 2.1.281)

Local workspace initialization installs synchronous `PreToolUse` and
`PostToolUse` hooks for `Agent` and legacy `Task`, preserving other settings and
plugin hooks. Explicit `disableAllHooks` prevents the local readiness marker.
Before launch, the hook commits an intent keyed by invocation, attempt, parent
native identity and tool-call ID. The post hook binds the structured `agentId`
response. A hook inside a subagent uses its `agent_id` as immediate parent,
not the shared root `session_id`. Failed or ambiguous binding retains the intent.

`tests/test_pinned_claude_child.py` drives the pinned binary with an offline
Messages fixture. Three nested launches must produce three pre-launch intents
and three exact bindings. Independent native transcript headers must match all
child IDs and retain the root session ID. Run with
`CLAUDE_NATIVE_TEST_BINARY=/path/to/claude`; Docker conformance runs disable
networking and supply no real credentials. This proves native registration and
binding, not descendant settlement or mixed-harness delegation.


## Structured cross-harness delegation

`syn-delegate` uses the retained child journal for Claude-to-Codex and
Codex-to-Claude calls. Each intent retains the parent's harness and the target
harness separately. The runner binds only the new process's own machine-stream
identity, records successful OS launch separately from failure to start, and
retains the actual exit code or terminating signal. Parent environment markers
are cleared before spawning so nested calls cannot inherit an obsolete parent.

Claude's `Bash` hook prepends quoted context exports without changing the tool's
permission decision. Codex uses its native shell `CODEX_THREAD_ID`; no Codex
command-rewrite or permission-granting hook is installed. Journal migration adds
nullable lifecycle fields without changing existing exported records or their
source hashes. Version 2 pages carry cross-harness/lifecycle observations;
readers still accept version 1.

The offline `test_pinned_cross_harness.py` runs the pinned real Claude and Codex
binaries through Claude -> Codex -> Claude. It verifies independent native files,
pre-launch intents, exact parents and successful delegate outcomes. This proves
the controlled shim path; it does not seal run-wide descendant coverage, add a
workflow-success gate, or complete mixed resume/fork acceptance.


## Re-verification at Claude 2.1.281 / Codex 0.156.1, 2026-09-24 UTC

The omni-agent image moved to Claude Code 2.1.281 and Codex 0.156.1. The
sections above that name 0.150.1 or 2.1.250 record what was observed at those
versions and are kept as history.

The Codex trust hashes were recomputed through the 0.156.1 `hooks/list` API
against a freshly installed capture configuration. Both handlers report the
same `currentHash` as before and `trustStatus: trusted`, so
`CAPTURE_HASHES` is unchanged. Upstream's hash function
(`codex_config::version_for_toml`) is byte-identical between the two tags.

All four pinned modules, `test_pinned_codex_hooks.py`,
`test_pinned_codex_child.py`, `test_pinned_claude_child.py` and
`test_pinned_cross_harness.py`, passed (6 tests, none skipped) against the real
binaries in the built image, in a network-disabled container, with no
credentials.


## Fail-closed launch guard and native lifecycle, 2026-09-25 UTC

Part of syntropic137/syntropic137#1398, acceptance rows 2 and 4.
agentic-session-store 0.5.0.

### Why the recorder failed open

Measured against the pinned binaries in `agentic-workspace-omni-agent:2.1.281`,
offline, with a Messages or Responses fixture:

| Hook outcome at PreToolUse | Claude Code 2.1.281 | Codex 0.156.1 |
| --- | --- | --- |
| Exit 0 | Launch proceeds | Launch proceeds |
| Exit 2, nonempty stderr | Launch denied, stderr to model | Launch denied, stderr to model |
| Exit 1 | Launch proceeds (probe) | Launch proceeds (source) |
| Command not found (127) | Launch proceeds (probe) | Launch proceeds (source) |
| Hook timeout | Launch proceeds (probe) | Launch proceeds (source) |
| Shell used | `/bin/sh -c` (probe) | `$SHELL -lc`, else `/bin/sh -lc` (source) |

Codex rows marked "source" come from `codex-rs/hooks/src/engine/command_runner.rs`
and `events/pre_tool_use.rs` at `rust-v0.156.1`: only exit 2 with nonempty stderr
blocks; a spawn error, timeout or any other exit is a non-blocking failure. The
pinned-binary tests below confirm the guarded outcome for both harnesses.

A bare `python3 -m agentic_session_store.child_hook` therefore let a child launch
with no durable intent whenever the interpreter was missing, could not import the
package, crashed, or hung.

### Guard

`agentic_session_store.hook_command.guarded_command` is the installed command.
It is inline POSIX shell (no file to go missing):

- runs the recorder with the payload on descriptor 3, output discarded;
- a watchdog kills it after 20 s (`sleep 20 && kill -9`, so a missing `sleep`
  disables only the watchdog); the recorder also stops itself at 15 s with
  `SIGALRM`; the harness timeout is 30 s, so the guard always decides;
- maps any nonzero recorder status to one fixed stderr line and the configured
  status: 2 (deny) for PreToolUse, 1 (report, never block) for every other event.

Only PreToolUse may deny. On Codex PostToolUse, exit 2 replaces the spawn result
the parent model sees with an error while the child keeps running. On
SubagentStop, exit 2 in both harnesses forces the child to continue.

Installation replaces an older unguarded capture group in place (same index, so
the Codex trust entry is rewritten, not orphaned) instead of running both.
Codex trust hashes for the three guarded handlers were read from the pinned
0.156.1 `hooks/list` API and verified `trusted`.

Because a lock timeout now denies the launch, opening a current journal takes no
write lock: the schema migration runs once and records SQLite `user_version`.
Before 0.5.0, every hook process rewrote the triggers under an exclusive lock,
which serialized concurrent launches (a CI run of the 32-way concurrent
registration test hit the 5 s busy timeout).

When the recorder cannot run, nothing can be written, so a denied launch leaves
no journal record. If the recorder committed the intent and then missed its
deadline, it marks that intent `launch_failed` with reason `capture_hook_failed`
(best effort, 1 s busy timeout).

### Lifecycle

| Event | Journal effect |
| --- | --- |
| PreToolUse | Intent, `status` `pending`, committed with synchronous FULL before exit 0 |
| PostToolUse | `launched` and bound to the returned child, one transaction |
| PostToolUse, Claude `status: "completed"` | Also `completed` in that transaction |
| PostToolUseFailure (Claude) | `launch_failed`, reason `native_tool_failed` or `native_tool_interrupted`; never bound |
| SubagentStop | Stop recorded by child ID; settles that child's `launched` intent to `completed` |

- A stop carries no tool-call ID, so it never creates or chooses a binding. It
  is kept in `child_stops`, so a stop that arrives before the launch
  acknowledgement settles the intent when the binding lands.
- Native `completed` has no exit code. It means the harness reported the child
  stopped. It is not descendant settlement, and a later resumed Codex turn does
  not reopen it.
- Every observation is idempotent: repeated hooks add no change rows.
- A different child ID for a bound intent is stored in `child_conflicts` and
  exported as a change carrying `conflict_native_id`; the binding is kept.
- Distinct states: `pending` (intent, launch never acknowledged, including a
  launch denied by another hook or a Codex spawn that failed, which fires no
  hook; null for native intents written before 0.5.0),
  `launched` (acknowledged and bound; the transcript may still be missing),
  `launch_failed` (harness reported failure; unbound).

Export uses schema version 3 only when a page carries native lifecycle or a
conflict. `WorkspaceChildJournalReader` (agentic-isolation 0.10.0) accepts v3,
requires launched native intents to be bound, forbids an exit code on a native
outcome, and now also accepts the `reason` field that v2 delegate
`launch_failed` records already carried. An older reader rejects v3 and does not
advance its checkpoint.

### Evidence

Unit (`tests/test_native_lifecycle.py`, run on macOS bash and on dash in the
pinned image): missing interpreter, interpreter without the package, hung
interpreter killed by the watchdog, recorder deadline, locked journal and
missing partition all deny; normal Claude and Codex intent, launched, bound,
completed; duplicate hooks idempotent; conflict recorded once and not applied;
failed and interrupted launches distinct; legacy journal upgrade.

Pinned, offline, network-disabled container, no credentials:

- `test_pinned_fail_closed.py`: Claude and Codex, missing and hung interpreter,
  child never runs, parent model receives the denial, journal empty. A mutation
  that installs the unguarded command makes the Claude cases fail (child runs).
  Claude rejected spawn (unknown agent type) records `launch_failed`.
- `test_pinned_claude_child.py`: three nested launches each record intent,
  launched and bound, then completed.
- `test_pinned_codex_child.py`: intent, launched and bound, completed (5/5 runs).
- `test_pinned_codex_hooks.py`: all three guarded handlers trusted.

### Not verified

- Claude synchronous Agent results (`status: "completed"`) and the order of
  SubagentStop against PostToolUse in that mode. Headless `-p` in 2.1.281
  returned `async_launched` for every probe, including without
  `run_in_background`. The journal is order-independent, but the mode is not
  exercised against the binary.
- `is_interrupt: true` on Claude PostToolUseFailure; only the rejected-spawn
  failure was driven through the binary.
- Child failure or cancellation after launch. Neither harness reports it through
  a hook in these versions (Codex has no PostToolUseFailure and fires
  PostToolUse only on success; SubagentStop carries no outcome), so such a
  child stays `launched` or becomes `completed`.
- zsh `.zshenv` preemption against the pinned image: zsh is not installed
  there. It is covered by unit tests where zsh exists.

### Review pass 1 hardening

Invariant: once capture hooks are installed, no PreToolUse allows a child
without a durable intent, and every durable intent reaches a terminal or an
explicitly recoverable state.

- **Contract required.** An installed hook that runs without an active
  session-store contract (provider unset or `none`) denies. The installer
  refuses to install without one, so a disabled capture configuration never
  has capture hooks.
- **Schema validated, not trusted.** The journal records SQLite `user_version`,
  but a writer trusts it only when every required column and every trigger
  definition also match. agentic-session-store 0.4.0 ignores the marker and
  rewrites its triggers on every open, so the real definitions are checked and
  repaired under the write lock. A journal with a newer `user_version` is
  rejected by writers and by the exporter, and a PreToolUse against it denies.
  A vendored 0.4.0 journal (`tests/legacy_0_4_0`) interleaved with this
  version exports every lifecycle change.
- **Explicit pending state.** PreToolUse commits native intents as `pending`.
  The watchdog sends SIGTERM (20 s), then SIGKILL 4 s later. On SIGTERM the
  recorder marks an intent it already committed `launch_failed` with reason
  `hook_watchdog`. Only a SIGKILL between commit and exit leaves it `pending`,
  which is the explicit recoverable state (recover from archived native
  evidence; never by timing). An intent is also left `pending` when another
  hook denies the launch or when Codex rejects the spawn, since neither is
  reported to any hook. Reader validation: `pending` is native-only, unbound
  and has no outcome.
- **Shell startup is a checked precondition.** Measured against pinned Codex
  0.156.1 in `codex exec`, hooks run through the user's passwd shell with `-c`
  (`/bin/bash -c` in the image), whatever `$SHELL` says. Setting `SHELL`
  therefore changes nothing. `$SHELL -lc` is only the fallback for a session
  without a turn environment. Bash reads `$BASH_ENV` and zsh reads `.zshenv`
  before the hook command, so a file there that exits or hangs launches the
  child with nothing recorded. `test_pinned_shell_startup.py` reproduces this.
  No hook can prevent it, so `agentic_session_store.hook_probe` runs the real
  guard through the harness shells with the caller's environment. It requires
  the exact deny status and message for a payload the recorder must reject,
  and a clean pass for a capture probe payload. Two callers run it:
  - session-store init (local provider), which refuses readiness on failure;
  - `syn-delegate` before every start, with the delegate's own environment,
    which records `launch_failed` with reason `capture_hook_unreachable` and
    exits 70 on failure.
- **Login-shell PATH.** The probe found a real gap: Codex runs its shell tool
  with `bash -lc`, and Debian `/etc/profile` drops `/opt/venv/bin`. So a
  `syn-delegate` launched from Codex gave its Claude child a PATH with no
  `python3`, and that child's capture hooks could not run. The images now
  keep `/opt/venv/bin` on PATH for login shells
  (`/etc/profile.d/10-agentic-venv.sh`). `test_pinned_cross_harness.py` now
  fails on an image without this file, because `syn-delegate` refuses there,
  and passes with it.
