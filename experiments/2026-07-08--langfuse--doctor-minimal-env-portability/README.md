# LangFuse Doctor Minimal Env Portability

## Question

Can `scripts/langfuse-observability-doctor.sh` run in a minimal Mac/VPS/Docker
shell where developer conveniences such as `rg` and `cargo` may be absent,
while still reporting official-plugin readiness, JSONL/Syntropic137 fanout, and
OTLP noise-guard status without leaking secrets?

## Hypothesis

1. The current doctor likely depends on `rg` because it was written in a repo
   where `rg` is always available; a minimal PATH without `rg` will either fail
   or emit stderr noise and weak false negatives.
2. Replacing `rg` usage with standard `grep -E` checks and adding an explicit
   `--no-tests` mode will make the doctor more portable for VPS and Docker
   workspaces while keeping the default local developer mode strong.
3. In minimal mode, the doctor should still report `file_jsonl_supported=true`,
   `syntropic_jsonl_supported=true`, and `mcp_server_present=true` from
   repo-local files.
4. In default mode on this MacBook, the doctor should continue to run the
   focused `cli_exporters` test and report `focused_test_status=pass`.

## Setup

- Repository: `agentic-primitives`
- Branch: `feat/observability-exporter-primitive`
- Prior experiment:
  `experiments/2026-07-08--langfuse--portable-setup-doctor`

## Conditions

1. Baseline: run the current doctor with a minimal PATH that omits `rg` and
   cargo, preserving only standard shell utilities.
2. Treatment: remove the `rg` dependency and add `--no-tests`.
3. Re-run the doctor with the same minimal PATH and `--json --no-tests`.
4. Re-run default doctor mode on this MacBook.
5. Run syntax, JSON parse, diff, and secret-scan hygiene.

## Expected Signals

- Baseline either fails, emits dependency noise, or reports weaker evidence.
- Treatment minimal JSON exits `0`, parses with `jq`, and reports:
  - fanout support true;
  - MCP present true;
  - focused test status `skipped` with an explicit no-tests reason.
- Default mode still reports focused test status `pass` when cargo is present.
- No raw LangFuse keys appear in artifacts.
