---
name: running-experiments
description: Use when creating, scaffolding, executing, scoring, or auditing a hypothesis-first experiment in any repo that follows the `experiments/<date>--<slug>/` convention, OR when capturing a prospective experiment as a proposal under `docs/experiments/proposals/`. Trigger phrases include "new experiment", "new probe", "run an experiment", "score the probe", "write the verdict", "hypothesis first", "design the eval pack", "two-commit rule", "hypothesis scorecard", "write a retrospective for", "is this an experiment", "capture this as a proposal", "prospective experiment", "lock this idea", "promote this proposal". Covers the four-file layout (README, eval-pack, results, verdict), the verdict vocabulary (go, no-go, inconclusive), the proposal lifecycle (`docs/experiments/proposals/<slug>.md` then promoted to a real experiment), and the relationship between an experiment and its retrospective under `docs/retrospectives/`. Do NOT use for: ad-hoc debugging sessions, code review, skill authoring (see `authoring-skills`), or domain-specific probes that have their own workbench skill (those repos extend this skill with daemon/bank machinery of their own).
placement: "Domain skill. Install in `plugins/<domain-plugin>/skills/<name>/` (the canonical home in plugin-structured repos; this skill lives at `plugins/experiments/skills/running-experiments/` in agentic-primitives) or `skills/<name>/` (in flat-structured repos). NOT in `.claude/skills/`. That scope is reserved for meta skills that teach how to author other skills."
---

# Running experiments

## Overview

An experiment is a falsifiable probe: a predicted outcome committed before any data is collected, a frozen eval pack, runs that produce evidence, and a verdict that scores both the hypothesis and the question. Two commits per experiment (`hypothesis for <slug>`, then `run <slug> (<verdict>)`) make the timeline auditable. The result lands in a retrospective (canonical path: `docs/retrospectives/NNN-<topic>.md`) so the lesson outlives the probe folder.

This skill is the contract for that loop. Drafting, running, scoring, and auditing all live here. Repo-specific paths (where retrospectives live, what the status matrix looks like, which canonical scripts to use) belong in each consumer repo's CLAUDE.md or AGENTS.md; this skill provides the durable methodology, not the per-repo conventions.

## Outcomes we are looking for

Durable goals. Each has 1-2 signals a reviewer can check later.

### Outcome 1: predictions precede data

The commit timestamp on `hypothesis for <slug>` is older than every file in `runs/`. Without this anchor, scoring degenerates into storytelling.

- *Signal:* `git log --diff-filter=A -- experiments/<slug>/README.md` predates any `experiments/<slug>/runs/**` file.
- *Signal:* the README's `## Hypothesis` section contains predicted numbers, directions, or failure modes -- not "the system will work."

### Outcome 2: experiments are comparable across time

Slug shape, four-file layout, and verdict vocabulary are uniform, so a reader six months later can scan `experiments/` and find what they need.

- *Signal:* folder name matches `YYYY-MM-DD--<slug-with-double-dash-segments>`.
- *Signal:* each experiment has all four files: `README.md`, `eval-pack.md`, `results.md`, `verdict.md`.

### Outcome 3: load-bearing claims have evidence

Any claim in `docs/evolution/` or a retrospective that drives an architectural decision points back to a specific experiment artifact.

- *Signal:* claims of the form "X saves Y%" cite a path under `experiments/<slug>/runs/`.
- *Signal:* the cited artifact exists and contains the number being quoted.

### Outcome 4: wrong predictions get the headline

A scorecard of 5/5 correct is a warning, not a victory -- it usually means the hypothesis was written after the run, or the question was obvious. Misses are where the learning lives.

- *Signal:* `verdict.md` has a `## Hypothesis scorecard` section that names misses with one-line reasons.
- *Signal:* the executive summary and retrospective for the probe foreground what was wrong, not what was right.

### Outcome 5: scope is honest

An experiment is for a question whose outcome you don't already know. Debugging, code reading, and feature implementation are not experiments and don't belong under `experiments/`.

- *Signal:* the README's `## Question` section names a falsifiable claim, not a task.
- *Signal:* declared mapping probes (no hypothesis) are explicit about that exemption, not silently hiding it.

## Principles

1. **Hypothesis-first commit is the falsifiability anchor.** A separate commit before any `runs/` artifact is the only mechanical proof that the prediction preceded the data. Honor-system "I predicted this" claims are not auditable. The first commit message is `experiments: hypothesis for <slug>`.

