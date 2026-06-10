# EXP-07 — Antigravity readiness research + experiment

**Date:** 2026-06-10
**Owner:** Codex agent
**Branch:** `agentprims-exp07`
**Goal:** Determine whether Antigravity CLI can replace the Gemini lane in `interactive-tmux` and capture a matrix row.

## 1) Research summary

### Command, install, and identity
- Antigravity CLI command is `agy`.
- Official install method is `curl -fsSL https://antigravity.google/cli/install.sh | bash` (plus OS-specific PowerShell/CMD variants). See official docs and README.
- `agy --version` exists after install and reports `agy version ...`.

Sources:
- https://docs.flutter.dev/ai/antigravity-cli (states executable `agy`, install commands, and `agy --version` sample)
- https://raw.githubusercontent.com/google-antigravity/antigravity-cli/main/README.md

### Version and release channel
- Release metadata reports latest tag `1.0.7` (published 2026-06-09), and the installer reported `Latest available version: 1.0.7` during image build.

Sources:
- https://api.github.com/repos/google-antigravity/antigravity-cli/releases/latest
- https://raw.githubusercontent.com/google-antigravity/antigravity-cli/main/CHANGELOG.md
- local installer output captured in EXP-07 smoke run

### Migration path from Gemini CLI
- Officially positioned as the replacement for Gemini CLI. Public migration notes describe: transition from Gemini CLI, migration command `agy plugin import gemini`, and an onboarding/migration pass on first startup when Gemini config is detected.

Sources:
- https://docs.flutter.dev/ai/antigravity-cli (automatic migration notes)
- https://raw.githubusercontent.com/google-antigravity/antigravity-cli/main/README.md
- https://github.com/google-gemini/gemini-cli/discussions/27274

### TUI vs GUI-only
- Antigravity CLI is described as terminal-first/TUI and keyboard-first; our container capture confirms interactive UI screens.
- It prints an interactive login menu and accepts navigation keys / text input.

Sources:
- https://raw.githubusercontent.com/google-antigravity/antigravity-cli/main/README.md (states TUI)
- container capture evidence (see section 2)

### Auth and headless behavior
- Auth flow is browser-based/system-keyring with SSH fallback that prints an authorization URL.
- `agy --help` includes `--print`, `--prompt`, `--prompt-interactive`, and `--print-timeout` flags for non-interactive operation.
- In this environment, non-interactive `--print` blocks at auth and times out waiting for a code.

Sources:
- https://raw.githubusercontent.com/google-antigravity/antigravity-cli/main/README.md
- local `agy --help` output (container)

### Auth material location
- Official docs point at `~/.gemini/antigravity-cli/settings.json` and related `~/.gemini` paths for settings/certs/state.
- Initial startup auto-creates CLI app-data dirs under `~/.gemini/antigravity-cli`.

Sources:
- https://raw.githubusercontent.com/google-antigravity/antigravity-cli/main/README.md
- local file-system snapshot from container run

## 2) Experiment (EXP-07 protocol adapted from EXP-03)

### Method executed
1. Built a `node:22` image, installed `tmux` and `antigravity` via `curl -fsSL https://antigravity.google/cli/install.sh | bash`.
2. Started container with throwaway copies mounted at `/root/.gemini` and `/root/.antigravitycli` (never committed).
3. Started tmux in detached session: `tmux new-session -d -s agysession "agy"`.
4. Sent key sequences via `tmux send-keys` and captured output via `tmux capture-pane -p -t agysession`.
5. Repeated with and without host `~/.gemini` copy (both throwaway).

### Observed evidence
- Startup succeeds with tmux hosting and interactive frame:
  - ASCII terminal UI banner + menu appears.
  - Session is alive and `tmux ls` shows the workspace session.
- Submit keys work:
  - `tmux send-keys -t agysession "1" Enter` transitions to OAuth URL prompt.
  - Entering fake auth code via `tmux send-keys` returns explicit auth error (`invalid_grant`) and returns to login state.
- Without any auth token state, CLI remains at login gate and does not progress to chat completion.
- `agy --print` returns auth-required message and waits for authorization code with timeout.
- This confirms **tmux-drivable UI exists**, but end-to-end prompt completion is blocked by auth dependency.

### Matrix row proposal (for `experiments/EXP-05-interactive-tmux-provider.md`)

| Dimension | Result (Agy) |
|---|---|
| Binary / command | `agy` |
| Install path | `curl -fsSL https://antigravity.google/cli/install.sh | bash` |
| TUI present | Yes (authenticated terminal session) |
| Submit keys | `send-keys <prompt> Enter` (interactive mode) |
| Readiness gate | Login screen + auth menu in pane; startup requires OAuth/login completion |
| Init gate | `not signed in` login screen; optional migration path exists but migration not sufficient for session auth in this run |
| Completion heuristics | Not validated (auth gate blocks conversational response path) |
| Headless/unattended flags | `--print`, `--print-timeout`, `--prompt-interactive` available |
| Credential mount | Throwaway `~/.gemini` and `~/.antigravitycli` mountable; current data shape is not immediately accepted as active Antigravity token without login flow |

## 3) Verdict for EXP-07

**Result: PASS for TUI installability and tmux drivability (interactive channel works).**

**Result: Blocked for full smoke completion in this environment** because Antigravity requires active auth handoff and did not auto-authorize with existing `~/.gemini` copy.

### Recommended migration plan
- Keep Gemini lane active for unattended flows until Antigravity auth bootstrap strategy is proven.
- If attempting staged replacement, guard Antigravity lane behind a feature flag and require explicit `auth_prepared=true` / “interactive login completed” gate before enabling provider usage.
- If Antigravity is to fully replace Gemini, add provider-side auth bootstrap contract first (for containerized login or equivalent token handoff), then rerun EXP-07 for a true 3/3/steady-state smoke.
