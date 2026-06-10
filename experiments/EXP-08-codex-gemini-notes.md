# EXP-08 — Observability notes: CODEX + GEMINI

Date: 2026-06-11
Branch: `agentprims-exp08`

This note records empirical container-level findings from the throwaway mounted-credential probe for interactive-tmux (`obscodegem-probe`).

## Probe setup (assumed unchanged)

- Workspace name: `exp08-obscodegem-probe`
- Container: `interactive-tmux-exp08-obscodegem-probe-b21fac59`
- Mounted credential/state dirs:
  - `/home/agent/.codex` -> `/data/tmp/interactive-tmux-exp08-obscodegem-probe-uwyn6d56/codex.dir`
  - `/home/agent/.gemini` -> `/data/tmp/interactive-tmux-exp08-obscodegem-probe-uwyn6d56/gemini.dir`
- I used throwaway mounts only; no credential writes into images.

## CODEX

Container log location:
- Primary transcript dir: `/home/agent/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-<timestamp>-<uuid>.jsonl`
- Example captured file:
  - `/data/tmp/interactive-tmux-exp08-obscodegem-probe-uwyn6d56/codex.dir/sessions/2026/06/10/rollout-2026-06-10T22-52-21-019eb3bc-97a4-7c42-b193-0be2d63e6fd4.jsonl`
- Companion files visible: `/home/agent/.codex/history.jsonl`, multiple sqlite files, `.tmp/`, shell snapshot files.

File format and confirmed fields:
- Line-oriented JSONL.
- `session_meta` record includes:
  - `payload.id`
  - `payload.cwd`
  - `payload.originator` (`codex-tui`)
  - `payload.cli_version`
  - `payload.model_provider`
- Turn context is recorded with `turn_context` containing `turn_id`, `approval_policy`, `sandbox_policy`, `permission_profile`.
- Tool call is represented as `response_item` of type `function_call`:
  - includes `name` (e.g., `exec_command`)
  - includes serialized `arguments`
- Tool output is returned as matching `response_item` of type `function_call_output`.
- Observed token fields in session context:
  - `event_msg.payload.total_token_usage.input_tokens`
  - `cached_input_tokens`
  - `output_tokens`
  - `reasoning_output_tokens`
- Confirmed latency field seen in stream events:
  - `event_msg.payload.time_to_first_token_ms`
- `duration_ms` has **not** been confirmed in this probe’s Codex JSONL records.

Token semantics caveat:
- Counts are emitted with both raw and cached token components in the same record (`total_token_usage` with `cached_input_tokens`), so aggregation must not double-count cached tokens across runs.
- Exact token-delta semantics beyond this (per-message delta vs cumulative) are still marked unknown; at least cached components are explicit and present.

Extraction recipe:
- Easiest: because `.codex` is already mounted, read files directly on host from `/data/tmp/.../codex.dir/...`.
- No container restart needed.
- Alternate: `docker cp <container>:/home/agent/.codex/sessions/<...>/rollout-....jsonl <host_dest>`.

What does not work / unknown:
- No guaranteed first-class `duration_ms` field for tool calls in Codex JSONL from this run.
- Mapping from `payload.id`/session UUID to logical workspace is inferential via mount path + `cwd`; no separate workspace-id key was confirmed.

## GEMINI

Container log locations:
- Session logs: `/home/agent/.gemini/tmp/workspace/chats/session-*.jsonl`
- Example captured file:
  - `/data/tmp/interactive-tmux-exp08-obscodegem-probe-uwyn6d56/gemini.dir/tmp/workspace/chats/session-2026-06-10T22-52-398c9179.jsonl`
- Additional visible logs:
  - `/home/agent/.gemini/tmp/workspace/logs.json`
  - `/home/agent/.gemini/tmp/workspace/logs/` (dir; empty for this run)

File format and confirmed fields:
- Line-oriented JSONL.
- First line is header metadata:
  - `sessionId`
  - `projectHash`
  - `startTime`, `lastUpdated`, `kind`
- Messages are stored either as:
  - plain user/gemini messages
  - `$set` records mutating in-memory `messages`
- Tool calls are present in the message record as `toolCalls`:
  - `name` (`update_topic`, `read_file`)
  - `args`
  - `status`/`resultDisplay` style companion payload.
- Token fields are nested in each model record under `tokens`:
  - `input`, `output`, `cached`, `thoughts`, `tool`, `total`

Token semantics caveat:
- Token accounting appears to be cumulative/recomputed against conversation context:
  - same conversation shows `input` values stepping from `9404` to `9666` across turns (not a small per-turn delta).
- `cached` did remain `0` in this run, so cache behavior under this path is unconfirmed; treat as incomplete.

Extraction recipe:
- Host-read directly from mounted dir (`/data/tmp/.../gemini.dir/...`) worked and is the fastest path.
- Alternate: `docker cp <container>:/home/agent/.gemini/tmp/workspace/chats/<file>.jsonl <host_dest>`.

What does not work / unknown:
- No stable per-tool `duration_ms` field seen in captured records.
- `tool-call` traces are present but may not be one-to-one with user-visible turn boundaries unless the orchestrator correlates by index/message order.
- `projectHash` is present but not yet mapped to host-visible workspace-id in this probe.

## Gemini CLI deprecation note

- Runtime banner still reports imminent deprecation in this run:
  - "Gemini CLI will stop serving requests on June 18"
- This means these paths are currently valid for now, but migration risk is high.
- Antigravity status remains tracked in EXP-07 (separate experiment).
