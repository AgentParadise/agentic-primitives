---
title: "ADR-039: Agent execution model - pass a command, exit-code completion, Stop-hook observability"
status: proposed
created: 2026-07-07
updated: 2026-07-07
author: Syntropic137
---

# ADR-039: Agent execution model - pass a command, exit-code completion, Stop-hook observability

## Status

**Proposed**

- Created: 2026-07-07
- Updated: 2026-07-07
- Author(s): Syntropic137
- Related: ADR-038 (Rust-first execution + contracts), ADR-035 (workspace injection contract)

## Context

The workspace substrate (`itmux`) drives coding-agent CLIs (claude, codex, gemini) inside a
Docker container. The first design drove the agent's INTERACTIVE TUI over tmux: launch the TUI,
type the task with `send-keys`, and infer "the turn is done" by scraping the pane. That path had
three recurring problems:

1. **Completion is a heuristic.** With no process exit to key on, "done" was inferred from pane
   liveness / error markers - fragile (a `capture-pane` hang once wedged a phase indefinitely; a
   `success` flag reported liveness, not task outcome).
2. **A send-race.** The TUI dropped the first keystrokes of a submission, needing per-harness
   readiness gates.
3. **The premise was uncertain.** The interactive path was chosen partly because headless
   `claude -p` was expected to be removed from the Anthropic Max plan; if that were false, the
   interactive machinery might be unnecessary complexity.

Separately, container auth kept failing with 401s: the credential-transfer path copied the host
`~/.claude/.credentials.json`, which on macOS is a stale artifact.

Before committing more of the substrate to the interactive path, we validated the load-bearing
assumptions with three isolated experiments (EXP-07, EXP-08, EXP-09; run 2026-07-07 against
`agentic-workspace-interactive-tmux:latest`, claude 2.1.126 + codex 0.139.0, subscription auth,
evidence captured from inside the container). This ADR records the decision those experiments
drove. The full experiment records (hypotheses committed before data per the running-experiments
two-commit protocol, plus `runs/` evidence) live in `experiments/EXP-07..09` and their setup +
outputs are summarized in Rationale below.

## Decision

We adopt a **"pass a command"** execution model as the default, and demote interactive send-keys
to an opt-in adapter:

1. **Default execution = run a headless command inside a tmux pane.** The recipe/adapter produces
   a launch argv (`claude -p "$TASK"`, `codex exec "$TASK"`); it runs in a tmux pane in the
   persistent container. **Completion is the process exit code** (deterministic, no send-race, no
   pane heuristic). **Observability** is the harness hook stream (Claude's `Stop` + `PreToolUse`
   fire even for `claude -p` in a pane) plus pane capture. **Persistence** is the container: it
   survives the command and can run a follow-up.
