# Verdict

**go**: align the install surface around official LangFuse plugins and keep the
fallback exporter as a deliberate, quieter path.

The experiment supports the current pivot. Official Claude/Codex plugins remain
the right canonical path for rich LangFuse traces. The local agentic-primitives
layer should focus on durable JSONL, Syntropic137 projection, fallback OTLP, and
agent-facing query/feedback tools.

## Hypothesis scorecard

| Prediction | Observed | Score | Evidence |
|---|---|---|---|
| Repo is already aligned on official plugins as canonical, JSONL as safe fanout, and Rust OTLP as fallback. | Correct. ADR/docs/README already encode the boundary. | correct | `runs/repo-setup-surface-audit.md` |
| Setup guide has small drift from current official plugin docs. | Correct. Drift found around Claude config path, runtime requirements, and Codex config precedence. | correct | `runs/official-reference-snapshot.md`, `runs/repo-setup-surface-audit.md` |
| Noise-control contract remains valid after doc alignment. | Correct. Focused CLI exporter tests pass. | correct | `runs/cli-exporters-test.txt` |
| Documentation/config audit can close ambiguity without exporter code changes. | Correct for install-surface ambiguity. No Rust implementation change was needed. | correct | `runs/repo-setup-surface-audit.md` |

## Decision

- Keep official LangFuse Claude/Codex plugins as the canonical rich trace path.
- Keep JSONL and `syntropic_jsonl` fanout available alongside official plugins.
- Keep Rust `langfuse_otlp` as explicit fallback/collector/smoke support.
- Do not claim .9 complete from this run; real marketplace-installed session
  traces for both Claude and Codex still need backend validation.
