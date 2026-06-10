# EXP-05a Claude Auth Matrix

## Hypothesis

1. Interactive Claude authentication uses files under `~/.claude` for tokens and session state, while `~/.claude.json` only carries onboarding or preference metadata.
2. Mounting only `~/.claude.json` into a workspace container will not reliably authenticate an interactive Claude CLI session.
3. Mounting only `~/.claude` will authenticate if mounted to the same path expected by the installed CLI runtime.
4. Mounting both `~/.claude` and `~/.claude.json` will authenticate if either contains the required credentials.
5. Whether the same auth contract changes between native package install and npm install of `claude-code` is uncertain and needs verification.

## Planned method

- Capture host auth artifacts and classify what secret fields they contain (redacted).
- Build/run an interactive Claude container workflow for each mount combination: only `~/.claude`, only `~/.claude.json`, both, neither.
- Record whether startup reaches interactive prompt, whether authentication succeeds, and whether a submitted test prompt returns output.

## Planned results

- Populated once probes complete.
