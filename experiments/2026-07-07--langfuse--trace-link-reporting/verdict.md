# Verdict

**Go for trace-link reporting as a local `.9` slice; no-go for claiming real
LangFuse visibility.**

The local exporter now reports a deterministic LangFuse trace URL when project
id metadata is available, while keeping project id optional for ingestion. This
is enough for `AgentRunResult.observability` to carry a user-facing trace link
once real backend ingestion succeeds.

| Hypothesis | Observation | Verdict | Evidence |
| --- | --- | --- | --- |
| Optional project id is accepted from config/env | Contract round-trip and resolver test pass with defaults and env lookup | correct | `runs/contract-roundtrip.txt`, `runs/langfuse-tests.txt` |
| Missing project id does not fail export | Resolver treats project id as optional; missing-env test still reports only required key failures | correct | `runs/langfuse-tests.txt` |
| Successful local receiver export reports a LangFuse UI trace URL | Local receiver transport test asserts one `/project/project-123/traces/<32_hex>` link | correct | `runs/langfuse-tests.txt` |
| Ingest endpoint is not exposed as the human link | `target` remains OTLP traces endpoint; `links` comes from `trace_link()` | correct | code under test, `runs/full-test.txt` |

## Next Decision

- Keep `.9` open until
  `experiments/2026-07-07--langfuse--otel-ingestion-smoke` passes against
  LangFuse Cloud or the planned Mac Mini self-host.
- The next real-backend smoke must prove the reported trace id is visible or
  queryable in LangFuse, not merely that the local local receiver accepted transport.
