# Verdict

**Go for exporter-isolated fanout.**

The fanout primitive degrades per exporter: a misconfigured LangFuse exporter
does not prevent local file observability from receiving the complete normalized
event stream.

| Hypothesis | Observation | Verdict | Evidence |
| --- | --- | --- | --- |
| `itmux codex-exec` can run with file and LangFuse exporters together | Runtime probe exited 0 with both flags | correct | `runs/runtime-exit.txt`, `runs/result.json` |
| Missing LangFuse env reports failed LangFuse exporter | Result contains `langfuse_otlp` status `failed` | correct | `runs/result.json` |
| File exporter still writes and reports every event | File report is `ok` with `events_exported = 6` | correct | `runs/result.json`, `runs/events.jsonl` |
| Stdout and file exporter match | Event types and seq values match exactly | correct | `runs/inspection-summary.txt` |

## Next Decision

- `.6` has stronger evidence for the reusable fanout primitive: backend
  failures are isolated and do not destroy local observability.
- `.9` can keep LangFuse as an optional backend during setup because missing
  config does not break the file fallback.
