# Audit checklist for skills

A binary pass-fail checklist a reviewer walks top to bottom when auditing a skill against the `authoring-skills` chassis. Each criterion is checkable without aesthetic judgment: "Did the author follow the rule?" not "Is the writing good?"

## Source attribution

This checklist consolidates rules defined in sibling references:

- `skill-template.md` (canonical section ordering)
- `description-trigger-rules.md` (frontmatter routing)
- `outcomes-laddering.md` (outcomes and recommendation grouping)
- `anti-yellow-flags.md` (tone and prohibited constructs)
- `anthropic-skill-creator.md` (upstream Anthropic guidance)

## How to use this checklist

1. Open the target `SKILL.md` and its bundled `references/`, `scripts/`, and `assets/` (if present).
2. Walk this document top to bottom. Mark each numbered criterion pass or fail.
3. For each fail, identify the smallest change that closes the gap. Do not redesign the skill.
4. Apply audit fixes one skill per commit. Do not bundle multiple skills into a single audit commit; per-skill commits keep blame and rollback clean.
5. After fixes, re-run the checklist on the changed skill to confirm every criterion now passes.

A criterion that does not apply (for example, procedural-skill checks against a principle-doc skill) is marked N/A. N/A is not a failure, but the reviewer must record why it does not apply.

---

## Section 1: Frontmatter and routing

1. **Frontmatter present and well-formed.** Pass if YAML frontmatter sits at the top of `SKILL.md` enclosed in `---` fences, containing exactly two fields: `name` and `description`. No extra fields, no trailing whitespace inside the fences.
   - *Common failure:* author adds `version`, `author`, or `tags`. Strip them; the harness ignores everything beyond `name` and `description`.

2. **`name` matches the directory.** Pass if `name: foo-bar` and the skill file lives at `skills/foo-bar/SKILL.md`. A mismatch breaks routing and discovery.
   - *Common failure:* renamed directory but did not update frontmatter, or vice versa.

3. **`description` includes 5 or more trigger phrases.** Pass if the description names at least five concrete situations, file types, keywords, or user intents that should activate the skill. See `description-trigger-rules.md`.
   - *Common failure:* description states what the skill *is* rather than when it should fire.

4. **`description` includes at least one explicit non-trigger when adjacent skills exist.** Pass if the description names what the skill is *not* for, in cases where a sibling skill could be confused with it. See `description-trigger-rules.md`.
   - *Common failure:* two adjacent skills both claim "use when reviewing code" and the harness cannot disambiguate.

5. **No marketing language in the description.** Pass if the description contains none of: "best", "powerful", "advanced", "comprehensive", "world-class", "cutting-edge". Marketing tokens are routing noise.
   - *Common failure:* description opens with "A powerful skill for ..." which tells the router nothing useful.

---

## Section 2: Body structure (principle-doc skills)

Apply this section when the skill documents principles, outcomes, and recommendations rather than a step-by-step procedure.

6. **`## Overview` present and approximately one paragraph.** Pass if Overview frames what the skill is about in durable language. Fail if Overview is a bullet list, a table of contents, or longer than three paragraphs.
   - *Common failure:* Overview restates the description verbatim instead of framing the underlying domain.

7. **`## Outcomes we are looking for` present and near the top.** Pass if Outcomes appears between Overview and Principles. See `outcomes-laddering.md`.
   - *Common failure:* outcomes appear at the bottom of the file as an afterthought, making the principle list read like floating advice.

8. **3 to 5 outcomes.** Pass if the count is 3, 4, or 5. Occasionally 6 or 7 is acceptable for broad skills. Fail if the count is 1, 2, or greater than 7.
   - *Common failure:* a single bloated "Outcome 1: do everything well" that cannot be evaluated.

9. **Each outcome has 1 or 2 evidence signals.** Pass if every outcome names a concrete observation a reviewer could make to confirm the outcome holds. A goal without a signal cannot be checked.
   - *Common failure:* outcomes phrased aspirationally ("write good code") with no signal naming what good looks like in this skill's context.

10. **Outcomes are goals, not tools or metrics.** Pass examples: "Agent can perceive UI state without human translation." Fail examples: "Use Playwright" (tool), "Page load under 800ms" (raw metric without goal context).
    - *Common failure:* the recommendations section migrated upward and now sits in the outcomes slot.

11. **`## Principles` present and lean.** Pass if Principles contains 5 to 8 entries, each 2 to 5 sentences. Each principle is written in the imperative and includes the why, not only the what.
    - *Common failure:* 15 principles, each one sentence long. Consolidate or move detail into a reference file.

