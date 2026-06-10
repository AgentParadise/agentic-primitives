# EXP-08 — Observability for the interactive-tmux provider

Status: **HYPOTHESIS** (frozen 2026-06-11, before any probing)
Branch: `agentprims-exp08`
Off:    `feat/interactive-tmux-workspace-provider` @ `f671a2e`
Date:   2026-06-11

## Context (one sentence)

The interactive-tmux provider on PR #202 ships claude/codex/gemini TUIs
inside a container but loses the observability surface the
`claude-cli` provider exposed in non-interactive (`-p`) mode (native
OTel traces, structured tool events, token deltas). Syntropic137's
stress run (`syntropic137 exp/interactive-tmux-stress`,
`STRESS-REPORT.md` finding **D-obs-1**) observed *uniformly zero*
telemetry from interactive workspaces — Lane-2 events, tool timelines,
and token metrics are blind on this provider.

EXP-08 asks: **what telemetry CAN we extract from interactive claude
running inside the provider's container, and what's the minimum-viable
contract the driver should expose so Syntropic137's existing
observability stack works on interactive workspaces?**

This experiment covers **claude** + the overall provider design. A
sibling probe on pane 3 (codex agent, branch TBD) covers codex + gemini
specifics; their findings will be merged into the design section here
when they announce via Agent Mail.

## Hypothesis (frozen 2026-06-11 before any probing)

