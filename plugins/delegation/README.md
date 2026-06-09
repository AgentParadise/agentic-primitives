# delegation plugin

Handing work off to other agents. A home for skills that delegate or transfer
work — to an autonomous Claude instance, to a fresh session, and (over time) to
other coding agents.

## What this plugin provides

- **`delegating-to-claude-p` skill** (under `skills/delegating-to-claude-p/`):
  The empirically-validated flag set and prompt template for autonomous
  `claude -p` delegation, plus failure modes, recipe templates, and a cost
  reference grounded in real arc data (5 paired trials + 22 sub-experiments
  total, from the agentic-harness-lab v0.8.0 dogfood arc). The skill body is
  generic — it documents how `claude -p` actually behaves, not project-specific
  conventions.

- **`delegating-to-codex` skill** (under `skills/delegating-to-codex/`):
  The validated non-interactive `codex exec` invocation for handing a task to
  OpenAI Codex CLI — the sandbox/approval ladder, the `--json` event schema for
  triage, a when-to-delegate framework, failure modes, and an empirical trial.
  Flags are described by behavior to stay version-generic. Headline caveat:
  Codex has no built-in budget cap, so runs must be bounded externally.

- **`writing-handoffs` skill** (under `skills/writing-handoffs/`):
  Compacts the current conversation into a structured handoff document so a
  fresh session or agent can continue a branch or task with full context. Writes
  to `docs/handoffs/YYYYMMDD-handoff_<name>.md` (configurable; `<name>` defaults
  to the branch slug) from a template that captures purpose, current state,
  files affected, rationale, do's-and-don'ts learned, and suggested skills.

## Why a dedicated plugin

Delegation is a first-class agentic-primitive concern that cuts across SDLC,
research, and experiment workflows. Whether you're dispatching an autonomous
`claude -p` run or handing a paused branch to the next session, the patterns —
how to phrase the contract, what context to transfer, what the receiver needs to
succeed — are reusable. Centralizing them here means a consumer installs one
plugin and gets the canonical recipes without re-deriving them. Future
delegation targets (e.g. other coding agents) belong here too.

## Source evidence

`delegating-to-claude-p` retrospective:
`docs/retrospectives/023-harness-dogfood-claude-p-steering.md` in
`agentic-harness-lab` (S1 → S22, 2026-05-18 → 2026-05-19).

## See also

- `plugins/sdlc/skills/security-hardening/` — the CI side of the consumer
  posture (hard gates that `claude -p` retries against, not against).
- `plugins/experiments/skills/running-experiments/` — the experiment
  discipline that produced the `delegating-to-claude-p` evidence base.
