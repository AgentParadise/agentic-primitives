# Flake Handling

Flake patterns observed during the harness-engineering v0.2.1 routing validation and surrounding work.

Source attribution:

- Empirical study: `/Users/neural/Code/AgentParadise/harness-engineering/docs/superpowers/specs/2026-05-14-routing-test-results.md` (the P06 flake is described in Experiment 1).
- Chassis: `/Users/neural/Code/AgentParadise/harness-engineering/skills/skill-testing/SKILL.md` (Outcome 4: flakes are distinguished from real failures).

## What a flake is

A flake is a test failure that does not reproduce when re-run with identical inputs and configuration. It is distinct from two adjacent concepts:

- A real failure reproduces. Run it again, same inputs, same config, you get the same failure. This is signal about the system under test.
- A flaky test is a test whose own definition is unreliable: the matrix entry, the expected skill, the negative controls, or the prompt itself produces inconsistent verdicts even when the system under test is behaving identically. This is signal about the test, not the system.

For routing tests, the typical flake sits between these two. The model produces an unexpected response shape on one invocation and the same shape disappears on retry. The test definition is fine. The system under test is fine across the population of runs. A single sample landed in a tail of the distribution.

## Why flakes happen

Routing tests fire fresh `claude -p` sessions with identical system prompts and inputs. The model's response is largely deterministic across runs but not perfectly so. Several mechanisms push a single call off the expected path:

- Meta-interpretation. The append-system-prompt instructing the model to "just route" can occasionally be interpreted meta-style. The model decides the user is asking about routing in general rather than asking the underlying question. Instead of invoking a Skill, it writes about which skill it would invoke.
- Sampling nondeterminism. Even with low temperature, the underlying model is not perfectly deterministic across runs. A token boundary lands differently and a chain of decisions diverges.
- Cache-warming effects. The first call in a fresh suite hits a cold prompt-cache state. Subsequent calls hit a warm state. The model's behavior on a cold start can differ in small ways from its behavior on a warm start.
- Parallel-batch race conditions. When the harness fires N calls concurrently, ordering effects on shared resources (rate-limit windows, transient network slowness) can nudge a single call into a degraded response shape.

None of these mechanisms produce reliable failures. They produce occasional, non-reproducing failures. That is exactly the definition of a flake.

## The retry policy

Every FAIL in the batch run gets exactly one isolated retry via `run-one.sh`. The retry runs the same prompt with the same configuration in a fresh, non-parallel context.

- If the retry passes, the original is a flake. Note it in the suite-run output and move on.
- If the retry still fails, the description has a real gap. Investigate the stream output and either strengthen the description or update the expected skill in the matrix.

Why one retry, not three:

- Three retries papers over real flakiness. If a description fails one in three times, that is information you want to surface, not information you want to retry away.
- One retry distinguishes the meta-interpretation noise the model produces about once in fifty invocations from a description gap that reproduces every time.
- If you find yourself running three retries and getting mixed results, the underlying issue is something else: cost cap, prompt phrasing, plugin not loaded, infrastructure. The retry budget is not the right lever.

The retry is isolated by design. Running the retry inside the same parallel batch would reproduce the parallel-batch conditions that may have contributed to the flake. Running it alone removes that variable.

## Known flake patterns

### Meta-routing-table response

Symptom: the model returns a markdown table of routing decisions across an imagined test suite, with rows like P01 through P40, columns for expected skill and predicted skill, rather than invoking a single Skill.

Diagnostic: read the stream-json output and find the assistant message. The content is a text block, not a `tool_use`. The first Skill `tool_use` is absent.

Resolution: rerun in isolation. The condition that triggered the meta-interpretation does not reproduce. Long-term mitigation: the append-system-prompt could be tightened to reduce the chance of meta-interpretation, but a one-in-forty flake rate is acceptable for the cost of investigation.

### Wrong-plugin route

Symptom: the runner reports NONE but the stream output shows Claude invoked a different plugin's skill (for example, `superpowers:using-git-worktrees` won the route for a worktree-isolation prompt that the harness-engineering plugin was supposed to handle).

Diagnostic: `grep -oE '"skill":"[^"]+"' <stream-file>` reveals the routed skill name.

Resolution: this is not a flake. It is correct behavior for the test definition as written: the plugin under test did not get the route. If the test author wants the harness-engineering skill to win, the description needs a stronger trigger or the negative-control list needs to capture the overlap. Do not retry. Fix the matrix entry or the skill description.

### Empty stream or model error

Symptom: stream output is empty, or contains an error event with no assistant message.

Diagnostic: check the runner exit code, network connectivity, and the api-key auth path. Look for a `result` event with `subtype: error`.

Resolution: this is infrastructure, not the skill. Re-run. If it persists across re-runs, fix the infrastructure (auth, network, runner version) before continuing the suite.

