---
name: skill-testing
description: Use when validating that a Claude skill routes correctly and that its body earns its lines. Trigger phrases include "test the skill", "test routing", "is my skill triggering", "skill routes wrong", "wrong skill fires", "validate the skill", "skill audit empirically", "routing regression test", "body usefulness test", "is the skill actually useful", "with vs without the skill", "compare skill loaded vs baseline", "claude -p plugin-dir test", "skill not firing for prompt", "false positive skill activation". Covers two test modes: routing tests (does Claude invoke the expected skill given a realistic user prompt?) and body usefulness tests (does the skill body produce a meaningfully better answer than baseline Claude?). Applies to skills in this plugin, in other plugins, and to personal `~/.claude/skills` or project-local `.claude/skills/`. Do NOT use for authoring a new skill from scratch (use `authoring-skills`); do NOT use for general software test discipline (use software-leverage-points `testing`).
---

# Skill Testing

## Overview

A skill is two contracts wrapped in one file. The `description` is the routing contract: does Claude invoke the skill for the right prompts and only those prompts? The body is the usefulness contract: when invoked, does the content produce a meaningfully better answer than baseline Claude would have produced on its own? Both contracts can be tested mechanically. This skill is the test methodology.

Routing tests fire a battery of realistic user prompts at a fresh `claude -p` session with the plugin loaded, capture the first `Skill` invocation per call, and grade against an expected-skill matrix. Body usefulness tests fire the same prompt twice (once with the plugin, once without) and compare what changed. Together they answer the two questions that decide whether a skill earns its place.

## Outcomes we are looking for

### Outcome 1: routing failures are caught before users see them

The skill invokes for the prompts it should and stays quiet for the prompts it should not.

- *Signal:* every entry in a positive test matrix routes to its expected skill; every entry in a negative matrix returns NONE.
- *Signal:* when a description changes, the test matrix re-runs and either still passes or surfaces the exact prompts that now misroute.

### Outcome 2: bodies are verified to earn their lines empirically

The skill body produces content the baseline would not produce. Where the delta is small, the skill is at least anchoring framing or cross-referencing siblings.

- *Signal:* a with-plugin response contains opinions, validated stack versions, or cross-skill handoffs not present in a without-plugin response on the same prompt.
- *Signal:* where the delta is small, the author can articulate what structural value (framing, cross-references) the skill still provides.

### Outcome 3: tests are reproducible and cheap

Re-running the full suite is a single command. Cost stays bounded.

- *Signal:* the test runner is shell-scripted, parallelizable, and produces a tabular PASS/FAIL artifact.
- *Signal:* a 40-prompt routing pass costs under one dollar of API and finishes in under fifteen minutes.

### Outcome 4: flakes are distinguished from real failures

The model occasionally responds meta-style under `--print` mode (e.g., returning a routing table as text instead of invoking a Skill). A real failure reproduces on retry; a flake does not.

- *Signal:* every FAIL gets a single-prompt rerun before being treated as a description gap.
- *Signal:* known flake patterns (meta-routing-table, system-prompt-append over-influence) are documented and recognizable by the next reviewer.

### Outcome 5: testing is the integration step, not the afterthought

Tests run before declaring a skill done, not after users complain.

- *Signal:* description changes are accompanied by a test run.
- *Signal:* new skills land with at least 3 positive triggers and 1 negative control in the matrix.

## Principles

1. **Routing and usefulness are separate problems.** Triggering is a description problem; body content is a body problem. Test them with different methodologies and do not co-fix them. A misrouted skill cannot have its body tested honestly; a useless body still routes correctly.

2. **Test against fresh sessions.** `claude -p` with no session persistence and no prior conversation history is the only honest routing test. A live conversation has already loaded the skill's body and biases the next decision.

3. **The first `Skill` invocation is the routing answer.** Parse the stream-json output, find the first `tool_use` with `name: Skill`, read the `skill` input. That is the routing decision. Subsequent tool uses are downstream work, not routing signal.

4. **Negative controls are first-class.** A test matrix that contains only positive triggers measures only over-pulling, not under-pulling. Add 5+ prompts that should explicitly route to NONE (or to a sibling plugin) to catch descriptions that have grown too broad.

5. **Seam prompts test the boundary, not the center.** For every pair of adjacent skills, write at least one prompt that sits on the boundary. Center-of-mass prompts pass trivially; boundary prompts catch description drift.

6. **Flakes get retried, real failures get fixed.** A single FAIL on a batch run gets re-run in isolation before being treated as a description gap. The model exhibits occasional meta-routing-table responses under `--print` with opinionated system-prompt-appends; these are not description failures and should not be conflated.

