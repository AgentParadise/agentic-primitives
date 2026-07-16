# Codex Plugin Hooks Remediation

## Question

Does applying the doctor-recommended Codex `plugin_hooks` setting make this
MacBook's official LangFuse Codex plugin setup ready without changing repo
state or exposing credentials?

## Hypothesis

1. The current user Codex config already has the official
   `tracing@codex-observability-plugin` enabled under `~/.codex/config.toml`.
2. Adding `plugin_hooks = true` under the existing `[features]` table in that
   same user config will make `scripts/langfuse-observability-doctor.sh`
   report `official_plugins.codex.plugin_hooks_enabled=true` and
   `official_plugins.codex.config.ready=true`.
3. The remediation does not require LangFuse credentials and should not change
   repository-tracked files other than experiment artifacts.
4. The doctor should still report `TRACE_TO_LANGFUSE` and `LANGFUSE_*` as
   missing in the bare shell, because this probe only remediates Codex hook
   activation, not runtime credential injection.

## Setup

- Repository: `agentic-primitives`
- Branch: `feat/observability-exporter-primitive`
- User config under test: `~/.codex/config.toml`
- Prior evidence:
  - `experiments/2026-07-08--langfuse--codex-plugin-hooks-doctor`

## Conditions

1. Baseline: capture redacted relevant Codex config lines and doctor JSON before
   remediation.
2. Treatment: add only `plugin_hooks = true` under `[features]` in
   `~/.codex/config.toml`.
3. Verification: rerun the doctor in JSON and text modes.
4. Hygiene: record the user-config diff with only non-secret lines, run
   `git status --short`, `git diff --check`, and scan artifacts for raw
   LangFuse keys.

## Expected Signals

- Baseline doctor shows Codex tracing plugin configured and plugin hooks false.
- Treatment doctor shows Codex tracing plugin configured, plugin hooks true, and
  config ready true.
- Bare shell LangFuse runtime env remains missing, proving this probe did not
  sneak credentials into shell config.
- Repository status remains clean except this experiment's artifacts and the
  pre-existing untracked handoff directory.
