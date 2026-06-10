# EXP-06 — Fresh-Agent Validation of the interactive-tmux provider

Status: **DONE**
Branch: `agentprims-exp06`
Provider under test: `providers/workspaces/interactive-tmux/`
Date: 2026-06-10

## Context (one sentence)

EXP-05 built a new Docker workspace provider, `providers/workspaces/interactive-tmux`,
that runs interactive `claude`/`codex`/`gemini` CLIs in tmux panes inside a
container and drives them from the host via `docker exec tmux send-keys` /
`tmux capture-pane`. EXP-06 asks whether a fresh agent can use that provider
**from its own documentation alone** — i.e. without reading EXP-01..05, the
FRICTION files, or any other agent's report.

## Hypothesis (frozen 2026-06-10 before any probing)

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

2. **Three documented paths exercised (each row in the results table):**
   - **A — Build** — followed the doc's Build section verbatim
     (`just build-provider interactive-tmux`).
   - **B — Smoke test** — followed the doc's Smoke test section verbatim
     (`bash providers/workspaces/interactive-tmux/scripts/smoke.sh`).
   - **C — Python driver round-trip** — followed the doc's "Host-side
     driver" Python example verbatim
     (`InteractiveTmuxWorkspace.start_workspace`, `send_message`,
     `await_completion`, `capture_response`, `stop`) for each of
     `claude`, `codex`, `gemini`. Test script at
     `/tmp/exp06_driver_test_save.py`.

3. **Doc-gap accounting (recorded in real time, see § Doc-gap log):**
   For each step I recorded verbatim what the doc said vs what I had to do
   that the doc did not say. No silent improvisation: every deviation
   counts as a doc gap.

## Results

Counts: 3 documented paths (A,B,C) × {1 build run, 3 agents × 1 prompt
round-trip in smoke, 3 agents × 1 prompt round-trip in Python}. Total
agent round-trips covered by this report: **6** (3 in smoke + 3 in
Python). One additional CLI-shim round-trip was run for `claude` only as
a corroborating probe of the docs' "CLI shim is bundled for shell-script
consumers" section.

| # | Step                                                | Outcome                              | Doc-gap count |
|---|-----------------------------------------------------|--------------------------------------|---------------|
| A | Build per docs                                      | PASS (image tagged `:latest` + `:2.1.126`) | 0     |
| B | Smoke test per docs (3 agents × 1 prompt)           | PASS 3/3 (marker+token on same line) | 0             |
| C | Python driver round-trip per docs (3 agents × 1 prompt) | PASS 3/3 (marker+token on same line) | **1** (import) |

Per-agent verdict (1 prompt each, run twice — once via smoke, once via Python):

| Agent  | Smoke pass/fail | Python driver pass/fail | Token observed                      |
|--------|-----------------|--------------------------|-------------------------------------|
| claude | PASS            | PASS                     | `● SMOKE-CLAUDE-2705074`, `● EXP06-PY-CLAUDE` |
| codex  | PASS            | PASS                     | `• SMOKE-CODEX-2705074`,  `• EXP06-PY-CODEX`  |
| gemini | PASS            | PASS                     | `✦ SMOKE-GEMINI-2705074`, `✦ EXP06-PY-GEMINI` |

Transcript evidence:

- `providers/workspaces/interactive-tmux/runs/smoke-{claude,codex,gemini}.txt`
  — written by `scripts/smoke.sh` during step B.
- `providers/workspaces/interactive-tmux/runs/exp06-py-{claude,codex,gemini}.txt`
  — written by `/tmp/exp06_driver_test_save.py` during step C.

Both sets show the per-agent response marker prefixed in front of the
echo token on the same line, which is the same correctness rule the
provider's own smoke script applies (`grep -qF "${MARKER}${TOKEN}"`).

## Doc-gap log (verbatim observations during probing)

**Gap 1 (Python import not explained) — severity: low, blocking for step C.**

- **What the doc said** (README.md, "Host-side driver" section):
  > ```python
  > from interactive_tmux import InteractiveTmuxWorkspace
  > from pathlib import Path
  > ```
- **What actually happened:** copy-pasting that line into `/tmp/exp06_driver_test.py`
  and running `python3 /tmp/exp06_driver_test.py` gave
  `ModuleNotFoundError: No module named 'interactive_tmux'`.
- **What I had to do that the doc did not say:** set
  `PYTHONPATH=providers/workspaces/interactive-tmux/driver` before running.
  The driver is a single file, not a package on PyPI; the README never
  mentions installation, packaging, or `PYTHONPATH`. A consumer outside
  this repo (e.g. Syntropic137) has no documented integration path —
  they have to figure out from filesystem inspection that the importable
  module lives at `providers/workspaces/interactive-tmux/driver/interactive_tmux.py`.
- **Cheapest patch:** one line under the Python example, e.g.
  `# Assumes providers/workspaces/interactive-tmux/driver is on sys.path.`
  Optionally followed by either a `pyproject.toml`/wheel exposing the
  module or a documented `sys.path.insert(0, ...)` recipe.

