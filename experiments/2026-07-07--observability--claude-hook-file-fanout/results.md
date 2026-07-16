# Results

| Probe | Evidence | Result |
|---|---|---|
| Baseline file fanout | `runs/baseline-stdout.jsonl`, `runs/baseline-events.jsonl`, `runs/baseline-result.json`, `runs/summary.json` | File fanout worked: 11 stdout events and 11 exported events. Run itself failed with Claude `API Error: 401`. |
| Claude plugin hook fanout | `runs/treatment-stdout.jsonl`, `runs/treatment-events.jsonl`, `runs/treatment-result.json`, `runs/summary.json` | Plugin path was passed as `claude --plugin-dir /workspace/plugins/observability`, but output still contained only driver-level events. Run failed with Claude `API Error: 401`. |

## Counts

| Probe | Exit | Stdout events | Exported events | Session events | Tool events | Exporter status | Exporter count |
|---|---:|---:|---:|---:|---:|---|---:|
| Baseline | 3 | 11 | 11 | 1 | 10 | `ok` | 11 |
| Treatment | 3 | 11 | 11 | 1 | 10 | `ok` | 11 |

## Observations

- The file exporter mirrors stdout event JSONL exactly for driver-level
  `tool_start`, `tool_end`, and `session_end` events.
- `AgentRunResult.observability.exporters[0].events_exported` matches the file
  line count in both conditions.
- Relative exporter paths produce relative links in the result bundle, not
  `file://` links.
- Claude credential transfer/auth is not healthy in this environment: both
  runs reached Claude Code, then failed with an Anthropic 401.
- The treatment proves the recipe path can launch Claude with the plugin dir,
  but does not prove hook-derived lifecycle/tool observability because the
  agent failed before useful hook activity was visible.
