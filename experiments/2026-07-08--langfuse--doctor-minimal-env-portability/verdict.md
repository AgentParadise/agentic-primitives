# Verdict

## Decision

go

The setup doctor is now more portable for VPS and Docker workspace surfaces.
The baseline proved the first version still assumed `rg`; treatment removed
that dependency and added `--no-tests` so minimal shells can still produce a
useful readiness report without Cargo.

## Evidence

- Baseline stderr: `runs/baseline-minimal-json.err`.
- Treatment minimal JSON: `runs/treatment-minimal-json.json`.
- Treatment default JSON: `runs/treatment-default-json.json`.
- Syntax/diff/secret hygiene: `runs/test-bash-n.txt`,
  `runs/diff-check.txt`, `runs/secret-scan.txt`.

## Hypothesis scorecard

| Prediction | Observed | Score | Notes |
|---|---|---:|---|
| Current doctor depends on `rg` in minimal PATH | Confirmed | correct | Baseline emitted `rg: command not found` and false fanout negatives. |
| `grep -E` plus `--no-tests` improves portability | Confirmed | correct | Minimal treatment exited `0`, no stderr, JSON parsed. |
| Minimal mode still reports fanout/MCP support | Confirmed | correct | file JSONL, Syntropic137 JSONL, and MCP presence all true. |
| Default MacBook mode keeps cargo-backed guard test | Confirmed | correct | Default JSON reports `focused_test_status=pass`. |

## Follow-up

- A future Docker-image-level probe can run this same doctor inside the actual
  interactive-tmux image. This experiment covered minimal shell portability
  without requiring image rebuilds.
