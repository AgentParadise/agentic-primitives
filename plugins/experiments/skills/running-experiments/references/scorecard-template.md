# Hypothesis scorecard template

Every `verdict.md` includes a `## Hypothesis scorecard` section, except for declared mapping probes (which have no hypothesis to score). Misses get the headline; a probe where every prediction was right either tested something obvious or had a hypothesis written after the data.

## Canonical shape

```markdown
## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| LogsQL `| fields` cuts response size ≥5× | 11.9× | ✅ correct | exceeded prediction; baseline 2300 B → 200 B |
| Bare-word match works without `|~` | works on `_msg` | ✅ correct | |
| p95 query latency ≤ 200 ms | 0.52 s | ❌ wrong | cardinality higher than predicted; follow-up needed |
| `severity` is the field name (not `level`) | confirmed | ✅ correct | silent-empty when wrong |
| Projection drops `_stream` context | confirmed | 🟡 partial | direction right, but re-query without projection restores it cheaply |
```

## Scoring vocabulary

- **✅ correct** -- observed result matches the predicted number / direction within the predicted tolerance.
- **🟡 partial** -- direction correct, magnitude or boundary off. Useful -- names exactly where the model of the system was incomplete.
- **❌ wrong** -- observed result contradicts the prediction. **These are the rows that make the probe worth running.** Cite the contradicting evidence path in Notes.

## When the scorecard is suspiciously clean

If every row is ✅, audit:

1. Did smoke testing happen before the hypothesis commit? Check `git log --diff-filter=A -- experiments/<slug>/runs/` vs. the hypothesis commit timestamp.
2. Was the question trivial -- i.e., did anyone actually not know the answer? If so, write it as a mapping probe explicitly, not a hypothesis-testing one.
3. Were the predictions vague enough to be unfalsifiable ("the system will work")? Tighten next time.
