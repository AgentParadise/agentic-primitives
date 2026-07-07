# Verdict

**Go for config/fail-fast slice; no-go for claiming LangFuse export.**

This validates the next `.9` implementation layer after the mock OTLP preflight:
the Rust contract can carry LangFuse exporter config safely, the schema exposes
it, and missing credentials are surfaced through `ObservabilityBundle` instead
of silent success or stdout pollution.

## Hypothesis Scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Typed config round-trips | Contract test passed | correct | `runs/contract.txt` |
| Schema includes `langfuse_otlp` | Schema grep found the variant | correct | `runs/schema-grep.txt` |
| Missing env reports redacted failure | Fanout missing-env test passed | correct | `runs/fanout.txt` |
| Endpoint/auth derivation is unit-testable | Endpoint/auth tests passed | correct | `runs/fanout.txt` |

## Design Impact

- `.9` has a typed exporter configuration surface now.
- Secrets stay as environment-variable references in the spec; values are read
  at runtime and are not included in config errors.
- The next implementation step is real OTLP transport and semantic span
  encoding, validated first against a mock receiver and then against LangFuse.