2. **No smoke testing before the hypothesis commit.** A "let me verify the setup works" run leaks the answer. Verify the setup by *reading* code, configs, and the `_template/README.md` pre-flight checklist -- not by running the experiment.

3. **The eval pack is frozen.** Once `eval-pack.md` is committed alongside the hypothesis, mid-experiment edits invalidate the run. If the pack is wrong, start a new probe; don't rewrite the spec to match what you observed.

4. **Conditions exist to isolate one variable at a time.** A one-condition probe can show whether something *worked*, but not whether it was *the system* that worked vs. the baseline drift. Pair every claim that "X helps" with a condition that exercises the alternative.

5. **Verdicts are tied to evidence, not impressions.** `go` / `no-go` / `inconclusive` each cites paths under `runs/`. `inconclusive` is a real verdict, not a copout -- use it freely and follow up with a sharper probe.

6. **Tool guidance is dated and isolated.** Specific commands (`pnpm harness boot --bug …`, `rtk pnpm …`, LogsQL projections) live in `## Recommended tools and practices` so they can rot without taking the principles down with them.

## Anti-patterns

Observations from probe audits. Each names a failure mode an auditor can spot in a real folder.

- **Scorecard 100% correct.** The auditor sees every prediction marked ✅ in `verdict.md`. This means the hypothesis was written after the run or the question was trivial. Either way, the probe didn't earn its keep.

- **`runs/` files older than the hypothesis commit.** `git log -- experiments/<slug>/` shows runs predating `experiments: hypothesis for <slug>`. The two-commit rule was violated; falsifiability is gone.

- **Smoke-test fingerprints in the hypothesis.** The README hedges with words like "as we observed in early runs" -- meaning the hypothesis was edited after looking at data. Smoke-testing leaked the result.

- **One-condition probe with a comparative claim.** `verdict.md` says "X is 80% faster" but `eval-pack.md` only exercised X -- no baseline, no alternative. The number is unfalsifiable.

- **Magic numbers without evidence paths.** `results.md` headline table cites "11.9× reduction" with no link to a `runs/` artifact. The number could be invented and no one would know.

- **Debugging stuffed into `experiments/`.** The README's question is "why is the layout broken?" instead of "does technique X catch layout breaks within Y wall-clock?". This is a debugging session, not an experiment.

- **Mid-experiment eval-pack edits.** `git log -- experiments/<slug>/eval-pack.md` shows edits after the first `runs/` file. The frozen-spec rule was violated.

- **Tool churn rotting principles.** Removing a specific command (say, an RTK invocation) breaks half the skill body because tool guidance was woven through the structural sections. Dated `## Recommended tools and practices` exists to prevent exactly this.

## Recommended tools and practices (as of 2026-05-13)

Concrete commands, harness toggles, and patterns. When a tool here is replaced, edit only this section.

### Outcome: predictions precede data

- **Scaffold from the template.** `cp -R experiments/_template experiments/<slug>` then fill `README.md` only -- leave `runs/` empty. Ladders up by separating spec-time work from data-time work.
- **Run the `_template/README.md` pre-flight checklist before committing the hypothesis.** Clean working tree, known stack state, empty `.harness/artifacts/<iso_key>/`, documented tool versions. Ladders up by ruling out confounds before they corrupt the hypothesis. See `references/preflight.md`.
- **First commit is `experiments: hypothesis for <slug>`.** No other files in this commit beyond the four scaffolded files. Ladders up by making the timeline mechanical.

### Outcome: experiments are comparable across time

- **Slug shape: `YYYY-MM-DD--<dimension>--<short-question>`.** Today's date, kebab-case. Examples in `experiments/` are the canonical references. Ladders up by giving folder listings a stable scannable shape.
- **Four files exactly: `README.md` (question + hypothesis + setup), `eval-pack.md` (frozen probe set), `results.md` (per-probe scoring), `verdict.md` (go/no-go/inconclusive + scorecard).** Ladders up by making cross-probe comparison mechanical.

### Outcome: load-bearing claims have evidence

- **Headline numbers in a table at the top of `results.md`.** Each row cites a path under `runs/`. Ladders up by making evidence-or-fabrication a one-glance audit.
- **Retrospective under `docs/retrospectives/NNN-<topic>.md`** when the probe changes how we work. Cross-link from the verdict. Ladders up by giving the lesson somewhere stable to live after the probe folder ages out of attention.

### Outcome: wrong predictions get the headline

