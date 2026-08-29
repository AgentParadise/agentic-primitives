---
name: html-guide
description: Write a long-form technical guide as one self-contained HTML file, for a specific reader who must make a specific decision in a domain whose vocabulary they lack. Trigger phrases include "explain X to me properly", "explain it like I'm 16", "I need to understand X before I decide", "write me a primer on", "get me up to speed on X so I can choose", "teach me enough X to make an architecture call", "brief me on", "explainer", "field guide", "html guide", "html doc", "technical guide with a table of contents", "I don't know the words for this domain". Produces a .html file with a floating scroll-spy table of contents, a vocabulary table at the top, and inline SVG diagrams that carry real numbers. Do NOT use for a one-scroll visual poster or architecture graphic (use the docs `system-infographic` skill), for prose or Markdown documentation sites (use the docs `fuma` skill), for a tutorial teaching a reader to perform a task rather than choose between options, for slide decks, or for an interactive web app or UI component (use `frontend-design`).
---

# HTML guide

## When to Use (and When NOT to Use)

Use when:
- A named person has to make a decision, and the blocker is vocabulary rather than intelligence. They can hold a hard idea; they do not know the words.
- The output should be a document the reader scrolls, jumps around inside, and returns to, not a graphic they absorb in one pass.
- The subject has an organizing constraint (a budget, a ceiling, a guarantee) that most of the material is a consequence of.
- The reader will act on the result, so accuracy matters more than polish and simplifications have to be flagged.

Do NOT use when:
- The deliverable is a one-scroll visual poster, architecture graphic, or how-it-works diagram: use the docs `system-infographic` skill.
- The deliverable is prose or Markdown documentation, or a docs site: use the docs `fuma` skill.
- The reader is going to perform the task, not choose between options. That is a tutorial, and a tutorial is ordered by steps rather than by when a term is needed.
- The subject has no single organizing constraint. Without one this genre degrades into an encyclopedia entry, and a reference doc serves better.
- The request is for slides, or for an interactive app or component.

## Input

- The decision being made, and by when. Required, because it bounds scope; without it the guide grows to cover the field.
- The real target: platform, scale, hardware, tier, load. Required, and worth pushing for even when the user has not volunteered a number. This is where wrong premises hide, and a wrong premise is a rewrite rather than an edit.
- The reader's actual worry, in their own words. Optional to ask for directly, but it must be inferred if not given, because it gets its own section.
- What the reader already knows. Optional; defaults to "expert engineer, zero vocabulary in this domain."
- A source of truth for the facts: repo, spec, docs, or your own domain knowledge with its limits stated. Required, since the reader will act on this.
- Output path for the `.html` file. Optional; default `docs/<topic>.html` in the relevant repo.
- A headless browser for the render check. Optional but strongly preferred; without it you ship a page you have not seen.

## Workflow

1. **Interview the premise before outlining.** Ask what is being decided and by when, what the real target is, what is already ruled out, and what failure the reader is worried about. Confirm the target number back to the user explicitly. A guide anchored to the wrong constraint is not editable into a correct one, because every figure, annotation, and conclusion derives from it. See `references/authoring-method.md`.
2. **Pick the anchoring constraint.** One real, singular, quantified limit that most sections are a consequence of. Test it two ways: missing it has a consequence the reader can feel, and at least two thirds of your planned sections derive from it. If the second test fails you have chosen a topic rather than a constraint.
3. **Name the human consequence of missing it.** Write the sentence that turns the number into something the reader will refuse to trade away. The number is the handle; the consequence is what makes the constraint hold under pressure.
4. **Inventory the vocabulary and order the sections by need.** List every term the guide will use, then walk the argument and note where each one first becomes necessary. That order is the section order, not alphabetical and not by subsystem. Split overloaded terms into their two senses (the phenomenon and the machinery), because conflating them is usually why the reader was confused.
5. **Copy `assets/template.html` to the output path and fill the spine.** Masthead (eyebrow, claim-shaped title, deck naming reader and decision and scope), the anchoring-constraint section, the vocabulary table near the top with a section-pointer chip per entry, body sections in need order, and the reader's-fear section near the end. Keep prose inside `.col`; the template's comments mark what each block is for.
6. **Draw only diagrams that carry quantities.** Before each one, name the sentence the reader should be able to say after looking at it; if that sentence is the paragraph above, do not draw it. Hand-author inline SVG using the token classes so it is correct in both themes. Budget-shape comparisons and pipelines with per-stage costs are the two that usually carry the document. See `references/diagram-patterns.md`.
7. **Flag every simplification where it occurs.** Use a `.note.caveat` or an inline clause rather than stating a tidy falsehood. Mark illustrative figures as illustrative in the caption and again in the footer. The reader who acts on an unflagged simplification stops trusting the whole document.
8. **Update the table of contents and check the style rules.** TOC entries and numbers must match the section markers and ids. No em dashes or en dashes: it is the house rule here, and it is also the most obvious generated-text tell. Vocabulary near the top, not the bottom.
9. **Render and read it before hand-off.** Screenshot full-page at a wide viewport (so the floating TOC is visible), at roughly 780px (so the gutter collapse and figure panning are exercised), and once with `data-theme="dark"` on the `html` element. Look at the images. Then open it for the user with `open <file>`. Shipping a guide you have not seen rendered is the most common way one goes out broken.

