---
name: authoring-skills
description: Use when authoring or auditing a Claude skill (`SKILL.md` with YAML frontmatter), refining an existing skill, or reviewing a skill against a chassis. Trigger phrases include "write a skill", "author a skill", "audit this skill", "review the skill", "skill structure", "skill shape", "SKILL.md template", "skill description", "skill frontmatter", "skill not triggering". Covers Claude Code skills, plugin skills, personal `~/.claude/skills`, and project-local `.claude/skills/`. Applies to principle-doc skills (durable knowledge about a concern) and procedural skills (workflow with input/output). Do NOT use for slash commands, hooks, or MCP servers; those have different shapes.
placement: "Meta-skill. Install in `.claude/skills/<skill-name>/` (repo-local meta scope) or `plugins/<meta-plugin>/skills/<skill-name>/` (when exported via a meta plugin). NOT alongside domain-specific skills under `skills/` or `plugins/<domain-plugin>/skills/`. The rule: skills that teach how to author other skills live at the meta level, separate from skills that teach a specific domain concern."
---

# Authoring Skills

## Overview

A skill is a `SKILL.md` file (plus optional bundled resources) that teaches Claude how to handle a concern by being loaded into context when relevant. Two things determine whether a skill works: whether Claude routes the right tasks to it (the description's job), and whether the body actually helps once loaded (the content's job). Most skill problems are one of those two; this chassis exists to make both reliable.

This skill is the canonical authoring contract. Follow it whenever writing a new skill or auditing an existing one, both inside this plugin and in any other Claude project. It distills Anthropic's official skill-creator guidance and adds two opinionated additions: **Outcomes** as a durable north-star section, and an **anti-yellow-flag** posture that prefers observation over command-form rules.

## Outcomes we are looking for

Goals are durable. Tools and tactics will change; these will not. Each outcome has 1-2 evidence signals you can check later to see whether the goal is being met.

### Outcome 1: skills route correctly

Claude invokes the right skill for the task without prompting from the user.

- *Signal:* the user gives a task that matches the skill's domain, and Claude reaches for the skill on its own.
- *Signal:* unrelated tasks do NOT trigger the skill (no false-positive activations cluttering the session).

### Outcome 2: the body earns its lines

Every paragraph in a loaded skill pulls weight. The agent can act faster and more correctly with the skill than without it.

- *Signal:* if a paragraph were removed, behavior would measurably degrade.
- *Signal:* the skill body fits comfortably under 500 lines; depth lives in `references/`.

### Outcome 3: durable content does not rot with the tool layer

Principles and outcomes outlive specific tool recommendations. When a recommended library is replaced, only the dated tools-and-practices section needs editing.

- *Signal:* the date on `## Recommended tools and practices (as of YYYY-MM-DD)` matches the last edit to that section; everything above it is unaffected by tool churn.

### Outcome 4: auditing is mechanical, not opinion-shaped

A reviewer following this chassis can decide if a skill conforms without making aesthetic judgments. Gaps are checkable.

- *Signal:* the audit checklist in `references/audit-checklist.md` returns a clean pass-fail per criterion.

### Outcome 5: the chassis demonstrates itself

This skill obeys its own rules. If you read this file looking for a violation of the chassis, you will not find one. Drift in this file is an outage of the entire authoring discipline.

- *Signal:* `authoring-skills` itself passes the audit checklist with zero findings.

## Principles

1. **Structure is two-axis: type and shape.** A skill is either a **principle doc** (durable knowledge about a concern, consulted not invoked) or a **procedural skill** (a workflow with input, steps, and output). The two have different section orders; pick one consciously. See `references/skill-template.md` for both canonical shapes.

2. **The description carries the routing.** Triggering is a separate problem from execution. The description must list explicit trigger phrases, common synonyms, file extensions when applicable, adjacent intents users phrase casually, and explicit non-triggers ("Do NOT use for X"). Description content lives in the description, not the body. See `references/description-trigger-rules.md`.

3. **Outcomes are the north star, recommendations ladder up.** Every principle-doc skill carries a `## Outcomes we are looking for` section near the top, before any "how." The `## Recommended tools and practices (as of YYYY-MM-DD)` section groups recommendations under the outcome each one serves, with a one-line rationale linking the tool to the goal. When a tool rots, the outcome above survives. See `references/outcomes-laddering.md`.

