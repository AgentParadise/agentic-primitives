# Eval Pack

This eval pack is frozen after the hypothesis commit.

## Probe A: Baseline

Search the repository for an existing executable LangFuse setup doctor.

Evidence:

- `runs/baseline-search.txt`
- `runs/baseline-search-exit.txt`

## Probe B: Treatment Command

Add `scripts/langfuse-observability-doctor.sh`.

Required behavior:

- `--json` prints JSON only.
- default mode prints a short text report.
- no command output includes raw LangFuse public or secret key values.
- exits `0` when it can produce a report, even if optional tools are missing.
- includes explicit status for official Claude plugin surface, official Codex
  plugin surface, runtime LangFuse env, JSONL fanout, Syntropic137 fanout, and
  Rust OTLP noise guard.

Evidence:

- source diff
- `runs/doctor-text.txt`
- `runs/doctor-json.json`
- `runs/doctor-*-exit.txt`

## Probe C: Validation

Run:

```bash
bash -n scripts/langfuse-observability-doctor.sh
scripts/langfuse-observability-doctor.sh --json
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml cli_exporters -- --nocapture
git diff --check
```

Evidence:

- `runs/test-bash-n.txt`
- `runs/test-doctor-json-parse.txt`
- `runs/test-cli-exporters.txt`
- `runs/diff-check.txt`

## Probe D: Hygiene

Scan the changed source and experiment artifacts for raw LangFuse key patterns.

Evidence:

- `runs/secret-scan.txt`
- `runs/secret-scan-exit.txt`

## Verdict Rules

Use verdict `go` if the doctor is executable, parseable, secret-safe, and
captures all ownership checks without requiring a live LangFuse backend.

Use verdict `no-go` if the doctor prints secrets or cannot distinguish
official-plugin rich tracing from fallback OTLP.

Use verdict `inconclusive` if the environment cannot run shell scripts or the
repo lacks the CLI/source surfaces needed for static checks.
