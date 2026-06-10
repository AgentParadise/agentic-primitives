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

## Results
The experiment ran successfully (observed in 1 run).
- **Environment & Setup**: A single `node:22` image seamlessly installed and launched `@anthropic-ai/claude-code`, `@openai/codex`, and `@google/gemini-cli`.
- **Authentication**: All three agents were successfully authenticated simultaneously by mounting the host's `~/.claude.json`, `~/.codex`, and `~/.gemini` directories. Note: For Claude, the `.claude.json` file needs to be mounted explicitly as it holds the OAuth tokens on the host.
- **Initialization Gates**:
  - `claude` requested a "Folder Trust" prompt because the mock folder was used. Sending `Enter` bypassed it successfully.
  - `codex` triggered a "Hooks review" prompt. Sending `Escape` bypassed it.
  - `gemini` started directly with its prompt, thanks to `security.folderTrust.enabled: false` being pre-configured.
- **Independent Prompt Submission**: 
  - Claude correctly answered `10+10` -> `● 20`.
  - Codex correctly answered `20+20` -> `• 40` (after using `C-j C-m`).
  - Gemini correctly answered `30+30` -> `✦ 60` (using explicit `Enter`).
- **Concurrent Test**: Submitting a follow-up prompt (`Multiply by 2`) to both Claude and Gemini simultaneously using background `docker exec tmux send-keys` commands worked flawlessly. Claude returned `40` and Gemini returned `120`. No cross-contamination, pane locking, or interference was observed. Both maintained their independent conversational contexts.

## Conclusions (Verdict: go)
**go**: A single Docker container acting as a "swarm" workspace can concurrently host and run all three CLI agents in separate tmux windows. Each agent can be programmatically driven and monitored from the host without interfering with the others. 

**Recipe for Unattended Swarm Operation:**
1. Base image must have Node v20+. Install all three npm packages.
2. Mount host credentials for all three (`~/.claude.json`, `~/.codex`, `~/.gemini`).
3. Handle agent-specific initialization flows programmatically (e.g. `Enter` for Claude trust, `Escape` for Codex hooks, configure Gemini trust to `false`).
4. Handle agent-specific prompt submission keys (`Enter` for Claude/Gemini, `C-j C-m` for Codex's first message).
5. Responses can be confidently parsed per pane using `tmux capture-pane -p -t <session>:<window>`.
