# Skill template: the two canonical shapes

Source: derived from `../SKILL.md` (the `authoring-skills` chassis). This
document is the canonical reference for the section-by-section shape of skills
in this plugin. When in doubt about whether a heading belongs, or how long a
section should be, consult this file.

## Two shapes, one chassis

Every skill in this plugin is one of two types:

1. **Principle doc.** A durable body of knowledge about a concern (security,
   testing, configuration, architecture, etc.). It is consulted, not invoked.
   A reviewer or implementer reads it to absorb principles, outcomes, and the
   current recommended tools. Most skills in this plugin are principle docs.

2. **Procedural skill.** A workflow with a defined input, a numbered sequence
   of steps, and a defined output. It is invoked to do work. Orchestrators
   (review fan-outs, merge cycles), maintenance skills (audits, bootstrappers),
   and setup skills are procedural.

Pick principle-doc when the artifact answers "what does good look like for
this concern, and how do I recognize it." Pick procedural when the artifact
answers "run these steps to produce this result." A skill is rarely both. If
you find yourself wanting both, split into two skills and have the procedural
one cite the principle doc.

A useful tell: if the natural opening sentence is "When you are reviewing X,
look for Y," it is a principle doc. If the natural opening is "Given input X,
produce output Y by doing the following steps," it is procedural.

## Principle-doc shape, section by section

The principle-doc skeleton:

```
---
name: <name>
description: <trigger phrases + contexts + explicit non-triggers>
---

# Title

## Overview
## Outcomes we are looking for
## Principles
## Anti-patterns
## Recommended tools and practices (as of YYYY-MM-DD)
## References
## Continual improvement
```

### Overview

What it is for: a one-paragraph durable framing of the concern. Names the
concern, says why it matters, and gestures at the boundary of what the skill
covers. The reader should know within five lines whether they are in the
right document.

Example opening:

```
Configuration is how a system absorbs change without code edits. Strong
configuration practice keeps secrets out of source, makes environment-specific
behavior explicit, validates at startup, and stays discoverable. This skill
covers env-var layering, typed config objects, and twelve-factor parity.
```

Does NOT belong: trigger phrases (those live in frontmatter), tool
recommendations, step-by-step instructions, or rationale for individual rules.

Length budget: one paragraph, three to six sentences.

### Outcomes we are looking for

What it is for: the north-star goals that a reviewer or implementer is trying
to achieve. Each outcome is a state of the world, not an activity. Each
outcome carries one or two observable signals so a reviewer can tell whether
the outcome is met.

Example opening:

```
### Secrets never appear in source or build artifacts
Signals: no secret-shaped strings in git history; CI secret scan passes; all
runtime secrets resolve from a secret store or injected env.

### Configuration is validated at process start, not first use
Signals: the process exits with a clear error on missing or malformed config;
no `KeyError` or `undefined` at request time from missing config.
```

Does NOT belong: tool names (those live under Recommended tools), narrative
prose, or anti-patterns. Keep outcomes terse and state-shaped.

Length budget: three to five outcomes. Below three suggests the concern is too
narrow to deserve its own skill. Above five suggests you are mixing two
concerns.

### Principles

What it is for: the durable HOW. Short, declarative statements of the rules
that, if followed, tend to produce the outcomes above. Principles outlive any
particular tool.

Example opening:

```
- Treat configuration as a typed object, not a bag of strings.
- Validate the whole config at startup; fail loud, fail early.
- Separate secret from non-secret config so they can be stored differently.
- Prefer environment variables for deployment-varying values; prefer files
  for structure-heavy values.
```

Does NOT belong: tool-specific guidance (Vault, doppler, etc.), version
numbers, or anything dated.

Length budget: five to eight principles. More than eight and the reader stops
internalizing them.

### Anti-patterns

What it is for: observational descriptions of common failure modes. Phrased
as patterns to recognize, not commands to follow.

Example opening:

```
- `.env` files committed to git, even under `.env.example` aliases that
  accidentally contain real values.
- Reading `os.environ` ad hoc throughout the codebase rather than through a
  single typed config object.
- Defaulting secrets to empty strings, hiding misconfiguration until a 401
  appears in production.
```

Does NOT belong: imperative commands ("do not commit secrets"). Write them as
patterns you can spot in a diff: "Secrets defaulted to empty strings."

