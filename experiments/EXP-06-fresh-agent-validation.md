# EXP-06 — Fresh-Agent Validation of the interactive-tmux provider

Status: **in-flight** (hypothesis frozen 2026-06-10 before any probing)
Branch: `agentprims-exp06`
Provider under test: `providers/workspaces/interactive-tmux/`

## Context (one sentence)

EXP-05 built a new Docker workspace provider, `providers/workspaces/interactive-tmux`,
that runs interactive `claude`/`codex`/`gemini` CLIs in tmux panes inside a
container and drives them from the host via `docker exec tmux send-keys` /
`tmux capture-pane`. EXP-06 asks whether a fresh agent can use that provider
**from its own documentation alone** — i.e. without reading EXP-01..05, the
FRICTION files, or any other agent's report.

## Hypothesis

> The provider's docs (`providers/workspaces/interactive-tmux/README.md` plus
> the `interactive-tmux` row in `providers/workspaces/README.md`) are
> sufficient for a newcomer with no lab context to:
>
> 1. build (or reuse) the image,
> 2. start a workspace, and
> 3. round-trip exactly one prompt+response through each of the three agent
>    CLIs (`claude`, `codex`, `gemini`) without referring to any other
>    document or guessing at undocumented behaviour.

If H is true, an integration consumer like Syntropic137 can adopt this
provider just by reading the provider directory. If H is false, the doc-gap
list at the bottom of this report identifies the cheapest patches.

## Method

1. **Constraints (self-imposed before reading anything):**
   - Read only `providers/workspaces/interactive-tmux/**` and the
     `interactive-tmux` row of `providers/workspaces/README.md`. Nothing
     under `experiments/` (including EXP-05) or any FRICTION/handoff file.
   - Use throwaway COPIES of host credentials per the docs. Never bake or
     commit credential bytes.
   - Stay on branch `agentprims-exp06`.

2. **Steps (each is one row in the results table below):**
   - **Build** — follow the doc's Build section verbatim.
   - **Smoke test** — follow the doc's Smoke test section verbatim
     (`bash providers/workspaces/interactive-tmux/scripts/smoke.sh`). This
     is the simplest documented integration: one prompt+capture per agent.
   - **Python driver round-trip** — follow the doc's "Host-side driver"
     Python example verbatim (`InteractiveTmuxWorkspace.start_workspace`,
     `send_message`, `await_completion`, `capture_response`) for each of
     `claude`, `codex`, `gemini`.

3. **Doc-gap accounting (recorded in real time):**
   For each step, record verbatim:
   - what the doc said,
   - what actually happened,
   - what I had to do that the doc did not say.
   No silent improvisation: if I had to deviate from the docs to make
   something work, it counts as a doc gap (the verdict cares about whether
   a newcomer with only the docs could land it).

## Result placeholders (filled in below after probing)

| # | Step | Outcome | Doc-gap count |
|---|------|---------|---------------|
| 1 | Build per docs | TBD | TBD |
| 2 | Smoke test per docs (3 agents) | TBD | TBD |
| 3 | Python driver round-trip per docs (3 agents) | TBD | TBD |

Per-agent verdict (filled in after probing):

| Agent  | Smoke pass/fail | Python driver pass/fail | Notes |
|--------|-----------------|--------------------------|-------|
| claude | TBD             | TBD                      |       |
| codex  | TBD             | TBD                      |       |
| gemini | TBD             | TBD                      |       |

## Doc-gap log (recorded verbatim as encountered)

(empty at hypothesis freeze — populated during probing)

## Verdict

(to be written after results are in)
