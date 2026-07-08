# Codex Plugin Hooks Doctor

## Question

Can the LangFuse observability doctor turn a missing Codex `plugin_hooks`
setting from an ambiguous false value into a secret-safe, machine-parseable
diagnosis with exact remediation guidance?

## Hypothesis

1. The current MacBook Codex config has the official LangFuse Codex marketplace
   and tracing plugin enabled, but does not have `plugin_hooks = true` in a
   scanned Codex config file.
2. The current doctor reports only `plugin_hooks_enabled=false`, which is
   insufficient for quick remediation because it does not identify checked
   config paths or the required TOML snippet.
3. Extending the doctor output with checked config paths and a short
   remediation string will make the setup gap actionable without printing
   secrets or modifying user config.
4. The change will preserve minimal VPS/Docker portability: JSON output still
   parses under `PATH=/bin:/usr/bin`, and `--no-tests` still avoids Cargo.

## Setup

- Repository: `agentic-primitives`
- Branch: `feat/observability-exporter-primitive`
- Doctor: `scripts/langfuse-observability-doctor.sh`
- Prior evidence:
  - `experiments/2026-07-08--langfuse--portable-setup-doctor`
  - `experiments/2026-07-08--langfuse--doctor-minimal-env-portability`
  - `experiments/2026-07-08--langfuse--doctor-workspace-image`

## Conditions

1. Baseline: run the current doctor in JSON mode and capture whether Codex
   plugin hooks are false while the tracing plugin is configured.
2. Treatment: patch only the doctor/docs so the JSON and text reports name
   checked config paths and the remediation for Codex plugin hooks.
3. Validation: run the doctor in normal JSON mode and minimal
   `PATH=/bin:/usr/bin` JSON mode with `--no-tests`.
4. Hygiene: verify shell syntax, JSON parseability, `git diff --check`, and no
   raw LangFuse key values in the new artifacts.

## Expected Signals

- Baseline JSON shows `official_plugins.codex.plugin_hooks_enabled=false`.
- Treatment JSON includes a Codex config diagnostics object with:
  - checked config paths;
  - whether any config file exists;
  - whether the tracing plugin is configured;
  - whether `plugin_hooks = true` was found;
  - a remediation snippet or instruction.
- Text output includes the same remediation without secret values.
- Minimal mode exits 0 and parses as JSON.
