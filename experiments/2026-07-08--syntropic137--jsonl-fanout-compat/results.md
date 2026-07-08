# Results

## Headline

| Probe | Evidence | Result |
|---|---|---|
| Parser surface | `runs/syntropic-parser-surface.md` | Syntropic137 HookWatcher expects top-level `event_type`, `session_id`, `timestamp`; `HOOK_EVENT_MAP` does not currently include `token_usage`. |
| Baseline AgentRunEvent JSONL | `runs/baseline-agent-run-events.jsonl`, `runs/baseline-parse.json` | Parsed count `0`: current canonical `AgentRunEvent` JSONL is not direct-compatible with Syntropic137 HookWatcher. |
| Control hook-style JSONL | `runs/control-hook-events.jsonl`, `runs/control-parse.json` | Parsed count `4`: session/tool hook-style rows are consumed; `token_usage` is skipped by current Syntropic137 map. |
| Treatment exporter tests | `runs/treatment-test.txt`, `runs/treatment-test-exit.txt` | Passed: `syntropic_jsonl` exporter writes hook-style rows; contract round-trip passes; CLI builder includes exporter. |
| Treatment parse check | `runs/treatment-syntropic-events.jsonl`, `runs/treatment-parse.json` | Parsed count `2`: Syntropic137 consumes treatment session/tool rows and skips emitted `token_usage` row. |
| CLI exporter tests | `runs/cli-exporters-test.txt`, `runs/cli-exporters-test-exit.txt` | Passed: existing file/LangFuse guard tests plus Syntropic137 CLI exporter test pass. |
| Hygiene | `runs/fmt-check.txt`, `runs/fmt-check-exit.txt`, `runs/diff-check.txt`, `runs/diff-check-exit.txt` | Passed. |

## Baseline

The baseline confirmed the hypothesis. Feeding representative
agentic-primitives `AgentRunEvent` JSONL into Syntropic137's existing
`HookWatcher.read_existing()` returned:

```json
{"parsed_count": 0}
```

Reason: Syntropic137's hook parser looks for `event_type` or `handler`.
Canonical `AgentRunEvent` rows use `type`, `run_id`, `seq`, `ts`, and payload
fields.

## Control

The same watcher parsed hook-style session/tool rows:

- `session_started`
- `tool_execution_started`
- `tool_execution_completed`
- `session_ended`

The control included a `token_usage` row, but Syntropic137's current
`HOOK_EVENT_MAP` does not include `token_usage`, so that row was skipped.

## Treatment

Implemented a separate `syntropic_jsonl` exporter and
`--observability-syntropic-file` CLI flag.

This preserves all existing paths:

- canonical `file` exporter still writes full `AgentRunEvent` JSONL;
- `langfuse_otlp` remains fallback/collector/unsupported-harness export;
- official LangFuse plugins remain canonical for rich Claude/Codex traces;
- Syntropic137 gets a local hook-style projection without enabling noisy
  fallback LangFuse traces.

Focused Rust tests passed:

- `run::observability::tests::syntropic_jsonl_exporter_writes_hook_style_events`
- `cli_tests::cli_exporters_include_syntropic_jsonl_when_configured`
- `observability_syntropic_jsonl_exporter_round_trips_with_typed_config`

The generated schema includes `syntropic_jsonl`.

## Known Limitation

The new exporter emits `token_usage` rows for forward compatibility, but
Syntropic137's current HookWatcher skips them. Until Syntropic137 adds
`token_usage` to `HOOK_EVENT_MAP`, its transcript/OTLP lanes remain the token
and cost source. This experiment closes the session/tool JSONL fanout gap, not
the Syntropic137 token projection gap.
