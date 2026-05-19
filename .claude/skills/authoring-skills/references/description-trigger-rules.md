# Description Trigger Rules

How to write the `description:` field in a skill's frontmatter so the skill actually gets invoked when it should be, and only when it should be.

**Source attribution:** Distilled from Anthropic's official skill-authoring guidance (see `anthropic-skill-creator.md` in this directory) and from observed routing behavior in Claude Code and agent harnesses. Per Anthropic, the description is the single biggest determinant of whether a skill triggers. Claude undertriggers by default, so descriptions need to be slightly "pushy."

## Why descriptions matter most

The description is always in context for routing decisions. The body is not. The body is only loaded after the description has already triggered the skill.

This means triggering and body content are two different problems:

- **Triggering** is solved by the description.
- **Execution quality** is solved by the body.

Most "this skill doesn't fire when I expect it to" complaints are description problems, not body problems. Authors instinctively reach for the body when their skill misfires; that is the wrong lever.

Target roughly 100 words for the description, but length follows clarity, not the other way around. A 40-word description that lists the right trigger phrases beats a 200-word description that paraphrases the skill's mission statement.

## What goes in a good description

A description carries four loads. In order of routing weight:

1. **What the skill does**, in one short clause. Not a thesis. A clause.
2. **Specific contexts when to use it**, phrased the way a user actually phrases tasks. Trigger phrases include:
   - Verbs: `audit`, `write`, `review`, `refactor`, `set up`, `cut`, `bump`, `sync`.
   - Nouns: `pipeline`, `test`, `dashboard`, `release`, `manifest`.
   - Tool names users would say out loud: `Playwright`, `Vector`, `OTLP`, `Grafana`, `Prometheus`.
   - File extensions when applicable: `.docx`, `SKILL.md`, `compose.yaml`, `pyproject.toml`.
   - Symptoms users describe rather than the cause: `my skill is not triggering`, `this PR is breaking`, `the deploy is stuck`, `the agent can't see logs`.
3. **Synonyms.** Users phrase things differently than skill authors. "Browser debugging" and "UI debugging" and "frontend troubleshooting" might all route to the same skill. List the variants. Do not assume the user will speak your taxonomy.
4. **Adjacent intents** users phrase casually that map to this skill: "see what the page looks like", "find the slow request", "check the logs from yesterday", "why did this fail last night". These are the lowest-confidence inputs and they need explicit help.

Then add the suppression load:

5. **Explicit non-triggers** when adjacent skills exist:
   ```
   Do NOT use for X (use sibling skill Y); do NOT use for Z (use skill W).
   ```
   This is what suppresses false-positive activations. Without explicit non-triggers, two skills that share vocabulary fight each other and the router picks badly.

## What does NOT go in a description

- **Internal jargon the user would not type.** If your team calls it "the substrate layer" and users call it "the API", write "API".
- **Marketing language.** "The best skill for..." or "comprehensive coverage of..." adds zero routing signal. Strip it.
- **The skill's own structural conventions** (Outcomes, Principles, section names). Those are not what the user typed. The user typed "review my PR", not "run the Outcomes section".
- **Cross-references to other skills by file path.** Cross-references go in the body. The description is for routing, not navigation.
- **Long sentences.** Each phrase should be skim-readable. The router scans; it does not parse paragraphs.

## A good and a bad description, side by side

Bad description (too topical, no triggers):

```yaml
description: This skill is about agent-queryable telemetry interfaces. It covers logs, metrics, and traces.
```

Good description (carries the routing load):

```yaml
description: Use when reviewing or setting up agent-queryable telemetry: LogsQL, PromQL, TraceQL, trace lookup by ID, log search by attribute. Trigger phrases include "search the logs", "what's the p95 latency", "find the trace for request X", "query metrics", "agent can't see logs", "Grafana", "VictoriaLogs", "VictoriaMetrics", "VictoriaTraces", "Tempo", "Loki", "Mimir", "Prometheus". Use when an agent needs to read telemetry, not just emit it (for emission see the `telemetry-pipeline` skill). Do NOT use for general-purpose log hygiene; that's the software-leverage-points `logging` skill.
```

