# Routing Test Methodology

Methodology derived from the harness-engineering v0.2.1 routing validation (2026-05-14). The full results that motivated this document live at `../../../docs/superpowers/specs/2026-05-14-routing-test-results.md`. The chassis-level principles this document elaborates are in `../SKILL.md`. Read that first if you have not already.

This document is the depth reference for the routing-test mode of `skill-testing`. It describes how to fire user-style prompts at fresh `claude -p` sessions with a plugin loaded, capture the routing decision deterministically, and grade it against a test matrix.

## Why test routing empirically

A skill's `description` is its routing contract. The contract is enforced not by a parser but by Claude's interpretation of the description against a real user prompt. The only way to know whether the contract holds is to watch Claude make the call. A simulated routing judge (a separate model session that reads all descriptions and decides which skill should fire for a prompt) gives useful early signal during authoring, but it answers a different question. It measures "given the descriptions in isolation, which skill *should* route", not "given a fresh session with this plugin loaded, which skill *does* route".

Simulation routinely passes where live testing fails. Three common causes: the model interprets a prompt meta-style under `--print` mode and never invokes a Skill at all; another plugin's overlapping skill fires first; an unrelated `--append-system-prompt` biases the routing decision. None of these surface in a description-only simulation. Live `claude -p` invocation is the only honest test of the contract that actually ships.

## The fresh-session requirement

Every prompt fires against a new `claude -p` session with no carry-over state. A conversation that has already loaded the skill's body (because an earlier turn invoked it) has read the trigger phrases verbatim and is biased toward routing the same way again. That bias is exactly what we are trying to measure the absence of: the routing decision should come from the description alone, as it would for a user typing the prompt cold.

Operationally this means:

- One prompt per `claude -p` invocation. Do not batch multiple prompts into a single conversation.
- Pass `--no-session-persistence` so the run does not write to the user's session history.
- Do not reuse a session id across prompts.
- Do not warm the session with a setup turn.

The runner at `../scripts/run-one.sh` enforces this by spawning a fresh process per prompt and never sharing state between calls.

## The stream-json contract

`--output-format stream-json --verbose` makes `claude -p` emit a newline-delimited JSON stream to stdout. Each line is a typed event. The events relevant to routing are `assistant` events whose `message.content` array contains a `tool_use` block.

The routing answer is the **first** `assistant` event whose `message.content` contains a `tool_use` block where `name` is `"Skill"`. The `input.skill` field on that block is the routed skill, formatted as `"<plugin-name>:<skill-slug>"`.

A minimal relevant line (anonymized, formatted for readability; in the real stream it is a single line) looks like:

```json
{
  "type": "assistant",
  "message": {
    "content": [
      {
        "type": "tool_use",
        "name": "Skill",
        "input": { "skill": "example-plugin:example-skill" }
      }
    ]
  }
}
```

Later `tool_use` events in the same stream (`Read`, `Bash`, `Edit`, `Grep`) represent downstream work the skill or the model is doing after routing. They are not routing signal. Counting them inflates pass rates with content that does not measure the routing decision.

If the stream contains no `tool_use` with `name: "Skill"` at all, the routing decision is **NONE**: the model elected not to invoke any skill from any plugin. This is the correct outcome for negative-control prompts.

## The grep-based extraction

The runner extracts the routing decision with a single grep:

```bash
grep -oE "\"skill\":\"${PLUGIN_NAME}:[a-z-]+\"" "$STREAM_FILE" | head -1
```

Two reasons grep is sufficient rather than a full JSON parser:

1. The routing answer appears in the stream as a JSON object literal that contains the exact substring `"skill":"<plugin>:<slug>"`. There is no ambiguity from nested structures or quoting; grep matches the literal.
2. `head -1` gives the first occurrence. Because the runner asks for a fresh session and the model invokes a skill at most once per routing decision, the first match is the routing answer.

The `${PLUGIN_NAME}` filter is load-bearing. It prevents the extractor from matching a `Skill` invocation from another plugin the user happens to have installed (for example a `superpowers:` or `sdlc:` skill whose description overlaps the prompt). Without the prefix filter, an unrelated plugin's skill firing would be reported as a PASS or FAIL against the wrong reference set. With the filter, an unrelated plugin firing produces an empty match, which the runner correctly translates to NONE.

## Parallel-batch cost optimization

All prompts in a suite share the same `claude -p --plugin-dir <path>` invocation pattern. The system prompt, the loaded plugin manifest, and the skill descriptions are identical across every call. This is ideal for prompt caching.

After the first call in a batch, every subsequent call within the cache window hits cache for the description portion. In the v0.2.1 validation, `cache_read_input_tokens` dominated over `cache_creation_input_tokens` from the second prompt onward. A 40-prompt suite costs roughly $0.50 to $1.00 total in practice. The per-prompt cost cap (`MAX_BUDGET`, default 0.30 USD) is a safety net for a runaway call, not a sizing constraint.

The runner at `../scripts/run-all.sh` batches with the bash background-job pattern, defaulting to 5 parallel jobs:

```bash
while IFS=$'\t' read -r id expected prompt; do
  ( "$RUNNER" "$id" "$expected" "$prompt" >> "$OUT" 2>&1 ) &
  running=$((running + 1))
  if [ "$running" -ge "$BATCH" ]; then
    wait
    running=0
  fi
done < "$PROMPTS"
wait
```

macOS bash 3.2 does not support `wait -n` (the "wait for any one job" form), which is why the loop uses fire-N-then-wait-all rather than a true rolling pool. Wall-clock for a 40-prompt suite at BATCH=5 has stayed under 15 minutes in practice.

## The append-system-prompt trick

The runner passes:

