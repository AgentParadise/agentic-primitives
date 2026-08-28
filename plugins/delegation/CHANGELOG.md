# Changelog - delegation plugin

## 1.2.3 - 2026-08-27

Removes `--no-session-persistence` from the canonical `claude -p` invocation in
`delegating-to-claude-p`, and explains when the flag is right and when it
destroys the only record that a delegated run happened.

The flag suppresses the child's PERSISTED session on disk. It does not silence
the `stream-json` on stdout, so a caller that keeps that stream still has
telemetry; what is lost is the resumable session, and with it anything that
finds delegated runs by sweeping session directories. Its documented rationale -
"clean one-shot trials do not pollute interactive history" - was written for a
developer's laptop, where there is an interactive history to pollute. Inside a
disposable orchestration workspace there is none, and the flag is the single
reason a delegated child can be invisible to everything downstream.

The consequence was measured on Syntropic137, in both directions:

- A **codex leader delegating to Claude** recorded one session and priced only
  the leader. The Claude child wrote no transcript, so its tokens exist
  nowhere, because the canonical recipe here carried the flag while the
  codex-side recipe did not.
- A **claude leader delegating to Codex**, run against an image carrying the
  old recipe, produced the mirror image: the Codex child DID persist, its
  transcript reached the session store already tagged with `execution_id`,
  `workflow_id` and `phase_id`, and it was the flag alone that made the
  reverse case invisible.

Where the session-store capability is enabled and initialised, it links the
harness session roots into an export partition, so a child that persists a
session is collected automatically and one invoked with
`--no-session-persistence` leaves nothing there to collect. That is a property
of the capability rather than of every orchestrated workspace, and the skill now
says so rather than leaving it to be rediscovered.

`--ephemeral` is given the same treatment in `delegating-to-codex`. Persistence
is a property of delegation, not of one CLI, and correcting only the Claude side
would have left the identical failure reachable from the other direction.

## 1.2.2 - 2026-08-18

Makes `< /dev/null` part of the canonical `codex exec` invocation in
`delegating-to-codex`, rather than something the caller is expected to know.

`codex exec` reads stdin **in addition to** the prompt argument. Launched from
any context whose stdin never reaches EOF - a background shell, a CI step, an
agent harness - it prints `Reading additional input from stdin...` and hangs
forever: no events, no error, no tokens consumed, just a wedged process until
something kills it. Because the skill's documented invocation omitted the
redirect, **following this skill verbatim reproduced the hang.**

It recurred on 2026-08-17 during Syntropic137 #829: two review dispatches
wedged for roughly 20 minutes each, and both were misread as the model being
slow because nobody inspected the stream file. The tell is now documented
alongside the fix - a wedged run's `--json` stream stalls at ~39 bytes, the
exact length of that banner, while a healthy run passes 100KB within a minute.

The redirect is applied to every invocation the skill shows (canonical,
`review` subcommand, `gtimeout` example), with a new failure-mode row and a
per-flag rationale entry.

One deliberate exception is called out: the skill-injection recipe pipes a
`SKILL.md` in on stdin, and that pipe closes on its own, which is precisely
what Codex is waiting for. Redirecting from `/dev/null` there would defeat the
mechanism.

## 1.2.1 - 2026-08-17

Fixes `delegating-to-codex` against `codex-cli 0.147.0`. The documented
invocation no longer worked: **`--full-auto` was removed**, so the recipe aborted
with `error: unexpected argument '--full-auto'`. Replaced throughout with
`-s workspace-write`, with a callout explaining the drift so anyone on an older
CLI understands the rename. `--ask-for-approval` is likewise no longer an `exec`
flag (`--approve-for-me` is the nearest equivalent).

Adds a section for the new **`codex exec review`** subcommand (`--base`,
`--uncommitted`, `--commit`), including the non-obvious constraint that those
scoping flags are **mutually exclusive with a custom prompt** — you get Codex's
stock rubric or your own instructions, never both — plus a table for choosing
between it and a steered `codex exec`, and the "do NOT modify tracked files"
prompt guard for read-only reviews that still need to run tests.

Two new failure-mode rows for both errors. Trial T1's invocation is left as it
was actually executed on 0.137.0 and annotated, rather than retconned. Verified
against `codex-cli 0.147.0`; every other documented flag (`--json`, `-o`, `-C`,
`--ephemeral`, `--add-dir`, `--output-schema`, `--skip-git-repo-check`) is
unchanged.

## 1.2.0 - 2026-06-08

- Adds `delegating-to-codex` skill: the validated non-interactive `codex exec`
  invocation, the sandbox/approval ladder, the `--json` event schema for triage,
  a when-to-delegate framework, failure modes, and two empirical trials. Also
  documents how to have Codex use a Claude skill (e.g. pr-review) — inject the
  skill via stdin or `AGENTS.md`, since Codex has no skill auto-dispatch — with
  a paired with/without trial (T2) showing the injected skill reproduces the
  skill's exact output contract. Flags are described by behavior to stay
  version-generic; verified against `codex-cli 0.137.0`. Headline caveat: Codex
  has no built-in budget cap — bound runs externally.

## 1.1.0 - 2026-06-08

Renamed plugin from `claude-p` to `delegation` — a broader home for skills that
hand work off to other agents (autonomous `claude -p` today; other coding agents
later). The `delegating-to-claude-p` skill is unchanged apart from its
`placement:` path.

- Adds `writing-handoffs` skill: compacts the current conversation into a
  structured handoff document (`docs/handoffs/YYYYMMDD-handoff_<name>.md`,
  configurable) so a fresh session or agent can continue a branch or task with
  full context. Ships a `template.md` skeleton.

## 1.0.0 - 2026-05-19

Initial release.

- Adds `delegating-to-claude-p` skill: the empirically-validated `claude -p`
  flag set, prompt template, failure modes, recipe templates, and cost
  reference. Source evidence: agentic-harness-lab retrospective 023
  (S1 → S22, 22 sub-experiments).
