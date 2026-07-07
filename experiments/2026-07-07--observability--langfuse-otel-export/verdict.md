# Verdict

**Go for current exporter path; no-go for claiming real LangFuse backend
visibility until the OTLP ingestion smoke passes.**

The historical run correctly identified that `.9` needed `.6` to provide a
typed exporter interface. That part is now implemented. The current rerun shows
the CLI can instantiate file plus `langfuse_otlp` exporters and preserve local
JSONL observability. It still cannot create a real LangFuse trace in this shell
because no LangFuse env/credentials are present.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| LangFuse/OTEL exporter creates one trace per run | Exporter exists, but real trace not created because `LANGFUSE_BASE_URL` is missing | partial | `runs/current/result.json`. |
| Trace contains child observations for run phases | Local event stream exists; backend trace not observed | partial | `runs/current/stdout.jsonl`, `runs/current/events.jsonl`. |
| Result report includes a usable LangFuse trace link | No link because export failed before backend ingestion | wrong | `runs/current/result.json`. |

## Design Impact

- `.6` now has the typed exporter/fanout substrate this experiment originally
  required.
- `.9` has local config, transport, trace-link, CLI setup, and fail-fast
  evidence.
- `.9` still cannot close until real LangFuse ingestion, trace visibility, and
  trace-link resolution are observed against Cloud or the Mac Mini self-host.