- **`## Hypothesis scorecard` table in `verdict.md`** with predicted / observed / score / notes per prediction. Misses are flagged 🟡 partial or ❌ wrong with a one-line reason. See `references/scorecard-template.md`.
- **Second commit is `experiments: run <slug> (<verdict>)`.** This commit contains `eval-pack.md` (final), `runs/`, `results.md`, `verdict.md`, and any retrospective updates. Two commits per experiment, never more for the spec/result split. Ladders up by keeping the audit trail clean.

### Outcome: scope is honest

- **Mapping probes (no hypothesis) declare the exemption.** Add a `## No hypothesis (mapping probe)` section to the README and skip the scorecard. Ladders up by making the exemption visible rather than silent.
- **Audit a candidate experiment against the "When NOT" list before scaffolding.** See `references/audit-checklist.md`. Ladders up by catching debugging-disguised-as-experiment at intake.

## Intake: the FOCUS gate

Before scaffolding, the candidate experiment must pass FOCUS. FOCUS is borrowed from AI-pilot design (Schneider Electric and the broader "designing successful AI pilots" literature); it transfers cleanly to harness probes because both share the same risk: spending real time and tokens on a question whose answer won't change anything. Each letter is a gate, not a wish -- if the answer is "I don't know" or "no," fix that first or drop the probe.

| Gate | Question for a harness-lab probe | Failure mode if you skip it |
|---|---|---|
| **F**it | Does this question fit a current strategic priority (the active `docs/evolution/v0.X.Y` cycle, a known cost/wall-clock claim under load, or a documented gap)? | Probes that don't fit produce results no one acts on; the verdict ages out unread. |
| **O**rganization pull | Will the result get used? Is there a decision waiting on this evidence (a tool adoption, a skill rewrite, a removed dependency)? | Without a downstream decision, the probe is a curiosity, not leverage. |
| **C**apability readiness | Do we have the tooling and skills to actually run the eval pack -- the right harness toggles, observability queries, evidence-capture scripts? | Mid-probe tool gaps turn into yak-shaving and contaminate the run. |
| **U**nderlying data | Is the measurable data available and ready (logs/metrics/traces wired, baseline numbers captured, a clean stack state) and is the *baseline* defined before the run? | "Before and after" without a captured "before" is just "after." Baseline is the comparative anchor; without it you have anecdotes. |
| **S**uccess | Can the probe baseline the current state and measure impact against a predefined success metric (numbers, directions, failure modes)? | If success is undefined at hypothesis time, the verdict will be retrofitted to the data -- see anti-pattern "scorecard 100% correct." |

**Pilot-design adaptations.** Successful AI pilots use clear boundaries, appropriate duration, and predefined success metrics. For harness-lab probes:

- **Clear boundaries** = the frozen eval pack. The pack states the universe under test; everything outside is explicitly out of scope and goes in a follow-up probe.
- **Appropriate duration** = time-box per probe. An organizational pilot runs 8-12 weeks; a harness probe usually runs hours to a few days. If a probe drags past a working week, split it. "Long enough to collect meaningful data, short enough to show wins" applies to both scales.
- **Predefined success metrics** = the hypothesis's predicted numbers, committed before any `runs/` artifact. Schneider Electric's contact-generation pilot worked because the before/after metric was defined before deploying Copilot -- same anchor here.
- **Structured feedback mechanisms** = the retrospective under `docs/retrospectives/` and the executive summary update. Insights captured continuously across probes are what let the next probe build on the last instead of relitigating it.

If a candidate fails one or more FOCUS gates, the move is rarely "run a sloppier probe." It's: capture the missing piece (priority, decision, tooling, baseline, metric) first, then come back. Or write a smaller mapping probe to surface the missing piece deliberately.

## Prospective experiments (proposals)

Not every idea is ready to run. A real experiment costs hours of agent + human time and locks in a frozen eval pack. Skipping the proposal step for half-formed ideas pollutes `experiments/` with hypotheses no one acts on -- exactly the "Fit / Organization pull" FOCUS failure mode.

**A proposal is a captured idea that's hypothesis-shaped but not on the running queue.** It lives at `docs/experiments/proposals/<YYYY-MM-DD>--<slug>.md` and holds enough context that a future reader (human or agent) can decide whether to promote it to a real experiment without re-deriving the thinking.

### When to write a proposal vs. scaffold an experiment

| Situation | Write a proposal | Scaffold an experiment |
|---|---|---|
| Idea surfaced mid-conversation; we want to capture it before it's lost | ✓ | ✗ |
| FOCUS gate currently fails on Fit, Organization pull, or Underlying data | ✓ (capture; revisit when the gate clears) | ✗ |
| We've committed to running this next or now | ✗ | ✓ |
| We're deciding between several adjacent ideas and want to see them side-by-side | ✓ (write proposals for each, then pick) | ✗ until picked |
| The work would be obvious enough that a frozen eval pack doesn't add value (a pure refactor, a doc fix, an upstream version bump) | ✗ (just commit it; it's not an experiment at all) | ✗ |

