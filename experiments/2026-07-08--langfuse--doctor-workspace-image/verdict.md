# Verdict

## Decision

go

The portable LangFuse setup doctor works inside the actual
`agentic-workspace-interactive-tmux:latest` Docker workspace image when the repo
is mounted read-only and tests are disabled. This moves the setup-readiness
claim from "minimal shell likely works" to "the current Docker workspace image
surface can run the preflight."

## Evidence

- Image inspect: `runs/image-inspect.json`.
- Doctor output: `runs/image-doctor.json`.
- JSON assertion: `runs/image-doctor-parse.txt`.
- Secret scan: `runs/secret-scan.txt`.

## Hypothesis scorecard

| Prediction | Observed | Score | Notes |
|---|---|---:|---|
| Doctor runs in interactive-tmux image with bash/grep/coreutils/repo files | Confirmed | correct | `docker run ... doctor --json --no-tests` exited `0`. |
| Image report marks fanout/MCP/noise guard fields true | Confirmed | correct | `jq -e` assertion passed. |
| Image run does not require Cargo, Docker inside Docker, `rg`, or live LangFuse credentials | Confirmed | correct | Cargo absent in image; tests skipped explicitly; env missing reported as missing. |
| Missing image should produce inconclusive, not false pass | Not exercised | partial | Image existed locally, so the missing-image path was not needed. |

## Follow-up

- A future target-machine deployment probe should run the same command on the
  Mac Mini or VPS once those hosts exist.
