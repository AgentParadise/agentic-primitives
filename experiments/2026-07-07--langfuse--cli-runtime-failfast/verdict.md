# Verdict

**Go for runtime fail-fast through the CLI path; no-go for real LangFuse
visibility.**

The actual `itmux codex-exec --observability-langfuse` path behaves correctly
when LangFuse env is missing: the agent run can still succeed, stdout remains
machine-parseable event JSONL, and the final result reports an actionable
failed LangFuse exporter.

| Hypothesis | Observation | Verdict | Evidence |
| --- | --- | --- | --- |
| Synthetic successful `codex exec --json` run exits successfully | Runtime probe exited 0 and result success was true | correct | `runs/runtime-exit.txt`, `runs/result.json` |
| Missing LangFuse env reports failed exporter | Result contains `langfuse_otlp` status `failed` | correct | `runs/result.json` |
| Failure names missing env and avoids secret values | Error names `LANGFUSE_BASE_URL`; no secret values are present | correct | `runs/result.json` |
| Stdout remains valid event JSONL | Six stdout lines parse as `AgentRunEvent` with seq `0..5` | correct | `runs/stdout.jsonl`, `runs/inspection-summary.txt` |

## Next Decision

- Keep `.9` open until a real LangFuse deployment accepts the OTLP payload and
  exposes a discoverable/queryable trace.
- This result means missing or incomplete setup is safe to expose to users:
  it fails in `ObservabilityBundle`, not by breaking the run or stdout stream.
