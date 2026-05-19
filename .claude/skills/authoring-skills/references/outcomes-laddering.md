# Outcomes laddering

Project addition on top of Anthropic skill-creator guidance. The skill-creator
documentation covers structure, frontmatter, and progressive disclosure. This
document covers the most opinionated addition the harness-engineering chassis
makes on top of that: durable Outcomes as the north star of every skill, with
Recommended tools and practices grouped under and laddering up to those
outcomes.

## The pattern in one diagram

```
   Outcomes (durable goals)
       ^ ladders up to
   Recommended tools and practices (dated, churns)
       ^ replaced when better options emerge
```

Outcomes stay. The layer below them is allowed to rot. This is intentional
separation, not accidental drift.

Why two layers instead of one:

1. When a tool gets replaced, only the dated
   `## Recommended tools and practices (as of YYYY-MM-DD)` section needs
   editing. The outcomes above it are unaffected.
2. A new reader can decide whether a tool recommendation is still valid by
   asking a single question: does it still serve the named outcome? If yes,
   keep it. If no, the recommendation has rotted even if the section's date
   is recent.
3. Auditing becomes mechanical. For every recommendation, you can point at the
   outcome it ladders up to. If you cannot, the recommendation is unmoored
   and should be removed or rewritten.

The contract: outcomes are load-bearing. Tools are replaceable. A skill that
inverts this (long tool list, vague or absent outcomes) will not survive its
first tool churn cycle.

## Writing good outcomes

An outcome is:

- A *goal*, not a tool or a metric.
  - Goal: "Agent can perceive UI state without human translation."
  - Tool: "Use Playwright." (Wrong: names the implementation.)
  - Metric: "Page load under 800ms." (Wrong: a measurement, not a purpose.)
- Stated as a single sentence in plain English. Avoid jargon when a plain
  word will do. If you need a term of art, define it once nearby.
- Paired with one or two *evidence signals*: checkable facts that, if true,
  suggest the outcome is being met. Signals can age faster than the outcome
  itself, and that is fine. Treat them as the dated layer for the outcome
  the same way recommendations are the dated layer for principles.
- Independent of the others when possible. If two outcomes overlap heavily,
  merge them. Two outcomes that always rise and fall together are one
  outcome wearing two hats.
- Few in number. Three to five outcomes per skill is the comfortable range.
  More than seven is a strong signal the skill is doing the job of two
  skills and should be split.

A useful test: read the outcome aloud to someone outside the project. If they
cannot tell whether it is being met without asking which tools you use, the
outcome is written at the right altitude. If their first follow-up question
is "how", the outcome is doing its job: leaving the "how" to the layer below.

### Outcome template

```
### Outcome N: <single plain-English sentence>

<One short paragraph: why this matters, what failure looks like.>

Evidence signals:
- <Checkable fact 1.>
- <Checkable fact 2.>
```

## Writing good recommendations under outcomes

Each recommendation:

- Is grouped under the outcome it serves. If a recommendation genuinely
  ladders up to two outcomes, list it under both rather than splitting it
  across the gap. Duplication here is cheap; ambiguous attribution is not.
- Names the tool or practice first, then states the laddering with a phrase
  like "Ladders up by ..." or "Serves this outcome by ...". The laddering
  sentence is the load-bearing part. Without it, the recommendation is just
  a brand name.
- Lives under a dated section header:
  `## Recommended tools and practices (as of YYYY-MM-DD)`. The date is the
  honesty marker. It tells a future reader how stale the list is allowed to
  be before they should re-evaluate.
- Is observational about its tradeoffs, not advocacy. Note what the tool
  costs, what it does not cover, and what would make you replace it. A
  reader who disagrees can disagree on the evidence rather than the vibe.

### Recommendation template

```
- <Tool or practice name>. <One sentence describing what it does.>
  Ladders up by <how this advances the outcome above>.
  Tradeoffs: <what it costs, what it does not cover>.
```

## Worked example A: browser-legibility

