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
