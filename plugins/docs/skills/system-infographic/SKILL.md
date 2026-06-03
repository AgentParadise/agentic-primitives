---
name: system-infographic
description: Produce a single self-contained HTML infographic that explains how a system, flow, pipeline, architecture, or setup works. Trigger phrases include "make an infographic", "build an infographic", "diagram how this works", "visual explainer", "how-it-works page", "explain the architecture visually", "onboarding diagram", "flow diagram", "show the flow from X to Y", "visualize the pipeline", "schematic of the system", "one-pager that explains", "turn this README into a graphic". Output is a portable .html file (inline CSS, web fonts, no build). Do NOT use for prose documentation (use the docs `fuma` skill), for building an interactive web app or reusable UI component (use `frontend-design`), or for data-driven charts from a dataset.
---

# System infographic

## When to Use (and When NOT to Use)

Use when:
- A user wants a visual one-pager that explains how a system, flow, pipeline, or setup works (onboarding, hand-off, a "how it works" page).
- You are turning a README flow, an architecture, or a setup guide into something a reader absorbs in one scroll.
- A diagram needs to show a trust boundary, a data path, or a sequence of phases, not just a bullet list.

Do NOT use when:
- The deliverable is prose documentation: use the docs `fuma` skill.
- The deliverable is an interactive web app or a reusable UI component: use `frontend-design`.
- The graphic is a data chart driven by a dataset (bar, line, series): that is a charting task, not an explainer.
- The format requested is a slide deck or a static raster image with no HTML.

## Input

- Source of truth for the system being explained: a repo, README, spec, or a clear verbal description. Required, because the graphic must match reality and a real source beats memory.
- Output path for the `.html` file. Optional; default `docs/<topic>.html` in the relevant repo.
- Aesthetic direction. Optional; default is the dark technical-schematic blueprint in `assets/template.html`.
- A headless browser (Playwright or Chromium) for the screenshot QA step. Optional but recommended; without it you ship unseen.

## Workflow

1. Extract the real flow from the source of truth. Read the repo, justfile, README, or spec and list the actual phases, the exact commands, what is local versus external, and any trust or security boundary. A graphic that invents steps is worse than none, because readers trust a diagram more than prose.
2. Choose the spine that matches the content. Common spines: a linear pipeline (A to B to C), a perimeter map (what stays inside a trust boundary versus what crosses it), phase blocks (one-time versus per-call versus continuous), and a numbered setup checklist. Most system explainers combine a map centerpiece, phase cards, and a setup checklist. See `references/aesthetic-system.md`.
3. Commit to a semantic visual system before writing markup. Assign each accent color one durable meaning (for example one hue for local or secret, one for data flow, one for a danger boundary, one for success) and reuse it everywhere. Pair a characterful display font with a monospace for commands and labels. Color used decoratively that elsewhere carries meaning confuses the reader, so keep the mapping strict. Start from `assets/template.html`.
4. Build one self-contained HTML file. Inline all CSS in a `<style>` block, load fonts through a single Google Fonts `<link>`, and avoid external JS libraries; a few lines of vanilla JS for reveal-on-scroll is fine. Self-containment is what makes the artifact emailable, committable, and openable with no build step.
5. Fill the spine with the real content from step 1: a hero stating the one-line thesis, the map or pipeline centerpiece, phase cards for the steps, callout chips for the invariants that make the system work, and a numbered setup checklist with copy-able command chips. Use the actual commands, not placeholders.
6. Add restrained motion and print support. One staggered reveal on load (IntersectionObserver, or CSS `animation-delay`), hover affordances on nodes, and an `@media print` block so the file exports to PDF cleanly. Motion should aid comprehension and sequencing, not perform.
7. Render and inspect before hand-off. Open the file in headless Chromium, scroll so reveal animations fire, screenshot it full-page, and look at the image. Check a narrow viewport (around 800px) for the responsive collapse. Fix overflow, low contrast, and broken connectors. Shipping an infographic you have not seen rendered is the most common way one goes out broken. See `references/screenshot-qa.md`.
8. Open it for the user and offer follow-ups. On macOS, `open <file>`. Offer a light or print theme, an Open Graph share image, or folding the graphic into the README as a linked diagram.

## Output

- One self-contained `.html` file at the chosen path, openable offline (apart from the web-font CDN), printable to PDF.
- A full-page screenshot used for the QA pass (transient; commit only if useful).
- No build artifacts, no installed dependencies, no external runtime beyond the font CDN.

## Outcomes we are looking for

### The infographic is accurate to the system it explains
Signals: every command and step in the graphic exists in the source repo or spec; a domain owner reading it does not flag an invented step.

### The artifact is self-contained and portable
Signals: opening the single file in a fresh browser renders the whole page; there is no build step; print preview is legible on one or two pages.

### The design is distinctive, with a semantic visual system
Signals: each accent color carries one consistent meaning; the page would not be mistaken for a default framework template; the font pairing is not Inter, Roboto, or Arial.

### It was verified visually, not shipped blind
Signals: a full-page screenshot was rendered and inspected; the layout holds at both desktop and narrow widths.

## Recommended tools and practices (as of 2026-06-03)

### For: accuracy to the system
- Build the flow from the repo, justfile, README, or spec, not from memory. Lift the real commands and the real boundary. This prevents the invented-step failure that makes a diagram actively misleading.
- Name the trust boundary explicitly when the system has one (what stays local versus what crosses a network or goes to a third party). The boundary is usually the part readers most misunderstand, so it earns the centerpiece.

### For: self-contained and portable
- One `.html` file: inline CSS, fonts via a single Google Fonts `<link>`, zero JS dependencies. The artifact then opens anywhere with no toolchain.
- Add the `@media print` block while writing the CSS, not after. PDF export becomes a first-class output rather than a retrofit.

### For: a distinctive, semantic design
- Map each accent color to one meaning and reuse it; pair a characterful display font with a monospace for commands and code. A consistent color-to-meaning map is what lets a reader decode the diagram without a legend.
- Default starting point: the dark technical-schematic blueprint (faint grid background; amber for local or secret; teal for data flow; red for a boundary; green for ok; Chakra Petch with JetBrains Mono). Override per context, but start from a working base. See `assets/template.html` and `references/aesthetic-system.md`.

### For: visual verification
- Render with headless Chromium (Playwright) and screenshot the full page, then inspect the image before delivering. A screenshot surfaces overflow, contrast, and broken-connector bugs that reading the markup hides. See `references/screenshot-qa.md`.
- Check a narrow viewport near 800px. Infographics are read on laptops and phones, and the responsive collapse is where layouts break.

## References

- `assets/template.html`: the self-contained starter skeleton (the CSS system plus structural blocks) to copy and fill.
- `assets/example-how-it-works.html`: the flagship worked example, the infographic that prompted this skill.
- `references/aesthetic-system.md`: the semantic color system, font pairings, and spine patterns in depth.
- `references/screenshot-qa.md`: the headless-render-and-inspect loop, with the Playwright snippet and what to look for.

## Continual improvement

File drift, gaps, or proposed updates at https://github.com/AgentParadise/agentic-primitives/issues