Below is a credible outcomes section for a skill about giving coding agents
visibility into browser state, followed by a partial recommendations section
showing the laddering. Paraphrased to illustrate the shape; not a verbatim
copy of any current skill file.

```
## Outcomes we are looking for

### Outcome 1: agent can perceive UI state without human translation

The agent should be able to answer "what is on the page right now" using
the same kind of structured data a human inspector would read, not by
asking a human to describe a screenshot. When this outcome is missing,
every UI bug becomes a ping-pong between the agent and the human, and
the agent's iteration loop stalls.

Evidence signals:
- The agent can list visible interactive elements with their roles and
  labels without a human paraphrasing a screenshot.
- A failing selector produces a diagnostic the agent can act on, not just
  a generic "element not found".

### Outcome 2: failures arrive as structured signals, not screenshots alone

When a UI action fails, the agent receives console errors, network
failures, and accessibility-tree state alongside any visual artifact.
Screenshots are evidence for humans; structured signals are evidence the
agent can route into its next decision.

Evidence signals:
- Console errors and failed network requests are captured automatically
  on test failure.
- A failure report includes at least one machine-readable artifact in
  addition to any image.

### Outcome 3: before/after state is diffable

For any UI change the agent makes, the prior and current state can be
compared without rerunning the whole flow. This keeps regressions cheap
to detect and keeps "did this change anything I did not intend" answerable
in seconds.

Evidence signals:
- Snapshots are stored in a format that diffs cleanly in version control
  or a review tool.
- Reverting a change visibly reverts the snapshot, with no manual cleanup.
```

```
## Recommended tools and practices (as of 2026-05-13)

### Outcome: agent can perceive UI state without human translation

- Playwright Node SDK via npx playwright. Provides accessibility-tree
  snapshots (token-cheap structured DOM), screenshots, and console plus
  network event capture from a single entry point.
  Ladders up by giving every human inspection action a programmatic
  equivalent the agent can call directly.
  Tradeoffs: Node toolchain assumed present; Chromium download on first
  run can be slow on cold machines.

- Per-invocation Playwright-bundled Chromium rather than a system browser.
  Ladders up by removing the "is the right browser even installed" question
  from every iteration, which previously consumed a meaningful share of
  failed runs.
  Tradeoffs: larger on-disk footprint; version is pinned to the Playwright
  release rather than tracking system updates.

### Outcome: failures arrive as structured signals, not screenshots alone

- Default to capturing console messages and network responses on every
  Playwright run, not only on failure.
  Ladders up by making the structured-signal path the cheapest path,
  so the agent never has to retry just to get logs.
  Tradeoffs: slightly larger artifact directory; trivial to gitignore.

- Emit failure reports as JSON next to any PNG. Ladders up by ensuring
  the agent always has a machine-readable artifact alongside any human
  one, even when a screenshot is also produced.
  Tradeoffs: a small amount of report-formatting code to maintain.

### Outcome: before/after state is diffable

- Snapshot accessibility trees as pretty-printed JSON, not as opaque
  binary blobs. Ladders up by making "what changed" answerable with a
  standard diff tool, no custom viewer required.
  Tradeoffs: slightly more verbose on disk than a binary representation.
```

Notice what the laddering does. If a future reader replaces Playwright with
some successor (call it FutureDriver), they can check each bullet: does
FutureDriver still give every human inspection action a programmatic
equivalent? Does it still remove the "is the browser installed" question?
If yes, swap the name and keep the bullet. If no, the bullet needs a real
rewrite, not just a search and replace.

## Worked example B: testing-coverage

A more generic illustrative example. Outcomes for a skill about keeping
the codebase mechanically consistent and well-tested:

```
## Outcomes we are looking for

### Outcome 1: the codebase stays consistently formatted without human review effort

Formatting drift is never a topic in code review. Whatever style the
project uses, the machine enforces it, so humans (and agents) spend their
attention on logic instead of whitespace.

Evidence signals:
- Pull request reviews do not contain formatting comments.
- A fresh clone, with no manual setup beyond the documented bootstrap,
  formats on commit automatically.

### Outcome 2: regressions are caught before they reach the integration branch

A change that breaks previously working behavior fails locally or in CI
before it can land. The team does not rely on manual smoke testing to
notice regressions.

Evidence signals:
- Coverage report exists and is published per build.
- A deliberately broken test case fails the merge gate, not only a
  later deploy step.
```

