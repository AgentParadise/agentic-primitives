# `itmux` — Rust port of the interactive-tmux driver

A parity-faithful Rust implementation of the Python host-side driver at
`../driver/interactive_tmux.py`. Ships as a single statically-linkable
binary `itmux`, suitable for baking into a workspace image or vendoring
into orchestrators that prefer a memory-safe, fast-startup CLI over a
`python3 driver/interactive_tmux.py` shell-out.

## Why a Rust port

Two things the Python single-file driver does not give you:

- **Single static binary** — no Python interpreter on the consumer's
  PATH, no `PYTHONPATH` shim. Drop `itmux` next to your orchestrator and
  it runs.
- **Faster cold start** — every CLI invocation in the Python driver pays
  `python3 -m interactive_tmux` import + argparse cost (~120 ms); `itmux`
  is a single ELF, ~5 ms cold. Matters when an orchestrator drives N
  `send`/`await`/`capture` cycles back-to-back.

It is **not** a behavioural fork: the per-agent matrix, structured-result
shapes, on-disk workspace registry, and CLI surface are byte-compatible
with the Python driver. The two CLIs share
`/tmp/interactive-tmux-workspaces/<name>.json`, so a Rust `start`
round-trips with a Python `stop` and vice versa.

## Build & install

```bash
cd providers/workspaces/interactive-tmux/driver-rs/
cargo build --release
# Binary at target/release/itmux (~2.4 MB)
```

Cargo honours `CARGO_TARGET_DIR` if set; otherwise the binary lands at
`target/release/itmux` next to `Cargo.toml`. For ad-hoc use on PATH:

```bash
install -m 0755 target/release/itmux ~/.local/bin/
itmux --help
```

## CLI surface (parity with Python `python3 driver/interactive_tmux.py`)

```bash
itmux start    --name w1
itmux send     --name w1 --agent gemini --text "Refactor lib/foo.py"
itmux await    --name w1 --agent gemini --timeout 60
itmux capture  --name w1 --agent gemini
itmux exec     --name w1 -- bash -lc 'ls /workspace'   # NEW: docker exec bypass
itmux stop     --name w1
```

Every JSON-emitting subcommand uses the same field names and string
literals as the Python `to_dict()`/`AwaitResult` output (`ready`,
`timed_out`, `reason`, `duration_ms`, `stable_polls_observed`, `pane`,
`error`). Exit codes match Python: `0` ready, `2` await timeout, `3`
startup-readiness failure.

## `itmux run` observability export

`itmux run` emits normalized `AgentRunEvent` JSONL on stdout. For reusable
observability outside stdout consumers, configure the portable file exporter:

```bash
itmux run \
  --recipe /path/to/recipe \
  --task "Implement the change" \
  --observability-file /tmp/itmux-run-events.jsonl \
  --result-file /tmp/itmux-run-result.json
```

The exporter appends the same normalized run events to the JSONL file and the
final `AgentRunResult.observability.exporters[]` report includes status,
event count, target, and a link URI. This works the same on a Mac, a VPS, or
inside Docker when the path is mounted into the executing environment.

LangFuse fallback/collector export plugs into the same fanout layer through
OTLP HTTP/protobuf:

```bash
itmux run \
  --recipe /path/to/recipe \
  --task "Implement the change" \
  --observability-file /tmp/itmux-run-events.jsonl \
  --observability-langfuse \
  --result-file /tmp/itmux-run-result.json
```

For rich Claude/Codex traces, prefer LangFuse's official Claude Code and Codex
plugins. Load `LANGFUSE_*` from the operator's secret manager before running
the fallback command. See
[`docs/guides/langfuse-observability-setup.md`](../../../../docs/guides/langfuse-observability-setup.md)
for the macOS Keychain, VPS, Docker, and real backend smoke procedure.

When `TRACE_TO_LANGFUSE=true` indicates an official LangFuse plugin is active,
the CLI suppresses the Rust OTLP writer to avoid duplicate/noisy LangFuse
traces while preserving `--observability-file` JSONL fanout. Use
`--observability-langfuse-force` only for deliberate fallback/collector smoke
or Syntropic137 routing.

If LangFuse config is missing or invalid, the run still completes and local
file export still works; the LangFuse exporter reports `status:"failed"` in the
final observability bundle.

For Codex recipes, `itmux run` defaults to the existing interactive TUI
workspace mode. Use `--codex-mode exec` when the run needs structured Codex
tool/token/cost telemetry:

```bash
itmux run \
  --recipe /path/to/codex-recipe \
  --task "Reply exactly: OK" \
  --codex-mode exec \
  --observability-file /tmp/codex-run-events.jsonl \
  --observability-langfuse \
  --result-file /tmp/codex-run-result.json
```

`--codex-mode exec` is valid only for recipes whose default agent is Codex. It
loads the recipe prompt/model, runs `codex exec --json`, strips an `openai/`
model prefix before passing the model to Codex, and normalizes the structured
event stream through the same `AgentRunEvent` and exporter fanout used by the
rest of `itmux run`. The default `tui` mode remains the Docker workspace path
and currently has only coarse lifecycle observability.