12. **`## Anti-patterns` present and observational.** Pass if Anti-patterns lists 6 to 12 entries written as observations of what auditors see in the wild. Fail if entries lean on heavy ALWAYS/NEVER blocks. See `anti-yellow-flags.md`.
    - *Common failure:* anti-patterns written as commands ("Never use X") rather than descriptions of the failure mode and its consequence.

13. **`## Recommended tools and practices (as of YYYY-MM-DD)` present and dated.** Pass if the heading carries a date and that date falls within the most recent release cycle of the plugin. Stale dates signal abandoned recommendations.
    - *Common failure:* the date was set at skill creation and never refreshed when tools were swapped.

14. **Recommendations are grouped under outcomes with explicit laddering.** Pass if each recommendation block names which outcome it serves. See `outcomes-laddering.md`.
    - *Common failure:* a flat list of tools with no link back to the outcome each serves.

15. **`## References` section present if the skill has bundled references.** Pass if the body links every file under `references/` at least once, with a one-line description of when to consult that reference.
    - *Common failure:* a reference file exists on disk but is never linked from the body, so readers never discover it.

16. **`## Continual improvement` section present with the canonical GitHub link.** Pass if the section invites contributions and points at the plugin repository so readers know where to file follow-ups.
    - *Common failure:* the link points at a personal fork or a closed-source mirror.

---

## Section 3: Body structure (procedural skills)

Apply this section when the skill is procedural: an orchestrator, a maintenance routine, a setup wizard, or any skill whose primary output is "the user did the steps".

17. **`## When to Use` and `## When NOT to Use` present.** Pass if both sections exist and each lists concrete situations. The pair calibrates routing for procedural skills the way the description does for principle-doc skills.
    - *Common failure:* "When NOT to Use" is omitted because the author could not think of a counter-example. Force the question: what skill or path supersedes this one?

18. **`## Input` section names parameters explicitly.** Pass if every input the procedure consumes (arguments, files, environment variables) is named with its type and whether it is required.
    - *Common failure:* the workflow references `$ARGUMENTS` or environment variables that are never declared in Input.

19. **`## Workflow` is numbered steps.** Pass if the workflow is a numbered list, each step a single sentence or short paragraph. Sub-steps allowed at one level of nesting. Prose-paragraph workflows fail.
    - *Common failure:* an unordered bullet list. Order matters; ordering must be explicit.

20. **`## Output` describes the artifact(s) produced.** Pass if Output names what files, commits, branches, messages, or state changes exist after the procedure completes successfully.
    - *Common failure:* Output is missing entirely, leaving the agent unable to verify the procedure ran to completion.

21. **Outcomes and recommendations sections present when the procedure has a clear north star.** Pass if the procedure ladders to outcomes (see `outcomes-laddering.md`). Optional and may be omitted for thin procedural wrappers (for example, a 5-step utility).
    - *Common failure:* an orchestrator that drives many sub-skills omits outcomes, so the reader cannot tell what success looks like end to end.

---

## Section 4: Body content quality

22. **Imperative voice with explained why.** Spot-check three paragraphs at random. Pass if each answers "why" alongside "what". Fail if the paragraphs read as command lists with no rationale.
    - *Common failure:* a principle that says "Validate input at the boundary" without saying why the boundary is the right place.

23. **No heavy ALWAYS/NEVER blocks.** Pass if the body avoids capitalised commandment lists. See `anti-yellow-flags.md`. Targeted use of "never" inside a single sentence is acceptable; multi-bullet ALWAYS/NEVER walls are not.
    - *Common failure:* a six-bullet "NEVER do X" list that reads like a warning sign rather than guidance.

24. **No "this skill helps with..." opener.** Pass if the Overview does not restate the frontmatter description. The description already states what the skill helps with; repeating it wastes the top of the body.
    - *Common failure:* Overview begins "This skill helps you ..." which is exactly what the description already conveyed.

25. **No `## When to Use` in the body for principle-doc skills.** Pass if principle-doc skills route entirely from the frontmatter description. Procedural skills are exempt (see Section 3).
    - *Common failure:* principle-doc skill duplicates routing rules in the body, creating two places that drift apart.

26. **Citations present for source-derived claims.** Pass if each principle either names its source (paper, post, internal doc, observable practice) or rests on a fact a reviewer can verify directly. Unsourced assertions fail.
    - *Common failure:* "Studies show that ..." with no study named. Either name it or drop the claim.

