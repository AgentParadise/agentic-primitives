# EXP-04: combined-swarm-container

## Question
Can ONE Docker image containing all three CLIs (claude, codex, gemini) plus tmux host a 3-pane tmux session where each pane runs one interactive agent, and ALL THREE can be driven independently from the host via `docker exec tmux send-keys / capture-pane` concurrently without interfering?

## Hypothesis
We predict that:
1. We can build a single image (`node:22` based) with `@anthropic-ai/claude-code`, `@openai/codex`, and `@google/gemini-cli`.
2. By mounting the host's credentials for all three (`~/.claude`, `~/.codex`, `~/.gemini`), we can authenticate all agents simultaneously.
3. We can create a tmux session with 3 windows or panes (we will use windows for easier targeting: `claude-win`, `codex-win`, `gemini-win`) and run one CLI in each.
4. Each agent can be driven independently using their respective prompt submission patterns (e.g., Gemini needs explicit `Enter`, Codex needs `C-j C-m` for the first prompt, Claude typically accepts `Enter` or `C-m`).
5. A cross-check where two agents (e.g., Claude and Gemini) are sent prompts concurrently will succeed without interfering with each other's pane outputs or state.

## Method
1. Build `Dockerfile.exp04`.
2. Create throwaway credential copies for all 3 agents in a temporary host directory (e.g., `/tmp/swarm_creds/claude`, etc.). Ensure Gemini's `security.folderTrust.enabled: false`.
3. Run container `exp04-swarm` mounting the credentials to `/root/.claude`, `/root/.codex`, `/root/.gemini`.
4. Start a tmux session `swarm`:
   - Window `claude`: `claude`
   - Window `codex`: `codex --no-alt-screen`
   - Window `gemini`: `gemini`
5. Verify all three agents started and handle any initial gates (e.g., Codex trust banner).
6. Send prompt 1 to Claude: "What is 10+10? Answer simply." Capture & verify.
7. Send prompt 1 to Codex: "What is 20+20? Answer simply." Capture & verify.
8. Send prompt 1 to Gemini: "What is 30+30? Answer simply." Capture & verify.
9. **Concurrent test**: Send a follow-up prompt to Claude ("Multiply by 2") and Gemini ("Multiply by 2") concurrently. Wait for both and verify independent context.
10. Record results, completion detection mechanisms, and run counts.

## Expected Signals
- All three CLIs launch successfully in their respective tmux windows.
- Each CLI responds correctly to prompts.
- Concurrent prompts do not cause pane locking or message cross-contamination.
