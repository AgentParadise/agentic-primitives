# Changelog - delegation plugin

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
