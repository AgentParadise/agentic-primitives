# Eval Pack

## Probe A: Baseline Doctor JSON

Run:

```bash
scripts/langfuse-observability-doctor.sh --json --no-tests
```

Save stdout, stderr, and exit status under `runs/baseline-*`.

Pass condition: JSON parses and shows the current Codex hook/config state.

## Probe B: Treatment Doctor JSON

After the doctor patch, run:

```bash
scripts/langfuse-observability-doctor.sh --json --no-tests
```

Save stdout, stderr, and exit status under `runs/treatment-*`.

Pass condition: JSON parses and contains Codex config diagnostics plus
remediation guidance without credential values.

## Probe C: Treatment Text

Run:

```bash
scripts/langfuse-observability-doctor.sh --no-tests
```

Save stdout, stderr, and exit status under `runs/treatment-text-*`.

Pass condition: text names Codex plugin hook status and remediation guidance.

## Probe D: Minimal Shell

Run:

```bash
env -i HOME="$HOME" PATH="/bin:/usr/bin" bash scripts/langfuse-observability-doctor.sh --json --no-tests
```

Save stdout, stderr, and exit status under `runs/minimal-*`.

Pass condition: exit 0, stderr empty, JSON parses, and Codex config diagnostics
remain present.

## Probe E: Hygiene

Run:

```bash
bash -n scripts/langfuse-observability-doctor.sh
git diff --check
rg -n 'pk-lf-[A-Za-z0-9_-]+|sk-lf-[A-Za-z0-9_-]+' experiments/2026-07-08--langfuse--codex-plugin-hooks-doctor/runs scripts/langfuse-observability-doctor.sh docs/guides/langfuse-observability-setup.md
```

Pass condition: shell syntax and diff checks pass; secret scan has no raw key
matches except intentionally redacted/documentation placeholders if any.

## Verdict Rules

Use `go` if the doctor becomes actionable and remains portable/secret-safe.

Use `no-go` if the doctor still only reports a boolean, fails in minimal mode,
or risks leaking credentials.

Use `inconclusive` if local Codex config cannot be inspected enough to score
the treatment.
