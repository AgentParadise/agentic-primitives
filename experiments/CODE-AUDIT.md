# CODE-AUDIT — interactive-tmux deliverable audit (R1)

Scope: provider deliverable only, not experiment narrative.  
Data checked from `providers/workspaces/interactive-tmux/**`, required experiment logs, and git commit records.

## 1) Provider inventory

| Path | LOC |
|---|---:|
| `providers/workspaces/interactive-tmux/Dockerfile` | 114 |
| `providers/workspaces/interactive-tmux/manifest.yaml` | 130 |
| `providers/workspaces/interactive-tmux/README.md` | 274 |
| `providers/workspaces/interactive-tmux/driver/__init__.py` | 9 |
| `providers/workspaces/interactive-tmux/driver/interactive_tmux.py` | 1064 |
| `providers/workspaces/interactive-tmux/scripts/entrypoint.sh` | 41 |
| `providers/workspaces/interactive-tmux/scripts/smoke.sh` | 82 |
| `providers/workspaces/interactive-tmux/scripts/smoke_provider_adapter.py` | 201 |

Total LOC (tracked implementation files): 1915  
Artifacts: 16 files under provider root and 10 run logs in `runs/`.

## 2) Lab commit accounting

Branch commit counts are measured since baseline `d807ab0`.

| Branch | Commits since base | Latest SHA |
|---|---:|---|
| `agentprims-exp02` | 8 | `317137248` |
| `agentprims-exp03` | 7 | `45bf05ecf` |
| `agentprims-exp05` | 4 | `8e4d62171` |
| `agentprims-exp06` | 4 | `05d926b24` |
| `agentprims-lab` | 9 | `0d8297a0a` |

Author counts since base (`git log --no-merges d807ab0..branch`):
- `agentprims-exp02`: NeuralEmpowerment 8
- `agentprims-exp03`: NeuralEmpowerment 7
- `agentprims-exp05`: NeuralEmpowerment 4
- `agentprims-exp06`: NeuralEmpowerment 4
- `agentprims-lab`: NeuralEmpowerment 9

## 3) Quantitative claim checks (holds = verified from evidence)

1. **EXP-05 smoke claim:** 3/3 agents pass per smoke run.
   - Evidence: `experiments/EXP-05-interactive-tmux-provider.md` + `providers/workspaces/interactive-tmux/scripts/smoke.sh` + `providers/workspaces/interactive-tmux/runs/smoke-*.txt`
   - Result: **holds**
   - Checked outputs include marker tokens for Claude, Codex, Gemini in each run.

2. **EXP-05a 4-mount matrix claim:** 2×2 matrix covers all Claude auth combinations and reports required mount outcome.
   - Evidence: `experiments/EXP-05a-claude-auth-matrix.md`
   - Result: **holds**
   - Reported pass only on `~/.claude/` + `~/.claude.json`.

3. **EXP-05-review M1 fix claim:** startup readiness error path is present and fixed (not silently ignored).
   - Evidence: `experiments/EXP-05-review-codex.md` sections for M1 and fix summary + `providers/workspaces/interactive-tmux/driver/interactive_tmux.py`
   - Result: **holds**
   - `STARTUP_READY_TIMEOUT`/raising path present and covered by verification updates.

## 4) Additional integrity checks

- Smoke scripts exist and are executable by path (`smoke.sh`, `smoke_provider_adapter.py`) and are referenced from provider docs.
- Provider API surface exposed through `driver/interactive_tmux.py` and protocol adapter.
- Branch `origin/main` was shown clean for pre-existing `providers/workspaces/claude-cli/` in review notes, indicating this delivery is isolated to new provider path.

## 5) Non-passing findings (none)

No functional blockers found in deliverable files. Remaining risk is operational: if auth mount state drifts, deterministic startup still depends on `~/.claude` and `~/.claude.json` presence.

## 6) Completion

CODEX-side audit complete. Findings and raw-claim checks are recorded in this file and mirrored in `analytics-data.json`.

