# EXP-03: gemini-in-tmux-in-docker

## Question
Can an interactive `gemini` CLI session running inside a tmux pane inside a Docker container be programmatically driven (send prompts, capture responses) from the host using `docker exec tmux send-keys` and `tmux capture-pane`?

## Hypothesis
We predict that:
1. We can install `gemini` and `tmux` in a base ubuntu container.
2. By mounting the host's `~/.gemini` directory (with `security.folderTrust.enabled: false` to bypass the trust modal), the `gemini` CLI will start interactively and authenticate successfully.
3. We can send a prompt from the host using `docker exec <container> tmux send-keys -t <pane> "prompt" C-m`.
4. We can capture the response and detect completion programmatically using `docker exec <container> tmux capture-pane -p -t <pane>`.
5. We can send a second follow-up message to prove true back-and-forth interactivity.

## Method
1. Create a Dockerfile extending `ubuntu:latest` (or `providers/workspaces/base`), installing `tmux`, `curl`, `npm`, and installing the `gemini` CLI.
2. Copy host's `~/.gemini` to a temporary throwaway directory, and modify `settings.json` to set `security.folderTrust.enabled: false`.
3. Run the container: `docker run -d --name exp03-gemini -v <tmp_gemini>:/root/.gemini <image> sleep infinity`.
4. Start tmux inside the container: `docker exec -d exp03-gemini tmux new-session -s geminisession -d 'gemini'`
5. Verify gemini started.
6. Send prompt 1: `docker exec exp03-gemini tmux send-keys -t geminisession "What is 2+2? Answer simply." C-m`
7. Loop and capture pane until response is complete.
8. Send prompt 2: `docker exec exp03-gemini tmux send-keys -t geminisession "Multiply that by 10." C-m`
9. Loop and capture pane until response is complete.
10. Record findings.

## Expected Signals
- Successful gemini start without hanging on a folder trust prompt.
- `capture-pane` shows the LLM output.
- Second prompt correctly references the first.
