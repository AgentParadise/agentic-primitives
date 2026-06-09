# Changelog - delegation plugin

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
