# LangFuse Doctor Workspace Image

## Question

Does the portable LangFuse observability doctor run inside the actual
`agentic-workspace-interactive-tmux:latest` Docker workspace image with the repo
mounted read-only, so Docker workspace operators can verify official-plugin
rich tracing, JSONL/Syntropic137 fanout, and OTLP noise-control readiness from
inside the workspace surface?

## Hypothesis

1. The current `scripts/langfuse-observability-doctor.sh --json --no-tests`
   should run inside the interactive-tmux image because it now only requires
   bash, grep, standard core utilities, and repo-local files.
2. The image-level run should report JSONL fanout support, Syntropic137 fanout
   support, MCP server presence, and OTLP suppression/force support as true.
3. The image-level run should not require Cargo, Docker, `rg`, or live
   LangFuse credentials.
4. If the image is absent locally, the useful result is an inconclusive verdict
   with precise build instructions, not a false pass.

## Setup

- Repository: `agentic-primitives`
- Branch: `feat/observability-exporter-primitive`
- Image under test: `agentic-workspace-interactive-tmux:latest`
- Prior experiments:
  - `experiments/2026-07-08--langfuse--portable-setup-doctor`
  - `experiments/2026-07-08--langfuse--doctor-minimal-env-portability`

## Conditions

1. Inspect whether `agentic-workspace-interactive-tmux:latest` exists locally.
2. If present, run the doctor inside the image with the repo mounted read-only:
   `bash /repo/scripts/langfuse-observability-doctor.sh --json --no-tests`.
3. Parse the JSON on the host.
4. Scan artifacts for raw LangFuse key patterns.

## Expected Signals

- Docker image inspect exits `0`, or the verdict records a precise missing-image
  blocker.
- Image doctor run exits `0`.
- Image doctor JSON parses with `jq`.
- Fanout and MCP fields are true.
- Guard fields are true with `focused_test_status="skipped"` and
  `focused_test_detail="tests disabled by --no-tests"`.
- No raw `pk-lf-*` or `sk-lf-*` values appear in artifacts.
