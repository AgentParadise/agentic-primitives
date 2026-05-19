# Body-usefulness methodology

The depth document for the body-usefulness test: paired `claude -p` runs of the same prompt with and without the plugin loaded, qualitative comparison of the two responses, and a judgment about whether the skill body earns its lines.

## Sources

- Empirical study: `../../../docs/superpowers/specs/2026-05-14-routing-test-results.md` (Experiment 3 documents the paired-run methodology and the two worked examples summarized below).
- Chassis: `../SKILL.md` (Principle 7, "Body usefulness is comparative, not absolute," and the body-usefulness-test-mode workflow).
- Authoring contract: `../../authoring-skills/SKILL.md` Principle 9, "Encode opinions the baseline would not produce."

## Why body usefulness needs an empirical test

Routing tests answer a single question: does the right skill load for the right prompt? They say nothing about whether the loaded content was worth loading. A skill can pass every routing prompt in its matrix and still produce content baseline Claude would have written from general knowledge. Routing without usefulness is overhead: cache weight, token spend, and reviewer attention spent on a body that adds no marginal signal over the model's own training.

The body-usefulness test isolates the plugin's marginal contribution. Same prompt, same model, same auth, same other plugins enabled, no session persistence. The only delta is whether `--plugin-dir` is passed. Whatever changes between the two responses is what this plugin's body contributed. That isolation is what makes the test honest: any other variable (a different prompt, a different model, a warm session) would let baseline cleverness or accumulated context confound the comparison.

## The paired-run protocol

Step by step:

1. Pick a representative user prompt. Real user phrasings, not meta-questions about the skill ("how do I do X?" not "which skill handles X?"). A good prompt comes from a transcript, a teammate's Slack question, or another agent's phrasing. Author-written prompts overfit the description.

2. Run A, with plugin:

   ```bash
   claude -p --plugin-dir <plugin-path> \
     --output-format text \
     --dangerously-skip-permissions \
     --no-session-persistence \
     "$PROMPT" > with-plugin.md
   ```

3. Run B, without plugin: identical command, minus `--plugin-dir`. Output to `without-plugin.md`.

   ```bash
   claude -p \
     --output-format text \
     --dangerously-skip-permissions \
     --no-session-persistence \
     "$PROMPT" > without-plugin.md
   ```

4. Read both side by side. Two terminal panes or a diff tool work; the comparison is qualitative, not mechanical, so reading is the right operation.

5. Compare on the criteria in the next two sections.

Use the same prompt verbatim across both runs. Any drift (paraphrase, reordered clauses, trailing whitespace differences that get auto-stripped by a shell) invalidates the comparison. If the prompt is multi-line, pipe it from a heredoc or a file so both runs receive byte-identical input.

## What "earns its lines" means

The body earns its lines when the with-plugin response contains at least one of:

- **A validated stack opinion the baseline would not produce.** Specific pinned versions ("Playwright 1.49 with bundled Chromium, not system Chrome"), rejected alternatives with rationale ("MCP delivery costs 5-20 KB of schema per turn, not worth it for this use"), project-specific recommendations that come from a lab pilot rather than from general best practice. The signal is that the recommendation reads dated and opinionated, not encyclopedic.

- **A cross-skill handoff naming a sibling concern.** "Extract the `traceparent` from the captured request header and hand it to telemetry-query for backend trace lookup" is a handoff: it names a sibling skill, a specific data shape, and the boundary at which control transfers. "Use a logger" or "consider observability" is not a handoff; it is a category reminder.

- **An anti-pattern that comes from project experience.** "Feeding the full screencast frame-by-frame to the model: vision tokens explode" came from running this in the harness lab. "Use try/except" or "watch out for race conditions" is general best practice the model already knows. The signal is specificity to the stack and a stated cost.

- **A recommendation explicitly tied to a stated outcome.** "Per-invocation Chromium because the per-worktree isolation outcome lives at the app port, not the browser process" is laddered: it cites the outcome the choice serves, and an auditor can check that the ladder still holds when tools change. "Use Chromium" is bare advice with no anchor.

Any one of these is sufficient. The test is not cumulative scoring; the question is whether the with-plugin response carries content the baseline would not.

