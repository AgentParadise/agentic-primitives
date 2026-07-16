# Eval Pack

## Probe A: Command-Plan Safety

Run:

```bash
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml --test cred_transfer
```

Pass requires:

- `docker_run_argv_passes_env_names_without_secret_values` passes.
- `default_env_passthrough_only_enables_claude_token_for_claude` passes.

## Probe B: Claude Recipe Run

Run:

```bash
providers/workspaces/interactive-tmux/driver-rs/target/debug/itmux run \
  --recipe runs/claude-recipe \
  --task "Reply exactly: CLAUDE_ENV_TOKEN_OK" \
  --json true \
  --observability-file runs/itmux-run-events.jsonl \
  --result-file runs/itmux-run-result.json
```

Capture:

- `runs/itmux-run-stdout.jsonl`
- `runs/itmux-run-stderr.txt`
- `runs/itmux-run-exit.txt`
- `runs/itmux-run-events.jsonl`
- `runs/itmux-run-result.json`
- `runs/summary.json`

## Scoring

Pass requires:

- command exits 0
- result success is true
- output/session evidence includes `CLAUDE_ENV_TOKEN_OK`
- stdout event count equals exporter event count
- result exporter report status is `ok`
- result exporter event count equals exporter file line count

Failure modes to classify:

- host token env missing
- Docker env passthrough not applied
- Claude auth still 401s
- exporter fanout count mismatch
- run succeeds but result/outcome detection still marks failure
