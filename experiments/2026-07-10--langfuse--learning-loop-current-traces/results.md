# LangFuse Learning Loop Current Traces

Date: 2026-07-10

## Question

Can the current local LangFuse backend support agent learning loops across both
Claude and Codex traces?

## Method

- Loaded the local LangFuse Docker Compose credentials from
  `.agentic/langfuse/langfuse/.env`.
- Queried trace discovery with `itmux langfuse-traces` for all traces and
  harness-specific views.
- Queried representative current traces with `itmux langfuse-trace --api
  legacy-trace --include-scores --output summary`.
- Wrote two trace-scoped feedback scores with `itmux langfuse-score`.
- Read scores back with `itmux langfuse-scores`.
- Exercised the MCP learning-loop implementation directly through
  `agentic_langfuse_learning_loop_report` internals for all recent traces and a
  Codex-filtered report.

Raw evidence is in `raw/`.

## Results

Trace discovery returned 36 backend traces over 2 pages.

| Harness | Count | Cost | Observations | Missing list-level model |
|---|---:|---:|---:|---:|
| Claude | 22 | 3.639436 USD | 426 | 14 |
| Codex | 8 | 0.592478 USD | 47 | 4 |
| Unknown/noisy historical rows | 6 | 0 USD | 51 | 6 |

Top discovered cost traces were all Claude traces:

| Trace | Harness | Cost | Observations |
|---|---|---:|---:|
| `4cbfce7cab007d5b2cef2a1d84802984` | Claude | 0.732671 USD | 59 |
| `69c7a463e8688b2e75688592302533f4` | Claude | 0.660375 USD | 73 |
| `82ae1ad31d4e6c0847b1eeae9703b6a5` | Claude | 0.586882 USD | 46 |
| `53a78022e53d9abd2ef5de95c9add4f3` | Claude | 0.395196 USD | 24 |

Representative current Claude trace:

- Trace: `53a78022e53d9abd2ef5de95c9add4f3`
- Model recovered from detail view: `claude-sonnet-5`
- Usage: 1,348,312 total tokens
- Cost: 0.395196 USD
- Generations: 12
- Agent-visible tools: 11 successful calls, mostly `Bash`, plus
  `AskUserQuestion`

Representative current Codex trace:

- Trace: `b928a86e0c44784896a2224778c339c4`
- Model recovered from detail view: `gpt-5.5`
- Usage: 33,950 total tokens
- Cost: 0.171775 USD
- Generations: 2
- Agent-visible tools: 1 successful `exec_command`

Score write-back works:

- Claude score id: `3c5a719f-844d-4837-971a-3bfd4bef7652`
- Codex score id: `20e41eaf-6464-4d0f-be38-dba101301369`
- `langfuse-scores --score-ids ...` reads both scores back.
- `langfuse-scores --trace-id ...` reads the Codex score back.
- `langfuse-scores --name agentic.learning_loop_trace_quality` reads both
  scores back.

MCP learning-loop report works:

- Recent unfiltered report drilled into 8 traces, all Claude due current sort
  order. It aggregated 4,545,255 tokens, 1.688999 USD, 59 generations, 61
  successful agent-visible tool calls, and zero failed tools.
- Codex-filtered report drilled into 4 Codex traces. It aggregated 100,270
  tokens, 0.506575 USD, 6 generations, 4 successful agent-visible tool calls,
  and zero failed tools.

## Insights

The integration is now good enough for learning loops. It can answer:

- Which traces cost the most?
- Which harness/provider/model produced the trace?
- How many generation calls happened?
- What were the token and cost totals?
- Which agent-visible tools ran?
- Did agent-visible tools fail?
- Which traces have evaluator feedback scores?

The remaining gaps are concrete and fixable:

1. Trace-list rows often have `model: null`, even when trace detail contains
   generation model data. Discovery should optionally enrich model/cost/token
   fields from detail rows or document that list-level model is best-effort.
2. Official plugin tool observations are end-only in current summaries
   (`start_count: 0`, positive `end_count`). That is acceptable for success
   accounting, but start/end pairing should not be interpreted as complete
   lifecycle coverage.
3. Score readback with `trace_id + name` returned zero rows, while trace-only,
   name-only, and score-id reads worked. The CLI/MCP path should avoid relying
   on combined backend filters and instead fetch by trace or name, then filter
   locally.
4. The older Rust OTLP-era traces are visibly less useful/noisier than the
   official plugin traces. Keeping LangFuse writes on the official plugin path
   is the right architecture.

## Verdict

Pass with follow-up fixes. LangFuse is now usable as the learning-loop store for
both Claude and Codex on this local backend. The next improvement should be a
small read-side normalization pass for discovery model enrichment and robust
score filtering.