---

## Section 5: Bundled resources

27. **SKILL.md is under 500 lines.** Pass if `wc -l SKILL.md` reports fewer than 500. If over, body content must have been moved into `references/` and the body must point at those references.
    - *Common failure:* a 900-line SKILL.md that buries the routing-relevant top section under a long appendix. Move the appendix to `references/`.

28. **`references/` directory present if SKILL.md is over approximately 300 lines or has depth that does not fit cleanly in the body.** Pass if depth has been externalised rather than crammed inline. A 280-line skill without references is acceptable; a 280-line skill that links five external blog posts inline is not.
    - *Common failure:* deep technical detail inlined in SKILL.md that would be a clean reference file.

29. **Each `references/` file has a clear topic and a one-line header description.** Pass if every reference file opens with a header that states what the file covers and when to read it. Reference files without orientation headers fail.
    - *Common failure:* a reference file that opens straight into content with no orientation, leaving the reader unsure what context to bring.

30. **`scripts/` if present contains executable, deterministic helpers and is referenced from SKILL.md.** Pass if scripts have shebangs, run without manual edits, and are mentioned in the body where they apply. Per Anthropic guidance, scripts replace narrative steps that the agent should execute deterministically.
    - *Common failure:* scripts ship without shebangs or with hard-coded paths that only work on the author's machine.

31. **`assets/` if present contains templates, fonts, fixtures, or fixed artifacts the skill produces or compares against.** Pass if every asset is referenced by name from SKILL.md or from a reference file. Orphan assets fail.
    - *Common failure:* an `assets/` directory that accumulates over time and is never pruned, with files no skill section ever links.

---

## Section 6: Style hygiene

32. **No em-dashes (U+2014).** Pass if `grep -cP "\x{2014}" SKILL.md` returns 0 (Perl-mode regex expands `\x{2014}` to the em-dash byte sequence at runtime so this rule file itself stays em-dash-free). This plugin's house rule. Use colons, commas, periods, parentheses, or restructure the sentence. Run the same check on every file under `references/`.

33. **Cross-references use relative paths.** Pass if links between SKILL.md and bundled files use paths like `references/foo.md`, not absolute paths or `file://` URLs. Absolute paths break when the skill is installed under a different root.

34. **No marketing language.** Pass if "powerful", "comprehensive", "best-in-class", "cutting-edge", "next-generation", and similar superlatives do not appear in body prose. Quoting a third-party name that contains these words is acceptable.

35. **Tone is observational, not promotional.** Spot-check the anti-patterns and recommendations sections. Pass if each entry describes (what is observed, what happens, what the consequence is) rather than advocates (why this approach is great).

---

## Section 7: Demonstration test

36. **2 to 3 realistic test prompts run before the skill is declared done.** Pass if the author has invoked the skill via realistic user prompts and recorded what triggered and what did not. The notes do not need to ship with the skill, but the author should be able to produce them on request.
    - *Common failure:* the skill was written, committed, and never invoked. The first real user is the first test, and routing bugs surface in production.
    - *What good looks like:* three prompts including one that should fire the skill, one that is adjacent but should not fire it, and one borderline case that exercises the non-trigger rule from criterion 4.

---

## What to do with findings

For each failed criterion:

1. Identify the smallest change that closes the gap. Do not redesign the skill in the same pass.
2. Open a commit that touches only this skill. The commit message should name the skill and the criteria addressed (for example, "authoring-skills: fix criteria 11, 13, 32").
3. Re-run the checklist against the changed skill to confirm the failed criteria now pass and no previously passing criteria regressed.
4. If multiple skills failed the same criterion, audit each one in its own commit. Bundling masks per-skill regressions.

A skill that fails three or fewer criteria can usually be fixed in one pass. A skill that fails ten or more criteria is a candidate for a deeper rewrite using `skill-template.md` as the starting point rather than incremental patching.

---

## Cross-references

- `skill-template.md` for the canonical body skeleton to copy when starting a new skill or rewriting a failing one.
- `description-trigger-rules.md` for the rules governing criteria 3, 4, and 5.
- `outcomes-laddering.md` for the rules governing criteria 7, 8, 9, 10, and 14.
- `anti-yellow-flags.md` for the rules governing criteria 12, 23, and 35.
- `anthropic-skill-creator.md` for the upstream guidance that informs criteria 27 through 31.
