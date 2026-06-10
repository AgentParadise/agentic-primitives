# EXP-05 Cross-review: codex lead provider implementation

Date: 2026-06-10  (review performed on `agentprims-exp02` branch)
Target under review: `agentprims-exp05` implementation of
`providers/workspaces/interactive-tmux` and `provider` driver.

I reviewed implementation behavior against:
- `agentprims-lab` reports `EXP-01/02/03/04`
- `agentprims-exp02` `experiments/EXP-05a-claude-auth-matrix.md`
- build conventions (`scripts/build-provider.py`, `claude-cli` provider)
- API expectations in `agentic_isolation`.

I also ran the driver smoke once in `agentprims-exp05` worktree for empirical confirmation:
```bash
cd /home/ubuntu/Code/AgentParadise/agentic-primitives/.ntm/worktrees/agentprims/exp05
bash providers/workspaces/interactive-tmux/scripts/smoke.sh
```
Observed output: 3/3 pass (`claude`, `codex`, `gemini`).

## Findings by severity

### Blocker

- **None identified.**
  - The integration succeeds in smoke (`3/3 agents`) and there are no evidence-backed hard crashes or irreversible state leaks.
  - The issues below reduce reliability/error transparency and API fitness rather than making the provider categorically unusable.

### Major

1. **`start_workspace` can return success without startup gate success (readiness false-positive path is unhandled).**
   - `start_workspace -> _bootstrap_tmux_and_launch` calls `_wait_for_text(...)` for each agent but discards the return value; failures only log a warning.
   - Evidence: `.ntm/worktrees/agentprims/exp05/providers/workspaces/interactive-tmux/driver/interactive_tmux.py:575-580`, `582-590`.
   - Why this matters: callers cannot reliably treat `start_workspace` as a successful “ready to send” operation. This is worse than the tested isolation protocols, where startup/warmup markers are part of the contract (`EXP-01` leg (a), `EXP-01` readiness discussion, and the explicit smoke contract in this EXP-05 iteration).
   - Concrete mismatch vs measured behavior: `EXP-05` experiment doc describes startup markers and warns that misses are actionable warnings (`EXP-05` section “Known benign warning during start”, lines 185-197).

2. **Protocol is not compatible with current `agentic_isolation.WorkspaceProvider` contract without an adapter layer.**
   - `InteractiveTmuxWorkspace` exposes `start_workspace/send_message/await_completion/capture_response/stop`, while `WorkspaceProvider` requires `create/destroy/execute/read_file/file_exists/...`.
   - Evidence: protocol in `lib/python/agentic_isolation/agentic_isolation/providers/base.py:73-128` and workspace flow in `lib/python/agentic_isolation/agentic_isolation/workspace.py:204-275`.
   - Impact for Syntropic137: direct substitution into existing isolation layer is not possible; an adapter/bridge is required before programmatic integration.

3. **Error-state semantics are under-specified for Syntropic137 orchestration.**
   - `await_completion` returns plain `bool` with no reason/phase code; caller cannot distinguish “never ready yet,” “timed out,” or “agent failed/errored.”
   - Evidence: `.ntm/worktrees/agentprims/exp05/providers/workspaces/interactive-tmux/driver/interactive_tmux.py:600-651`.
   - In `agentic_isolation.ExecuteResult`, timeout/error semantics are explicit (`timed_out`, `exit_code`, `stderr`) (`.../providers/base.py:21-44`), so this API is not isomorphic with existing structured result patterns.

4. **Claude readiness heuristic is implemented with 2 signals where prior measurements codified 3.**
   - Adapter reports three-signal intent in docstring, but code checks only `esc to interrupt` and `? for shortcuts`.
   - Evidence: `.../interactive_tmux.py:205-209` vs doc in `.../interactive_tmux.py:23-24` and EXP-01 friction suggestion (`.ntm/worktrees/agentprims/lab/experiments/FRICTION-claude.md:170-175`).
   - This is a measurable mismatch: startup/done heuristics were explicitly stabilized around multi-condition checks to avoid redraw ambiguity (`FRICTION-claude` line 170+).

### Minor

1. **`.claude` mount/auth handling diverges from EXP-05a matrix assumptions in a way that should be made explicit in code/comments.**
   - EXP-05a matrix shows authenticated/unauthenticated outcomes for mount combinations and reports that `.claude` alone is insufficient while `.claude.json` alone starts interactive but unauthenticated (`EXP-05a-claude-auth-matrix.md:46-49`).
   - `interactive_tmux` always synthesizes a `~/.claude.json` when only `~/.claude/` is supplied and copies only `.credentials.json` from `.claude/` (`.../interactive_tmux.py:155-170, 175-184, 420-445`).
   - This may change behavior from the matrix model and should be documented as either: “synthetic `claude.json` fallback is supported” or “both mounts must be explicitly provided.”

