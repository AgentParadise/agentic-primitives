# Trusting derived signals

**A signal is only evidence if you have read what produces it.**

Every example below is real, all of them happened on 2026-08-14, and most of
them happened to the two sessions who wrote this page while they were writing
it. They are recorded with names and blame attached because a sanitised version
of this page would be less useful and, given the subject, faintly absurd.

## Start here: the one where nobody had an excuse

`agentic_memory` declared `requires-python = ">=3.10"` and classified 3.10 as
supported. Its `contract.py` imports `enum.StrEnum`, which landed in 3.11. On
3.10 the package fails at import. The same mismatch existed in
`agentic_session_store`.

CI pinned 3.11, so nothing ever ran the version the package claimed to support.
The declaration was not wrong-and-caught; it was wrong and structurally
unfalsifiable.

Now the part that makes it the right opening example. The obvious fix is "add
these packages to the CI matrix." **That does not help.** The matrix pins a
version too, so a package can still advertise a floor that CI never runs.
Adding the declared minimum as a second literal entry works today and rots
immediately, because the next person to bump a floor edits `pyproject.toml` and
not the workflow, and the version is now written in two places, which is the
condition that produced the bug.

The gap survives the obvious fix. Every other example here is a case where a
better check would have worked. This is a case where the check everyone reaches
for is itself the blind spot. Tracked as
[#300](https://github.com/AgentParadise/agentic-primitives/issues/300).

## The spine: read, acquire, produce, verify

Four ways to be wrong about evidence, ordered by how invisible each one is.

### 1. Read: the contract was narrower than the consumer assumed

A transcript exporter marked its state file for `rejected` items even though the
store never stored them. A prune gate read the exporter's exit code as a claim
about per-item success. It never was: `run()` returns `Ok(summary)` regardless
of the counters inside it.

The precise shape matters, because the exporter is *mostly* careful. Three
outcomes fail to store an item, and only one of them marks state:

| Outcome | Marked? | Consequence |
|---|---|---|
| `rejected` | **yes** | Never stored, never retried. The bug. |
| `failed` | no | Retries next sweep, genuinely stored if it later succeeds. |
| `skipped_oversize` | no | Recounted every sweep, never captured. |

The exporter's own doc comment says state is marked for "accepted, duplicate, or
per-item rejected: all three mean the store processed it." Processed is not
stored. That single word is the whole defect, and it is why the fix's sticky
sentinel is scoped to `rejected` alone rather than to failure generally.

So the first sweep correctly refused to prune, and the second sweep saw the same
transcript as `skipped_unchanged`, read all counters as zero, and deleted it.
**The gate refused where the loss was visible and deleted where it was
invisible**: exactly inverted, and only in the case nobody would notice.

The exit code was not lying. It was answering "did the process complete" and
being read as "was every item stored."

*This one leaves an artifact. You can go back and re-read the exit code, and the
answer is sitting there.*

### 2. Read: common-mode failure between the test and the code

A LangFuse MCP server framed its stdio messages with LSP-style `Content-Length`
headers. MCP requires newline-delimited JSON, one message per line. A real
client's `initialize` was consumed as a header, `content-length` resolved to
zero, and the server exited without writing a byte. Every packaged tool was
unusable.

It shipped with a self-test, and the self-test passed. It built its requests
using the server's own `_frame` helper, so both sides were wrong in the same
direction and round-tripped happily.

**A test that exercises the system through the system's own helper proves the
helper is self-consistent and nothing else.**

The same shape reappeared hours later, in a test written specifically to prove
a bug was fixed. The probe read `${SESSION_STORE_TAGS:-<unset>}`, and `:-`
substitutes for empty as well as unset, so the pre-fix behaviour of exporting an
empty value printed `<unset>` too. **One colon** between a regression test and a
decorative one. It was caught by running the pre-fix code against the new test
rather than assuming a new test is load-bearing because it is new.

### 3. Acquire: the signal answered a different question

A pull request carrying two blockers passed **all 22 CI checks**. One blocker
made the MCP server non-functional. The other exposed `langfuse_base_url` as a
caller-controlled parameter on seven agent-callable tools while the server
attached `LANGFUSE_SECRET_KEY` as Basic auth to whatever origin it named, so
injected tool arguments could aim the credential at any host.

Nothing was wrong with the pipeline. It tested formatting, linting, unit
behaviour, and plugin manifests, and all of that passed. Nothing in it tested
an MCP server against the protocol or looked for a credential reaching a
caller-chosen destination.

**A green pipeline is not evidence of correctness. It is evidence that the
checks you wrote passed.** The gap is the shape of what you did not think to
check, which is precisely the shape you cannot see. Tracked as
[#299](https://github.com/AgentParadise/agentic-primitives/issues/299).

The cheap corollary, and the most portable sentence here:

> **A flaky test that passes on rerun is not a green test. It is an unread
> signal.**

*Acquisition failures leave nothing behind, but the absence is discoverable if
you think to look.*

### 4. Produce: a signal we minted ourselves, that lied

A finalizer printed a notice announcing that a pre-base64 partition had been
recovered, added deliberately so a real condition would be visible to an
operator.

It branched on "the `_B64` record is absent" rather than "a legacy record is
present." A `.capture-env` that is truncated, empty, or foreign takes the same
branch, so it prints a recovery that did not happen and tells an operator they
have legacy partitions they may not have. An operator acting on it does
migration work for a state that does not exist.

**The instinct to add observability is not the same as adding trustworthy
observability. A signal you wrote yesterday deserves the same suspicion as one
you inherited**, arguably more, because its author remembers the intent, and
intent is not what the code does.

The lying notice and the `:-` probe above are the same act, trusting something
because you just wrote it, but they lie at different distances. **The notice
lied about the world; the test lied about the code.** A reader who guards only
against the first will still write the second, because a test feels like
verification rather than like output.

There is a third distance, and it is the one with no code in it at all. The
handoff message describing this mechanism named a constant
`__FINALIZE_BUDGET_SIGNALED_S`. The source says `__FINALIZE_BUDGET_SIGNAL_S`.
Its author had read that file hours earlier. **A summary you write for someone
else is a produced signal too**, and it is the one nobody thinks to verify,
because it is prose rather than output. It was caught only because the reader
checked the source instead of the message.

The cleanest instance of this mechanism has no bug in it at all.

When a file moves, every document pointing at the old path breaks. The obvious
maintenance is to update them all. But a changelog entry exists to say what was
true when that version shipped, and a closed issue is an account of where a fix
happened. Rewriting either so a link keeps working makes it assert a path that
did not exist at the moment it describes.

**Falsifying a record to keep a link working is the same error as a signal
reporting a state that does not exist.** Both trade accuracy for the appearance
of consistency, and both leave a reader confidently wrong. The difference is
that nobody experiences the first one as a mistake, because it arrives dressed
as diligence.

The correct move is to leave the historical records alone and accept that a grep
for the old path will return hits, then say somewhere current that those hits
are intentional. A reader briefly confused by a stale-looking reference is a much
smaller cost than a record that lies.

*This is the worst of the four. A misread leaves an artifact you can re-read.
An absence is discoverable. A lying signal leaves an artifact that actively
argues against looking further.*

## The drift detector that drifted

The best instance came last, and it is the one to remember if you remember only
one.

An ADR states that a naming rule has two implementations, `__capability_env_prefix`
in shell and `capability_env_name()` in Python, and that they must agree. A
conformance test was written specifically because **a claim in an ADR that two
things must agree is worthless without something checking it.** Its teeth were
verified by mutating the shell function and watching the test fail.

It got its value from reading the *real* entrypoint off disk rather than a copy,
because a test that re-derives the shell logic in Python proves only that Python
agrees with itself.

Then the entrypoint moved. The test kept pointing at the old path, failed with
`FileNotFoundError`, and nobody noticed. **The thing written to catch drift
drifted, and its own drift was undetected.**

Note what this is not. It is not carelessness. The property that made the test
worth having, reaching into the source tree for the genuine artifact, is exactly
the property that coupled it to the source tree and let a relocation break it.
**The strength and the fragility are the same design decision.**

Three gates ran and none of them was wrong about what it checked. The move task
ran the integration suite; this is a unit test. The move review verified `R100`
pure renames and diffs; it did not execute tests. The documentation repoint swept
references; this is a path in Python, not in prose. Each scope was correctly
defined. The test fell between them, and nothing owned the gap.

The asymmetry is the lesson worth carrying: `/opt/agentic/**` did not move, so
nothing *inside* a container broke. The only thing that broke was a check
reaching in from outside. **A verifier that couples itself to a layout inherits
that layout's churn**, and it will not tell you when the coupling snaps, because
the failure is its own absence.

Ask of any check you rely on: if this stopped running tomorrow, how would I find
out? For most checks the honest answer is that you would not, and the check that
watches for drift is the one whose silence is least distinguishable from success.

## The one where we did it to ourselves, while writing this

Two sessions identified that `agentic_memory` and `agentic_session_store` had no
CI coverage. Both agreed adding them was right. They negotiated the sequencing
carefully: whether to land the fixes before the matrix entries or together, and
why one commit that cannot leave `main` red at any intermediate point is better.

**Neither of them ran the checks.**

Both packages had pre-existing lint and format failures. Adding the matrix
entries as discussed would have turned `main` red immediately. The two sessions
had reasoned at length about *the decision to acquire a signal* without
acquiring it, which takes four seconds.

This is worse than every example above and completely invisible, because there
is no output to misread. It was caught only because one session thought to ask
the other to run the checks on the package it owned before landing.

## Why the mechanisms matter more than the stories

The milestone that produced half this page found **four data-loss paths. Three
of them were introduced by the fixes for the previous ones.**

Each fix was locally correct. Each one opened the next hole somewhere its author
was not looking. A `rm -rf` of un-uploaded transcripts became a migration; the
migration's prune escaped its spool on a path-shape check; the ownership marker
that fixed that still fired on an incomplete sweep because exit 0 did not mean
what it looked like.

That progression is the argument for this page existing. A reader who takes away
four war stories patches the instance in front of them and ships the next one.
A reader who takes away the mechanisms can spot the fifth instance, including
one in their own fix.

It also answers the obvious objection, which is "just review more carefully."
The author of the prune gate **did** review it, and declared the counter
selection justified. The hole was in the code behind the signal being reviewed.
Care applied to the signal does not reach the producer.

## What to actually do

- **Before trusting a signal, read what writes it.** Not the docs for it, the
  code. Especially an exit code, a summary line, or a counter.
- **Ask what question the signal answers**, and whether it is the question you
  are asking. "Did it complete" is not "did it all succeed."
- **Make a test fail against the unfixed code** before believing it proves
  anything. If it cannot fail, it is decoration.
- **Never let a test share a helper with the thing it verifies.** Write the
  probe independently, even if that means duplicating logic.
- **Treat a green pipeline as coverage of what you thought of**, and ask what
  failure class it does not touch.
- **Rerun is not repair.** A flake is an unread signal; read it.
- **Audit the signals you add** as hard as the ones you inherit. Check the
  branch condition of any message that claims something happened.
- **Derive, do not duplicate.** A value declared in two places is a divergence
  waiting to happen, and CI comparing itself to itself proves nothing.
- **Do not update a record to keep a link working.** Changelogs and closed
  issues describe a past state. Fix the live pointers, leave the history, and
  note somewhere current that the stale-looking references are deliberate.
- **Encode "this must not change" as a check, not as care.** A rename script
  that asserts which paths it must leave alone catches the sweep that looks
  right in the source tree and is wrong everywhere else.
- **Ask of every check: if this stopped running, how would I find out?** A check
  that has silently stopped is indistinguishable from a check that keeps
  passing, and the ones that reach outside their own tree are the likeliest to
  stop.
- **A sweep that matches paths cannot see a renamed function.** Twice in one
  afternoon a rename outran a path-based search. Sweep identifiers back against
  the source too, or a doc will name a function that no longer exists and fail
  exactly like a broken link, without a link checker to notice.
- **When you find a defect, ask whether it ever ran**, not only how to fix it.
  Fixing forward is not assessing exposure.

## Provenance

Two Claude Code sessions working the same repository on 2026-08-14, who
discovered mid-afternoon that they were on the same branch and had not known.

Held to the standard the page argues for, both halves stated plainly:

- The prune/exit-code defect was its author's to catch and they did not. An
  external reviewer found it by reading the exporter's source after that author
  had shipped the gate, reviewed it, and declared the counter selection
  justified.
- The MCP session called a pipeline merge-ready twice on the strength of green
  checks: once before the cross-model review that found both blockers, and once
  by reporting a coverage failure as pre-existing when coverage passed on
  `main`.
- The exposure question on the credential path, had it ever run against a real
  key, was asked by the session that had *not* found it, holding a two-sentence
  summary. The session that found it, wrote the fix, the PR comment and the
  issue, never asked. Proximity to a finding is what suppressed the question; it
  had stopped being a live thing and started being material.

## Related

- [#299](https://github.com/AgentParadise/agentic-primitives/issues/299): CI
  cannot catch MCP protocol breakage or credential exfiltration
- [#300](https://github.com/AgentParadise/agentic-primitives/issues/300):
  `requires-python` is an untested claim
Two documents referenced above land with the workspace capability work on
`feat/workspace-capability-modules` and are not yet on `main`, so they are named
rather than linked: `docs/adrs/040-workspace-capability-modules.md` and
`docs/workspace-capabilities.md`. The latter's finalizer timing budget section
is where the `entrypoint.sh` and finalizer examples come from.