### Proposal file format

Lightweight by design. Each `docs/experiments/proposals/<slug>.md` has these sections:

```markdown
# Proposal: <slug>

**Status:** proposed
**Captured:** YYYY-MM-DD
**Triggered by:** (conversation, observation, or external signal that surfaced this)

## Question
   One sentence. Same shape as the experiment README's Question.

## Why it matters (cost of not knowing)
   What decision would the experiment's result inform? What's the downside
   of running blind / continuing without an answer?

## What running it would look like
   - Implementation sketch
   - Predicted numbers / bands / failure modes
   - Eval-pack shape (probes, conditions, what would invalidate the run)

## What this proposal explicitly does NOT cover
   Scoping fence. Sibling proposals if relevant.

## What promotes this from proposal to experiment
   The condition that would move it from `docs/experiments/proposals/` to `experiments/`.
   Often: a downstream decision needing the data, a related arc landing,
   or an explicit user-pulled "run this next."

## References
   Other proposals, prior experiments, retrospectives, or code that this
   proposal builds on or against.
```

See `docs/experiments/proposals/2026-05-14--identifier-uniqueness-vs-lsp-for-agent-navigation.md` for a canonical example.

### Promotion lifecycle

```
docs/experiments/proposals/<slug>.md
        │
        │  ← User or arc planning explicitly says "run this next."
        ▼
experiments/<YYYY-MM-DD>--<slug>/  (scaffold from _template; copy Question + Predictions from proposal)
        │
        │  ← Two-commit rule from here: hypothesis, run, verdict.
        ▼
docs/retrospectives/NNN-<topic>.md (if the result changes how we work)
```

After promotion, the proposal stays as a **captured-context record** with a link to the experiment, or gets archived. The proposal's "What promotes…" section becomes a useful history of *why* this experiment was prioritized when it was. Don't delete proposals just because they got promoted -- the captured triggering context is the cheap part of the audit trail.

### What proposals are NOT

- A backlog to grind through. Proposals accumulate; only some get promoted; that's fine.
- A substitute for the hypothesis-first commit. Promotion still requires the two-commit rule.
- A retrospective replacement. Retros are post-run lessons; proposals are pre-run framing.
- A todo list. The breadcrumb (`docs/v0.X-next-steps.md` per active arc) is for "items we plan to run next, in order." Proposals are "ideas captured; promotion timing TBD."

## How to use this skill: authoring mode

0. **Check `docs/experiments/proposals/` first.** If a proposal for this idea already exists, copy its Question and "What running it would look like" into the new experiment README rather than re-deriving them; the proposal's framing is usually richer than a from-scratch first draft. Update the proposal's status to `promoted` with a link to the experiment.
1. Walk the FOCUS gate above. If any gate fails, address it before scaffolding -- don't proceed with a known-weak probe. **If the gate fails on Fit / Organization pull / Underlying data, write a `docs/experiments/proposals/<slug>.md` instead and stop.** Promotion can happen later when the gate clears.
2. Audit the candidate against `references/audit-checklist.md` -- is this actually an experiment? If not, stop here.
3. Pick the slug: `YYYY-MM-DD--<dimension>--<short-question>`.
4. `cp -R experiments/_template experiments/<slug>`.
5. Walk the `_template/README.md` pre-flight checklist (`references/preflight.md`). Resolve every confound or document it as part of Setup.
6. Fill `README.md` (question, hypothesis with predicted numbers, setup, conditions, expected signals) and `eval-pack.md` (frozen probe set).
7. Commit: `experiments: hypothesis for <slug>`. No other files. No smoke test before this.
8. Run the eval pack. Write to `runs/`. Score in `results.md` with evidence links.
9. Write `verdict.md` with verdict and `## Hypothesis scorecard`. Wrong predictions get the headline.
10. If the result changes how we work, write `docs/retrospectives/NNN-<topic>.md` and cross-link.
11. Update the status matrix in the root `README.md` if applicable.
12. Commit: `experiments: run <slug> (<verdict>)`.

## How to use this skill: audit mode