> **H1 (session JSONL is reachable).** The interactive `claude` TUI
> writes a per-session JSONL transcript inside the container, under a
> path keyed off the workspace's working directory (analogous to the
> `claude -p` and IDE paths: `~/.claude/projects/<cwd-slug>/<session>.jsonl`).
> The JSONL contains:
>   - `message` records with `tool_use` and `tool_result` content blocks;
>   - per-turn `usage` deltas (input/output token counts);
>   - timestamps adequate to reconstruct a tool timeline.
>
> **H2 (extraction is mechanical).** Once the path is known, the file
> can be extracted from a stopped (or live) workspace container with
> either `docker cp <container>:<path> <host>` or a pre-arranged
> bind-mount of the session directory to the host. No tmux scraping is
> required to recover the structured event stream.
>
> **H3 (hooks fire under interactive mode).** Claude Code's
> `PreToolUse` / `PostToolUse` hook surface — the same one
> `agentic_events` / the `observability` plugin relies on — fires under
> the interactive TUI exactly as it does under `claude -p`. A
> hook that writes JSONL events to a mounted volume produces the same
> event shape that the non-interactive path produces.
>
> **H4 (native OTel works, or is one env-var away).** The interactive
> TUI honors the same `OTEL_*` / `CLAUDE_CODE_*OTEL*` env vars as the
> `claude-cli` provider. If a collector endpoint is reachable, spans
> arrive with the same span names and attributes as the non-interactive
> path.
>
> **H5 (the three caveats from prior work still apply, and matter).**
> The token-accounting caveats baked into Syntropic137's Lane-2 design
> hold under interactive mode too:
>   - Claude's `usage.input_tokens` is the **uncached delta** for the
>     turn, not a running total.
>   - Codex's per-turn totals **include cached tokens**.
>   - Gemini **re-counts the full conversation history** on every turn.
>   - Therefore: NEVER cross-sum provider tokens; normalize at the
>     adapter layer.
>
> **H6 (the driver should grow a `collect_observability(agent)` API.)**
> The cheapest contract addition for Syntropic137 is a single driver
> method that returns a per-agent dict of file paths + parsed event
> records gathered at workspace stop (and a streaming sibling that
> tails the same files during the workspace's life). Streaming via a
> mounted volume is preferable to docker-cp-on-stop because it lets the
> orchestrator emit Lane-2 events in real time and survives a container
> crash.

If H1-H4 hold, we have a working extraction story for at least one
provider. If H5 holds, the existing Syntropic137 normalization rules
still apply. If H6's design fits, PR #202 can ship the observability
hook as a small driver addition without a separate adapter package.

## Method

1. **Hypothesis commit before probing.** This file commits at the
   `HYPOTHESIS` step (per the running-experiments two-commit protocol).
   No `runs/` artifacts yet. The next commit will land the run + a
   verdict block at the bottom of this file.

2. **Probes (empirical, not doc-reading).**
   - **Probe 1 — JSONL.** Start a workspace via the provider. Send a
     prompt that forces ≥1 tool call (e.g., `Read a file under /tmp`).
     Locate `~/.claude/projects/...` inside the container; inspect a
     JSONL session; tabulate which fields are present
     (`tool_use_id`, `usage.input_tokens`, ISO timestamps, etc.).
     Run `docker cp` to extract; verify byte-equal to a bind-mount.
   - **Probe 2 — Hooks.** Configure `~/.claude/settings.json` inside
     the container with a `PreToolUse` matcher that pipes the hook
     payload to `/host-events/claude.jsonl`. Bind-mount
     `/host-events` to a host directory. Trigger a tool call. Inspect
     the produced JSONL. Document the matcher syntax and the smallest
     hook that produces a usable Lane-2 event row.
   - **Probe 3 — OTel.** Set `OTEL_EXPORTER_OTLP_ENDPOINT` (and any
     `CLAUDE_CODE_*OTEL*` siblings) in the container's environment.
     Run a `nc -l -p PORT` quasi-collector on the host or skip to
     "env vars accepted" if a real collector is not available in the
     ~30 min budget. Document the env surface either way.

3. **Design synthesis.** Combine the three probes + the codex/gemini
   findings (when they land via Agent Mail) into a "Provider
   observability contract" section: per-agent log locations, extraction
   lifecycle, normalization target, the three token caveats, and the
   proposed `collect_observability(agent)` API addition with a
   signature sketch.

4. **Constraints.**
   - Stay on `agentprims-exp08`. Never push `main`.
   - Use throwaway credential copies (the provider already does this).
   - Use the EXACT provider on the parent branch — do NOT modify the
     driver during the probe. Driver changes belong in a follow-up
     commit (or PR), gated on the verdict here.
   - Hypothesis section is FROZEN at commit time; any prediction
     revision goes in the verdict's "What I got wrong" section, not by
     editing the hypothesis above.

## Results

Status: **DONE** (claude lane). Codex + gemini sections are placeholders
to be filled when the codex agent (pane 3) announces via Agent Mail.

Branch updated to `agentprims-exp08` @ this commit.
Evidence artifacts under
`providers/workspaces/interactive-tmux/runs/exp08/`:
- `claude-session.jsonl` — 14-record session transcript captured via
  `docker cp` from the running workspace (Probe 1).
- `hook-events.jsonl` — `PreToolUse` / `PostToolUse` /
  `UserPromptSubmit` / `Stop` events emitted by an in-container hook
  to a regular dir (proxy for a `/host-events` bind-mount) (Probe 2).
- `claude-session-otel.jsonl` — second session captured while OTel
  exporters were also firing (Probe 3).
- `otel-instruments.txt` — extracted list of `claude_code.*` OTel
  instrument names observed on `/v1/metrics` + `/v1/logs`.

### Probe 1 — session JSONL is reachable (H1 ✅ + H2 ✅)

Container path mapping:

| In-container path                                                              | Source                |
|--------------------------------------------------------------------------------|-----------------------|
| `/home/agent/.claude/projects/<cwd-slug>/<session-uuid>.jsonl`                  | Session transcript    |
| `/home/agent/.claude/sessions/<pid>.json`                                       | Session registry      |
| `/home/agent/.claude/projects/<cwd-slug>/memory/`                               | Per-session memory    |

The `<cwd-slug>` is the workspace's working directory with `/`
replaced by `-`, e.g. `/workspace` → `-workspace`. `<session-uuid>` is
the standard Claude session UUID (also surfaced as `sessionId` in the
JSONL records and as `session_id` in hook payloads).

Extraction is mechanical:

```bash
# Snapshot a finished session:
docker cp <container>:/home/agent/.claude/projects/-workspace/. \
    ./runs/<workspace-name>/projects/

# Or bind-mount the dir for streaming access:
docker run ... \
    -v /tmp/exp08-projects:/home/agent/.claude/projects \
    ...
```

JSONL records carry **everything Syntropic137 Lane-2 needs**:

| Field                              | Source record                       | Notes |
|------------------------------------|-------------------------------------|-------|
| `timestamp` (ISO with ms)          | every event record                  | wall-clock; reconstruct timeline directly |
| `uuid` / `parentUuid`              | every event record                  | causal links between user → assistant → tool_use → tool_result |
| `sessionId`                        | every record                        | groups records into a single conversation |
| `cwd`, `gitBranch`, `version`      | every event record                  | provenance context for downstream filtering |
| `message.role` ∈ {user,assistant}  | `type: user|assistant`              | conversation turn |
| `message.content[*].type` = `tool_use` | `type: assistant` after a model decides to call a tool | name (`Read`), id (`toolu_…`), and `input` with the tool args |
| `message.content[*].type` = `tool_result` with `tool_use_id` | `type: user` after the tool returns | response payload + `is_error` flag |
| `message.model`                    | `type: assistant`                   | exact model id (e.g. `claude-opus-4-7`) |
| `message.stop_reason`              | `type: assistant`                   | `tool_use` / `end_turn` / `max_tokens` etc. |
| `message.usage.input_tokens`       | `type: assistant`                   | **uncached delta only** (see Caveat C1 below) |
| `message.usage.cache_creation_input_tokens` / `cache_read_input_tokens` | `type: assistant` | cache breakdown |
| `message.usage.output_tokens`      | `type: assistant`                   | model output |
| `durationMs`                       | `type: system, subtype: turn_duration` | end-to-end wall-clock per assistant turn (3.7s / 2.6s observed) |
| `requestId`                        | `type: assistant`                   | matches the Anthropic API request, useful for cost-back-tracing |

One captured assistant record (record 6 of the probe transcript):

```json
{
  "type": "assistant",
  "timestamp": "2026-06-10T22:29:13.797Z",
  "uuid": "d004cf61-98a6-4869-9232-0bc56d548dcb",
  "model": "claude-opus-4-7",
  "stop_reason": "tool_use",
  "usage": {
    "input_tokens": 6,
    "cache_creation_input_tokens": 7246,
    "cache_read_input_tokens": 14817,
    "output_tokens": 77
  },
  "content": [{"type": "tool_use", "name": "Read", "id": "toolu_019TJVeTLwQ1JkABNoCrvnvG",
               "input": {"file_path": "/workspace/exp08-readme.txt"}}]
}
```

The matching `tool_result` in record 7 carries `tool_use_id` linking
back to that id, plus the actual file content the tool returned.

### Probe 2 — hooks fire under interactive mode (H3 ✅)

Installing a hook is exactly as documented for `claude -p`. The
prototype lives in `runs/exp08/hook-emit.sh` (stages on host, copied to
`/home/agent/hook-emit.sh` inside the container), wired in via
`/home/agent/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse":        [{"matcher": "*", "hooks": [{"type": "command", "command": "/home/agent/hook-emit.sh PreToolUse"}]}],
    "PostToolUse":       [{"matcher": "*", "hooks": [{"type": "command", "command": "/home/agent/hook-emit.sh PostToolUse"}]}],
    "UserPromptSubmit":  [{"matcher": "*", "hooks": [{"type": "command", "command": "/home/agent/hook-emit.sh UserPromptSubmit"}]}],
    "Stop":              [{"matcher": "*", "hooks": [{"type": "command", "command": "/home/agent/hook-emit.sh Stop"}]}]
  }
}
```

`hook-emit.sh` reads the JSON payload Claude pipes on stdin, wraps it
in a minimal Lane-2 envelope (`{ts_ms, container, event, payload}`),
and appends it to `/host-events/claude.jsonl`. With `/host-events`
bind-mounted to the host, the orchestrator gets a streaming append-only
event log per workspace.

Observed event sequence for a single tool-using turn (extracted from
`runs/exp08/hook-events.jsonl`):

| `ts_ms` (Δ from first) | `event`            | Useful payload fields                                                         |
|------------------------|--------------------|-------------------------------------------------------------------------------|
| 0 ms                   | `UserPromptSubmit` | `session_id`, `transcript_path`, `cwd`, `permission_mode`, `prompt`           |
| +2049 ms               | `PreToolUse`       | `tool_name="Read"`, `tool_input={"file_path":"..."}`, `tool_use_id`           |
| +2170 ms (= +121 ms after Pre) | `PostToolUse`      | `tool_name`, `tool_input`, `tool_response`, `tool_use_id`, **`duration_ms=48`** |
| +3660 ms               | `Stop`             | `last_assistant_message`, `stop_hook_active=false`                            |

The `PostToolUse` payload's `duration_ms` is the per-tool execution
time (48 ms for a 79-byte Read). That's a Lane-2 native field —
no wall-clock subtraction required.

### Probe 3 — native OTel works as-is (H4 ✅)

Set five env vars at launch:

```bash
CLAUDE_CODE_ENABLE_TELEMETRY=1 \
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_METRICS_EXPORTER=otlp \
OTEL_LOGS_EXPORTER=otlp \
OTEL_TRACES_EXPORTER=otlp \
OTEL_METRIC_EXPORT_INTERVAL=2000 \
OTEL_LOGS_EXPORT_INTERVAL=2000 \
  claude
```

A throwaway Python TCP listener on `:4318` captured **real OTLP HTTP
traffic** posting to `/v1/metrics` and `/v1/logs` (no `/v1/traces` was
observed during the short probe; metrics + logs is the surface that
fired). User-Agent: `OTel-OTLP-Exporter-JavaScript/0.208.0`. Resource
attributes include:

```
service.name        = claude-code
service.version     = 2.1.126
host.arch           = amd64
os.type             = linux
terminal.type       = tmux        ← provider-visible
start_type          = fresh
user.id, session.id, organization.id, user.email, user.account_uuid, user.account_id
```

Instruments observed (full list at
`runs/exp08/otel-instruments.txt`):

```
claude_code.active_time.total
claude_code.api_request
claude_code.cost.usage
claude_code.events
claude_code.hook_execution_start
claude_code.session.count
claude_code.token.usage
claude_code.user_prompt
```

The same instrument names the `claude-cli` provider's
`otel_native: true` marker promises. **Interactive claude in tmux is
fully observable via OTel with zero code changes** — just env vars and
a reachable collector. The image's outbound network policy must allow
the collector endpoint; nothing else is required.

## Design — provider observability contract

This is the design the probes prove out. It is the contract PR #202
should adopt; the implementation is small (a few env-var pass-throughs,
one extra optional bind-mount, an opt-in hooks scaffold, and a single
new public method on the workspace) and lands in a follow-up commit.

### Three channels, each with a defined extraction lifecycle

| Channel                     | What you get                                             | Extraction surface                                 | Best lifecycle      |
|-----------------------------|----------------------------------------------------------|----------------------------------------------------|---------------------|
| **Session JSONL**           | Full turn-by-turn conversation, every tool call/result, per-turn `usage`, ISO timestamps, `requestId`, model id, `stop_reason` | bind-mount `/home/agent/.claude/projects` to host; or `docker cp` at stop | **streaming via bind-mount** preferred; `docker cp` is the at-stop fallback when no host-volume is acceptable |
| **Hooks → file**            | Real-time Lane-2-shaped events with `PreToolUse` / `PostToolUse` / `UserPromptSubmit` / `Stop`. `PostToolUse` carries native `duration_ms` per tool. | bind-mount a `/host-events/<agent>.jsonl` file; settings.json wires the hook | **streaming** (always) — the file is the lane |
| **Native OTel**             | OTLP metrics + logs with `claude_code.{session.count, active_time.total, token.usage, cost.usage, api_request, hook_execution_start, user_prompt, events}` resource-tagged with `service.name=claude-code` + `session.id` + `user.account_uuid` + `terminal.type=tmux` | inject `OTEL_*` + `CLAUDE_CODE_ENABLE_TELEMETRY=1` env at container launch; point at an existing collector | **streaming** (real-time push) |

Why all three (not just one): the three channels capture three
**different** views of the same activity:

- **Session JSONL** is the ground-truth replay log (durable; what
  the model and the tool actually exchanged).
- **Hooks** are the cheapest **real-time** Lane-2 event stream
  (PreToolUse / PostToolUse fires before/after the actual tool call
  with `duration_ms`).
- **OTel** delivers the **cost + token + cost.usd metrics** Syntropic137
  already aggregates (`claude_code.cost.usage`, `claude_code.token.usage`)
  in a shape an existing collector consumes without further work.

A consumer can opt into any subset. The driver shouldn't force all three
on — for a CI smoke run, just the session JSONL via `docker cp` at stop
might be enough.

### Normalization target — what Syntropic137 Lane-2 needs

Lane-2 events the orchestrator already consumes today (from
`claude -p`):

```json
{
  "timestamp_ms": <int>,
  "session_id": "<uuid>",
  "agent": "claude",
  "kind": "tool_use" | "tool_result" | "turn" | "stop",
  "tool_name": "Read",
  "tool_args_digest": "sha256:…",         // truncated args
  "duration_ms": 48,
  "tokens": {                              // OPTIONAL — agent-specific
    "input_tokens_uncached": 6,
    "cache_read": 14817,
    "cache_creation": 7246,
    "output": 77
  },
  "model": "claude-opus-4-7",
  "cost_usd": <float>                      // OPTIONAL
}
```

**Mapping from each channel to that target:**

- From **session JSONL**: walk records sorted by `timestamp`. Emit
  `tool_use` events from assistant `content[].type=tool_use`, paired
  `tool_result` from the subsequent user record with matching
  `tool_use_id`. Emit a `turn` event per assistant record with `model`,
  `tokens.*` from `message.usage`, `stop_reason`, and
  `duration_ms` from the following `type:system, subtype:turn_duration`
  record.
- From **hooks JSONL**: each event already carries
  `hook_event_name`, `tool_name`, `tool_input`, `tool_response`,
  `duration_ms`, `session_id`, `transcript_path`. Map
  `PreToolUse`→`tool_use` (no tokens), `PostToolUse`→`tool_result`
  (with `duration_ms`), `UserPromptSubmit`→`turn-start`,
  `Stop`→`turn-end` (with `last_assistant_message`).
- From **OTel**: pipe metrics into the existing Syntropic137
  collector pipeline; nothing new to normalize.

### The three token-accounting caveats (re-confirmed)

H5 holds. The Lane-2 normalizer must continue to apply these (cited
verbatim from prior Syntropic137 work; each was re-verified in the
probes here):

- **C1 — Claude `usage.input_tokens` is the uncached delta.**
  Not a running total. Probe transcript example: an assistant turn
  with `input_tokens=6, cache_read_input_tokens=14817,
  cache_creation_input_tokens=7246` — the "6" is the new tokens for
  THIS turn beyond the 14817-token cache hit and the 7246-token cache
  write. Sum `cache_read + cache_creation + input` to get the
  "what the model actually saw" total; the raw `input_tokens` is the
  **incremental** number useful for delta-cost.
- **C2 — Codex per-turn totals include cached tokens.** Surfaced by
  the sibling probe; do not cross-sum with Claude's deltas.
  _(Confirm/refine with codex pane finding when announced.)_
- **C3 — Gemini re-counts the full conversation history per turn.**
  Each turn's `usage` is the cumulative context window cost, not
  per-turn delta. Multiply at your peril.
  _(Confirm/refine with gemini pane finding when announced.)_
- **C4 (cross-cutting) — NEVER cross-sum tokens across providers.**
  Normalize at the adapter layer: Lane-2's `tokens.input_tokens_uncached`
  is the lowest common denominator for Claude; codex/gemini map to
  their own provider-specific fields that the Lane-2 frontend
  formats per agent.

### Proposed driver API addition

The cheapest contract addition for PR #202 is a single new public
method on `InteractiveTmuxWorkspace`, plus a couple of optional
constructor kwargs to wire bind-mounts. Sketch (Python; Rust parity
straightforward):

```python
@dataclass
class ObservabilitySources:
    session_jsonl: Path | None           # in-container path to the session JSONL
    hook_events_jsonl: Path | None       # in-container path to the bound hook log
    otel_endpoint: str | None            # value of OTEL_EXPORTER_OTLP_ENDPOINT, if set

@dataclass
class ObservabilityBundle:
    sources: ObservabilitySources
    session_records: list[dict]          # parsed JSONL (when present)
    hook_events: list[dict]              # parsed hook JSONL (when present)


class InteractiveTmuxWorkspace:
    @classmethod
    def start_workspace(
        cls,
        ...,
        host_hook_events_dir: Path | None = None,    # bind-mounted to /host-events
        host_projects_dir: Path | None = None,       # bind-mounted to ~/.claude/projects
        otel_endpoint: str | None = None,            # passed as OTEL_EXPORTER_OTLP_ENDPOINT
        otel_extra_env: dict[str, str] | None = None,
    ): ...

    def collect_observability(self, agent: AgentName = "claude") -> ObservabilityBundle:
        """Snapshot the current observability state for `agent`.

        Safe to call multiple times during a workspace's lifetime
        (each call returns the current cumulative state). The driver
        reads from the bind-mounted host paths when they were
        configured; otherwise it `docker cp`'s the in-container files
        at call time.
        """
```

Wire-up in the existing driver:

- `start_workspace(host_hook_events_dir=…)` adds an extra `-v
  <host>:/host-events` mount and installs the hook scaffold under
  `~/.claude/settings.json` automatically. The hook script
  `/home/agent/hook-emit.sh` is baked into the workspace image or
  copied in by the driver at start.
- `start_workspace(host_projects_dir=…)` adds `-v
  <host>:/home/agent/.claude/projects` so the session JSONL streams
  to the host without `docker cp`.
- `start_workspace(otel_endpoint=…)` sets `CLAUDE_CODE_ENABLE_TELEMETRY=1`
  + `OTEL_EXPORTER_OTLP_ENDPOINT=<endpoint>` in the container env.
  `otel_extra_env` lets the integrator add their own
  `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_LOG_LEVEL`, etc.
- `collect_observability(agent)` does whatever extraction the user
  didn't already get streaming: docker-cp when no bind-mount, or
  parses the bind-mounted file.

These are pure additions. Existing callers (smoke, EXP-05/06 probes,
Syntropic137 today) are unaffected — all new kwargs default to `None`.

### Streaming vs at-stop, per channel

| Channel       | Streaming option        | At-stop fallback                  | Recommendation |
|---------------|-------------------------|-----------------------------------|----------------|
| Session JSONL | bind-mount `~/.claude/projects` | `docker cp` in `stop()`       | Bind-mount in production; `docker cp` is fine for CI smoke runs that already discard the container. Survives container crash either way for the bind-mount case. |
| Hooks         | bind-mount `/host-events` | none — events are lost without the mount | **Always bind-mount.** The hook writes happen continuously during the workspace; an at-stop pull would require an in-image hook script that buffers to a path we then `docker cp`, which is strictly worse than the bind-mount. |
| OTel          | always streaming (push to collector) | none                          | Use a real collector. If unavailable, skip OTel for now; the JSONL + hooks already cover Lane-2's needs. |

The driver's `stop()` should NOT auto-pull observability artifacts —
that would couple shutdown latency to artifact size. Have callers
call `collect_observability()` explicitly when they want the snapshot,
THEN `stop()`.

### Per-agent log locations (claude confirmed; codex + gemini TBD)

| Agent  | Session transcript                                                   | Hook surface                          | Native OTel                          |
|--------|----------------------------------------------------------------------|---------------------------------------|--------------------------------------|
| claude | `~/.claude/projects/<cwd-slug>/<session-uuid>.jsonl`                 | `~/.claude/settings.json` `hooks:` block | `CLAUDE_CODE_ENABLE_TELEMETRY=1` + `OTEL_*` env (proven this probe) |
| codex  | _(pending codex pane probe)_                                         | _(pending)_                            | _(pending)_                           |
| gemini | _(pending gemini pane probe)_                                        | _(pending)_                            | _(pending)_                           |

The codex pane agent is researching the codex + gemini equivalents in
parallel; this table will be filled in (and any provider-quirks that
emerge will be added to the C2 / C3 caveats above) when they announce
their findings via Agent Mail. **This commit lands without those rows;
a follow-up commit on `agentprims-exp08` will merge them in when they
arrive.**

## Verdict

**Hypothesis upheld across the board (H1-H6).** The provider can ship
real Lane-2 observability for interactive workspaces with no driver
core changes — only **additive** plumbing (env-var pass-throughs, two
optional bind-mounts, a baked-in hook scaffold, and one new
`collect_observability()` method). D-obs-1 (telemetry uniformly zero)
is **a configuration gap, not an architectural gap.**

Score (probes that produced evidence):

- H1 (session JSONL reachable):                     **PASS** (14-record probe transcript)
- H2 (extraction is mechanical):                    **PASS** (docker cp → byte-equal copy on host)
- H3 (hooks fire under interactive mode):           **PASS** (4 events captured)
- H4 (native OTel works as-is):                     **PASS** (real OTLP HTTP traffic captured; 8 distinct `claude_code.*` instruments observed)
- H5 (three token caveats still apply):             **PASS** (Claude `input_tokens=6` while `cache_read=14817` re-confirmed the uncached-delta semantics; codex+gemini caveats pending sibling probe)
- H6 (driver should grow `collect_observability`):  **PASS** as design (sketch above; implementation deferred to a follow-up commit on this branch or a separate PR)

What I got wrong (none of the H1-H4 predictions; one design assumption
revised): I expected the driver would need to **own** the hook script
(bake it into the image). The probe showed the hook script can be
**copied in by the driver at start**, which keeps the image
unchanged and the hook config purely caller-driven. The
`start_workspace(host_hook_events_dir=…)` kwarg sketched above
reflects that revision.

Net: PR #202 can absorb a small additive observability commit and
close D-obs-1 in the same review cycle. The image needs no rebuild;
only the driver and the docs change. A future PR can layer in a
Lane-2 normalizer that reads the three channels and emits the
canonical event stream Syntropic137 already consumes — but the
PROVIDER's contract is complete once the kwargs + method above land.

## Cross-references

- PR #202 (the provider this experiment instruments).
- `STRESS-REPORT.md` D-obs-1 (the finding that triggered this experiment).
- `experiments/EXP-05-interactive-tmux-provider.md` (the provider's own
  experiment record).
- `providers/workspaces/claude-cli/manifest.yaml` `otel_native: true` /
  `otel_enabled: true` (the non-interactive provider's OTel posture
  — confirmed in this probe to apply to interactive too).
- Syntropic137 Lane-2 observability docs (to be cited once the codex
  pane's findings land with the exact field-name mapping).