## What "framing-only" means

Sometimes the with-plugin response is similar to baseline in content but adds structural value: explicit cross-references to sibling concerns ("see also telemetry-pipeline for the collector-side enrichment"), anti-patterns observed in the wild ("dead worktrees and orphan databases accumulate within a week"), outcomes phrased as goals ("the isolation outcome is one-task-one-port, not one-task-one-container"). This is framing-only contribution.

Framing-only skills can earn their lines. A reader who already knows the territory still benefits from the goal-shaped framing and the cross-references that route them to adjacent depth. But framing-only skills warrant a check: is the framing valuable enough to justify the body's loaded weight, or should the framing be condensed into a shorter body with depth pushed down into `references/`? If the body could shrink to 100 lines without losing the framing, shrink it. The cache cost of a 400-line body that adds 100 lines of unique framing is paid every time the skill loads.

## When baseline already has the answer

Some skills overlap with widely-known practices baseline Claude already knows: git worktrees, JSON logging, basic CI patterns, conventional commits, common test-pyramid advice. In those cases, the with-plugin marginal contribution is smaller. This is a fair finding, not a failure of the test.

The skill still earns its lines if it adds:

- Opinions baseline lacks (validated versions, rejected alternatives with rationale).
- Framing baseline lacks (outcomes, cross-references to sibling skills, anti-patterns from project experience).
- Hard-won project experience (specific bug patterns, teardown discipline, the secrets-do-not-`cp` discipline that came from a real rotation incident).

If a skill on widely-known ground adds none of those, the body may be a candidate for trimming. The skill might collapse into a one-line cross-reference inside an adjacent skill, or move its depth to `references/` and shrink its body to a short anchor. Audit such skills against `authoring-skills` Principle 9 before deciding to keep the full body.

## Other plugins muddying the baseline

Baseline Claude in a user's normal environment has access to whatever other plugins are enabled (superpowers, sdlc, software-leverage-points, ui-ux-pro-max, and so on). Some of those plugins have overlapping skills. `superpowers:using-git-worktrees` overlaps with this plugin's `worktree-isolation`. The `sdlc:testing-expert` skill overlaps with parts of `application-legibility`.

