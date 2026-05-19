# Experiment audit checklist

Binary pass/fail per criterion. Walk top to bottom. A clean experiment passes every box. The checklist also doubles as an intake filter: if a candidate can't plausibly pass §1, don't scaffold.

## §1. FOCUS intake gates

- [ ] **Fit** -- the question maps to an active priority in `docs/evolution/v0.X.Y` or a documented gap.
- [ ] **Organization pull** -- a downstream decision is waiting on this evidence (adoption, removal, rewrite).
- [ ] **Capability readiness** -- harness toggles, observability queries, and evidence-capture scripts the probe needs all exist and work.
- [ ] **Underlying data** -- baseline is captured (or capturable) before the run; logs/metrics/traces wired for the conditions under test.
- [ ] **Success** -- the README's hypothesis names predicted numbers, directions, or failure modes -- not "it will work."

## §2. Folder shape

- [ ] Folder name matches `YYYY-MM-DD--<slug>--<short-question>` (kebab-case, double-dash segments, today's date).
- [ ] All four files present: `README.md`, `eval-pack.md`, `results.md`, `verdict.md`.
- [ ] `runs/` exists and contains the raw evidence artifacts.

## §3. Two-commit rule

- [ ] `git log --diff-filter=A -- experiments/<slug>/README.md` predates every file under `experiments/<slug>/runs/`.
- [ ] A commit message exactly matching `experiments: hypothesis for <slug>` exists.
- [ ] A second commit message matching `experiments: run <slug> (<verdict>)` exists, with `runs/`, `results.md`, `verdict.md` in that commit.
- [ ] `eval-pack.md` has no edits after the first `runs/` file's commit (the pack was frozen).

## §4. Hypothesis quality

- [ ] Hypothesis includes at least one predicted number OR direction OR failure mode.
- [ ] If declared as a mapping probe (no hypothesis), the README has an explicit `## No hypothesis (mapping probe)` section.
- [ ] Conditions table names baseline (a) and at least one alternative -- unless the probe is purely descriptive.

## §5. Evidence

- [ ] `results.md` opens with a headline table; each row cites a path under `runs/`.
- [ ] Cited paths exist and contain the quoted numbers.
- [ ] No magic numbers in `results.md` or `verdict.md` without a path link.

## §6. Verdict and scorecard

- [ ] `verdict.md` has a verdict of `go` / `no-go` / `inconclusive`.
- [ ] Reasoning ties to specific evidence paths.
- [ ] `## Hypothesis scorecard` section is present (unless mapping probe).
- [ ] At least one row is 🟡 partial or ❌ wrong, OR the README makes a credible case the question was non-trivial. (100% correct scorecards are flagged for review, not auto-failed.)

## §7. Downstream propagation

- [ ] If the verdict changes how we work: `docs/retrospectives/NNN-<topic>.md` exists and is cross-linked from `verdict.md`.
- [ ] If the verdict updates the status matrix in the root `README.md`: the matrix cell is bumped in the same commit as the verdict.
- [ ] Executive summary (`docs/executive-summary.md`) updated if the headline learning warrants it.

## §8. Scope hygiene

- [ ] The question is not a debugging task disguised as an experiment.
- [ ] The question is not answerable by reading code + grep.
- [ ] The probe is time-bounded -- under a working week. If it grew larger, it should have been split.

## How to use a failure

A failed box is a finding, not a verdict. Fix the smallest thing that closes the gap. If a probe fails §3 (two-commit rule), it's unsalvageable -- record the finding in the retrospective and move on; don't backfill timestamps.
