# experiments plugin

A plugin for running hypothesis-first experiments inside any repo.

## What this plugin provides

- **`running-experiments` skill** (under `skills/running-experiments/`):
  The canonical workflow for creating, scaffolding, executing, scoring,
  and auditing an experiment. Covers the four-file layout (README,
  eval-pack, results, verdict), the verdict vocabulary (go, no-go,
  inconclusive), and the two-commit rule.

The skill body is generic. Repo-specific conventions (folder root,
status-matrix paths, retrospective layout) belong in each consumer
repo's CLAUDE.md, not in this skill.

## Why a dedicated plugin instead of a meta skill

Experiments are a first-class domain concern with their own
vocabulary, discipline, and tooling surface. The plugin shape gives
future tooling (eval-pack generator, status linter, results
aggregator) a home without bloating the meta plugin.

## See also

- `plugins/meta/skills/authoring-skills/` -- the chassis for writing
  the skill in this plugin (and any other skill).
