# Anti-Yellow-Flags: Observed Failure Modes in Skill Authoring

Distilled from Anthropic's skill-creator guidance (the "yellow flags" they call out for skills that look disciplined but read as brittle) and from observed failure modes in this plugin's own skill corpus. The Anthropic list names a handful of stylistic tells; this document expands that list with patterns surfaced during audits of skills authored in this repository.

This is a catalog of observations, not a list of commandments. Each item describes what the failure mode looks like when it shows up in a `SKILL.md`, why it degrades the skill's effectiveness, and how to rework it.

## Why observations beat commandments

Anti-patterns work better when stated as "this is what I see in the wild" rather than "you shall not do X." The agent reads the skill and parses observations more effectively than imperatives because observations carry context: what triggered the pattern, what it looks like on the page, and what it means for the reader. An imperative strips that context down to the rule itself, and in doing so it loses discriminative power on edge cases. The agent confronted with a near-match cannot tell whether the rule applies, because the rule no longer carries the signal that distinguishes its in-scope cases from adjacent ones.

The second reason is tonal. A skill saturated with "NEVER" reads like a policy document, and policy documents teach readers to skim. An observation invites the reader to check the artifact against the description, which is the behavior the skill actually wants. The shift from "you must" to "this is what a healthy version looks like" turns the skill into a diagnostic instrument rather than a tribunal.

## Yellow flags Anthropic explicitly names

### Heavy ALWAYS / NEVER / MUST blocks

Reads like a policy document. After three imperatives in a row, the agent stops parsing each one and starts skimming the block as a unit. The third NEVER carries no more weight than the first; in practice it carries less, because attention is already gone. Reframe as "do X because Y," with the rationale carrying the discriminative weight. The reader who understands the Y can apply the X to cases the author did not anticipate.

### Rigid structures dressed up as discipline

Excessive section headers with one-sentence bodies. Each header promises a topic; each body delivers a sentence; the cumulative effect is a table of contents pretending to be a document. The ritual of structure substitutes for the content the structure was meant to organize. A skill with eight `##` headers and forty lines of body is, in almost every case, four headers and forty lines of body wearing a costume.

### Test-overfit content

The skill solves the two examples the author ran during drafting and falls apart on the third real task. Symptom: every example in the body refers to the same domain, the same tools, or the same shape of problem. The skill is a transcript of the debugging session that produced it, not a general guide. The fix is to write at the level of pattern (what is true across cases) and demote the specific examples to one or two illustrations.

### Description that describes the topic, not the trigger

"This skill is about X." The agent does not learn when to invoke; the user does not see the routing signal. The description's job is to fire on the right requests and stay silent on adjacent ones. A description that names the topic without naming the trigger phrases will either over-fire (matching anything in the topic neighborhood) or under-fire (failing to match phrasings the author did not consider). See `description-trigger-rules.md`.

## Yellow flags from this plugin's own audit

### `## When to Use` section in a principle-doc body

Routing logic in the wrong place. "When to use" belongs in the description (frontmatter), where the harness reads it to decide whether to load the skill. Putting it in the body means the harness already loaded the skill before the reader learned whether to use it. Body should open with `## Overview` or the first content section, not a re-litigation of the routing decision.

### Body's first sentence is "This skill is for X."

The frontmatter already said that. The first body sentence is the most valuable real estate in the file; spending it on a re-introduction wastes the slot. First sentence should deliver useful content: the central observation, the load-bearing principle, the thing the reader came for.

### `## Red Flags - STOP` as commandments

Each entry starts with "NEVER" or has an imperative shape. The auditor reading the skill against an artifact cannot mark "NEVER make the agent read pasted screenshots" as present or absent, because "NEVER" is a rule, not a property. Reframe each entry as an observation about the artifact: "the agent is required to read pasted screenshots to debug UI bugs," or "the workflow lacks a programmatic screenshot capture step." These can be checked against the codebase; rules cannot.

### Rationalization-prevention tables that double as "I told you so" lists

Useful in moderation. Over-deployed, they perform discipline without enforcing it: the reader sees a long table, recognizes the pattern, and skips it. Cap at 5 to 7 rows in the body. If the catalog needs more entries, move the long form to `references/rationalizations.md` and leave a pointer.

### Growth examples that drift specific-to-the-domain

Skills sometimes ladder examples through POC / Growing / Production / Safety-critical. When the production tier just says "in production, add tools," it adds no information; "more rigor" is not a maturity level. The example must distinguish what changes at each maturity level beyond a vague increase in discipline. If the author cannot articulate the change, the tier should be cut.

### Key Patterns blocks with too many checkmark and cross pairs

Two or three pairs is instructive. Ten is noise. The signal-to-context-cost drops fast past three. If the patterns are genuinely ten distinct lessons, they belong in a `references/patterns.md` file with room to breathe; if they are variations on a theme, three representative pairs carry the meaning.

### Tools listed without rationale

"Use Playwright." The next reader cannot tell whether the recommendation is still valid when Playwright is replaced by something else, because the recommendation was tied to the tool name rather than the outcome the tool delivered. Every recommendation cites the outcome it ladders up to. See `outcomes-laddering.md`.

### Outcomes section absent

The skill is a pile of tactics with no north star. When the tools rot, the whole body rots with them, because nothing in the document tells the reader what the tactics were trying to achieve. The outcomes section is what survives a tool migration; without it, the skill has a half-life equal to the half-life of its tooling.