When the without-plugin run still has those other plugins available, the baseline is not a pure baseline. It is "harness-engineering not loaded, everything else loaded." The delta the test measures is the marginal contribution over a richer baseline. This is the right comparison for most users (the user's actual environment is rich, not bare), but the write-up should name it. Note in the test record which other plugins were active in the baseline run, and note when the baseline invoked a sibling-plugin skill. Do not pretend it is pure-baseline; the comparison is honest about the environment.

If a pure-baseline measure is needed, the only honest way to get it is to disable all other plugins before Run B. That is more work, and most teams will not bother. Naming the muddying is enough for most use cases.

## Two worked examples from the v0.2.1 validation

Both examples are drawn from Experiment 3 of the 2026-05-14 routing-test-results study. See the source spec for the full prompts and verbatim Run-A / Run-B outputs.

### Test 3a: browser-legibility

Prompt asked the agent to walk through wiring up browser eyes for a coding-agent debugging harness, with components, key choices, and pitfalls, under 400 words.

Large delta. With-plugin uniquely produced:

- Explicit rejections of MCP-server delivery (with the per-turn schema-cost rationale), Puppeteer, Browserless, Stagehand, and Browserbase. The rejections cite the harness-lab pilot, not general opinion.
- Per-invocation Playwright-bundled Chromium with no container and no port allocation. The choice is tied to the per-worktree isolation outcome.
- ffmpeg keyframe-grid pattern: WebM for humans, grid for the agent, vision-token-aware.
- Cross-stack handoff: extract `traceparent` from captured request headers and pass to `telemetry-query` for backend trace lookup. The handoff names a sibling skill and a specific data shape.
- Anti-pattern: "feeding the full screencast frame-by-frame to the model: vision tokens explode." Project-specific cost, not general advice.

Without-plugin produced competent generic advice: `getByRole`, `getByTestId`, `storageState`, `.har` for network logging, reduced-motion CSS for diff stability. Useful, but the kind of content the model can produce from training alone.

Verdict: the body earns its lines. The plugin's marginal contribution is large because the content encodes harness-lab-validated opinions baseline would not produce.

### Test 3b: worktree-isolation

Prompt asked how to set up per-task isolation for two coding agents stepping on each other (port 3000 collisions, shared Postgres, interleaved logs), under 400 words.

Smaller delta. The baseline run was assisted by `superpowers:using-git-worktrees`, a sibling-plugin skill that covers overlapping ground. This made the without-plugin comparison a "richer baseline" comparison, not pure-baseline.

With-plugin still added:

- Hash-derived port allocation from the worktree slug, so the same worktree gets the same port every boot. Deterministic, project-specific discipline.
- OTel resource-attribute attachment cross-referencing telemetry skills. Names the sibling concern.
- Teardown reaper and weekly cleanup discipline, with the project-experience observation that dead worktrees and orphan databases accumulate within a week.
- Secrets-do-not-`cp .env` principle, anchored on rotation drift.

Without-plugin (assisted by the sibling skill) produced its own valuable content: named layers (filesystem, runtime, logs), `COMPOSE_PROJECT_NAME` for Compose namespacing, `jq` filtering on a `task` field, a concrete justfile recipe, and a "don't coordinate, isolate" principle.

Verdict: the body earns its lines, but by a smaller margin. Where the plugin encodes harness-lab-validated opinions (slug-derived port allocation, teardown reaper, secrets discipline), the delta is real. Where it covers widely-known practice (git worktrees as a concept), the baseline (richer for having a sibling skill) closes most of the gap. The plugin still wins on framing, cross-references, and project-specific discipline.

Summary across both tests: where the plugin encodes opinions baseline would not generate, the delta is large. Where it covers widely-known ground, the delta is smaller but framing and cross-references still earn the lines.

## When to run a body test

- When authoring a new skill, before merge. Confirms the body contributes something baseline does not.
- When the description changes substantively. The new triggers may pull the skill into prompts the body was not written for; the body may need refreshing to match.
- When auditing an existing skill against `authoring-skills` Principle 9. The body test is the empirical answer to "would the user get a meaningfully different answer without this skill loaded?"
- As part of a periodic plugin-wide sweep, especially after the underlying stack (tools, versions, sibling plugins) shifts.

## When NOT to run a body test

- For minor wording fixes to the body. The structure is unchanged; the test would not differ.
- For procedural skills whose body is a workflow rather than opinion content. Routing tests are sufficient; the workflow's correctness lives in its steps, not in its comparative novelty.
- For maintenance skills the user never sees the body of directly (skills that exist to coordinate other skills, or to declare a non-trigger boundary). The body test does not apply when the body is structural.

## Cost

Two `claude -p` calls per skill under test. Each call costs roughly the same as a routing-test call; the system prompt and the loaded skill descriptions hit cache after the first call in a batch, so per-call new-token cost is low. Pair-testing two or three skills in a sitting costs a few cents. Pair-testing the full plugin is bounded by the number of skills (12 in v0.2.1: roughly 24 calls, well under a dollar).

The cost is small enough that the test should not be skipped on cost grounds. The reason to not run it is one of the "when NOT to" cases above, not the API spend.

## Cross-references

- `./routing-test-methodology.md`: the sibling test mode that answers "does the right skill load?"
- `./flake-handling.md`: meta-routing-table phenomenon and retry rules. Relevant if a paired run produces unexpected meta output from one side.
- `../SKILL.md`: the skill-testing chassis, including the body-usefulness-test-mode workflow this document expands.
- `../scripts/`: shell scripts for the routing-test runner. There is no dedicated body-test runner; the protocol above is two manual `claude -p` invocations and a visual diff, which is right-sized for the qualitative comparison.
- `../../authoring-skills/SKILL.md` Principle 9: the authoring-side statement of "encode opinions the baseline would not produce," which this test empirically validates.
- `../../../docs/superpowers/specs/2026-05-14-routing-test-results.md`: the empirical study, including the verbatim Run-A and Run-B outputs for both worked examples.
