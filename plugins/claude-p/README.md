# claude-p plugin

Recipes and patterns for delegating implementation work to non-interactive
`claude -p` (the autonomous one-shot invocation of Claude Code).

## What this plugin provides

- **`delegating-to-claude-p` skill** (under `skills/delegating-to-claude-p/`):
  The empirically-validated flag set and prompt template for autonomous
  `claude -p` delegation, plus failure modes, recipe templates, and a cost
  reference grounded in real arc data (5 paired trials + 22 sub-experiments
  total, from the agentic-harness-lab v0.8.0 dogfood arc).

The skill body is generic — it documents how `claude -p` actually behaves,
not project-specific conventions. Project-specific budget caps, hooks, and
skills live in each consumer repo's CLAUDE.md.

## Why a dedicated plugin

`claude -p` delegation is a first-class agentic-primitive concern: the flag
set, prompt phrasing, and steering surface analysis cut across SDLC,
research, and experiment workflows. Centralizing the recipe here means a
consumer can install one plugin and get the canonical invocation pattern
plus the failure-mode catalog without re-deriving it.

## Source evidence

Retrospective: `docs/retrospectives/023-harness-dogfood-claude-p-steering.md`
in `agentic-harness-lab` (S1 → S21, 2026-05-18 → 2026-05-19).

## See also

- `plugins/sdlc/skills/security-hardening/` — the CI side of the consumer
  posture (hard gates that `claude -p` retries against, not against).
- `plugins/experiments/skills/running-experiments/` — the experiment
  discipline that produced this skill's evidence base.
