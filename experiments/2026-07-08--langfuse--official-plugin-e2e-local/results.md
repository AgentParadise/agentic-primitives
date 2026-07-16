# Results

## Headline

| Probe | Result | Evidence |
| --- | --- | --- |
| Local LangFuse readiness | Pass | `runs/readiness.txt` |
| Official Claude hook fixture export | Pass | `runs/claude-summary.md`, `runs/claude-trace-shape.json`, `runs/claude-trace-full.json` |
| Official Codex hook fixture export | Pass | `runs/codex-summary.md`, `runs/codex-trace-shape.json`, `runs/codex-trace-full.json`, `runs/codex-sidecar.txt` |
| Noise-control check | Pass | `runs/noise-control.md` |

## Probe A: Local LangFuse Readiness

Local LangFuse web returned HTTP 200 at `http://localhost:3000`, and the
ignored local `.env` contained the project id plus public/secret key variables.
The run artifacts record only `set`/`missing` status, not key values.

## Probe B: Official Claude Hook Fixture Export

The official Claude hook exported the fixture transcript successfully.

Observed:

- hook exit `0`
- trace id `76a54f7c977ae138c22ebae34b05e047`
- trace environment `official-plugin-e2e-local`
- root input present
- root output present
- observation types: `SPAN`, `GENERATION`, `TOOL`
- semantic tool observation: `Tool: Read`
- two generation observations: `LLM Call 1`, `LLM Call 2`

The fixture does not include nonzero token usage, so cost is zero. That is a
fixture limitation, not an exporter failure.

## Probe C: Official Codex Hook Fixture Export

The official Codex hook exported the fixture rollout successfully.

Observed:

- hook exit `0`
- sidecar present with completed turn recorded
- trace id `6905cfb7d1b969a0214e613383748ce7`
- trace environment `official-plugin-e2e-local`
- root input present
- root output present
- observation types: `AGENT`, `GENERATION`, `TOOL`
- semantic tool observation: `exec_command`
- two generation observations named `gpt-5.4`
- usage details present:
  - generation 1: `input=100`, `output=20`, `total=120`
  - generation 2: `input=150`, `output=30`, `total=180`
- total cost reported by LangFuse: `0.001374999999`

## Probe D: Noise-Control Check

No Rust OTLP exporter command was run. The only export commands were the
official Claude and Codex hook entrypoints. Query commands used `itmux`, but no
`--observability-langfuse` writer path was used.

## Conclusion

This validates the architectural pivot with runtime evidence against local
self-hosted LangFuse:

- official Claude plugin produces rich root/generation/tool traces;
- official Codex plugin produces rich root/generation/tool traces with usage,
  cost, and sidecar dedup state;
- the Rust OTLP exporter is not required for rich Claude/Codex LangFuse traces;
- JSONL/Rust OTLP can remain separate local/fallback/collector concerns without
  polluting LangFuse by default.
