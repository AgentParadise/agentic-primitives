# Results

| Probe | Evidence | Result |
|---|---|---|
| Contract round-trip | `runs/contract.txt`, `runs/contract-exit.txt` | Passed: `observability_langfuse_otlp_exporter_round_trips_with_env_refs` exited 0. |
| Fanout config validation | `runs/fanout.txt`, `runs/fanout-exit.txt` | Passed: endpoint derivation, Basic auth derivation, and missing-env redaction tests exited 0. |
| Schema and hygiene | `runs/schema-grep.txt`, `runs/schema-grep-exit.txt`, `runs/fmt.txt`, `runs/fmt-exit.txt`, `runs/clippy.txt`, `runs/clippy-exit.txt` | Passed: schema contains `langfuse_otlp`; fmt and clippy exited 0. |

## Key Data

| Field | Value |
|---|---|
| Contract test exit | 0 |
| Fanout test exit | 0 |
| Schema grep exit | 0 |
| `langfuse_otlp` schema line | `agent-run-spec.schema.json:195` |
| Fmt exit | 0 |
| Clippy exit | 0 |

## Classification

The Rust contract now accepts typed `langfuse_otlp` exporter configuration and
the fanout reports missing LangFuse env as an explicit failed exporter report.
Real OTLP transport remains intentionally disabled until the real LangFuse
ingestion smoke passes.
