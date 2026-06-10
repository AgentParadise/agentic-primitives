# EXP-05a Claude Auth Matrix

## Hypothesis (frozen)

- Interactive Claude sessions authenticate from token material in `~/.claude/.credentials.json`.
- `~/.claude.json` is metadata-only and should not be used as the token source for interactive sessions.
- Mount combinations should be tested as:
  - none
  - `.claude`
  - `.claude.json`
  - both
- If mount layout changes behavior, we need to know which layout is required for containerized interactive sessions.

Committed as `100a3b0` before probing.

## Method

### Host inspection (READ-ONLY, no secret values)

- Read `/home/ubuntu/.claude/.credentials.json` structure:
  - top-level keys: `claudeAiOauth`
  - nested keys: `accessToken`, `refreshToken`, `expiresAt`, `scopes`, `subscriptionType`, `rateLimitTier`
  - token lengths: `accessToken` 108 chars, `refreshToken` 108 chars
  - file size 471 bytes
- Read `/home/ubuntu/.claude.json` structure:
  - 44 top-level keys, including `installMethod` and various onboarding metadata
  - file size 58,260 bytes
- No tokens were copied into the repo or markdown.

### Container probing protocol

1. Use `agentic-claude-cli-tmux:exp01` (has `tmux` + `claude`).
2. Launch tmux + interactive `claude` in a detached container session.
3. For each mount case, capture with `tmux capture-pane` and drive keys with `tmux send-keys`.
4. For startup gating, choose a style entry when prompted (`2` + `C-m` in this image).
5. For authenticated paths, accept trust prompt with `1`, submit prompts, capture output.

All mounts are throwaway copies under `/tmp` (not host directories).

## Results

### Mount matrix (host-runner-independent, observed counts shown)

| Case | Mounts provided | Runs observed | Startup outcome | Auth outcome | Prompt/response outcome |
|---|---|---:|---|---|---|
| none | none | N=2 | Runs to theme/login flow prompt (`2`+`C-m` needed), then selects `Select login method` UI | **Needs login** (OAuth required) | No authenticated prompt execution observed |
| .claude | only `~/.claude` directory | N=2 | `Claude configuration file not found at /home/agent/.claude.json` + `A backup file exists...`, then `Select login method` UI | **Needs login** (OAuth required) | No authenticated prompt execution observed |
| .claude.json | only `~/.claude.json` | N=2 | `Accessing workspace /workspace` + trust prompt + normal session splash (`Welcome back ...`) | **Session starts but not authenticated** (`Not logged in · Please run /login` on submit) | Submit succeeds as text, but completion is blocked until `/login` |
| both | both `~/.claude` + `~/.claude.json` | N=2 | `Accessing workspace /workspace` + trust prompt + normal session splash (`Welcome back ...`) | **Authenticated start (no login step)** | Prompt + follow-up are submitted from host via tmux and capture returns tool output activity / completed command paths |

### Install-method check (native vs npm)

- Host `.claude.json` includes `installMethod` metadata (`native` in current user file), but token material is still in `.claude/.credentials.json`.
- In-container interactive output, auth behavior did **not** differ by presence/absence of `installMethod` metadata.
- No native CLI package installation was available to test in this repo/worktree session; only npm-based workspace image (`agentic-claude-cli-tmux:exp01`) was used.

## Conclusions

1. The contradiction is resolved: in this environment, valid interactive sessions are driven by credential data in `~/.claude/.credentials.json`, while `~/.claude.json` by itself is insufficient.
2. Mounting only `.claude.json` starts Claude UI but remains unauthenticated (`Please run /login`), so it is not enough for authenticated interactive execution.
3. Mounting both files/directories is required for working authenticated startup in this image.
4. Evidence indicates the `installMethod` field in `.claude.json` is metadata-only and is not the credential source.