## `itmux codex-exec` observer export

`itmux codex-exec` runs `codex exec --json`, normalizes Codex's structured
events into the shared `AgentRunEvent` stream, and uses the same observability
exporters:

```bash
itmux codex-exec \
  --prompt "Reply exactly: OK" \
  --observability-file /tmp/codex-exec-events.jsonl \
  --observability-langfuse \
  --result-file /tmp/codex-exec-result.json
```

This is intentionally separate from the interactive Codex TUI path. The
empirical token/cost surface is `codex exec --json`: `turn.completed.usage`
maps to `type:"token_usage"` with `input_tokens`, `cached_input_tokens`,
`output_tokens`, and `reasoning_output_tokens`.

## Per-agent matrix (parity-encoded — callers should not need this)

| Concern    | Claude                                                                | Codex                                                                       | Gemini                                                       |
|------------|-----------------------------------------------------------------------|-----------------------------------------------------------------------------|--------------------------------------------------------------|
| Launch     | `claude` + Enter                                                      | `codex --no-alt-screen` + Enter, then `1` Enter (trust), then Escape (hooks)| `gemini` + Enter                                             |
| Submit     | `send-keys -l <text>` then `send-keys Enter` (two-step Enter)         | `send-keys -l <text>` then `send-keys C-j C-m` (first-send gotcha)          | `send-keys -l <text>` then `send-keys Enter` (never `C-m`)   |
| Readiness  | no `esc to interrupt` + `? for shortcuts` footer + `^❯\s*$` (3 signals)| no `• Working` + (`› ` ∨ `Tip:` ∨ `Write tests for`)                         | `Type your message` present + no `Thinking...` / `esc to cancel` |
| Auth mount | **Both** `~/.claude/` (creds) + synthesised `~/.claude.json`          | `~/.codex/` (tmp/log skipped — they race)                                    | `~/.gemini/` with `security.folderTrust.enabled=false` patched|
| Response marker | `● ` (U+25CF + space)                                            | `• ` (U+2022 + space)                                                       | `✦ ` (U+2726 + space)                                        |

Source of truth for these encodings:

- `src/adapter.rs` — readiness parsers + launch/submit dispatch
- `src/auth.rs` — host-auth mount preparation (synthesised
  `~/.claude.json` builder, gemini `settings.json` patch, codex
  tmp/log skip rule)
- `../../experiments/ANALYTICS.md` §4 — the matrix this implements
- `../driver/interactive_tmux.py` — the Python original this ports

## Tests

```bash
cargo test
```

Three test files, 25 tests total — none require a docker daemon:

| File | Coverage |
|---|---|
| `tests/readiness.rs` | Each per-CLI readiness/started predicate against fixture pane captures (`tests/fixtures/<agent>/*.txt`). Includes the negative cases that motivated EXP-01..04 (`esc to interrupt`, `• Working`, `Thinking...`, `esc to cancel`). |
| `tests/result_parity.rs` | `AwaitResult` serde shape matches Python `to_dict()`; reason-string literals, exit-code convention, agent name parsing, response-marker constants. |
| `tests/auth_parity.rs` | Synthesised `~/.claude.json` carries `oauthAccount` through, defaults the rest; gemini `settings.json` `folderTrust` patch; codex `tmp/`/`log/` skip; missing `.credentials.json` errors fail loud. |

## Parity smoke

`../scripts/smoke-rs.sh` mirrors `smoke.sh` line-for-line but drives the
workspace through `itmux`. Auto-builds the release binary on first run.

```bash
bash providers/workspaces/interactive-tmux/scripts/smoke-rs.sh
# Expected: [smoke-rs] ALL PASS (3/3 agents)
```

Pre-reqs are identical to the Python smoke: `agentic-workspace-interactive-tmux:latest`
built, host has `~/.claude/.credentials.json`, `~/.codex/auth.json`, and
`~/.gemini/`, plus docker access.

Per-agent transcripts land at `../runs/smoke-rs-<agent>.txt` (sibling to
the Python smoke's `runs/smoke-<agent>.txt`) so you can diff the two
outputs to verify the Rust path produces equivalent model responses.

## Credentials policy (same as the Python driver)

`itmux` copies host credential dirs into a throwaway dir under
`$TMPDIR/interactive-tmux-<name>-<rand>/` and mounts the copies into
the container. Source credentials are never moved or modified. `stop`
removes the throwaway dir. No credential bytes are ever baked into
binaries, fixtures, or commits — `tests/fixtures/` is purely TUI
capture text with smoke tokens scrubbed.

## What this port intentionally does NOT do

Same omissions as the Python v1 (no streaming, no reconnect to a running
workspace, no plugin baking). The driver is a transport, not a richer
abstraction. If you want streaming or richer config plumbing, the upstream
roadmap (`../README.md`'s "What this provider does NOT do (today)") is
shared with this port — it is not a fork.
