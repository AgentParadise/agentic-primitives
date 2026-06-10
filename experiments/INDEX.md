# Experiments INDEX

Single source of truth for the Flywheel Lab consolidated on the
`agentprims-lab` branch. One row per experiment.

**Branch of record** is the branch the report's evidence was committed
on under the running-experiments two-commit protocol. The files reachable
in `experiments/` on `agentprims-lab` are byte-equal copies imported from
those branches via `git show <branch>:<path>`; evidence under that
branch's `runs/` and ancillary artifacts (build scripts, Dockerfile
overlays specific to per-agent probes) remain on their source branches.

| ID       | Title                                                                | Verdict        | Branch of record                                  | Report on `agentprims-lab`                                           |
|----------|----------------------------------------------------------------------|----------------|---------------------------------------------------|----------------------------------------------------------------------|
| EXP-01   | claude interactive in tmux in docker                                 | `go`           | `ntm/agentprims/cc_1` @ 22ddf30                   | `experiments/EXP-01-claude-tmux-workspace.md`                        |
| EXP-02   | codex interactive in tmux in docker                                  | `go`           | `agentprims-exp02` @ 100a3b0                      | `experiments/EXP-02-codex-tmux-workspace.md`                         |
| EXP-03   | gemini interactive in tmux in docker                                 | `go`           | `agentprims-exp03` @ 45bf05e                      | `experiments/EXP-03-gemini-tmux-workspace.md`                        |
| EXP-04   | combined swarm-in-a-container (claude + codex + gemini)              | `go`           | `agentprims-exp03` @ 45bf05e                      | `experiments/EXP-04-combined-swarm-container.md`                     |
| EXP-04b  | EXP-04 hardening + run count (sub-experiment, same report)           | `go`           | `agentprims-exp03` @ 45bf05e                      | `experiments/EXP-04-combined-swarm-container.md` (section `## EXP-04b`) |
| EXP-05   | `interactive-tmux` workspace provider (productionised EXP-01..04)    | `go`           | `agentprims-exp05` @ b534ec2 (docs patch on `agentprims-exp05` @ 6373b8e) | `experiments/EXP-05-interactive-tmux-provider.md`                    |
| EXP-05a  | claude auth-file matrix (`.credentials.json` vs `.claude.json` — 2×2 mount probe) | `go` (both files required) | `agentprims-exp02` @ 44ca031                      | `experiments/EXP-05a-claude-auth-matrix.md`                          |
| EXP-06   | fresh-agent validation of `interactive-tmux` provider docs           | `go` (6/6 agents × paths; 4 small README gaps, all patched on `agentprims-exp05` @ 6373b8e) | `agentprims-exp06` @ 05d926b | `experiments/EXP-06-fresh-agent-validation.md`                       |

## Companion files

| Report               | Companion (also imported)            | Branch of record                |
|----------------------|---------------------------------------|----------------------------------|
| EXP-01               | `FRICTION-claude.md`, `LAB-PLAN.md`   | `ntm/agentprims/cc_1` @ 22ddf30  |
| EXP-02               | `FRICTION-codex.md`                   | `agentprims-exp02` @ 100a3b0     |
| EXP-03 / EXP-04      | `FRICTION-gemini.md`                  | `agentprims-exp03` @ 45bf05e     |
| EXP-03               | `Dockerfile.exp03`                    | `agentprims-exp03` @ 45bf05e     |
| EXP-04               | `Dockerfile.exp04`                    | `agentprims-exp03` @ 45bf05e     |

## What is NOT in this tree (by design)

- Per-probe `runs/` directories (capture-pane snapshots, run logs).
  These remain on their source branches because they are bulky and
  every claim in the reports cites a path relative to that branch's
  tree. Reviewers wanting raw evidence should `git checkout` the
  branch of record.
- Per-probe build scripts (`scripts/exp01-run.sh`, etc.). Same reason.
- Provider deliverables that have their own home outside `experiments/`
  (e.g., `providers/workspaces/interactive-tmux/` — that lives at the
  repo path, not under `experiments/`, and is on `agentprims-exp05`).
- ~~EXP-05a and EXP-06 reports: explicitly held back per the orchestrator
  dispatch — both are still in flight.~~ Both promoted 2026-06-10 (this
  commit) — see EXP-05a / EXP-06 rows in the main table.

## How this was assembled

This branch (`agentprims-lab`) was created from `agentprims-exp05`
(b534ec2). The ten report files imported from sibling branches were
copied with `git show <branch>:experiments/<file> > experiments/<file>`
and verified byte-equal via `sha256sum` against their source-branch
versions before the consolidation commit. `main` was not touched; no
branches were merged wholesale.

## Branch-of-record SHAs at consolidation time

```
ntm/agentprims/cc_1   22ddf30
agentprims-exp02      44ca031  (EXP-05a evidence)
agentprims-exp03      45bf05e
agentprims-exp05      6373b8e  (EXP-05 + EXP-06 docs patch)
agentprims-exp06      05d926b  (EXP-06 evidence)
origin/main           d807ab0
```
