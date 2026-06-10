# ANALYTICS — Flywheel Lab (ANALYTICS R1)

**Branch:** `agentprims-lab`  
**Session:** `agentprimsdeck`  
**Source evidence:** `experiments/*.md` (EXP-01..06, EXP-05a, EXP-05-review, FRICTION-*, LAB-PLAN, INDEX), `providers/workspaces/interactive-tmux/**`, git log on `agentprims-exp02`, `agentprims-exp03`, `agentprims-exp05`, `agentprims-exp06`, `agentprims-lab`  
**Companion numeric dump:** `analytics-data.json`

## 1) Lab envelope

| Field | Value |
|---|---|
| UTC wall clock | 2026-06-10T00:54Z to 2026-06-10T05:50Z |
| Wall-clock duration | 296 minutes |
| Worker sessions | 2 |
| Worker names | `agentprims` (3-lane), `agentprims6` (fresh-agent) |
| Branches pushed | 6 |
| Experiments covered | 9 (6 named + 2 sub + 1 cross-review) |
| Overall verdict | `go` / `go` / `go` |

Provider verdict chain:
implemented → fresh-agent doc validation PASS 6/6 → codex review approved-with-conditions (0 blockers, 4 majors) → fixes applied → independent verification APPROVED.

## 2) Per-experiment metrics

Durations are computed from hypothesis commit to results commit when both commits are present.

| ID | Verdict | Branch of record | Hypothesis SHA | Results SHA | Duration (min) | Report bytes | Report lines | Run count claimed |
|---|---|---|---|---|---:|---:|---:|---:|
| EXP-01 | go | `ntm/agentprims/cc_1` | `d62ff55` | `22ddf30` | 21.2 | 15234 | 254 | 15 |
| EXP-02 | go | `agentprims-exp02` | `not_isolated_in_log` | `4fa03c8` | null | 4836 | 121 | 1 |
| EXP-03 | go | `agentprims-exp03` | `c007975` | `11a5cc3` | 14.5 | 3994 | 49 | 1 |
| EXP-04 | go | `agentprims-exp03` | `6a978b4` | `9fdc74e` | 10.6 | 7675 | 86 | 1 |
| EXP-04b | go | `agentprims-exp03` | `73bb808` | `45bf05e` | 5.4 | null | null | 3 |
| EXP-05a | go | `agentprims-exp02` | `100a3b0` | `44ca031` | 48.0 | 3910 | 62 | 8 |
| EXP-05 | go | `agentprims-exp05` | `cb9540f` | `b534ec2` | 33.4 | 29082 | 539 | 6 |
| EXP-05 review | go | `agentprims-exp02` | `513d7fa` | `edd5a8f` | 50.0 | 6929 | 75 | 1 |
| EXP-06 | go (6/6) | `agentprims-exp06` | `3df25a7` | `05d926b` | 15.3 | 11358 | 222 | 6 |

## 3) Experiment and artifact size totals

- Total selected report bytes: 83,018
- Total selected report lines: 1,408
- Provider run artifacts under `providers/workspaces/interactive-tmux/runs`: 10
- Provider directory file count: 16

## 4) Per-CLI recipe matrix

| Dimension | Claude | Codex | Gemini |
|---|---|---|---|
| Submit keys | `send-keys -l TEXT` then `send-keys Enter` (two-step) | `TEXT` + `C-j` + `C-m` first prompt | `TEXT` + `Enter` |
| Readiness signals | `? for shortcuts` footer absent; `esc to interrupt` absent; prompt line `❯` empty (3 signals) | `• Working` absent; pane output byte-stable across repeated polls | `Type your message or @path/to/file` prompt marker |
| Init gates | pre-seed `~/.claude.json`; tmux size `-x 200 -y 50` | start with `--no-alt-screen`; send `1` then Enter; send Escape once | patch `security.folderTrust.enabled: false`; run on node:22+ |

## 5) Claimed auth outcomes in 2×2 matrix (EXP-05a)

| Mount combo | Result |
|---|---|
| none | login required |
| `~/.claude/` only | auth starts but no Max plan (`config` missing) |
| `~/.claude.json` only | auth works for CLI only, no Max plan |
| `~/.claude/` + `~/.claude.json` | Max plan + no wizard (required for unattended) |

## 6) Friction items by category and agent

| Agent | config | workaround-found | tooling-bug | docs-gap | Total |
|---|---:|---:|---:|---:|---:|
| Claude | 3 | 4 | 1 | 1 | 9 |
| Codex | 1 | 1 | 2 | 1 | 5 |
| Gemini | 3 | 0 | 1 | 2 | 6 |
| **Total** | **7** | **5** | **4** | **4** | **20** |

## 7) Review findings and fix status

| Finding | Severity | Status |
|---|---|---|
| M1 `start_workspace` startup gate not propagated | Major | fixed |
| M2 `WorkspaceProvider` adapter gap | Major | fixed |
| M3 `await_completion` result shape too weak | Major | fixed |
| M4 readiness signal gap (Claude) | Major | fixed |
| m1 `.claude` metadata fallback undocumented | Minor | fixed |
| m2 streaming abstraction omitted | Minor | fixed |
| PASS baseline behavior (smoke, auth matrix, conventions, independence) | pass | passed |

## 8) Fresh-agent validation outcome

- Smoke path: `PASS 3/3` (Claude, Codex, Gemini)
- Python path: `PASS 3/3` (Claude, Codex, Gemini)
- Total: `6/6`
- doc gaps found: 4
- doc gaps fixed: 4
- token probes observed: 6 unique tokens across smoke + driver paths

## 9) Budget burn (points)

| Provider plan | Start % | End % | Burned |
|---|---:|---:|---:|
| claude weekly | 93 | 78 | 15 |
| codex weekly | 63 | 57 | 6 |
| codex-spark weekly | 61 | 36 | 25 |
| gemini pro | 100 | 7 | 93 |
| gemini flash | 100 | 96 | 4 |

## 10) Incidents

- ntm first-send sat unsubmitted 3 times; recovered by clear+resend
- unrelated APS fork-bombed VPS to 28,683 processes; SSH lockout; recovered by reaping as root
- `agentprims6` full tmux session wipe caused one in-flight review context loss only; no committed work lost
- Gemini branch committed to local main first, then moved to feature branch and reset main
- 6 branches pushed to origin

## 11) Completion

ANALYTICS R1 completed and committed as deliverables for R2 handoff: `ANALYTICS.md`, `analytics-data.json`, `CODE-AUDIT.md`, `INSIGHTS.md`.
Notify completion via repository note + commit.