**Gap 2 (CLI shim cwd not stated) — severity: low, non-blocking.**

- **What the doc said** (README.md, immediately after the Python block):
  > ```bash
  > python3 driver/interactive_tmux.py start  --name w1
  > ```
- **What actually happened from a different cwd (`/tmp`):**
  `python3: can't open file '/tmp/driver/interactive_tmux.py': [Errno 2] No such file or directory`.
- **What I had to do:** `cd` to `providers/workspaces/interactive-tmux/`
  first, then re-run.
- **Cheapest patch:** prefix the snippet with a comment or absolute path,
  e.g. `# from providers/workspaces/interactive-tmux/` or use the path
  relative to repo root throughout.

**Gap 3 (pre-reqs only in `smoke.sh`, not in README) — severity: low, non-blocking on this box.**

- **What the doc said** (README.md, "Smoke test"): just the bash
  invocation, no listed pre-reqs.
- **What actually happened:** worked first try, because (a) the image
  exists (I built it in step A) and (b) the box has `~/.claude`,
  `~/.codex`, `~/.gemini` authed.
- **What I had to do that the doc did not say:** nothing — but only
  because I'd already done step A. On a cold box, a user reading **only**
  the README's "Smoke test" section would not learn that the image must
  be built first or that all three host auth dirs must already exist.
  The pre-reqs are listed in `scripts/smoke.sh`'s header comments
  ("Image agentic-workspace-interactive-tmux:latest built ...",
  "~/.claude, ~/.codex, ~/.gemini present on host (authed)"). They
  belong in the README too, because new users don't read scripts before
  running them.
- **Cheapest patch:** copy the smoke.sh comment block under the README's
  Smoke-test section as a bullet list.

**Gap 4 (undocumented startup warning) — severity: cosmetic.**

- **What the doc said:** nothing about per-agent readiness warnings
  during `start`.
- **What actually happened:** on one of two CLI-shim `start` calls the
  driver logged:
  `WARNING wait_for_text(codex, 'gpt-') timed out after 45.0s` and
  *still* returned `{"name": ..., "container": ..., "agents":
  [...]}`. The workspace was usable afterwards (sending to claude worked
  fine). Not a functional bug, but a newcomer might assume `start`
  failed.
- **Cheapest patch:** one sentence in the README's "What this provider
  does NOT do (today)" section, e.g. "`start` returns when *any* agent
  pane is ready; per-agent timeouts emit warnings but do not fail the
  call. Validate readiness per agent before sending."

### What the docs got positively right (kept me out of trouble)

- The per-agent matrix in the README (Launch / Submit / Readiness / Auth
  mount) explains *why* the driver is doing what it's doing — without it
  I would have plausibly guessed `Enter` on codex and tripped the
  documented first-send gotcha. I never had to act on it because the
  driver hides it, but reading the matrix changed my mental model from
  "tmux is tmux" to "each CLI has its own keystroke envelope; trust the
  driver". That is a real docs win.
- The "Claude auth: `.credentials.json` vs `.claude.json`" section
  pre-empted the question I was about to ask (`host_auth["claude"]`
  takes a directory, but Claude also reads a file at `$HOME`; the docs
  say the driver synthesises both). I would not have guessed this.
- The "Credentials are NEVER baked or committed" paragraph matches
  observed behaviour: the image carries no credential bytes and the
  driver mounts throwaway host-side copies, so my "do not commit secrets"
  guard rail is enforced by the provider, not by me.

## Verdict

**Hypothesis upheld for steps A and B (build, smoke). Hypothesis
partially upheld for step C (Python driver): the API call sequence in
the README example is correct, but the import line is not actionable as
written.**

Score per agent (1 prompt per path; 2 paths = smoke + Python; passing
needs marker+token on the same line in each transcript):

- claude: **2/2 PASS**
- codex:  **2/2 PASS**
- gemini: **2/2 PASS**

Could a newcomer (or Syntropic137's integration code) use this provider
from the docs alone?

- **Via the smoke script: yes**, once they've also read the pre-req
  comment block at the top of `smoke.sh` (which the README should pull
  forward — Gap 3).
- **Via the Python driver: yes after a one-line patch** (Gap 1 —
  "how do I make `from interactive_tmux import ...` resolve?"). With
  that patch, the README's example is end-to-end correct as written.
- **Via the CLI shim: yes**, with a one-line clarification that the
  shim's paths are relative to `providers/workspaces/interactive-tmux/`
  (Gap 2).

The docs **changed what I did** in two ways: (1) the per-agent quirk
matrix kept me from re-deriving the keystroke envelopes from scratch,
and (2) the auth-mount explainer kept me from passing the wrong path
shape into `host_auth`. They **did not change what I did** for the
build and smoke-test paths, which were straightforward command runs.

Net: the provider is shippable to a fresh consumer today, with **3 small
README patches recommended** to remove the four gaps above. None of the
gaps are architectural; all are one-liner clarifications. EXP-05's
"5/5 PASS" verdict on the provider's transport survives this
independent re-test (3/3 agents × 2 paths = 6/6 here).
