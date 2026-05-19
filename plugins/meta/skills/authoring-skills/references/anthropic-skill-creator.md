# anthropic-skill-creator

Distilled reference for the official Anthropic guidance on authoring Claude skills.

Distilled from Anthropic's skill-creator guidance, accessed 2026-05-13.

## Anatomy

A skill is a directory whose contents Claude can selectively pull into context:

```
skill-name/
├── SKILL.md          (required)
│   ├── YAML frontmatter: name, description
│   └── Markdown body of instructions
└── (optional bundled resources)
    ├── scripts/      executable code for repetitive or deterministic work
    ├── references/   docs that load into context only when needed
    └── assets/       templates, fonts, icons, and other artifacts used in output
```

Bundled resource conventions:

- `scripts/`: executable code Claude can run for deterministic or repetitive work. Scripts can execute without being read into context, which keeps token usage low.
- `references/`: longer-form documentation that Claude loads only when the body of SKILL.md instructs it to. Good home for spec-level detail, API surface tables, or domain background.
- `assets/`: files copied into the user's output, such as templates, fonts, or icons. Not instructions to Claude, ingredients for the result.

## Progressive disclosure across three levels

Skills are designed so that detail unfolds only when relevant. There are three levels:

1. **Metadata (name + description).** Always present in Claude's context. Roughly 100 words total. This is the trigger surface, what tells Claude the skill is the right tool for the current task.
2. **SKILL.md body.** Loaded when the skill triggers. Keep it under roughly 500 lines as a soft cap. Past that, comprehension degrades and the prompt starts to compete with itself.
3. **Bundled resources.** Loaded only when the body explicitly directs Claude to read them, or when scripts are invoked. Effectively unlimited in size, because most of it never enters the model's working context.

Knowing you are hitting the soft cap:

- SKILL.md is creeping past ~500 lines.
- Sections describe edge cases, file format minutiae, or long enumerations that most invocations will not need.
- You catch yourself adding "if you encounter X, here is the full background on X."

Fix: move the detail into `references/` and have SKILL.md point at the file by relative path. The body should read like a table of contents into the deeper material, not a copy of it.

## The description is routing

The `description` field in frontmatter is the single biggest determinant of whether a skill gets invoked at all. Treat it as a routing problem distinct from the execution problem solved by the body.

Why this matters:

- Claude tends to undertrigger skills. A description that is too narrow, too humble, or too abstract leaves the skill dormant.
- The body of SKILL.md is irrelevant if routing never selects the skill in the first place.

What to include in the description:

- What the skill does, stated plainly.
- Specific contexts where it should fire: trigger phrases the user is likely to say, file extensions the skill applies to, synonyms for the core concept, and adjacent intents that look like the core use case.
- Optional non-triggers when there is a sibling skill that overlaps. Naming what this skill is not for helps the router disambiguate.

All "when to use" content belongs in the description, not the body. The body is for "how to do it once selected."

Shape to aim for (informally, in the spirit of skills like the public `docx` skill): a sentence on capability, a sentence or clause listing trigger contexts and file types, and an optional clause on adjacent intents that should also pull this skill in. Slightly pushy beats slightly shy.

## Writing style

For the body of SKILL.md:

- Use imperative voice for instructions. "Read the manifest before editing" beats "the manifest should be read."
- Explain the why, not just the what. Modern models reason well about intent. A short rationale ("we read the manifest first because downstream steps assume its schema") generalizes better than a bare command.
- Treat heavy ALWAYS, NEVER, and MUST capitalization as a yellow flag. If a rule needs shouting to land, it usually needs explanation instead. Reframe as reasoning where you can, and reserve emphatic prohibitions for cases where the failure mode is severe and non-obvious.
- Keep the prompt lean. Cut sentences that do not change behavior. Cut examples that only restate the rule.
- Stay general. Example-specific instructions ("when the file is named `foo.json`...") tend to mislead on the next case. Prefer principles plus one illustrative example.
- Bundle repeated work. If the skill keeps walking Claude through the same five-step sequence, factor it into a script or a referenced procedure.

## The development loop

Skills are written iteratively. The loop:

1. Draft SKILL.md, frontmatter first.
2. Write two or three realistic test prompts. These should be the kinds of requests a real user would make, not idealized phrasings.
3. Run Claude against the skill on those prompts.
4. Review qualitatively. Did the skill trigger? Did it execute well once triggered? Where did it drift, over-explain, or miss?
5. Rewrite based on what failed. If triggering failed, edit the description. If execution failed, edit the body or push detail into references.
6. Repeat.

Optimize triggering and execution separately. They are different problems with different fixes:

- Triggering failures: change the description, add trigger phrases, add file extensions, add adjacent intents.
- Execution failures: tighten the body, add a missing step, factor a script, move noisy detail into `references/`.

Mixing the two slows the loop.

## Project additions on top of Anthropic guidance

The harness-engineering chassis layers two opinionated extensions on top of the official guidance. Both are conventions enforced by sibling references, not Anthropic requirements.

1. **Outcomes section.** Every skill in this plugin includes an `## Outcomes we are looking for` section near the top of SKILL.md. This anchors the skill to durable goals (what success looks like for the user) and separates those goals from the tools and procedures used to reach them. Tools rot. Outcomes do not. When a skill drifts, the outcomes section is the fixed point you re-derive from. See [outcomes-laddering.md](outcomes-laddering.md).

2. **Observational anti-patterns.** Where the conventional pattern is a "Red Flags - STOP" block in command form ("NEVER do X"), this chassis uses auditable observations: "If you observe X in the output, that is a signal that Y went wrong." This keeps the language descriptive rather than prohibitive, makes the signals checkable after the fact, and aligns with the "explain the why" guidance above. See [anti-yellow-flags.md](anti-yellow-flags.md).

Both extensions are compatible with the three-level disclosure model: the outcomes section sits in the body of SKILL.md (loaded on trigger), and the anti-pattern observations either sit inline or live in a referenced file depending on length.
