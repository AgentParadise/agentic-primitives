# Results

## Headline

| Probe | Result | Evidence |
|---|---:|---|
| Baseline doctor JSON | confirmed gap | `runs/baseline-doctor.json`, `runs/baseline-codex-summary.json` |
| Treatment doctor JSON | pass | `runs/treatment-doctor.json`, `runs/treatment-codex-summary.json` |
| Treatment text output | pass | `runs/treatment-text.txt` |
| Minimal shell JSON | pass | `runs/minimal-doctor.json`, `runs/minimal-codex-summary.json` |
| Hygiene | pass | `runs/bash-n.txt`, `runs/diff-check.txt`, `runs/secret-scan.txt` |

## Baseline

`runs/baseline-codex-summary.json` showed the setup caveat as a pair of
booleans:

- `plugin_hooks_enabled=false`
- `tracing_plugin_configured=true`

That confirmed the doctor detected the current MacBook state, but the output
did not tell the operator which config files were checked or what TOML shape to
add.

## Treatment

`scripts/langfuse-observability-doctor.sh` now emits a structured
`official_plugins.codex.config` object.

`runs/treatment-codex-summary.json` shows:

- checked paths:
  - `/Users/neural/.codex/config.toml` exists;
  - project `.codex/config.toml` is missing.
- `any_config_file_exists=true`
- `plugin_hooks_required=true`
- `plugin_hooks_found=false`
- `tracing_plugin_found=true`
- `ready=false`
- remediation: add `[features] plugin_hooks = true` and keep
  `[plugins."tracing@codex-observability-plugin"] enabled = true`.

`runs/treatment-text.txt` includes the same checked paths and remediation in the
human-readable report.

## Minimal Shell

The minimal shell command:

```bash
env -i HOME="$HOME" PATH="/bin:/usr/bin" bash scripts/langfuse-observability-doctor.sh --json --no-tests
```

exited `0`, emitted no stderr, and produced parseable JSON. In that reduced
PATH, `codex` and `node` were not present, but the config diagnostics remained
available and still found the user Codex config file.

## Hygiene

- `bash -n scripts/langfuse-observability-doctor.sh`: exit `0`.
- `git diff --check`: exit `0`.
- Secret scan over new run artifacts, the doctor, and setup guide found no raw
  LangFuse key values (`rg` exit `1`, empty output).