### Cost cap hit mid-call

Symptom: stream output ends abruptly without a final assistant message. The runner records FAIL or NONE.

Diagnostic: look for a `result` event indicating budget exhaustion, or a missing `result` event entirely while the stream stops cleanly.

Resolution: raise the `MAX_BUDGET` env var. The default 0.30 USD per call is generous for the lightweight routing prompts. If a prompt exceeds it, the prompt is doing more than routing (it pulled in a long skill body, fired a tool chain, or otherwise escaped the single-routing-decision boundary). Investigate the prompt before normalizing a higher budget.

### Cache cold-start

Symptom: the first call in a fresh suite has higher latency and slightly different behavior than subsequent calls.

Diagnostic: check `cache_creation_input_tokens` versus `cache_read_input_tokens` in the stream output's usage event.

Resolution: not a flake. The cache warms after the first call. The single-call-per-prompt design is unaffected because each prompt only needs one successful routing decision. If a cold start produces a borderline failure, treat it like any other FAIL and retry.

## Triaging a FAIL

Step by step, with no shortcuts:

1. Look at the result line. Note expected versus got.
2. Open the stream file at `${OUT_DIR}/results/<id>.jsonl`.
3. Read the first assistant message. Is it a `tool_use` of name Skill, or is it text?
4. If it is text and looks like a meta-routing-table or a general answer about routing: flake. Retry.
5. If it is text and looks like Claude declined to invoke anything (a hedged answer, a clarifying question, a refusal): borderline. Retry. If the retry produces the same text, the description is not strong enough to overcome Claude's reluctance to invoke without confirmation.
6. If it is a Skill `tool_use` but for a different skill than expected: real routing miss. Fix the description, not the test.
7. If it is a Skill `tool_use` for a different plugin's skill: not a flake. The description for the plugin under test is too weak relative to the overlap. Either strengthen its triggers or accept the routing and update the matrix.

The triage path is deliberately mechanical. The point is to remove judgment from the FAIL-versus-flake decision and replace it with a sequence of stream-shape checks.

## When a flake is actually a description issue in disguise

If the same prompt flakes more than once across multiple suite runs (not consecutive retries within a single run, but separate suite runs on different days or different branches), the underlying issue is probably description ambiguity. The description sits on the boundary between two routing decisions, and small perturbations push it one way or the other.

The fix is not better retry logic. The fix is to strengthen the description so it leaves the boundary. Add a discriminating trigger phrase, narrow the scope, or add a negative-control example that the test then encodes.

Heuristic: a prompt that flakes once in forty runs is noise. A prompt that flakes three times in forty runs is signal. Cross-reference the `flake-log.md` (see below) before deciding.

## Documenting flakes in test artifacts

When you accept a flake, record it. The minimum:

- Note it in the commit message for the test run.
- Or append a line to a sibling `flake-log.md` next to the matrix, with the date, prompt id, observed shape, and retry outcome.

A pattern that emerges over time, for example "P06 has flaked 3 times in 40 runs," is signal that warrants investigation. A single one-off retry is not worth recording beyond the suite-run notes. The log exists to surface the patterns, not to enumerate every retry.

Suggested log entry shape:

```
2026-05-14  P06  meta-routing-table  retry-passed
2026-05-21  P06  meta-routing-table  retry-passed
2026-06-03  P06  declined-to-invoke  retry-failed  description-tightened
```

## Long-term mitigations

Things worth considering when the flake rate becomes annoying enough to outweigh the cost of changing the harness:

- Tighter append-system-prompt that reduces the chance of meta-interpretation. Test the change against the existing suite to confirm it does not regress other prompts.
- Per-prompt-id retry with limited fan-out (for example, 2 attempts before declaring fail). Keep the limit small to preserve signal.
- Stream-shape inspection that separates "the model declined to invoke" from "the test infrastructure broke." These produce the same FAIL today but want different responses.
- Sample-N runs of the same prompt to compute a routing-success rate rather than a binary PASS/FAIL. Useful when boundary descriptions are intentional and the goal is to measure rather than eliminate flakes.

None of these are urgent at the current observed flake rate. Revisit when the suite grows past roughly 100 prompts or when manual triage time exceeds 10 minutes per suite run.

## Cross-references

- `routing-test-methodology.md`: the broader methodology this flake-handling guidance fits into.
- `test-matrix-template.md`: the matrix format that the retry policy operates on.
- `/Users/neural/Code/AgentParadise/harness-engineering/skills/skill-testing/SKILL.md`: the chassis, especially Outcome 4.
- `/Users/neural/Code/AgentParadise/harness-engineering/docs/superpowers/specs/2026-05-14-routing-test-results.md`: the v0.2.1 study, Experiment 1, which documents the P06 flake that motivated this reference.
