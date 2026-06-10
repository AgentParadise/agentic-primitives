# Interactive-tmux Workspace Provider

A workspace image bundling **claude**, **codex**, and **gemini** interactive
CLIs plus `tmux`, designed to be driven from the host via
`docker exec <container> tmux send-keys` / `tmux capture-pane`. Sibling to
the existing `claude-cli` provider; neither replaces the other.

## Why it exists

`providers/workspaces/claude-cli` drives Claude in non-interactive (`-p`)
mode, which is leaving the Max plan in ~5 days. The interactive transport
(tmux pane + host-side `docker exec`) was validated in EXP-01..04 of this
repo's experiment series and survives on the subscription plan. This
provider packages that transport as a real provider next to `claude-cli`.

## Build

Same convention as every other provider in this repo:

```bash
uv run scripts/build-provider.py interactive-tmux
# or
just build-provider interactive-tmux
```

Produces `agentic-workspace-interactive-tmux:latest` (and a version tag
matching the pinned `CLAUDE_CLI_VERSION` in the Dockerfile).

## Host-side driver

`driver/interactive_tmux.py` is a single-file Python 3.11+ driver (stdlib
only) exposing five primitives that hide the per-agent quirks:

```python
from interactive_tmux import InteractiveTmuxWorkspace
from pathlib import Path

ws = InteractiveTmuxWorkspace.start_workspace(
    name="my-workspace",
    host_auth={
        "claude": Path("~/.claude").expanduser(),
        "codex":  Path("~/.codex").expanduser(),
        "gemini": Path("~/.gemini").expanduser(),
    },
)

ws.send_message("claude", "Refactor lib/foo.py to use dataclasses.")
ws.await_completion("claude", timeout=120)
text = ws.capture_response("claude")
ws.stop()
```

A CLI shim is bundled for shell-script consumers:

```bash
python3 driver/interactive_tmux.py start  --name w1
python3 driver/interactive_tmux.py send   --name w1 --agent gemini --text "..."
python3 driver/interactive_tmux.py await  --name w1 --agent gemini --timeout 60
python3 driver/interactive_tmux.py capture --name w1 --agent gemini
python3 driver/interactive_tmux.py stop   --name w1
```

## Per-agent matrix (encoded in the driver — callers should not need this)

| Concern    | Claude                                                                 | Codex                                                                                  | Gemini                                                       |
|------------|-------------------------------------------------------------------------|----------------------------------------------------------------------------------------|--------------------------------------------------------------|
| Launch     | `claude` + Enter                                                        | `codex --no-alt-screen` + Enter, then `1` Enter (trust), then `Escape` (hooks review)  | `gemini` + Enter                                             |
| Submit     | `send-keys -l <text>` then `send-keys Enter`                           | `send-keys -l <text>` then `send-keys C-j C-m` (first-send gotcha — see EXP-02)        | `send-keys -l <text>` then `send-keys Enter` (never `C-m`)   |
| Readiness  | No `esc to interrupt` + `? for shortcuts` footer visible (3-signal)     | No `• Working` marker + idle indicator (`▌`) visible                                   | `Type your message` prompt indicator visible                 |
| Auth mount | **Both** `~/.claude/` and `~/.claude.json` — see below                  | `~/.codex/`                                                                            | `~/.gemini/` (settings.json auto-patched to disable folderTrust) |

## Claude auth: the `.credentials.json` vs `.claude.json` answer

EXP-01 and EXP-04 disagreed on where Claude's OAuth tokens live. The
disagreement was resolved empirically in EXP-05 with two isolated mount
tests:

- `~/.claude/.credentials.json` holds the actual OAuth tokens
  (`claudeAiOauth.{accessToken, refreshToken, ...}`). **Without it,
  Claude falls back to API Usage Billing (Sonnet) instead of Max plan
  (Opus 4.7).**
- `~/.claude.json` (a file at `$HOME`, peer of the `~/.claude/`
  directory, NOT inside it) holds `oauthAccount` metadata
  (uuid/email/org) plus onboarding markers (`hasCompletedOnboarding`,
  `theme`, `projects.<path>.hasTrustDialogAccepted`). Without it,
  Claude still authenticates against Max plan but shows the
  onboarding/theme/trust wizards on every fresh container.

The driver mounts both, copying `~/.claude/.credentials.json` into a
throwaway dir and synthesising a `~/.claude.json` that carries the host's
`oauthAccount` through plus pre-seeds the workspace path in the trust map.

## Credentials are NEVER baked or committed

`docker run` mounts throwaway host-side copies. The image contains zero
credential bytes. The `runs/` directory is shell-script output (transcripts
of model responses) and is safe to commit; the credentials themselves
never leave `/tmp/interactive-tmux-*` on the host.

## Smoke test

```bash
bash providers/workspaces/interactive-tmux/scripts/smoke.sh
```

Starts a workspace, sends one echo-token prompt per agent, captures the
response, verifies each token appears in its transcript. Writes
`runs/smoke-<agent>.txt` files as evidence.

## What this provider does NOT do (today)

- Stream partial responses. The API is poll-then-capture.
- Reconnect to a running workspace from a different driver process.
- Implement the `agentic_isolation.WorkspaceProvider` Protocol parity
  (that protocol is shaped around `execute(cmd) → result`, not around
  prompt round-trips; bridging is a separate decision).
- Plugin baking. The three CLIs run as humans run them; plugin
  participation through the interactive transport is a separate arc.

## See also

- `experiments/EXP-05-interactive-tmux-provider.md` — design,
  hypothesis, run evidence, verdict.
- `experiments/LAB-PLAN.md` (on `ntm/agentprims/cc_1`) — the broader
  lab roadmap.
- `experiments/EXP-01-claude-tmux-workspace.md` and friends — per-agent
  protocol validation that this provider is the integration of.
