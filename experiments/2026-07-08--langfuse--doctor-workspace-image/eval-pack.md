# Eval Pack

This eval pack is frozen after the hypothesis commit.

## Probe A: Image Availability

Run:

```bash
docker image inspect agentic-workspace-interactive-tmux:latest
```

Evidence:

- `runs/image-inspect.json`
- `runs/image-inspect.err`
- `runs/image-inspect-exit.txt`

## Probe B: Doctor Inside Workspace Image

If Probe A passes, run:

```bash
docker run --rm \
  -v "$PWD:/repo:ro" \
  -w /repo \
  agentic-workspace-interactive-tmux:latest \
  bash /repo/scripts/langfuse-observability-doctor.sh --json --no-tests
```

Evidence:

- `runs/image-doctor.json`
- `runs/image-doctor.err`
- `runs/image-doctor-exit.txt`

## Probe C: Parse and Assertions

Parse `runs/image-doctor.json` with `jq` and assert the key portable-readiness
fields are true.

Evidence:

- `runs/image-doctor-parse.txt`
- `runs/image-doctor-parse-exit.txt`

## Probe D: Hygiene

Run `git diff --check` and a strict raw LangFuse key scan over changed files and
experiment artifacts.

Evidence:

- `runs/diff-check.txt`
- `runs/diff-check-exit.txt`
- `runs/secret-scan.txt`
- `runs/secret-scan-exit.txt`

## Verdict Rules

Use verdict `go` if the image exists and the doctor runs inside it with the
expected fanout/MCP/noise-guard readiness fields.

Use verdict `inconclusive` if the image is absent locally or Docker is
unavailable.

Use verdict `no-go` if the image exists but the doctor cannot run in it or emits
false readiness for repo-local fanout support.
