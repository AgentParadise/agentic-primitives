# Results

## Headline

| Probe | Observed | Evidence |
|---|---:|---|
| Suppressed runtime OTLP requests with `TRACE_TO_LANGFUSE=true` | `0` | `runs/suppressed/receiver.json` |
| Suppressed runtime local file exporter | `ok`, `7` events | `runs/suppressed/result.json`, `runs/suppressed/events.jsonl` |
| Suppressed runtime Syntropic137 exporter | `ok`, `7` events | `runs/suppressed/result.json`, `runs/suppressed/syntropic-events.jsonl` |
| Forced runtime OTLP requests | `1` | `runs/forced/receiver.json` |
| Forced runtime local file exporter | `ok`, `7` events | `runs/forced/result.json`, `runs/forced/events.jsonl` |
| Forced runtime Syntropic137 exporter | `ok`, `7` events | `runs/forced/result.json`, `runs/forced/syntropic-events.jsonl` |
| Real Claude official-plugin LangFuse trace remains queryable | `97,804` tokens, `$0.1139603`, tool `Read` | `runs/real-langfuse-claude-summary.json` |
| Real Codex official-plugin LangFuse trace remains queryable | `34,445` tokens, `$0.174825`, tool `exec_command` | `runs/real-langfuse-codex-summary.json` |

`runs/headline-summary.json` contains the compact joined view used for the
table above.

## Runtime Suppression

The suppressed condition set `TRACE_TO_LANGFUSE=true` and ran:

```text
itmux claude-transcript --observability-file ... --observability-syntropic-file ... --observability-langfuse
```

without `--observability-langfuse-force`.

The local receiver captured zero requests:

```json
{"request_count": 0}
```

The final result reported only the local fanout exporters:

- `file`: `ok`, `events_exported: 7`
- `syntropic_jsonl`: `ok`, `events_exported: 7`

The emitted local event files each contain seven lines. The canonical file JSONL
contains `tool_start`, `tool_end`, `token_usage`, and `session_end`; the
Syntropic137 projection contains `tool_execution_started`,
`tool_execution_completed`, `token_usage`, and `session_ended`.

## Explicit Force

The forced condition used the same command and environment, plus:

```text
--observability-langfuse-force
```

The local receiver captured exactly one POST:

- path: `/api/public/otel/v1/traces`
- content type: `application/x-protobuf`
- `x-langfuse-ingestion-version: 4`
- `Authorization: Basic [REDACTED]`

The final result reported three exporters:

- `file`: `ok`, `events_exported: 7`
- `syntropic_jsonl`: `ok`, `events_exported: 7`
- `langfuse_otlp`: `ok`, `events_exported: 7`

This proves the fallback Rust OTLP path is still available for explicit smoke,
collector, unsupported-harness, or bridge use.

## Real LangFuse Backend Check

To avoid confusing the local receiver probe with the actual LangFuse
integration proof, this run also re-queried the two known real official-plugin
traces from the local LangFuse Docker Compose backend:

- Claude trace `0e553fc833c71639acd03be9807eb616`:
  `GENERATION`, `SPAN`, and `TOOL` observations; `97,804` total tokens;
  `$0.1139603` calculated cost; `agent_tools.names: ["Read"]`.
- Codex trace `b3d2561d7c0557c12fd427c02a16e2f3`:
  `AGENT`, `GENERATION`, and `TOOL` observations; `34,445` total tokens;
  `$0.174825` calculated cost; `agent_tools.names: ["exec_command"]`.

Those queries used:

```text
itmux langfuse-trace --api legacy-trace --output summary --trace-id <trace>
```

against `http://localhost:3000`, with credentials mapped from the local
LangFuse stack's ignored `.env`.

## Verification

- `cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml cli_exporters -- --nocapture`
  passed. Evidence: `runs/test-cli-exporters.txt`.
- `cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml syntropic_jsonl_exporter_writes_hook_style_events -- --nocapture`
  passed. Evidence: `runs/test-syntropic-exporter-rerun.txt`.
- `git diff --check` passed. Evidence: `runs/diff-check.txt`.
- Final unredacted LangFuse key scan found no matches. Evidence:
  `runs/secret-scan-final.txt`, `runs/secret-scan-final-exit.txt`.

Cargo still prints non-fatal APSS template diagnostics for `{{slug}}`
dependency skeleton manifests before tests finish successfully. That is
pre-existing dependency output and not related to this probe.