2. **No heavy execution-mode selector.** The "mode" reduces to command-choice + optional-pane.
   Interactive send-keys (today's `itmux` submit path) becomes a distinct **"steering" adapter**,
   selected only when a run genuinely needs mid-run interaction (answering a live prompt).
3. **Completion for the steering adapter** keys on the `Stop` hook event (exactly one per turn),
   not the pane heuristic; `SubagentStop` is advisory only (see Rationale - it also fires
   spuriously after every `Stop`).
4. **Credentials** are supplied per-run via a `.env`/env (`CLAUDE_CODE_OAUTH_TOKEN` /
   `CODEX_AUTH_FILE`, API-key fallbacks) and injected securely; the stale host on-disk file is
   never the source (ADR-039 companion work: PR #254).
5. **tmux is retained** as the multi-harness substrate (persistence, pane observability, harnesses
   without a headless mode) and as a hedge - not because `-p` is unavailable (it is not; see H2d).

Out of scope: the observability EXPORTER (hook events -> telemetry sink) is a separate work item;
this ADR only fixes that the Stop hook is the signal it consumes.

## Rationale (the experiments)

**EXP-07 - is the `Stop` hook a clean completion signal? Verdict GO.**
Setup: an instrument (`~/.claude/settings.json` hooks appending event + timestamp + session id to
a log; payload arrives via stdin JSON) driven across 4 probes. Outputs: a single task submission
fires exactly ONE `Stop` regardless of a 5-iteration internal loop (H1a); a background daemon the
agent spawns survives after `Stop` and does not multiply Stops - a "cron every 10 min" does NOT
emit a Stop every 10 min (H1b); a persistent session keeps a stable `session_id` and the container
is never torn down across turns (H1d). Miss (H1c, scored partial): a spurious `SubagentStop` fires
~1-3s AFTER the terminal `Stop` on every turn (a TUI title/summary background task), so
`SubagentStop` is NOT a clean "a user subagent ran" signal - key on `Stop`, treat `SubagentStop`
as advisory (a real subagent's `SubagentStop` precedes `Stop`; the spurious one follows).

**EXP-08 - subscription auth + does `-p` still work on Max? Verdict GO.**
Setup: a 2x2 (tmux vs `-p`) x (claude-only vs claude->codex) matrix with `ANTHROPIC_API_KEY` and
`OPENAI_API_KEY` asserted UNSET in-container. Outputs (verified from container captures): claude and
claude-delegated codex both authenticate on SUBSCRIPTION creds in BOTH tmux and `-p` (`AUTH_OK` file
written, codex `CODEX_OK`, `claude sub: max`, `codex auth_mode: chatgpt`, no API keys). Decisive
(H2d): **`claude -p` is NOT blocked on the Max plan** - the initial 401 was purely the stale on-disk
credential file; the live token is in the macOS Keychain and Claude does not self-refresh a stale
token in-container. So the interactive path is not FORCED by `-p` removal.

**EXP-09 - mode-selector vs "just pass a command"? Verdict GO, all H9a-d.**
Setup: M1 (interactive TUI + send-keys + Stop-completion) vs M2 (`claude -p`/`codex exec` inside a
tmux pane) vs M3 (pure headless, no tmux), over 5 probes. Outputs (verified): M2's `claude -p` in a
pane completes on a clean exit code (`EXIT=0`), the `m2.txt` sentinel is actually written, the `Stop`
hook still fires (H9a), and the container stays healthy for a 2nd command (`SECOND_OK`). M2 launches
claude AND codex with one headless argv shape - zero per-harness submit/completion branching (H9b).
The only capability unique to M1 is injecting input mid-run (H9c: a keypress answered a live
permission prompt). Therefore the mode reduces to command-choice + optional-pane (H9d).

## Alternatives Considered

### Alternative 1: Interactive send-keys as the default (the original design)

**Description**: Always drive the TUI, submit via `send-keys`, detect completion by pane scraping.

**Pros**: mid-run steering; a single mental model.

**Cons**: heuristic completion (wedge risk); send-race needing per-harness gates; more per-harness
adapter code; success != task outcome.

**Reason for rejection**: EXP-09 showed command-in-a-pane gets deterministic exit-code completion
AND the same observability + persistence, without the race or the heuristic. Send-keys is kept, but
scoped to the steering case where it is actually needed.

### Alternative 2: Pure headless, drop tmux entirely

**Description**: `docker exec claude -p ...`, no tmux pane (M3).

**Pros**: simplest; clean exit-code completion.

**Cons**: no pane observability; no container persistence between commands; no path for harnesses
that lack a headless mode; no mid-run steering ever.

**Reason for rejection**: loses the multi-harness substrate and the persistence/observability that
make the workspace valuable, and removes the hedge if `-p` is later restricted. EXP-09 P4 confirmed
M3 works but is one-shot with stdout-only telemetry.

### Alternative 3: A first-class execution-mode selector (interactive | headless)

**Description**: AgentRunSpec carries a `mode` enum; the orchestrator switches whole adapters.

**Pros**: explicit.

**Cons**: EXP-09 showed the two "modes" are not symmetric peers - headless-command-in-a-pane is the
general default and interactive is a narrow special case (steering). A heavy enum over-weights a
rare branch.

**Reason for rejection**: the distinction collapses to "which command + do I need steering," which
is lighter than a mode switch.

## Consequences

### Positive
- **Deterministic completion.** Exit code replaces the pane heuristic (`detect_outcome`) as the
  default "await" signal - the wedge/liveness-vs-outcome class of bugs goes away.
- **Less per-harness code.** One headless argv shape covers claude and codex; new harnesses are a
  command, not a submit/completion protocol.
- **Observability + persistence retained.** The `Stop` hook fires for `claude -p` in a pane, so
  telemetry is unified across modes; the container persists for multi-command / multi-turn.
- **The original doubt is resolved.** "Panes are always in progress" is moot - you run a command
  that exits.

### Negative
- **Two adapters to maintain.** The default command path AND the steering (send-keys) path. The
  send-keys/`detect_outcome` code is demoted, not deleted.
- **Codex hooks differ from claude's.** The `Stop`-hook telemetry unification is claude-specific;
  codex observability rides its own JSON/exit, so the "hooks fire in both" property is per-harness.

### Neutral
- The `AgentRunSpec` contract, the R7 orchestrator state machine, credential injection, and DooD
  transfer are UNCHANGED. This decision changes the default completion MECHANISM and the adapter
  emphasis, not the contract. Nothing built for #247 is wasted.

## Implementation Notes

- Add a **command-in-a-pane execution path** to the run orchestrator: launch the adapter's headless
  argv in a tmux pane, capture the exit code (`<argv>; echo EXIT=$? > file`), stream hook events,
  capture the pane, keep the container.
- Keep the send-keys submit + `detect_outcome` path as the **steering adapter**, selected explicitly
  (a run/recipe hint) when mid-run interaction is required.
- The tmux **pane** is ephemeral (dies on command exit); the **container** persists, not the pane -
  scrape telemetry live during the run or set `remain-on-exit on`.
- Credentials: use the `.env` loader (PR #254) - `CLAUDE_CODE_OAUTH_TOKEN` (preferred) / API-key
  fallback for claude, `CODEX_AUTH_FILE` / `OPENAI_API_KEY` for codex; never the stale on-disk file.
- Completion detection MUST key on the `Stop` event name; `SubagentStop` is advisory (fires
  spuriously after `Stop`).

## References

- EXP-07 (stop-hook completion), EXP-08 (subscription auth + `-p`-on-Max), EXP-09 (mode vs
  command) - experiment records in `experiments/`, run 2026-07-07, evidence under
  `experiments/runs/EXP-0{7,8,9}/` (verified from container captures: written sentinels, session
  ids, token counts, `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` unset).
- ADR-038: Rust-first execution and contracts.
- ADR-035: Workspace injection contract.
- PR #247: `itmux run` contract + R7 orchestrator. PR #254: `.env` credential loader.
- pi.recipes / introspection.dev - prior art for the recipe artifact (see the recipe standard).
