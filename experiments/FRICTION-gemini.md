# Friction Log: Gemini CLI

Records of tooling bugs, docs gaps, config issues, and workarounds.

## Config / Tooling Bugs
- **[config] Node Version Requirement**: The default `ubuntu:24.04` repos install Node 18, which causes an undici `ReferenceError: File is not defined` crash when running `@google/gemini-cli`. 
  - **Workaround found**: Use a `node:22` base image or explicitly install Node 20+.
- **[config] Folder Trust Gate**: The `--yolo` flag does not bypass the folder trust prompt. 
  - **Workaround found**: The `~/.gemini/settings.json` must be explicitly patched to contain `"security": { "folderTrust": { "enabled": false } }` before running the CLI unattended.
- **[tooling-bug] Tmux send-keys behavior**: Using `C-m` with `tmux send-keys` via `docker exec` does not consistently trigger a submission. 
  - **Workaround found**: Using the explicit `Enter` keyword (e.g., `tmux send-keys "prompt" Enter`) successfully submits the prompt.

## Swarm / Multi-Agent Friction (EXP-04)
- **[config] Claude Authentication Mount**: Unlike Codex and Gemini which authenticate primarily via their config directories (`~/.codex`, `~/.gemini`), Claude stores its primary OAuth token in a separate `~/.claude.json` file in the user's home directory.
  - **Workaround found**: Must explicitly mount `~/.claude.json` to `/root/.claude.json` in addition to the `~/.claude` directory when running unattended containerized instances.
- **[docs-gap] Claude Trust Prompt**: When running in a new workspace container, Claude presents a "Do you trust the contents of this directory?" prompt.
  - **Workaround found**: Send an explicit `Enter` key via tmux prior to sending the first prompt to bypass this gate.
- **[docs-gap] Codex Hooks Review Prompt**: Codex presents a "Hooks need review" screen on startup.
  - **Workaround found**: Must explicitly send an `Escape` key via tmux to close the hooks review menu before sending the first prompt.