Length budget: six to twelve. Fewer than six and the skill cannot anchor a
review; more than twelve and the list becomes unscannable.

### Recommended tools and practices (as of YYYY-MM-DD)

What it is for: the current, dated, opinionated set of concrete tools and
practices. Grouped under the outcome each recommendation ladders up to (see
`outcomes-laddering.md`). The date in the heading signals that this section
ages and must be refreshed.

Example opening:

```
(as of 2026-05-13)

### For: Secrets never appear in source or build artifacts
- Use `gitleaks` as a pre-commit hook and in CI.
- Store runtime secrets in 1Password or AWS Secrets Manager; inject at
  deploy time, never at build time.

### For: Configuration is validated at process start, not first use
- Use `pydantic-settings` (Python) or `zod` (TypeScript) for typed config
  with startup validation.
```

Does NOT belong: undated recommendations, principles restated as tools, or
tools without a parent outcome.

Length budget: roughly two to five recommendations per outcome. Total often
lands at fifteen to twenty-five bullets.

### References

What it is for: pointers to the `references/` directory, plus authoritative
external links. One line per reference, with a short gloss.

Example opening:

```
- `references/secret-rotation-runbook.md`: rotation procedure for each store.
- `references/twelve-factor-summary.md`: condensed version of the twelve-
  factor config chapter.
- https://12factor.net/config (canonical source)
```

Length budget: as long as needed, but each entry must earn its line.

### Continual improvement

What it is for: a single link to the GitHub issue tracker or discussions page
where readers can file drift, gaps, or proposed updates. Standardized across
skills so contributors know where to send feedback.

Example:

```
File drift, gaps, or proposed updates at
https://github.com/AgentParadise/harness-engineering/issues
```

Length budget: one to three lines.

## Procedural-skill shape, section by section

The procedural skeleton:

```
---
name: <name>
description: <trigger phrases for the procedure being invoked>
---

# Title
## When to Use (and When NOT to Use)
## Input
## Workflow
## Output
## Outcomes we are looking for
## Recommended tools and practices (as of YYYY-MM-DD)
## References
## Continual improvement
```

### When to Use (and When NOT to Use)

What it is for: a short decision aid. Two bulleted lists: when to invoke this
procedure, and when not to. The "not to" list is what prevents misrouting.

Example opening:

```
Use when:
- A pull request is ready for human review and you want a mechanical pre-pass.
- You are auditing a long-lived branch before merge.

Do NOT use when:
- The change is a docs-only edit (use `docs-review` instead).
- The branch has unresolved merge conflicts (resolve first).
```

Length budget: two to five bullets per list.

### Input

What it is for: the precondition. What the caller must provide, what state
the workspace must be in, what credentials or context must exist.

Example opening:

```
- A git branch with committed changes, rebased on the target branch.
- `gh` authenticated for the target repo.
- Optional: a path filter to scope the review.
```

Length budget: three to eight bullets.

### Workflow

What it is for: the numbered procedure. Each step is imperative, concrete,
and verifiable. Sub-steps allowed when a step decomposes naturally.

Example opening:

```
1. Resolve the diff range with `git merge-base` and capture the file list.
2. For each leverage-point skill, dispatch a parallel review agent scoped to
   the changed files.
3. Aggregate findings by severity; deduplicate cross-skill overlaps.
4. Emit a single review comment with grouped findings.
```

Does NOT belong: rationale paragraphs (push those to References), or
principles dressed up as steps.

Length budget: four to twelve top-level steps. Longer workflows should be
split into phases or sub-procedures.

### Output

What it is for: the postcondition. What artifact, file, comment, or state
change the caller can expect on success. Also: exit codes or status values if
the procedure is invoked programmatically.

Example opening:

```
- A single PR review comment containing grouped findings.
- Exit status: `DONE`, `DONE_WITH_CONCERNS`, or `BLOCKED`.
- No files committed; no branches pushed.
```

Length budget: two to six bullets.

### Outcomes we are looking for

Procedural skills may carry Outcomes when the procedure has a clear north
star. For a review orchestrator, the outcome is something like "the codebase
is audited mechanically with no findings missed." For a setup procedure, the
outcome is "a fresh contributor reaches a green test run in one command."

Skip this section if the procedure is purely mechanical and has no judgment
component (e.g., a file-renamer).

Length budget: one to three outcomes when present.

### Recommended tools and practices (as of YYYY-MM-DD)

