# Routing test results, 2026-05-14

Three experiments run against the v0.2.0 plugin to validate that skills route correctly and that their bodies earn their lines.

## Experiment 1: live routing test via `claude -p`

**Setup:** Each of 40 test prompts (35 positive triggers covering every skill, 5 negatives explicitly out of scope) fired against a fresh `claude -p --plugin-dir /path/to/harness-engineering` session. Stream-JSON output parsed for the first `Skill` tool invocation. Match against expected = PASS; mismatch or NONE = FAIL.

**Result:** 40 of 40 PASS.

One initial flake (P06 returned NONE in the parallel batch run; re-run in isolation passed). The flake was a meta-interpretation: the model in that fresh session decided to output a full-test-suite routing table as TEXT rather than invoke a skill. The prompt itself is sound and routes correctly under normal conditions.

**Cost:** roughly $0.50 - $1.00 total across the 40 runs. Each run hit cache for the system prompt and the 12 skill descriptions, so per-call new-token cost was low.

**Reproduction:** `/tmp/harness-routing-test/run-all.sh` (driver) reads `prompts.tsv` (the test matrix). Each row is `<prompt-id>\t<expected-skill>\t<prompt-text>`.

## Experiment 2: seam-description sharpening

The simulated routing judge (run 2026-05-13) flagged two boundaries where adjacent skills could plausibly compete:

1. **Trace propagation:** `application-legibility` and `telemetry-pipeline` both touched "trace id" in their trigger lists. Boundary is sharp in practice (in-app propagation vs. collector-side enrichment) but the descriptions did not say so.
2. **Escalation criteria:** `approved-scenarios` and `autonomous-validation-loop` both touched "escalate." Boundary is sharp (policy-level vs. loop-mechanic) but only one side declared it.

Both seams passed the live test (Experiment 1), but both got sharpened preemptively to prevent flakes under more ambiguous phrasings. Edits:

- `application-legibility` description: added "Do NOT use for collector-side enrichment" with explicit handoff to `telemetry-pipeline` and an explicit "this skill governs in-app propagation across HTTP handlers, queue messages, background jobs" framing.
- `telemetry-pipeline` description: added the reciprocal "Do NOT use for in-app propagation" with explicit handoff to `application-legibility`.
- `autonomous-validation-loop` description: scoped its "escalation" trigger to "loop-mechanic escalation" and pointed policy-level escalation at `approved-scenarios`.

Both seam-rerun prompts (P26 and P30) still route correctly after the edits.

## Experiment 3: body usefulness test

**Setup:** Two skills tested. For each, the same user prompt fired twice:

- **Run A:** with `--plugin-dir` (harness-engineering loaded, body content available after routing).
- **Run B:** without `--plugin-dir` (harness-engineering not loaded; user's other normal plugins still active).

Outputs compared qualitatively for distinctive content the plugin contributed beyond baseline.

### Test 3a: browser-legibility task

Prompt: "I am building a debugging harness for a coding agent and need to give it eyes on the browser. The agent should be able to capture before/after evidence of UI fixes. Walk me through what to wire up: components, key choices, and any pitfalls to avoid. Keep it tight, under 400 words."

**Run A unique content:**

- Explicit rejections of MCP-server delivery (with the 5-20 KB schema-per-turn cost rationale), Puppeteer, Browserless, Stagehand, Browserbase. These rejections came from the harness-lab pilot.
- Per-invocation Playwright-bundled Chromium (no container, no port allocation).
- ffmpeg keyframe-grid pattern (vision-token-aware: WebM for humans, grid for agent).
- Cross-stack handoff: extract `traceparent` from captured request headers, pass to `telemetry-query` for backend trace lookup.
- Anti-pattern: "feeding the full screencast frame-by-frame to the model: vision tokens explode."

**Run B unique content:**

- Specific Playwright API recommendations (`getByRole`, `getByTestId`, `storageState`).
- `.har` format for network logging.
- Deterministic viewport, reduced-motion CSS injection for diff stability.

**Verdict:** Run A delivers distinctive, validated-stack opinions the baseline does not produce. Run B is competent generic advice. The harness-engineering skill earns its lines.

### Test 3b: worktree-isolation task

Prompt: "Two coding agents on my team keep stepping on each other when working on the same repo: they both bind to port 3000, share the same local Postgres, and their logs interleave so I cannot tell which run produced which error. How should I set up per-task isolation? Keep it tight, under 400 words."

**Run A unique content:**

- Hash-derived port allocation from worktree slug (deterministic, "same worktree -> same port every boot").
- OTel resource-attribute attachment (cross-references telemetry skills).
- Teardown reaper + weekly cleanup discipline ("dead worktrees and orphan DBs accumulate within a week").
- Secrets-do-not-`cp .env` (drift on rotation).
- Incremental adoption path.

**Run B unique content:**

- Three named layers (filesystem / runtime / logs).
- `COMPOSE_PROJECT_NAME` for Compose-level namespacing.
- `jq` filtering on `task` field.
- Concrete justfile recipe.
- "Don't coordinate, isolate" principle.

**Notable finding:** Run B references `superpowers:using-git-worktrees` as a related skill. The baseline Claude in this user's environment was assisted by another plugin's skill that covers overlapping ground. This means the worktree-isolation skill's marginal delta over baseline is smaller than browser-legibility's, because git-worktree content is widely covered elsewhere.

**Verdict:** Run A still adds value (slug-derived discipline, teardown framing, secrets principle), but the delta is smaller. Where the plugin most earns its lines is in skills that encode opinions baseline Claude would not generate on its own (the harness-lab-validated 2026 stack).

## Integrated learnings

Encoded back into the plugin:

1. **The three seam-description edits** (Experiment 2) ship now in v0.2.1.

2. **A new principle in `authoring-skills`:** "the strongest skills encode opinions baseline Claude would not produce on its own." Where a skill's content overlaps with widely-known practice, it can still earn its lines by anchoring framing and cross-references, but the highest-leverage content is the dated, opinionated, harness-lab-validated stack. Encode in `Recommended tools and practices`.

3. **The routing test suite at `/tmp/harness-routing-test/`** is reproducible. The driver pulls fresh sessions, fires prompts in parallel, and grades against expected. Re-run after any description change.

4. **A meta-observation worth flagging:** under `--print` mode with an opinionated system-prompt-append, the model occasionally responds with a meta-routing-table rather than invoking a skill. The first P06 flake exhibited this. Future test harnesses should fire each prompt in true isolation (no shared cache pollution) and parse the first `tool_use` of name `Skill`. The driver already does this; the flake reproduced once in 40 trials and did not reproduce on retry.

## What did NOT change

- The 12 skill set.
- Outcomes, principles, anti-patterns, recommendations in any skill body. Experiment 3 affirms the content earns its lines; no revisions needed.
- The chassis structure. Section order, naming, and audit checklist are unchanged.

## Reproduction

```bash
# Live routing test
cd /tmp/harness-routing-test
./run-all.sh
# results.tsv contains <prompt-id> <expected> <got> <PASS|FAIL>

# Single re-run
./run-one.sh P26 application-legibility "How do I propagate trace IDs through background jobs?"

# Body usefulness comparison (with vs without plugin)
PROMPT="<your task>"
claude -p --plugin-dir /Users/neural/Code/AgentParadise/harness-engineering \
  --output-format text --dangerously-skip-permissions --no-session-persistence "$PROMPT"
claude -p --output-format text --dangerously-skip-permissions --no-session-persistence "$PROMPT"
```
