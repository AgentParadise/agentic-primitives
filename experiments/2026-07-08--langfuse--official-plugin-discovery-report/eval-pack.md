# Eval Pack

This eval pack is frozen after the hypothesis commit.

## Probe A: Baseline Discovery

Run:

```bash
itmux langfuse-traces --limit 20 --environment local-macbook
```

Evidence:

- `runs/baseline-traces.json`
- `runs/baseline-traces-exit.txt`

## Probe B: Baseline MCP Report

Call MCP `agentic_langfuse_learning_loop_report` over stdio with:

```json
{
  "limit": 20,
  "trace_limit": 10,
  "environment": "local-macbook",
  "include_scores": false,
  "include_insights": true
}
```

Evidence:

- `runs/baseline-mcp-report.json`
- `runs/baseline-mcp-report-exit.txt`

## Probe C: Treatment

If baseline confirms the gap, patch only discovery normalization and MCP
selector/filter/report behavior needed to include official-plugin traces.

Evidence:

- source diff
- focused unit tests

## Probe D: Treatment Discovery and Report

Re-run Probe A and Probe B. Also run harness-filtered MCP reports:

- `harness=claude`
- `harness=codex`

Evidence:

- `runs/treatment-traces.json`
- `runs/treatment-mcp-report.json`
- `runs/treatment-mcp-report-claude.json`
- `runs/treatment-mcp-report-codex.json`

## Probe E: Hygiene

Run focused tests, `git diff --check`, and a key-pattern scan over changed
artifacts.

Evidence:

- `runs/test-*.txt`
- `runs/diff-check.txt`
- `runs/secret-scan.txt`

## Verdict Rules

Use verdict `go` if official Claude and Codex traces appear in treatment
discovery and MCP learning-loop reports with inferred classification and tool
rollups.

Use verdict `no-go` if the official traces cannot be selected without
fallback-specific metadata.

Use verdict `inconclusive` if the local LangFuse backend no longer contains the
known traces.