What makes the second one better, line by line:

- "Use when reviewing or setting up" gives the router two concrete verbs.
- "agent-queryable telemetry" plus the query-language names (LogsQL, PromQL, TraceQL) catches users who know what they want to do but not what to call it.
- The quoted trigger phrases mirror how a user actually types: lowercase, conversational, with question marks and pronouns.
- Tool names (Grafana, VictoriaLogs, Tempo, Loki, Prometheus) catch users who arrive via their stack rather than via the concept.
- The parenthetical "(for emission see ...)" disambiguates a near-neighbor skill before the router has to guess.
- The explicit "Do NOT use for general-purpose log hygiene" prevents this skill from stealing routing from `logging`.

The bad version says what the skill is "about". The good version says when to fire it. Routers do not care about "about".

## Description-first drafting

Write the description before the body.

The test: if you cannot list 5-10 trigger phrases the user might type, the skill is either too narrow to ship or you have not understood what it is for yet. This is the test, not a suggestion.

Writing the body first feels productive, but you will then retrofit the description to match the body, which is exactly backwards. The description is the contract with the router; the body is the contract with the agent. Sign the routing contract first.

If you draft the description and the trigger phrases feel forced, that is signal. Either:

- The skill's scope is wrong (split it, or merge it with a sibling).
- The skill's name is wrong (rename so the description writes itself).
- The skill should not exist (the work belongs in an existing skill).

## Iterating descriptions separately from body

Triggering problems and execution problems are different problems. Do not change the description and the body in the same iteration; you will not know which fix caused the improvement (or regression).

Workflow:

1. Observe a routing miss or false positive.
2. Change only the description. Commit.
3. Re-run realistic prompts. Observe.
4. If routing is now correct but execution is poor, change only the body. Commit.
5. If routing is still wrong, change only the description again.

Bundling description and body edits is the single most common reason authors cannot tell which change helped.

## Trigger-phrase patterns by skill type

Different skill types attract different trigger phrases. Match the pattern to your skill.

**Principle-doc skill** (a reference that informs review or design). Trigger phrases are verbs the user does combined with the domain noun:

- "review the telemetry pipeline"
- "audit this skill's structure"
- "set up the failure signal"
- "check the dependency story"

**Procedural skill (orchestrator)** (a skill that runs an end-to-end flow). Trigger phrases are direct invocations plus symptom phrasing:

- "run a harness review"
- "audit the plugin"
- "review this PR through the leverage points"
- "we need a full review"
- "give me an audit"

**Maintenance skill** (a skill that keeps state in sync). Trigger phrases are versioning, release, and sync verbs:

- "bump the version"
- "cut a release"
- "sync the manifests"
- "pull upstream scaffold"
- "regenerate the lockfile"
- "promote staging to prod"

If your skill does not fit one of these patterns cleanly, pick the closest and write the description in that pattern's voice. Mixed-pattern descriptions route poorly because the trigger phrases pull in different directions.

## A short checklist

Before declaring a description done:

- Can you list 5-10 trigger phrases? If no, rewrite.
- Did you include 1-2 explicit non-triggers? If no, the routing will overshoot.
- Did you avoid marketing words? If no, strip.
- Does the description say WHAT (one clause) and WHEN (many trigger phrases) and NOT-WHEN (non-triggers)? If any missing, fill in.
- Did you run 2-3 realistic test prompts and observe routing? If no, you are guessing.

If all five answers are yes, ship it. If any answer is no, you are not done; you are hoping.

## Cross-references

Sibling files in this directory:

- `skill-template.md`: the canonical skeleton for a new SKILL.md, including frontmatter shape.
- `outcomes-laddering.md`: how to write the body's Outcomes section once the description is locked.
- `audit-checklist.md`: end-to-end review for a skill, including a description-quality pass.
- `anthropic-skill-creator.md`: upstream Anthropic guidance this document is distilled from.
