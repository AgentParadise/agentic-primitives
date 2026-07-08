# Verdict

## Decision

go

The doctor now turns the Codex plugin-hooks caveat into an actionable,
machine-parseable setup diagnosis without mutating user config or printing
secrets. This closes the local ambiguity around `plugin_hooks_enabled=false`:
the operator can see exactly which config files were checked and which
`[features]` setting is missing.

This does not itself enable hooks on the current MacBook. It makes the setup
state explicit and repeatable for MacBook/VPS/Docker readiness checks.

## Evidence

- Baseline gap: `runs/baseline-codex-summary.json`.
- Treatment JSON: `runs/treatment-codex-summary.json`.
- Treatment text: `runs/treatment-text.txt`.
- Minimal shell: `runs/minimal-codex-summary.json`.
- Hygiene: `runs/bash-n.txt`, `runs/diff-check.txt`, `runs/secret-scan.txt`.

## Hypothesis scorecard

| Prediction | Observed | Score | Notes |
|---|---|---:|---|
| Current MacBook has tracing plugin enabled but missing Codex plugin hooks | Confirmed | correct | Baseline and treatment both show `tracing_plugin_configured=true` and `plugin_hooks_enabled=false`. |
| Baseline doctor reports only a weak boolean | Confirmed | correct | Baseline had no checked path/remediation object. |
| Treatment can add checked paths and remediation without secrets or config mutation | Confirmed | correct | JSON/text outputs include paths and remediation; no config write occurred. |
| Minimal mode remains portable | Confirmed | correct | Minimal PATH run exited 0 and parsed as JSON with config diagnostics present. |

## Follow-up

- If the operator wants this MacBook fully ready by default, add
  `plugin_hooks = true` under `[features]` in `~/.codex/config.toml` or a
  project-local `.codex/config.toml`, then rerun the doctor.
- A future `--fix` mode could write a project-local config snippet, but this
  experiment intentionally kept the doctor read-only.
