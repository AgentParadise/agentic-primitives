# Results

## Headline

| Probe | Result | Evidence |
|---|---:|---|
| Baseline executable doctor exists | absent | `runs/baseline-search.txt` |
| Treatment doctor emits text and JSON | pass | `runs/doctor-text.txt`, `runs/doctor-json.json` |
| Doctor reports local MacBook setup without secrets | pass | `runs/doctor-json.json`, `runs/doctor-json-local-env.json` |
| Runtime guard remains green | pass | `runs/test-cli-exporters.txt` |
| Hygiene | pass | `runs/test-bash-n.txt`, `runs/test-doctor-json-parse.txt`, `runs/diff-check.txt`, `runs/secret-scan.txt` |

## Baseline

`runs/baseline-search.txt` found LangFuse setup docs and smoke helpers, but no
single executable doctor that checks the official plugin path, runtime env,
JSONL/Syntropic137 fanout, and fallback OTLP noise guard in one secret-safe
report.

## Treatment

Added `scripts/langfuse-observability-doctor.sh`.

Default text mode produced a short setup report in `runs/doctor-text.txt`.
JSON mode produced parseable JSON in `runs/doctor-json.json`.

On this MacBook shell, the doctor reported:

- Claude command present.
- Codex command present.
- Node major `22`, `node22_plus=true`.
- `uv`, `python3`, and `cargo` present.
- Codex tracing plugin configured.
- Codex `plugin_hooks` not detected in scanned config.
- Runtime `LANGFUSE_*` env missing in the default shell.
- File JSONL fanout supported.
- Syntropic137 JSONL fanout supported.
- MCP server present.
- OTLP suppression/force flag supported.
- Focused `cli_exporters` guard test status `pass`.

The local-env run in `runs/doctor-json-local-env.json` loaded the ignored local
LangFuse project env and set `TRACE_TO_LANGFUSE=true`. The report showed only:

- required LangFuse env `set`;
- `required_ready=true`;
- `official_plugin_active=true`;
- guard test `pass`.

It did not print any key values.

## Tests

- `bash -n scripts/langfuse-observability-doctor.sh`: exit `0`.
- `scripts/langfuse-observability-doctor.sh`: exit `0`.
- `scripts/langfuse-observability-doctor.sh --json`: exit `0`.
- JSON parse with `jq`: exit `0`.
- local-env JSON parse with `jq`: exit `0`.
- `cargo test ... cli_exporters`: exit `0`.
- `git diff --check`: exit `0`.
- strict raw LangFuse key scan: no matches (`rg` exit `1`, empty output).

## Notes

This probe intentionally does not call LangFuse or install official plugins.
It is a portable setup/readiness check. Real trace ingestion and queryability
remain covered by the official-plugin real-session and discovery-report
experiments.