```bash
--append-system-prompt "After reading the user request, decide whether to invoke a skill from the ${PLUGIN_NAME} plugin. If a skill clearly applies, invoke it via the Skill tool. If no ${PLUGIN_NAME} skill applies, do not invoke any Skill and just answer briefly. Do not do real work; just route."
```

This nudges Claude toward routing-as-the-task rather than actually executing whatever the user asked for. Without it, Claude often invokes the expected skill and then starts performing the audit, setup, or refactor the prompt asked for. That downstream work burns tokens we do not need and inflates wall-clock per call. The system-prompt-append is the cost cap.

The trade-off is that the append can occasionally over-influence routing. See the meta-routing-table flake under edge cases below. The append is the cheapest way to bound cost; the flake is the cost of bounding cost.

## Edge cases and false alarms

### Meta-routing-table responses

The model sometimes returns a markdown table of routing decisions across an imagined test suite rather than invoking a skill. This was observed once in the v0.2.1 validation (the P06 flake). The likely cause is the system-prompt-append being interpreted as a meta-test rubric: the model sees "decide whether to invoke a skill" and responds with a written-out decision rather than an actual tool call. When this happens, no `tool_use` with `name: Skill` appears in the stream, so the extractor returns NONE.

A single occurrence is a flake, not a description failure. The single-rerun policy from `flake-handling.md` applies: re-run the prompt in isolation; if it passes, the original was meta-interpretation noise.

### First tool_use is not a Skill

If Claude opens with a `Read`, `Bash`, or `Grep` tool call rather than a `Skill` invocation, the grep finds nothing matching the Skill pattern. The extraction returns empty and the runner reports NONE. This is the correct behavior: no Skill was invoked, so no routing decision was made. For a negative-control prompt this is a PASS; for a positive-trigger prompt this is a FAIL that points at a description gap.

### Plugin not loaded

If `--plugin-dir` is wrong, the directory is missing a manifest, or the plugin is malformed, `claude -p` boots without that plugin. Every prompt then returns NONE (because the plugin's skills are not available to route to) or routes to a different plugin's overlapping skill. Symptom: every prompt in the suite returns NONE, or every prompt routes to a non-`${PLUGIN_NAME}` skill that the grep filter discards.

Fix: probe the plugin before running the suite. A one-prompt probe asking Claude to list available skills from the plugin confirms it loaded. If the probe shows no skills from the expected plugin, the suite is testing the wrong thing.

### Other plugins' skills overlapping

If the user has `superpowers:using-git-worktrees` enabled, a worktree-isolation prompt may route to that skill instead of the harness-engineering equivalent. The runner's PLUGIN_NAME prefix filter discards that match, so the extractor returns NONE. The runner reports the prompt as NONE rather than as the overlapping skill's slug.

This is not a bug. The test correctly reports that the *plugin under test* did not receive the routing. If the suite expected the plugin under test to win the overlap, the description needs sharper trigger phrases. If the suite expected the overlap to be ceded to the sibling plugin, the prompt should be marked NONE in the matrix.

## Running the suite

1. Build a test matrix at `prompts.tsv`. Columns, tab-separated: `id`, `expected-skill-name-or-NONE`, `prompt-text`. See `test-matrix-template.md` for guidance on prompt selection and positive/negative/seam ratios.

2. Export the required environment variables:

   ```bash
   export PLUGIN_DIR=/absolute/path/to/plugin
   export PLUGIN_NAME=name-from-plugin.json
   ```

   `PLUGIN_NAME` must match the `name` field in the plugin's `.claude-plugin/plugin.json`. The runner uses it as the prefix filter on the grep extraction.

3. Run the full suite:

   ```bash
   ./scripts/run-all.sh prompts.tsv
   ```

   Optional tunables: `BATCH=5` parallel jobs (default), `OUT_DIR=/tmp/skill-testing` for artifacts, `MAX_BUDGET=0.30` per-call USD cap.

4. Read `results.tsv` (sorted by id). Walk every FAIL row. For each FAIL:

   ```bash
   ./scripts/run-one.sh <id> <expected> "<prompt>"
   ```

   If the rerun passes, treat the original as a flake and annotate `results.tsv` accordingly. If the rerun still fails, the description has a gap.

5. Fix the description per `../../authoring-skills/references/description-trigger-rules.md`. Re-run only the previously-failing prompts to confirm the fix. Then re-run the full suite to confirm no regressions on adjacent skills.

6. Commit the test matrix and the final `results.tsv` alongside the description change. Reviewers should see the evidence in the same PR.

## Cost guidance

Cap per-call cost with the `MAX_BUDGET` environment variable (default 0.30 USD). In practice the default 40-prompt suite has stayed under one dollar total because prompt caching reduces per-call input cost dramatically after the first call. The per-call cap is a safety net for a runaway call (the model spirals into a long completion), not a budget target.

If a suite begins to consistently approach the cap, two likely causes: the `--append-system-prompt` is not biting (Claude is doing the real work despite the instruction), or the prompts in the matrix are themselves very long. For the first, sharpen the append. For the second, shrink the prompts to the minimum that preserves user-style realism.

## Cross-references

- `body-usefulness-methodology.md`: the paired-run comparison procedure for the body contract. Routing tests verify Claude *invokes* the skill; body tests verify the invocation *helps*.
- `test-matrix-template.md`: how to pick prompts, the positive/negative/seam ratio, prompt-realism guidance.
- `flake-handling.md`: the meta-routing-table phenomenon in detail, the single-rerun policy, known patterns and their signatures.
- `../scripts/run-one.sh`: the reference single-prompt runner.
- `../scripts/run-all.sh`: the reference parallel-batch runner.
- `../../../docs/superpowers/specs/2026-05-14-routing-test-results.md`: the v0.2.1 validation results that produced this methodology (40/40 PASS after the single P06 rerun).
