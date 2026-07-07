# Results

| Probe | Evidence | Result |
|---|---|---|
| CLI surface | `cargo run --quiet -- langfuse-trace --help` output | Passed: command exposes trace/run id selection, bounded time window, field groups, limit, and API mode. |
| Bounded URL construction | focused Rust test output | Passed: endpoint input normalized to `/api/public/v2/observations`, time bounds and fields URL-encoded; legacy trace URL construction is covered for self-host compatibility. |
| Missing config fail-fast | `runs/missing-config.json`, `runs/missing-config-exit.txt` | Passed: exited 78 and reported only missing `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`. |

## Missing Config Output

```json
{"ok":false,"error":"missing required LangFuse query configuration","missing":["LANGFUSE_BASE_URL","LANGFUSE_PUBLIC_KEY","LANGFUSE_SECRET_KEY"]}
```

## Interpretation

The agent-facing query surface exists locally and is secret-safe. It does not
prove backend queryability because this environment still has no reachable
LangFuse configuration. The real `.9` close gate remains: export to a real
backend, wait for ingestion availability, then run `itmux langfuse-trace`
against the exported trace id or run id and confirm observation rows are
returned.
