# Eval Pack

This eval pack is frozen after the hypothesis commit.

## Probe A: Baseline Minimal PATH

Run current doctor with:

```bash
env -i HOME="$HOME" PATH="/bin:/usr/bin" bash scripts/langfuse-observability-doctor.sh --json
```

Evidence:

- `runs/baseline-minimal-json.json`
- `runs/baseline-minimal-json.err`
- `runs/baseline-minimal-json-exit.txt`

## Probe B: Treatment

Patch `scripts/langfuse-observability-doctor.sh` so it:

- does not require `rg`;
- supports `--no-tests`;
- reports an explicit skip reason when tests are disabled.

Evidence:

- source diff

## Probe C: Treatment Minimal PATH

Run:

```bash
env -i HOME="$HOME" PATH="/bin:/usr/bin" bash scripts/langfuse-observability-doctor.sh --json --no-tests
```

Evidence:

- `runs/treatment-minimal-json.json`
- `runs/treatment-minimal-json.err`
- `runs/treatment-minimal-json-exit.txt`
- `runs/treatment-minimal-json-parse.txt`

## Probe D: Default Local Mode

Run:

```bash
scripts/langfuse-observability-doctor.sh --json
```

Evidence:

- `runs/treatment-default-json.json`
- `runs/treatment-default-json-exit.txt`
- focused guard test status in the JSON

## Probe E: Hygiene

Run:

```bash
bash -n scripts/langfuse-observability-doctor.sh
git diff --check
rg -n 'sk-lf-[A-Za-z0-9]{8,}|pk-lf-[A-Za-z0-9]{8,}' ...
```

Evidence:

- `runs/test-bash-n.txt`
- `runs/diff-check.txt`
- `runs/secret-scan.txt`

## Verdict Rules

Use verdict `go` if minimal mode works without `rg`, default mode still keeps
the cargo-backed guard test, and artifacts remain secret-safe.

Use verdict `no-go` if the doctor still depends on developer-only tools.

Use verdict `inconclusive` if the minimal shell lacks `bash`.