```
## Recommended tools and practices (as of 2026-05-13)

### Outcome: the codebase stays consistently formatted without human review effort

- Project-standard formatter wired as a pre-commit hook with auto-fix on
  staged files. Ladders up by making the formatted state the default
  outcome of a commit, not a thing the contributor has to remember.
  Tradeoffs: first-commit-after-bootstrap can be slower while the hook
  warms up.

- Linter run in CI as a blocking check, configured to share the same
  rule set as the local hook. Ladders up by removing the "works on my
  machine" gap between local format and merged format.
  Tradeoffs: two places (local hook, CI) to keep in sync; mitigated by
  pointing both at the same config file.

### Outcome: regressions are caught before they reach the integration branch

- Coverage tool with a threshold enforced in CI (the project's chosen
  number, with rationale recorded nearby). Ladders up by making
  coverage regressions visible at the moment they are introduced, not
  weeks later.
  Tradeoffs: thresholds invite gaming via trivial tests; pair with a
  review norm that values meaningful assertions.

- Pre-merge test run on the same matrix as the release build. Ladders
  up by ensuring that the gate which protects the integration branch is
  the same gate that protects releases, removing a class of "passed CI,
  failed deploy" surprises.
  Tradeoffs: matrix runs cost CI minutes; revisit if the project's
  supported surface shrinks.
```

Both examples share a pattern. The outcomes do not name tools. The
recommendations name tools but always come back to the outcome they serve.
A reader can audit the recommendations bullet by bullet by asking only the
laddering question.

## Anti-patterns in this layer

Observations from skills that have rotted, or that we caught before they
rotted:

- **Outcomes that name tools.** "Use a structured logger" is not an outcome.
  The outcome is "the agent can query logs by attribute, not just by string
  match." When the outcome names the tool, replacing the tool requires
  rewriting the outcome, which defeats the layering.

- **Recommendations with no laddering.** "We use X." is not enough. Without
  a "ladders up by" sentence, the reader cannot tell whether X still earns
  its place. Unmoored recommendations are the first to rot and the hardest
  to remove, because nobody remembers why they were added.

- **More than seven outcomes per skill.** A skill with twelve outcomes is
  doing the job of two or three skills. Split it. Each child skill should
  end up with three to five outcomes and a clearer north star.

- **Outcomes section absent or buried at the bottom of the file.** The
  outcomes section is the north star. It cannot serve as a north star if
  the reader has to scroll past two hundred lines to find it. Put it near
  the top, right after the skill's purpose statement.

- **Outcomes section that contradicts the principles section.** If the
  principles say "fail fast" and the outcomes describe a system that
  swallows errors to keep going, the skill is unsure what it stands for.
  Fix one or the other before adding any recommendations underneath.

- **Undated recommendations section.** Without a date, a reader has no way
  to judge staleness. The date does not need to be a precise commit time;
  the YYYY-MM-DD on the section header is enough.

- **Recommendations advocating instead of observing.** "X is the best
  choice" is advocacy. "X gives us Y, costs us Z, and would be replaced
  if W appeared" is observation. The second form survives disagreement;
  the first invites it.

- **Evidence signals that restate the outcome.** "Evidence: the outcome
  is met" is not a signal. A signal is a checkable fact someone outside
  the project can verify. If you cannot write the signal as a yes/no
  question, the outcome is too vague.

## Cross-references

- `skill-template.md`: where the Outcomes section and the Recommended tools
  and practices section sit in the canonical shape of a skill file.
- `audit-checklist.md`: the binary checks an auditor runs against a skill,
  including the laddering audit.
- `anti-yellow-flags.md`: the broader anti-pattern catalog this document's
  Anti-patterns section is a focused slice of.
