# Canonical shell patterns

Reusable shapes for running probes against the harness-lab stack. When a specific command rots, edit this file -- the principles in `SKILL.md` stay put.

## Boot the stack with a planted bug

```sh
# Each branch gets a unique iso_key (port allocation + label prefix)
pnpm harness boot --bug BUG_COMPLETE_TASK_500
pnpm harness inspect            # discover allocated ports + iso_key
ISO_KEY=$(pnpm harness inspect --json | jq -r '.iso_key')
```

## LogsQL projection (cuts response size ~12×)

Always project the fields you need; without `| fields …` each log line returns ~2300 B.

```sh
# Errors on a specific endpoint
curl -s "http://localhost:$VL_PORT/select/logsql/query" --data-urlencode \
  "query={harness.iso_key=\"$ISO_KEY\"} req.url:/complete | fields _time, _msg, severity, req.url, res.statusCode, trace_id | limit 20"

# Word match (no |~ operator -- bare word or field:/regex/)
curl -s "http://localhost:$VL_PORT/select/logsql/query" --data-urlencode \
  "query={harness.iso_key=\"$ISO_KEY\"} \"TypeError\" | fields _time, _msg, severity, trace_id | limit 20"
```

Gotchas:
- Field name is **`severity`**, not `level`. `level:error` returns silently empty.
- `| fields` drops `_stream` and `_stream_id`. Re-query without projection if full context is needed for one line.

## Trace correlation

```sh
# Trace ID from a failed response → traces backend
curl -s "http://localhost:$VT_PORT/select/jaeger/api/traces/$TRACE_ID" \
  | jq '.data[0].spans | length'
```

## Before/after evidence capture

```sh
# Screenshot pair around a fix commit
node harness/agent-tools/screenshot-pair.mjs \
  --url "http://localhost:$WEB_PORT/" \
  --label-before "broken" --label-after "fixed" \
  --out experiments/<slug>/runs/screenshots/
```

See `.claude/skills/before-after-evidence/` for the full evidence-bundle recipe.

## Storing the probe script in-repo

Long probe sequences live in `scripts/run-experiment-<slug>.sh`, not inlined into `justfile` recipes. The script can be invoked from the experiment folder and committed alongside the eval pack -- that makes the probe reproducible months later when the inline `## How to run` block has been edited or forgotten.

## Parallelism, when applicable

Most harness-lab probes are I/O-bound (HTTP queries, browser sessions). Parallelize within a phase only when the probes target orthogonal resources -- different `iso_key`s, different endpoints, different toggles. Serialize across "reset" boundaries (`pnpm harness destroy` → boot).

If you're measuring p95 latency, run with concurrency = 1 -- concurrent invocations distort per-request latency.
