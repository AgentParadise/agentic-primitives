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

_(Will be populated in the run commit; this section is empty in the
hypothesis commit.)_

## Verdict

_(Will be populated in the run commit.)_

## Cross-references

- PR #202 (the provider this experiment instruments).
- `STRESS-REPORT.md` D-obs-1 (the finding that triggered this experiment).
- `experiments/EXP-05-interactive-tmux-provider.md` (the provider's own
  experiment record).
- Syntropic137 Lane-2 observability docs (cited in the design when the
  codex pane's findings land).
