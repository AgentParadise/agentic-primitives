# Results

## Headline

| Probe | Result | Evidence |
|---|---:|---|
| Baseline minimal PATH exposes dependency drift | confirmed | `runs/baseline-minimal-json.err`, `runs/baseline-minimal-json.json` |
| Treatment minimal PATH works without developer tools | pass | `runs/treatment-minimal-json.json`, `runs/treatment-minimal-json.err` |
| Default MacBook mode still runs guard test | pass | `runs/treatment-default-json.json` |
| Syntax / diff / secret hygiene | pass | `runs/test-bash-n.txt`, `runs/diff-check.txt`, `runs/secret-scan.txt` |

## Baseline

Baseline command:

```bash
env -i HOME="$HOME" PATH="/bin:/usr/bin" bash scripts/langfuse-observability-doctor.sh --json
```

It exited `0`, but `runs/baseline-minimal-json.err` contained:

```text
scripts/langfuse-observability-doctor.sh: line 100: rg: command not found
scripts/langfuse-observability-doctor.sh: line 111: rg: command not found
```

The JSON report also showed weaker evidence:

- `fanout.file_jsonl_supported=false`
- `fanout.syntropic_jsonl_supported=false`
- `mcp_server_present=true`

So the previous doctor was useful on the developer MacBook but not robust enough
for a minimal VPS or Docker shell.

## Treatment

Updated `scripts/langfuse-observability-doctor.sh` to:

- use standard `grep -E` checks instead of `rg`;
- add `--no-tests`;
- report `focused_test_status="skipped"` and
  `focused_test_detail="tests disabled by --no-tests"` when tests are disabled.

Updated setup docs to mention `--json --no-tests` for minimal VPS/Docker shells.

Treatment minimal command:

```bash
env -i HOME="$HOME" PATH="/bin:/usr/bin" bash scripts/langfuse-observability-doctor.sh --json --no-tests
```

It exited `0`, emitted no stderr, parsed with `jq`, and reported:

- `fanout.file_jsonl_supported=true`
- `fanout.syntropic_jsonl_supported=true`
- `fanout.mcp_server_present=true`
- `otlp_noise_guard.trace_to_langfuse_suppression_supported=true`
- `otlp_noise_guard.force_flag_supported=true`
- `otlp_noise_guard.focused_test_status="skipped"`

Default MacBook mode still reported:

- Claude present.
- Codex present.
- Node major `22`.
- file/Syntropic137 fanout supported.
- `focused_test_status="pass"` for the cargo-backed `cli_exporters` guard.

## Hygiene

- `bash -n scripts/langfuse-observability-doctor.sh`: exit `0`.
- `git diff --check`: exit `0`.
- strict raw LangFuse key scan: no matches (`rg` exit `1`, empty output).