Same shape as principle-doc. Dated, laddered under outcomes when outcomes
exist, otherwise grouped by workflow phase.

### References and Continual improvement

Same shape as principle-doc.

## Frontmatter rules

The YAML frontmatter is required at the top of every `SKILL.md`. It has
two required fields and one optional metadata field:

```
---
name: <kebab-case-name>
description: <routing description>
placement: <optional installation-target metadata>
---
```

Rules:

- `name` must be kebab-case (lowercase, hyphen-separated).
- `name` must match the directory name exactly. The skill at
  `skills/authoring-skills/SKILL.md` has `name: authoring-skills`.
- `description` carries all the routing weight. It must include trigger
  phrases (verbs and nouns the user is likely to say), the contexts where the
  skill applies, and explicit non-triggers when the skill is easily confused
  with a sibling.
- `placement` is optional. When present, it documents where the skill
  should live across consumer repos (meta scope, domain-plugin scope,
  flat-skill scope). It carries no routing weight; auditors and porters
  use it to keep installations consistent.
- No other top-level frontmatter fields are permitted. Versioning, owners,
  authorship, and tags live elsewhere (in a manifest or in the README).

For the full trigger-phrase grammar, see `description-trigger-rules.md`.

## Bundled resources

A skill may ship with sibling directories alongside `SKILL.md`:

### `references/`

Use for: durable supplementary documentation that the `SKILL.md` cites but
that would bloat it past the length guardrail. Section deep-dives,
checklists, templates, worked examples.

Naming: kebab-case `.md` files. Names should be nouns or noun phrases
(`audit-checklist.md`, `outcomes-laddering.md`), not verbs.

### `scripts/`

Use for: executable helpers that the workflow steps invoke. Bash, Python, or
Node scripts. Each script should be self-contained, with a header comment
describing input, output, and any environment requirements.

Naming: kebab-case with an extension (`run-audit.sh`, `aggregate-findings.py`).

### `assets/`

Use for: non-executable, non-Markdown artifacts that the skill ships:
templates, prompt snippets, sample YAML, fixture files, images used by
references.

Naming: descriptive, with the appropriate extension. Group by purpose when
the directory grows beyond ten files.

A skill with no bundled resources is fine. Do not create empty directories.

## Example openings

### Principle-doc example

```
---
name: cache-discipline
description: Use when reviewing caching concerns: cache key design, TTL
  selection, invalidation strategy, stampede protection, negative caching,
  observability of hit/miss rates. Not for CDN configuration (see
  `edge-delivery`) or database query plans (see `query-performance`).
---

# Cache discipline

## Overview
Caching trades freshness for latency and cost. Strong caching practice makes
that trade explicit per cache, names every key, bounds every TTL, and exposes
hit/miss rates as first-class telemetry.
```

### Procedural-skill example

```
---
name: release-cut
description: Use to cut a versioned release: tag the commit, generate the
  changelog, publish artifacts, and open a release PR. Not for hotfixes (see
  `hotfix-flow`) or pre-release tags (see `prerelease-cut`).
---

# Release cut

## When to Use (and When NOT to Use)
Use when the release branch is green and the changelog draft is approved.
Do NOT use for hotfixes or pre-release tags.
```

## Length guardrails

- **Soft cap: 500 lines** for `SKILL.md`. Above that, move material to
  `references/` and cite it. The chassis is meant to be skimmable in one pass.
- **Soft floor: 80 lines.** Below 80 lines often means the skill is too thin
  to stand alone. Consider merging with a neighbor, or expanding Outcomes
  and Anti-patterns until the skill earns its place.
- Individual sections have their own budgets (see above). Treat them as soft
  guidance, not hard limits, but be suspicious of any section that grows past
  twice its budget.
- `references/` files have no hard cap, but each should still be focused on
  one topic. Split when a file grows past 500 lines.

## Cross-references with siblings

- For the trigger-phrase grammar that goes in the `description` field, see
  `description-trigger-rules.md`.
- For the outcomes-to-recommendations laddering pattern (how each tool
  recommendation cites the outcome it ladders up to), see
  `outcomes-laddering.md`.
- For the audit checklist used to verify an existing skill against this
  chassis, see `audit-checklist.md`.
- For Anthropic's underlying guidance on skill authoring (the upstream
  philosophy this chassis specializes), see `anthropic-skill-creator.md`.
