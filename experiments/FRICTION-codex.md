# Friction Log: Codex tmux experiment

## Items

- [tooling-bug] **First prompt submit requires two-stage key sequence in this setup.**
  - In Run 1, a single `prompt + C-m` only rendered the text in the pane but did not dispatch.
  - Reliable pattern: `prompt + C-j + C-m`.
  - Evidence: Run 1, first submit (1/1), resolved only on second sequence.

- [tooling-bug] **Hook review state can steal key input immediately after startup.**
  - Startup enters hook review UI; without `Esc`, prompt text can land in the wrong screen.
  - Evidence: visible prompt transitions in Run 1 and Run 2.

- [docs-gap] **`codex` interactive onboarding flow and first-submit behavior are under-documented for tmux driving.**
  - No clear source guidance observed for the trust + hook screens and the first-submit two-key behavior.
  - Evidence: discovered empirically in Run 1 and Run 2.

- [config] **Mounted `.codex` imports config that triggers mcp_client startup warnings (`mcp_agent_mail`).**
  - Warnings are persistent but non-fatal in this run.
  - Evidence: MCP warning emitted in both runs.

- [workaround-found] **Working sequence for headless drive:**
  - launch codex → accept trust (`1`) → `Esc` out of hook review → prompt with `C-j C-m` (especially first submission) → poll via capture for completion marker text.
  - Evidence: full back-and-forth captured in Run 1 (2/2 successful completions with stable `codex` answers).

- [tooling-bug] **`~/.claude`-only path never completes interactive auth with only copied `.claude` + theme flow.**
  - Symptom: repeated startup on mount tests showed `Claude configuration file not found at: /home/agent/.claude.json` and login UIs without stable completion path.
  - Evidence: 2 runs; same with direct style-entry attempts (`2` + `C-m`).

- [docs-gap] **`~/.claude.json` is onboarding metadata, while credential state is in `.claude/.credentials.json` under npm-installed workspace image.**
  - Evidence: host inspection and container probes showed OAuth prompts for `.claude.json`-only and active session for dual mount.
  - Impact: prior docs claiming `.claude.json` as token source are inconsistent with observed startup flow.

- [config] **`installMethod: native` appears in `~/.claude.json`, but token location still relies on `.claude/.credentials.json`.**
  - Evidence: host key scan + interactive run output line `installMethod is native, but directory /home/agent/.local/bin does not exist`.

- [workaround-found] **Definitive volume test recipe**
  - Copy host auth material to temporary throwaway paths under `/tmp`, then mount:
    - none / `-v /tmp/exp-n/.claude:/home/agent/.claude:rw` / `-v /tmp/exp-n/.claude.json:/home/agent/.claude.json:rw` combinations.
  - Launch: `tmux new-session -d -s claude-sess 'claude'`.
  - Capture with `tmux capture-pane -t claude-sess:0.0 -p -S -200`.
  - Submit prompts from host with `tmux send-keys -t claude-sess:0.0 '...' C-m` and verify completion by prompt echo + tool output.
