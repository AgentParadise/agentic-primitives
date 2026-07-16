# Eval Pack

## Probe A: CLI Surface

```bash
cd providers/workspaces/interactive-tmux/driver-rs
cargo run --quiet -- langfuse-trace --help
```

Pass requires a documented `langfuse-trace` command with `--trace-id`,
`--run-id`, `--from-start-time`, `--to-start-time`, `--fields`, `--limit`, and
`--api`.

## Probe B: Bounded URL Construction

```bash
cd providers/workspaces/interactive-tmux/driver-rs
cargo test langfuse_trace_query_url_is_bounded_and_encoded -- --nocapture
```

Pass requires the query URL to normalize LangFuse OTEL endpoint input back to
the API origin, include bounded `fromStartTime`/`toStartTime`, and URL-encode
field groups. The same test set also covers `--api legacy-trace` URL
construction for self-host compatibility.

## Probe C: Missing Config Fail-Fast

```bash
env -u LANGFUSE_BASE_URL -u LANGFUSE_PUBLIC_KEY -u LANGFUSE_SECRET_KEY \
  providers/workspaces/interactive-tmux/driver-rs/target/debug/itmux \
  langfuse-trace \
  --run-id run-query-smoke \
  --from-start-time 2026-07-07T20:00:00Z \
  --to-start-time 2026-07-07T21:00:00Z
```

Pass requires exit `78` and JSON that names only missing env vars, with no
secret values.

## Probe D: Actual CLI Query Against Local Receiver

```bash
experiments/2026-07-07--langfuse--trace-query-cli/run-local-receiver-query.sh
```

Pass requires exit `0`, a captured `GET /api/public/v2/observations?...`
request, redacted evidence that Basic auth matched the synthetic credentials,
and a parsed JSON response in the command output.
