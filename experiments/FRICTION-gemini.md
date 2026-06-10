# Friction Log: Gemini CLI

Records of tooling bugs, docs gaps, config issues, and workarounds.

## Config / Tooling Bugs
- **[config] Node Version Requirement**: The default `ubuntu:24.04` repos install Node 18, which causes an undici `ReferenceError: File is not defined` crash when running `@google/gemini-cli`. 
  - **Workaround found**: Use a `node:22` base image or explicitly install Node 20+.
- **[config] Folder Trust Gate**: The `--yolo` flag does not bypass the folder trust prompt. 
  - **Workaround found**: The `~/.gemini/settings.json` must be explicitly patched to contain `"security": { "folderTrust": { "enabled": false } }` before running the CLI unattended.
- **[tooling-bug] Tmux send-keys behavior**: Using `C-m` with `tmux send-keys` via `docker exec` does not consistently trigger a submission. 
  - **Workaround found**: Using the explicit `Enter` keyword (e.g., `tmux send-keys "prompt" Enter`) successfully submits the prompt.