### Outcomes that name tools or metrics

"Page load under 800ms" is a metric, not an outcome. "Agent can detect performance regression without human intervention" is an outcome. The metric is a signal that the outcome is being met; promoting the signal to the goal causes the reader to optimize the number rather than the capability.

### Body over 500 lines with no `references/`

Loaded context budget is being wasted on detail the current task does not need. The body is for the load-bearing 20 percent; the references hold the depth. A skill that refuses to split is a skill that has not decided what its central claim is.

### Em-dashes

This plugin's house rule. The em-dash (U+2014) is a stylistic tell of LLM-written prose, and its presence indicates the author has not edited the model's output. Use colons, commas, periods, parentheses, or restructure the sentence.

### Marketing language

"Powerful," "comprehensive," "best-in-class," "advanced." Adds no information; degrades signal. The reader skips these words automatically, which means anything load-bearing positioned next to them is also at risk of being skipped.

### Cross-references with absolute paths

`/Users/neural/...` or `~/Code/...` in a cross-reference. Breaks the moment the skill is installed in a different location. Cross-references inside a skill use paths relative to the skill root (`references/foo.md`), and cross-references between skills use the plugin-qualified form documented in `anthropic-skill-creator.md`.

### Continual improvement section pointing at a stale URL

A common pattern: the skill ends with a "feedback welcome" link to a GitHub issue tracker, and the URL is wrong, dead, or pointing at the author's personal fork. The link must resolve. If there is no place to send feedback, omit the section.

## How to fix each, with examples

### Heavy NEVER block

Before:

```markdown
## Red Flags - STOP

- NEVER skip the test suite.
- NEVER push without review.
- NEVER commit generated artifacts.
- NEVER use force-push on shared branches.
```

After:

```markdown
## Observed failure modes

- The test suite is skipped, because the author believed the change was
  trivial. Trivial changes are the modal source of regressions in this repo,
  so the suite runs on every push.
- A commit lands without review, because the author had merge rights and a
  deadline. The review gate exists because the modal author has both.
```

The rule survives, but the rationale carries it; the reader who understands the rationale can apply the rule to cases the author did not list.

### Topical description

Before:

```yaml
description: This skill is about writing good skills.
```

After:

```yaml
description: |
  Use when creating, editing, or auditing a SKILL.md file in this plugin.
  Triggers on phrases like "write a skill", "audit my skill", "skill yellow
  flags", "skill anti-patterns". Does not trigger on general writing or
  documentation tasks unrelated to the skill format.
```

The trigger phrases are explicit, and the non-triggers prevent over-firing. See `description-trigger-rules.md`.

### Red Flags as commandments

Before:

```markdown
- NEVER make the agent read pasted screenshots.
```

After:

```markdown
- The workflow requires the agent to read pasted screenshots to diagnose UI
  bugs. The agent has no programmatic screenshot capture step.
```

The auditor can check the second version against the artifact and mark it true or false; the first version is a rule that the artifact cannot satisfy or violate, only ignore.

### Outcomes that name tools

Before:

```markdown
## Outcomes

- Playwright runs on every PR.
- Page load under 800ms.
```

After:

```markdown
## Outcomes

- The agent can detect UI regressions without human intervention on every
  pull request.
- The agent can detect performance regressions before they reach production.

## Current recommendations (2026-05)

- Playwright is the current browser automation tool.
- 800ms is the current page-load budget; see `references/performance.md`.
```

The outcomes name the capability; the dated recommendations name the tool that currently delivers it. When the tool changes, the outcomes survive.

### Body over 500 lines

Before: a single SKILL.md with sections on history, philosophy, tooling, examples, edge cases, and a glossary, totaling 700 lines.

After: a SKILL.md of 200 lines covering the load-bearing principles and routing, with pointers to `references/history.md`, `references/tooling.md`, `references/examples.md`, `references/edge-cases.md`, and `references/glossary.md`. The body loads on every invocation; the references load only when the task needs them.

## When a yellow flag is actually correct

Discipline has its place. Heavy NEVER blocks are appropriate for safety-critical rules where the cost of misinterpretation is real, and where the rule is the kind a competent reader might reasonably ignore. "NEVER commit secrets" is the canonical example: the reader will, in the wild, encounter situations where committing a secret feels expedient ("it is only a test key," "the repo is private"), and the imperative form is doing real work against a real rationalization.

The test is this: is the rule the kind a competent reader might reasonably ignore in the absence of the imperative? If yes (secrets, destructive git operations, prod-database writes), the NEVER form is appropriate and the cost of stylistic stiffness is worth paying. If no (formatting conventions, structural preferences, style choices), the "do X because Y" form is more effective, because the reader is not in danger of ignoring the rule, only of misapplying it, and the rationale is what enables correct application.

The chassis allows imperative form in narrow cases. The audit catches it when it has spread beyond those cases.

## Cross-references

- `audit-checklist.md`: the checklist the auditor walks when reviewing a skill against this catalog.
- `outcomes-laddering.md`: how to write an outcomes section that survives tool migration.
- `description-trigger-rules.md`: how to write a description that fires on the right requests and stays silent on adjacent ones.
- `anthropic-skill-creator.md`: the upstream guidance this catalog extends.
- `skill-template.md`: the starting structure that already encodes the fixes for the most common anti-patterns.