4. **Progressive disclosure across three levels.** Metadata (always in context) → SKILL.md body (loaded on trigger, lean, ~500 lines max) → bundled resources in `references/`, `scripts/`, `assets/` (loaded only when the body points to them). If the body grows past ~500 lines, move material to `references/`.

5. **Imperative voice, explained why.** Tell Claude what to do, but explain the reasoning. Skills are read by an agent that can reason; rote MUSTs and ALWAYS/NEVER paragraphs are less effective than "do X because Y." Heavy command-form rule lists are a yellow flag; see `references/anti-yellow-flags.md`.

6. **Observations beat shouting.** Anti-patterns are described as observations the auditor sees in real codebases ("the agent must read user-pasted screenshots manually because no programmatic capture path exists"). They are not commandments dressed up in caps ("NEVER read user-pasted screenshots"). The former is checkable; the latter performs discipline without actually enforcing it.

7. **General, not example-specific.** A skill gets used across many prompts. Do not overfit the body to two or three test cases. Worked examples belong in `references/` where they can be skipped when not relevant.

8. **Iterate, do not write-once.** Draft → write 2-3 realistic test prompts → run Claude with the skill → review what it did → revise. Trigger problems are a separate iteration loop from body problems. Do not co-fix them. For the full empirical methodology (live `claude -p` routing tests, body-usefulness paired runs, flake handling), see the sibling [`skill-testing`](../skill-testing/SKILL.md) skill and its references.

9. **Encode opinions the baseline would not produce.** A skill earns its lines most strongly when its body contains opinions, recommendations, or framings that baseline Claude (no skill loaded) would not produce on its own. Dated, hard-won, project-specific recommendations (validated stack versions, rejected alternatives with rationale, cross-skill handoff patterns) deliver more value than well-known best practices the model already knows. When auditing a skill, ask: if the user fired this prompt without the skill loaded, would they get a meaningfully different answer? If the answer is no, the skill is anchoring framing only; consider whether that justifies its lines or whether the content belongs as a one-line cross-reference. See `docs/superpowers/specs/2026-05-14-routing-test-results.md` for the empirical study that produced this principle.

## Anti-patterns

Observations from skill audits. Each one names a specific failure mode; see `references/anti-yellow-flags.md` for the longer list.

- **Description describes the topic, not the trigger.** "This skill is about telemetry pipelines." The agent does not know when to reach for it. The description should list phrases users actually type.
- **Body opens with `## When to Use` instead of `## Overview`.** Routing logic in the body is wasted bytes; routing logic is the description's job. Body opens with what the skill is and what the outcomes are.
- **Heavy ALWAYS / NEVER / MUST blocks.** Reads like a policy document; degrades to noise once the agent has seen the third one. Reframe as "do X because Y."
- **`## Red Flags - STOP` formatted as commandments.** Observational shape works better: name what the auditor sees, name what it means, name what to do.
- **Tools listed without rationale.** "Use Playwright." Why? For what outcome? When the tool rots, the next reader has no anchor.
- **Outcomes section absent.** Without it, the skill is a list of patterns with no north star, and tool drift kills the whole body over time.
- **Body over 500 lines with no `references/`.** Loaded weight is too high; the agent's context budget is spent on detail that was not relevant to this turn.
- **Skill describes its own existence in the body.** "This skill helps with X." The frontmatter description already said that. The body's first sentence should be useful content.
- **Audit mode mixed into authoring mode without separation.** Reviewers and authors have different jobs. Either ship two skills, or clearly split the body into "to write a skill" and "to audit a skill" sections.

## Recommended tools and practices (as of 2026-05-13)

The structural recommendations are tool-independent. The drafting and review loop suggests specific tools.

### Outcome: skills route correctly

- **Description-first drafting.** Write the description before the body. If you cannot list 5-10 trigger phrases the user might type, the skill is either too narrow or not yet understood. Ladders up by forcing routing logic into the field that carries it.
- **Explicit non-triggers in the description.** State "Do NOT use for X, Y" when adjacent skills exist. Ladders up by suppressing false-positive activations.
- **Run 2-3 realistic test prompts before declaring done.** Ladders up by surfacing routing gaps before deployment.

