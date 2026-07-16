# Eval Pack

## Probe A: Baseline

Capture:

```bash
scripts/langfuse-observability-doctor.sh --json --no-tests
awk 'NR>=45 && NR<=55 {print NR ":" $0}' "$HOME/.codex/config.toml"
```

Save stdout, stderr, and exit status under `runs/baseline-*`.

## Probe B: Remediation

Apply the minimal user-config edit:

```toml
[features]
plugin_hooks = true
```

Do not add LangFuse credentials. Do not edit repo-local Codex config.

Save a redacted diff or focused line excerpt under `runs/remediation-*`.

## Probe C: Treatment Doctor

Run:

```bash
scripts/langfuse-observability-doctor.sh --json --no-tests
scripts/langfuse-observability-doctor.sh --no-tests
```

Save stdout, stderr, and exit status under `runs/treatment-*`.

Pass requires Codex `plugin_hooks_enabled=true`,
`tracing_plugin_configured=true`, and `config.ready=true`.

## Probe D: Hygiene

Run:

```bash
git status --short
git diff --check
rg -n 'pk-lf-[A-Za-z0-9_-]+|sk-lf-[A-Za-z0-9_-]+' experiments/2026-07-08--langfuse--codex-plugin-hooks-remediation/runs
```

Pass requires no raw key matches and no unexpected repo changes.

## Verdict Rules

Use `go` if the doctor flips Codex readiness true with only the user-config
hook setting change.

Use `no-go` if the doctor still reports hooks false or requires additional
undocumented Codex setup.

Use `inconclusive` if the user config cannot be safely edited or verified.