1. Open `experiments/<slug>/` and walk `references/audit-checklist.md` top to bottom.
2. For each fail, identify the smallest change that closes the gap. If `runs/` predates the hypothesis commit, the probe is unsalvageable -- record the finding in the retrospective and move on; don't backfill timestamps.
3. Audit the retrospective (if any) against its cited evidence paths. Broken links mean the lesson is floating.
4. If multiple probes fail the same criterion, the criterion may need refinement -- flag in `references/audit-checklist.md` rather than working around it per-probe.

## References

- `references/preflight.md`: the pre-flight checklist from `_template/README.md`, with rationale per item and the retrospective each one came from.
- `references/scorecard-template.md`: canonical `## Hypothesis scorecard` table shape with worked examples (predicted right, partial, wrong).
- `references/canonical-scripts.md`: example shell patterns for running probes against the harness stack (boot with bug toggle, LogsQL projection queries, before-after evidence capture).
- `references/audit-checklist.md`: binary pass-fail criteria for an experiment folder, walkable top to bottom.

## Cross-references

- **Skill authoring chassis:** `../../../../../AgentParadise/harness-engineering/skills/authoring-skills/SKILL.md` -- the contract this skill itself was written against. Read it before refactoring this file.
- **Repo conventions:** `docs/AGENTS.md` for the agent runbook; `docs/evolution/` for the current synthesis; `docs/retrospectives/` for prior lessons; `experiments/_template/` for the scaffold.

## Parallel via worktrees (added 2026-05-14 from EXP-25)

When ≥3 experiments are independent and you have orchestrator budget for parallel dispatch, run them in isolated git worktrees with delegated subagents. Measured 2.08× speedup, zero merge conflicts, 1.0× token-cost ratio (no overhead) -- see retro 017.

### When to use this pattern

- **Yes:** ≥3 independent experiments, each with a clear hypothesis-first README committed, disjoint tree areas, distinct branches.
- **Probably:** 2 independent experiments where wall-clock dominates token cost (UE-class probes, long builds).
- **No:** experiments that share files, where one's verdict gates another's hypothesis, or where a single eval pack covers multiple probes.

### The orchestrator's contract

1. **Commit all hypotheses together first.** One commit on the arc branch with every README. The shared SHA is the timeline anchor for every subagent's `runs/`.
2. **Create one worktree per experiment.** Naming: `../<repo>-<slug>` for the directory, `feat/exp-N-<slug>` for the branch.
3. **Dispatch in one batch.** Use the Agent tool with `run_in_background: true`; send all dispatches in a single message.
4. **Charter template** (each subagent gets a self-contained prompt):
   - Working directory (the worktree path) -- explicit `cd` instruction.
   - Pointer to its README and the hypothesis-commit SHA.
   - Method bullets (don't make the subagent reinterpret the README from scratch -- extract the runnable steps).
   - Hard wall-clock budget with explicit "at budget, write inconclusive and stop" instruction.
   - Constraints carried over from CLAUDE.md (bracket env access, 100% coverage rule, etc.).
   - Final-report format: ≤200 words, fixed schema (verdict, wall-clock, scorecard counts, headline numbers, last-commit SHA, blockers).
5. **Measure from the orchestrator's perspective.** Real time = dispatch-to-task-notification. Subagent-reported "wall-clock" is its perceived effort, not real time -- useful for the subagent's own scorecard, not for the meta-measurement.

### High-risk experiment requirement: pre-flight env probe

For experiments touching new languages / engines / heavy installs (UE, Unity, Blender, large LLM models, etc.), the README's Method section MUST start with an env probe:

- Check for the required binary / SDK / toolchain at known install paths.
- If absent, the subagent writes `results.md` documenting the missing pieces + re-run trigger, then stops. Verdict = `inconclusive` with blocker tree.
- This is BETTER than a long grind ending in the same answer. Examples: EXP-22 returned in 85s with a complete UE re-run trigger.

### Integration step

1. After all subagents return: `git merge --no-ff feat/exp-N-<slug>` from the arc branch.
2. **Conflict count is a measurement.** Zero conflicts confirms the disjoint-tree-areas hypothesis. Non-zero conflicts means the experiments overlapped unexpectedly -- investigate before merging.
3. Run the full verification (`pnpm -r typecheck && pnpm -r test && biome check .`) on the integrated branch.
4. Score the meta-experiment if there is one (see EXP-25 for the canonical scorecard shape).

### What this pattern does NOT cover

- Cross-machine orchestration (CI / cloud). The orchestrator and worktrees share a filesystem today.
- Experiments with shared mutable state (a single database, a single port range outside the harness's hash-based allocation).
- Quality assessment of the subagent's verdict -- that's a separate measurement question.
