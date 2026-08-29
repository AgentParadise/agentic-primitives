# The visual system

What this file covers: the design system in `assets/template.html`, what each
token and component is for, and what to change per guide versus what to leave
alone. Read it during workflow steps 5 through 7, while filling the template.

The look is an editorial technical broadsheet: serif prose at a narrow measure,
monospace for every piece of metadata, a left gutter carrying section numbers, and
one accent hue reserved for the anchoring constraint. It reads as a document
rather than a web page, which is the point: the reader is settling in to make a
decision, not scanning a landing page.

## Tokens

Three semantic accents, each with one job. Reusing an accent for decoration
destroys the reader's ability to decode a diagram without a legend, so keep the
mapping strict.

| Token | Role | Where it appears |
| --- | --- | --- |
| `--amber` / `--amber-bright` | The spine: the anchoring constraint | Section markers, links, ceiling lines, glossary terms, the italic word in the title |
| `--amber-wash` | First-use term highlight | The `.term` underlay only |
| `--cool` | Secondary signal, the healthy state | Notes, comparison bars, non-critical diagram marks |
| `--warn` | The cliff: failure, overrun, caveat | `.note.caveat`, overrun bars, red diagram marks |

The neutrals ladder from `--ground` (page) through `--ground-2` (inset) to
`--panel` (raised surfaces: notes, figures). Ink goes `--ink` (prose),
`--ink-soft` (secondary prose, deck, table body), `--ink-faint` (captions,
metadata, inactive TOC). Lines go `--line` (structural) and `--line-soft` (row
separators inside a component).

**Change per guide:** the accent hues, if the domain has a natural palette. Keep
the roles and the neutral ladder, because the components assume them.

Every theme block is declared three times: `:root`, the
`prefers-color-scheme: dark` block, and explicit `:root[data-theme="light"|"dark"]`
overrides. The duplication is deliberate. Without the explicit `data-theme`
blocks the toggle cannot beat the OS preference in both directions.

## Type

`--serif` is a Charter stack falling back through Sitka, Cambria, Palatino, and
Georgia. `--mono` is a system-first stack. Both are local fonts by design: a
guide that fetches a webfont fails offline and stalls first paint, and this
artifact is meant to be committed, emailed, and opened on a plane.

Prose is 17px at 1.62 line-height in a 40rem column. Headings use `clamp()` and
`text-wrap: balance`, with `max-width` in `ch` so a long title breaks at a
sensible place rather than at the column edge.

Monospace signals metadata, without exception: eyebrow, section markers, table
headers, figure captions, glossary terms, callout labels, TOC, footer, and all
SVG text. Serif signals argument. The reader learns the split in one screen and
then navigates by it.

## Layout

The reading column is 40rem, left-aligned inside a 62rem wrap, with a 7rem left
gutter above 62rem. Prose stays narrow while figures break out to the full wrap
width by sitting outside `.col`. That is the whole layout trick, and it is why
diagrams can be wide without making paragraphs unreadable.

Section numbers live in `.marker`. Above 62rem they absolutely position into the
gutter, right-aligned; below, they sit inline above the heading. The reading
column never shifts between the two states.

## Components

**Masthead.** Eyebrow (who this is for), `h1` (the claim, with one italic accent
word), deck (the reader, the decision, the assumption, what is out of scope). The
title states a finding, not a topic.

**Vocabulary (`.gloss`).** A definition list of `div > dt + dd` pairs, stacking on
narrow screens and going two-column at 40rem. Each `dd` ends with a `.ref` chip
pointing at the section number that explains the term properly. Sits near the top,
inside `.col-wide` so definitions get more measure than prose.

**Callouts (`.note`).** Three variants. Default (cool) for a consequence or a
practical rule. `.caveat` (warn) for simplification flags and risks; never omit
these, since flagged lossiness is what keeps the guide trustworthy. `.analogy`
(amber) for the bridge from something the reader already knows, including where
the analogy breaks.

**Figures.** `<figure>` outside `.col`, `<svg>` with a `viewBox` and a real
`role="img"` plus `aria-label`, wrapped in `.scroller` when wide so narrow screens
pan instead of squashing. `<figcaption>` opens with a bold `Fig N.` and states the
conclusion the diagram supports, plus whether the numbers are measured or
illustrative. See `diagram-patterns.md`.

**Tables.** Wrapped in `.tbl-wrap` for horizontal overflow. Monospace uppercase
headers, first column bold at 30% width. Three or more things varying along two or
more axes belongs here rather than in prose.

**Inline.** `.term` highlights a glossary word on first use only, with an amber
underlay rather than a color change so it survives both themes. `.num` puts
quantities in tabular monospace so digits align down the page. `.ref` is the
section-pointer chip, prefixed with a section sign via `::before`.

**Floating TOC.** Fixed, right, vertically centred, monospace, with numbers
mirroring the section markers so a spoken reference lands. Hidden below 84rem
rather than squeezed, because the reading column outranks the navigation.
Scroll-spy marks the current section with an amber left border and sets
`aria-current`.

**Theme toggle.** A standalone file has no host to stamp `data-theme` on it, so it
ships its own button, persisting an explicit choice to `localStorage` and
otherwise deferring to the OS preference. This is the main adaptation needed when
porting a page out of a hosted artifact environment.

## Motion and accessibility

Motion is limited to `scroll-behavior: smooth`, guarded by
`prefers-reduced-motion: no-preference`. There is no reveal-on-scroll: a reference
document a reader jumps around inside is worse with entrance animations, because
content arriving late reads as content missing.

Sections carry `scroll-margin-top` so anchor jumps do not tuck a heading under the
viewport edge. Focus rings are explicit on links and buttons. Every SVG has a
label that describes what the diagram lets the reader conclude, not just what it
depicts.

## Print

The print block re-declares the token set against `:root` and both `data-theme`
selectors, so an explicit dark choice does not survive into a printed page. It
drops the TOC and the toggle, collapses the gutter, makes markers static, sets
`break-inside: avoid` on figures, notes, and tables, and `break-after: avoid` on
headings. Guides of this genre get printed and annotated more than their authors
expect.

## Anti-patterns

- Accent colors used decoratively somewhere else in the page, so a diagram's
  color-to-meaning map stops decoding.
- Webfonts loaded from a CDN, which breaks the offline promise and delays first
  paint on the one artifact that is supposed to open instantly.
- Literal hex values inside SVG marks, so the diagram is legible in one theme and
  invisible in the other. The exception is text sitting on a filled bar, where the
  fill keeps its color across themes while `--ink` flips, so a literal dark ink is
  correct there.
- A theme handled only through `prefers-color-scheme`, leaving the reader no way
  to override the OS in a standalone file.
- Prose set to the full wrap width, producing a 62rem measure nobody can read.
- The TOC squeezing the reading column on a laptop instead of hiding.
- Serif used for metadata or monospace used for argument, which erases the one
  signal the reader is navigating by.
- No print block, so exporting to PDF produces a dark page with a floating TOC
  overlapping the text.
