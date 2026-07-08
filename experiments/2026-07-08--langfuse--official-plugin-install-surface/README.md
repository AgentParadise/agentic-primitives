# Official Plugin Install Surface

## Question

Does the current agentic-primitives LangFuse setup surface match the official
Claude Code and Codex plugin install/config contracts closely enough that a new
MacBook, VPS, or Docker workspace can use the official plugins as the
canonical rich trace path without accidentally enabling duplicate Rust OTLP
export?

## Hypothesis

1. The repo is already aligned on the architecture: official LangFuse plugins
   are canonical for Claude/Codex rich traces, JSONL fanout remains safe to run
   in parallel, and Rust OTLP is fallback/collector-only by default.
2. The setup guide will have small drift from the current official plugin
   docs, especially around Claude marketplace configuration, runtime
   requirements, and Codex config precedence.
3. The noise-control contract will remain valid after doc alignment:
   `TRACE_TO_LANGFUSE=true` suppresses fallback `langfuse_otlp` while keeping
   file and Syntropic137 JSONL exporters available.
4. A focused documentation/config audit can close the install-surface ambiguity
   without changing the exporter implementation.

## Setup

- Repository: `agentic-primitives`
- Branch: `feat/observability-exporter-primitive`
- Official references:
  - <https://github.com/langfuse/Claude-Observability-Plugin>
  - <https://langfuse.com/integrations/developer-tools/claude-code>
  - <https://github.com/langfuse/codex-observability-plugin>
  - <https://langfuse.com/integrations/developer-tools/codex>

## Conditions

1. Baseline: inspect current repo docs and CLI help surfaces.
2. Treatment: compare them to the official references above and patch only
   install/config wording if needed.
3. Verification: run focused docs/search checks plus existing CLI exporter
   tests that prove the single-rich-exporter guard still holds.

## Expected Signals

- `results.md` cites exact run artifacts under `runs/`.
- Any doc drift is described as install/config drift, not as a failure of the
  architecture pivot.
- If code changes are unnecessary, the verdict should say so explicitly.
