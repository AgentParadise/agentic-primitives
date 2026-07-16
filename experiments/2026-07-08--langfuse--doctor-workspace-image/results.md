# Results

## Headline

| Probe | Result | Evidence |
|---|---:|---|
| Interactive-tmux image exists locally | pass | `runs/image-inspect.json` |
| Doctor runs inside the image | pass | `runs/image-doctor.json`, `runs/image-doctor.err` |
| Image doctor JSON assertions | pass | `runs/image-doctor-parse.txt` |
| Hygiene | pass | `runs/diff-check.txt`, `runs/secret-scan.txt` |

## Image Availability

`docker image inspect agentic-workspace-interactive-tmux:latest` exited `0`.
The image id is:

```text
sha256:33f465c7969ae4b00f48d7bdb354a82bf8e39838442187fc5d6598ab8bc07302
```

Tags:

- `agentic-workspace-interactive-tmux:latest`
- `agentic-workspace-interactive-tmux:2.1.126`

## Doctor In Image

Command:

```bash
docker run --rm \
  -v "$PWD:/repo:ro" \
  -w /repo \
  agentic-workspace-interactive-tmux:latest \
  bash /repo/scripts/langfuse-observability-doctor.sh --json --no-tests
```

The command exited `0` and emitted no stderr.

The JSON report showed:

- `tools.claude.present=true`, path `/usr/local/bin/claude`.
- `tools.codex.present=true`, path `/usr/local/bin/codex`.
- `tools.node.present=true`, `major=22`, `node22_plus=true`.
- `tools.python3.present=true`.
- `tools.cargo.present=false`.
- `runtime_env.required_ready=false` because `LANGFUSE_*` env was intentionally
  not injected.
- `fanout.file_jsonl_supported=true`.
- `fanout.syntropic_jsonl_supported=true`.
- `fanout.mcp_server_present=true`.
- `otlp_noise_guard.trace_to_langfuse_suppression_supported=true`.
- `otlp_noise_guard.force_flag_supported=true`.
- `otlp_noise_guard.focused_test_status="skipped"`.
- `otlp_noise_guard.focused_test_detail="tests disabled by --no-tests"`.

`runs/image-doctor-parse.txt` contains a passing `jq -e` assertion for the
fanout/MCP/noise-guard fields.

## Hygiene

- `git diff --check`: exit `0`.
- strict raw LangFuse key scan over the experiment artifacts: no matches
  (`rg` exit `1`, empty output).
