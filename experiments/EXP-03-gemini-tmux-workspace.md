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
1. Create a Dockerfile using Node 22 (required for `@google/gemini-cli`), installing `tmux`, `curl`, `git`, and installing the `gemini` CLI via `npm`.
2. Copy host's `~/.gemini` to a temporary throwaway directory, and ensure `settings.json` has `security.folderTrust.enabled: false`.
3. Run the container: `docker run -d --name exp03-gemini -v <tmp_gemini>:/root/.gemini <image> sleep infinity`.
4. Start tmux inside the container: `docker exec exp03-gemini tmux new-session -s geminisession -d 'gemini'`
5. Verify gemini started using `docker exec exp03-gemini tmux ls` and `capture-pane`.
6. Send prompt 1: `docker exec exp03-gemini tmux send-keys -t geminisession "What is 2+2? Answer simply." Enter`
7. Capture pane: `docker exec exp03-gemini tmux capture-pane -p -t geminisession -S - -E -`
8. Send prompt 2: `docker exec exp03-gemini tmux send-keys -t geminisession "Multiply that by 10." Enter`
9. Capture pane again to verify the response.
10. Record findings.

## Expected Signals
- Successful gemini start without hanging on a folder trust prompt.
- `capture-pane` shows the LLM output.
- Second prompt correctly references the first.

## Results
The experiment ran successfully (observed in 1 run).
- **Node.js version**: `ubuntu:24.04` installs Node 18 natively, which fails with `gemini` CLI due to missing `File` in `undici`. Using `node:22` base image resolved this.
- **Session startup**: Running `docker exec exp03-gemini tmux new-session -s geminisession -d 'gemini'` successfully starts the CLI in the background without hanging, since `folderTrust.enabled` is `false`.
- **Authentication**: Using a mounted `~/.gemini` copy successfully authenticates the CLI instance.
- **Prompt Execution**: Using `tmux send-keys` requires explicit `Enter` keys rather than `C-m` when sent through `docker exec`. The sequence `docker exec <container> tmux send-keys -t <session> "prompt string" Enter` works reliably.
- **Response Capture**: We captured the output successfully using `tmux capture-pane -p -t geminisession -S - -E -`. Completion is easily detectable programmatically by searching for the CLI's prompt indicator (`>   Type your message or @path/to/file` or `Shift+Tab to accept edits`).
- **Interactivity**: The second follow-up message correctly used the context of the first message. `4` was answered for `2+2`, and `40` for the follow-up `Multiply that by 10.`.

## Conclusions (Verdict: go)
**go**: The interactive `gemini` CLI can be successfully driven inside a Docker container via tmux panes. 
The host machine can reliably send keys and capture pane contents to programmatically drive the agent and detect command completion.

**Recipe for Unattended Operation:**
1. Base image must have Node v20+.
2. Mount a host `~/.gemini` profile with OAuth credentials.
3. Configure `~/.gemini/settings.json` to have `"security": { "folderTrust": { "enabled": false } }`.
4. Command to send prompt: `docker exec <container> tmux send-keys -t <session> "prompt" Enter`.
5. Command to capture pane: `docker exec <container> tmux capture-pane -p -t <session> -S - -E -`.