2. **No structured streaming/output abstraction for long-running runs.**
   - API surface has poll-then-capture only (`capture_response`), no structured event stream or partial token stream contract for host integration (`.../interactive_tmux.py:653-656`, `600-651`).
   - EXP-05 does validate one-shot smoke and explicit tokens, but future consumers (Syntropic137) likely need richer states than raw TUI text and polling.

## PASS findings (cross-check with requested dimensions)

- **Correctness (empirical baseline):** no obvious protocol regressions in measured sequence; smoke confirms end-to-end path for each agent (`claude`, `codex`, `gemini`).
- **AUTH matrix coverage:** per-implementation mount intent matches the “both for full auth” stance: `_ClaudeAdapter` copies `~/.claude/.credentials.json` and ensures `.claude.json` is present (`.../interactive_tmux.py:155-170`, `175-184`, `120-122` and EXP-05a: `55-61`).
- **Security:** no credentials copied into image layers; throwaway mounts + temp directories are removed on `stop` (`.../interactive_tmux.py:659-665`), and `.creds` file is copied by name (`166-170`).
- **Conventions:** manifest/Dockerfile shape and build path are consistent with `claude-cli` convention and `scripts/build-provider.py` expectations (`providers/workspaces/interactive-tmux/manifest.yaml:14-25`, `Dockerfile:46-56`, `Dockerfile:72-73`, `scripts/build-provider.py:230-246`). `git diff origin/main -- providers/workspaces/claude-cli/` is empty in this branch.

## Recommendation matrix for Syntropic137 integration

- Keep this as a focused interactive transport driver, but add a thin adapter that maps:
  1. `InteractiveTmuxWorkspace.start_workspace` -> `WorkspaceProvider.create`
  2. `send + await + capture` -> structured `execute`-style result objects (`exit_code`/`stdout`/`stderr`/`timed_out`) per `agentic_isolation`.
- Add explicit startup failure propagation in `start_workspace` (raise on any per-agent `_wait_for_text` miss unless caller opts out).
- Optionally add optional `await_ready(agent, timeout)` with machine-readable status enum so callers can distinguish startup gate timeouts from generation timeout.

## Final verification (independent, on commit 8e4d621)

Verdict: **APPROVED**.

1. Provider smoke (empirical) in `/tmp/verify-exp05`: command `bash providers/workspaces/interactive-tmux/scripts/smoke.sh`; result `ALL PASS (3/3 agents)` with claude/codex/gemini replies captured.
2. Adapter contract test (empirical): command `python3 providers/workspaces/interactive-tmux/scripts/smoke_provider_adapter.py`; result PASS for `WorkspaceProvider` methods `create`, `execute`, `write_file`, `file_exists`, `read_file`, `destroy`, plus claude `_handle.send_message`/`await_completion`.
3. M1 strict startup propagation spot-check: command `python3 - <<'PY' ...` using `InteractiveTmuxWorkspace.start_workspace(..., startup_timeout_s=0.01, strict_startup=True)`; result `StartupReadinessError` (includes timeout entries such as `timeout_never_ready`) instead of success.
4. M3 `await_completion` structured result spot-check: command `python3 - <<'PY' ... ws.await_completion('claude', timeout=0.2)`; result `AwaitResult(ready=False, timed_out=True, reason='timeout_never_ready')`; invalid agent name still raises `ValueError`.
5. M4 Claude three-signal readiness: method-level check confirmed `_ClaudeAdapter.is_ready('...\u27e9 Try...')` is false while `_ClaudeAdapter.is_started('...\u27e9 Try...')` is true, and `_ClaudeAdapter.is_ready('...\u27e9  ...')` is true (empty prompt marker now explicitly checked).
6. Credential-leak scan for commit diff: command `git log -p --no-color 8e4d621~1..8e4d621 | rg -ni "(ghp_|sk_live_|sk-ant-|xox[bap]|AKIA|eyJ[a-zA-Z0-9_-]{20,}|Bearer\\s+[A-Za-z0-9_\\-\\.=]{20,}|api[_-]?key|secret|token[:=])"` returned no credential-like tokens (only prose `token` in test/assertion text).