### Outcome: the body earns its lines

- **500-line soft cap on `SKILL.md`.** When the body grows past that, move material to `references/<topic>.md` and reference it from the body. Ladders up by keeping loaded weight low.
- **`references/`, `scripts/`, `assets/` subdirectories** for progressive-disclosure bundling. Ladders up by giving Claude a place to fetch depth only when the task requires it.
- **Cut-the-fat editing pass.** After draft, re-read and delete any paragraph that does not change agent behavior. Ladders up by removing rationalization-shaped filler.

### Outcome: durable content does not rot

- **`## Outcomes we are looking for` section near the top.** Tool-free, goal-shaped. Ladders up by giving the rest of the body something stable to ladder up to.
- **`## Recommended tools and practices (as of YYYY-MM-DD)` section.** Dated. Grouped under outcomes. Each recommendation cites the outcome it serves. Ladders up by isolating the high-churn layer to one section.
- **Citation discipline.** Source articles, RFCs, official docs, named practitioners. Ladders up by letting the next reader verify a recommendation against its source.

### Outcome: auditing is mechanical

- **`references/audit-checklist.md`** with binary pass-fail criteria per section. Ladders up by making "is this skill compliant?" answerable without aesthetic judgment.
- **A periodic skill sweep.** Audit every skill in the plugin against the chassis whenever the chassis itself changes. Ladders up by preventing chassis drift across the corpus.

### Outcome: the chassis demonstrates itself

- **Apply the chassis to this skill.** This `SKILL.md` follows the principle-doc shape it documents, has Outcomes near the top, has dated recommendations, has anti-patterns as observations. Ladders up by making the chassis falsifiable.

## How to use this skill: authoring mode

1. Decide the skill's **type**: principle doc (durable knowledge) or procedural (workflow). See `references/skill-template.md` for both shapes.
2. Draft the **description** first. List 5-10 trigger phrases, common synonyms, file extensions if relevant, explicit non-triggers. See `references/description-trigger-rules.md`.
3. Draft the **Outcomes** section before any other body content. Each outcome is a durable goal with 1-2 evidence signals.
4. Draft the **Principles** (for principle docs) or **Workflow** (for procedural). Lean. Imperative, with the why.
5. Draft the **Anti-patterns** as observations, not commandments.
6. Draft the **Recommended tools and practices** section. Group recommendations under outcomes. Each recommendation cites the outcome it ladders up to.
7. Move overflow detail to `references/<topic>.md` files.
8. Audit the draft against `references/audit-checklist.md`.
9. Run 2-3 realistic test prompts. Iterate description for routing problems, body for execution problems. Do not co-fix.

## How to use this skill: audit mode

1. Open the target `SKILL.md` and its `references/` directory.
2. Walk `references/audit-checklist.md` top to bottom. For each criterion, mark pass or fail.
3. For each fail, identify the smallest change that closes the gap. Prefer moving content over rewriting.
4. Apply the changes in one editing pass per skill. Do not bundle audit fixes for multiple skills into one commit; one skill per commit so the diff stays reviewable.
5. Re-run the checklist. If still failing on the same criterion, the criterion may need refinement; flag in `references/audit-checklist.md` rather than working around it in the audited skill.

## References

- `references/anthropic-skill-creator.md`: Anthropic's official skill-creator playbook, distilled.
- `references/skill-template.md`: canonical shapes for principle-doc and procedural skills, with every section explained and example openings.
- `references/outcomes-laddering.md`: the durable-outcomes-to-rotting-tools pattern with worked examples from real harness-engineering skills.
- `references/description-trigger-rules.md`: how to write descriptions that route correctly; trigger-phrase patterns; non-trigger declarations.
- `references/audit-checklist.md`: binary pass-fail criteria, walkable top to bottom.
- `references/anti-yellow-flags.md`: longer list of skill anti-patterns, observational style.

## Continual improvement

This skill is maintained at:
https://github.com/AgentParadise/harness-engineering/blob/main/skills/authoring-skills/SKILL.md

Improvements to the chassis must be applied to this file first, then propagated to every other skill in the plugin via a sweep. Chassis drift is the most expensive kind of drift; do not let it land without the sweep.