7. **Body usefulness is comparative, not absolute.** A skill earns its lines when its response is meaningfully different from a no-plugin baseline. "Meaningfully different" means at least one of: a validated stack opinion the baseline would not produce, a cross-skill handoff the baseline would not name, an anti-pattern that comes from project experience, a recommendation tied to a stated outcome.

8. **Run before merge, not after deploy.** Description changes are routing-contract changes. They get tested in the same PR that introduces them, the same way schema changes get a migration test.

## Anti-patterns

- **Test matrix consists only of positive triggers.** Catches over-broad descriptions but not under-pulling. Add explicit non-trigger prompts that should return NONE.
- **Tests run after deploy, not before merge.** Users discover routing failures before reviewers do. The matrix should run as a pre-merge step.
- **Single flake taken as a description failure.** A single FAIL on a batch run gets one retry. If the retry passes, the original was meta-interpretation noise, not a description gap.
- **Routing test asks Claude meta-questions.** "Which skill would you invoke?" measures Claude's introspection, not the actual routing decision. Real user-style prompts produce real routing.
- **Body usefulness test uses different prompts for the with-plugin and without-plugin runs.** The whole point is identical input, different config. Any prompt drift invalidates the comparison.
- **Stream-json output parsed for skill *content* instead of the first tool_use.** Skill body content appears later in the stream; only the first tool_use is the routing answer. Mixing them inflates pass counts with downstream-work signals.
- **Baseline run loads the skill via another route.** If a user has `superpowers:using-git-worktrees` enabled, a `worktree-isolation` baseline run will still get worktree advice from that skill. The test still informs but the delta is smaller than a pure-baseline comparison.
- **Test matrix never updated when descriptions change.** Stale matrices give false confidence. When a description gains a trigger phrase, add at least one prompt that exercises it.
- **All prompts written by the skill author.** The author's phrasings overfit the description. Realistic prompts come from users, transcripts, or another agent's phrasing.
- **Body usefulness judged on length or eloquence.** Longer is not better. The question is whether the response contains content the baseline would not have produced.
- **Live test skipped in favor of a routing-judge simulation alone.** Simulations are useful for early signal but the empirical claude -p test is the real measure. Do both: simulate during authoring, validate live before merge.
- **Test artifacts not committed.** When a test run reveals a routing issue, the matrix and the failure should land in the repo as evidence, not vanish from `/tmp`.

## How to use this skill: routing test mode

1. Build the test matrix at `<skill-or-plugin>/test/prompts.tsv` (or wherever the plugin convention places test artifacts). One row per prompt: `<id>\t<expected-skill>\t<prompt-text>`. Include 2-3 positive triggers per skill, 5+ negative controls, and 1+ seam prompt per adjacent-skill pair. See `references/test-matrix-template.md` for guidance on prompt selection.

2. Use the scripts under `scripts/`. `run-one.sh` fires a single prompt at `claude -p --plugin-dir <path>` with stream-json output, parses out the first `Skill` invocation, and reports PASS/FAIL. `run-all.sh` runs the full matrix in parallel batches and produces a sorted `results.tsv`.

3. Walk the FAIL rows. For each, re-run in isolation. If the rerun passes, the original was a flake (likely meta-routing-table interpretation; see `references/flake-handling.md`). If the rerun still fails, the description has a gap. Fix the description per `authoring-skills/references/description-trigger-rules.md`, then re-run only the previously-failing prompts to confirm.

4. Commit the results.tsv with the description change so reviewers see the evidence.

See `references/routing-test-methodology.md` for the full procedure including stream-json schema, parallel-batch cost optimization, and edge cases.

## How to use this skill: body usefulness test mode

1. Pick a representative user prompt for the skill under test. The prompt should be one a real user might type, not a meta-question about the skill.

2. Run the prompt twice in fresh `claude -p` sessions: once with `--plugin-dir <plugin-path>`, once without. Capture both responses as files. Both runs use the same model, the same auth, no session persistence; the only delta is whether the harness-engineering plugin is loaded.

3. Compare the responses. The skill body earns its lines if the with-plugin response contains at least one of:
   - A validated stack opinion the baseline would not produce (e.g., specific pinned versions, rejected alternatives with rationale)
   - A cross-skill handoff naming a sibling concern the baseline would not name
   - An anti-pattern that comes from project experience, not generic best practice
   - A recommendation explicitly tied to a stated outcome

4. If the delta is small, ask whether the skill is anchoring framing rather than producing distinctive content. Framing-only skills can earn their lines but warrant a check: is the cross-reference value enough to justify the body's lines, or should the content move to `references/` and the body shrink?