## Output

- One self-contained `.html` file at the chosen path: no build step, no network fetches, no webfonts, openable offline and diffable in git.
- A floating scroll-spy table of contents above 84rem, hidden below it.
- A vocabulary table near the top, each entry pointing at the section that explains the term.
- Inline SVG diagrams carrying real quantities, legible in light and dark.
- Light and dark themes plus a persisted theme toggle, and a print block that exports cleanly to PDF.
- Transient full-page screenshots from the render check. Commit only if useful.

## Outcomes we are looking for

### The reader can make the decision without further study
Signals: they act on it rather than asking a follow-up round of vocabulary questions; the guide's framing shows up in how they subsequently argue about the choice.

### One constraint visibly spines the document
Signals: the first section states a quantified limit, and a reader can explain why any later section exists by referring back to it.

### No term appears before its definition
Signals: the vocabulary table sits above the body sections; reading top to bottom, no undefined term is load-bearing.

### The guide stays trustworthy after the reader acts on it
Signals: every simplification carries a flag; illustrative figures are labelled as illustrative; a domain owner reading it does not find an invented fact.

### The artifact is self-contained and durable
Signals: it opens offline in a fresh browser with no build step; it renders correctly in both themes and prints legibly.

## Recommended tools and practices (as of 2026-07-29)

### For: the reader can make the decision
- Interview for the target number before outlining, and confirm it back. In the origin case the first version was built on 60Hz and 16.6ms, then the project turned out to target VR at 90Hz and 11.1ms, which changed every number and half the conclusions. Cheap question, expensive omission.
- Write for "expert in their own field, zero vocabulary in this one, deciding soon" rather than for a skill level. Literal "explain like I am 16" produces condescension, which loses a competent reader faster than jargon does.
- Give the reader's actual worry its own late section and settle it with arithmetic, then say what survives if the decision is revisited. That last part is what makes a decision safe to make now.

### For: one constraint spines the document
- Choose the constraint from `references/authoring-method.md`, which catalogs the likely anchor per domain (frame budget, partition behavior, request budget, staleness tolerance, and so on).
- State the human consequence immediately after the number, and again wherever a section implies a trade.

### For: no term before its definition
- Vocabulary table right after the opening framing, as a scannable and skippable lookup table with a `.ref` chip per entry. A bottom glossary means the reader meets terms for ten sections before the definitions arrive.
- Give overloaded terms two entries, one per sense.

### For: staying trustworthy
- `.note.caveat` for simplification flags, at the point of simplification rather than in a preamble.
- State in the footer what the document assumes, against what target, and which figures are illustrative.

### For: a self-contained, durable artifact
- Start from `assets/template.html` rather than composing CSS per guide. It carries the token system, the components, the scroll-spy, the theme toggle, and the print block, all verified rendering in light, dark, and narrow.
- Local font stacks only, no CDN. A guide that stalls on a webfont fetch fails at the one thing it promises, which is opening instantly anywhere.
- Token classes on every SVG mark instead of literal hex, so one diagram serves both themes. See `references/aesthetic-system.md`.
- Render-check with the Playwright headless shell if it is already on the machine, which avoids installing anything:
  `"$HOME/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell" --headless --disable-gpu --hide-scrollbars --window-size=1500,2600 --screenshot=out.png "file://$PWD/guide.html"`
  Note that `--force-dark-mode` does not emulate `prefers-color-scheme`; to check dark, copy the file with `data-theme="dark"` on the `html` element and render that.

### For: delegation
- This genre is a natural single-subagent task: one long prompt naming every term to cover, the ordering principle, the reader profile, the anchoring constraint, the diagram expectation, and the style rules. In the origin case that cost roughly 100k tokens for the first version and 175k for the revision round. A vague "write an explainer about X" does not produce this.
- Iterate with the same agent rather than spawning a second one. A second agent editing the same path races the first and drifts the numbers out of agreement with the figures. Fold multiple revision requests into one round.

## References

- `assets/template.html`: the fillable skeleton. Token system, components, scroll-spy TOC, theme toggle, print block. Copy this and fill it; do not compose the CSS per guide.
- `references/authoring-method.md`: the genre method. Premise interview, anchoring-constraint catalog by domain, vocabulary ordering, splitting overloaded terms, naming the reader's fear. Read during steps 1 through 4.
- `references/aesthetic-system.md`: what each token and component is for, what to change per guide, and the accessibility and print behavior. Read during steps 5 through 7.
- `references/diagram-patterns.md`: the test a diagram must pass, the four recurring patterns, and the SVG conventions that keep figures correct in both themes. Read during step 6.

## Continual improvement

File drift, gaps, or proposed updates at https://github.com/AgentParadise/agentic-primitives/issues