5. Where another plugin's sibling skill covers overlapping ground (e.g., `superpowers:using-git-worktrees` for worktree advice), note it. The plugin's marginal contribution is smaller in those areas, but not necessarily zero.

See `references/body-usefulness-methodology.md` for the full procedure.

## How to use this skill: pre-merge test gate

Combine routing and body modes as a checklist before merging a description change or a new skill:

1. Routing test for the modified skill: every prompt in the matrix PASSes.
2. Routing test for adjacent skills: seam prompts still route to the originally-expected skill, not the modified one (catches over-pull regressions).
3. For a new skill, body usefulness test: with-plugin produces at least one piece of distinctive content over without-plugin.
4. Commit the matrix and results next to the change.

If any step fails, the change is not ready. Fix and re-run.

## Recommended tools and practices (as of 2026-05-14)

### Outcome: routing failures are caught before users see them

- **`claude -p --plugin-dir <path>` as the test driver.** Loads the plugin for one session without modifying user settings.json. Ladders up by giving every test a fresh, repeatable routing decision.
- **`--output-format stream-json --verbose`** captures tool calls as parseable JSON lines. Ladders up by making the first `Skill` invocation extractable with a single `grep`.
- **`--no-session-persistence`** prevents the test run from polluting the user's session history. Ladders up by keeping tests hermetic.
- **`grep -oE '"skill":"<plugin>:[a-z-]+"' <stream-file> | head -1`** extracts the first invocation deterministically. Ladders up by making the test artifact a simple TSV that downstream tooling can grade.

### Outcome: bodies are verified to earn their lines empirically

- **Paired-run comparison.** Same prompt, two `claude -p` calls, one with `--plugin-dir` and one without. Save both outputs and diff. Ladders up by isolating the plugin's contribution.
- **Markdown side-by-side review.** Save outputs to `with-A.md` and `baseline-B.md`; read them in two terminal panes or in a diff tool. Visual comparison is faster than parsing scoring for small batches.

### Outcome: tests are reproducible and cheap

- **TSV test matrix.** One row per prompt; columns `id`, `expected`, `text`. Simple to read, simple to grep, simple to diff across versions. Ladders up by making the matrix a normal file that lives in git, not in a database.
- **Bash parallel batches.** macOS bash 3.2 does not support `wait -n`; use the "fire all background jobs, then wait" pattern with a batch counter. GNU parallel works too if installed.
- **Per-call max-budget flag (`--max-budget-usd 0.30`).** Caps cost per prompt. Ladders up by making a runaway test costable rather than a surprise on the invoice.
- **Cache-friendly invocation order.** Same system prompt across all calls means cache_read dominates after the first call. Ladders up by dropping the per-call cost an order of magnitude.

### Outcome: flakes are distinguished from real failures

- **Single-rerun policy.** Every FAIL gets one isolated re-run before being treated as a real failure. Ladders up by filtering out meta-interpretation noise that does not reproduce.
- **Documented flake patterns** in `references/flake-handling.md`. Ladders up by making "is this a flake or a real failure" recognizable, not a judgment call.

### Outcome: testing is the integration step

- **Test matrix lives in the repo.** Not in `/tmp`. Not in a Notion page. In a TSV next to the skill it tests. Ladders up by making the matrix versionable and reviewable in the same PR as the description change.
- **CI integration.** A future enhancement: wire the routing test to run on every PR that touches a `SKILL.md` description. Ladders up by catching routing regressions as part of the merge gate.

## References

- `references/routing-test-methodology.md`: full procedure, stream-json schema, parallel-batch optimization, cost guidance.
- `references/body-usefulness-methodology.md`: paired-run procedure, comparison criteria, framing-only-skill judgment calls.
- `references/test-matrix-template.md`: how to choose prompts, positive/negative/seam ratios, prompt-realism guidance.
- `references/flake-handling.md`: the meta-routing-table phenomenon, retry rules, known patterns.
- `scripts/run-one.sh`: single-prompt runner (PASS/FAIL output).
- `scripts/run-all.sh`: full-matrix parallel batch runner.
- `scripts/prompts.tsv.example`: an example test matrix drawn from the harness-engineering v0.2.1 validation.
- `../authoring-skills/SKILL.md`: the chassis this skill complements (authoring builds, skill-testing verifies).
- `../authoring-skills/references/description-trigger-rules.md`: when a routing test fails, this is where the fix is described.

## Continual improvement

This skill is maintained at:
https://github.com/AgentParadise/harness-engineering/blob/main/skills/skill-testing/SKILL.md

Test methodology refinements (new flake patterns, cheaper test orchestration, CI integration recipes) belong in this file and its references. The empirical study that produced this skill is at `docs/superpowers/specs/2026-05-14-routing-test-results.md`.
