# Load-bearing diagram patterns

What this file covers: which diagrams earn their place in a decision explainer,
the four patterns that recur, and the SVG conventions that keep them correct in
both themes. Read it during workflow step 6, when you know what the guide argues
and are deciding what to draw.

## The test a diagram has to pass

A diagram earns its place when it **encodes a quantity or a boundary that prose
would take paragraphs to convey**. In the origin case six inline SVGs were drawn
and two carried the document: a render-pass pipeline with per-pass millisecond
figures, and a budget-shape comparison against the ceiling. Both answer questions
directly. The other four restated adjacent prose.

Concretely, before drawing, name the sentence the reader should be able to say
after looking at it. If that sentence is already the paragraph above, do not draw
it. A diagram that restates prose costs scroll, and scroll is the scarce resource
in a long guide.

Corollary: put the numbers **in** the diagram. A pipeline diagram without
per-stage costs is a box-and-arrow picture of something the reader could have
inferred from the section headings. With costs, it is the artifact they screenshot
into the decision meeting.

## Conventions

Author inline SVG by hand. No external assets, no charting library, no build step,
because the file has to open anywhere and stay diffable in git.

- `viewBox` with no `width`/`height`, so CSS controls size. The template's
  `figure svg` rule handles the rest.
- `role="img"` plus an `aria-label` that states what the diagram lets the reader
  conclude, not merely what it depicts.
- Every mark takes a token class (`.f-amber`, `.s-cool`, `.f-warn`, and so on)
  rather than a literal hex. This is what makes one diagram correct in both
  themes. See `aesthetic-system.md`.
- Text uses `.t`, `.t-sm`, `.t-lg`, `.t-cap` at pixel sizes inside the viewBox
  coordinate space, so labels stay proportional as the figure scales.
- Wrap in `.scroller` when the natural width exceeds roughly 44rem. Panning beats
  squashing for anything with axis labels.
- The one place a literal color is right: text sitting on a filled bar. The bar
  keeps its fill across themes while `--ink` flips, so `fill="#111"` on an amber
  bar is correct and a token would break it.
- `opacity` is the cheap way to differentiate many bars of one hue without
  introducing accent colors that carry other meanings.

## Pattern 1: budget shape comparison

The highest-value diagram in the genre. Two or three stacked horizontal bars with
the same total, drawn against a dashed limit line, showing that the same aggregate
number can mean completely different health.

Use it when the reader's instinct is to ask "how fast or big is it" and the useful
question is "where does it go". It converts a total into a distribution, which is
what makes an optimization target obvious.

Structure: a dashed `.s-amber` vertical line for the ceiling with the limit
labelled to its right; an optional second dashed `.s-cool` line for a stretch
tier; a horizontal `.s-line` axis with scale ticks so bars mean something; one row
per case with a short label above; a closing `.t-sm .f-faint` line stating the
conclusion. The template's Fig 1 is a working skeleton of exactly this.

Add an overrun row in `.f-warn` when the constraint has a cliff, and label what
happens past the line. A cliff drawn is a cliff the reader remembers.

## Pattern 2: pipeline with per-stage cost

A left-to-right sequence of stages, each annotated with its cost and its
inputs and outputs. Use it when the document's central object is a process the
reader will reason about stage by stage, and when the argument depends on which
stages are swappable.

Make the swappable stage visually distinct, because that is usually the whole
point: it is the seam the decision is about. Label the contract crossing the seam
(what goes in, what comes out) rather than only naming the stage.

## Pattern 3: boundary map

Two regions with a labelled line between them, showing what is inside and what
crosses. Use it for trust boundaries, process boundaries, cache boundaries, or
network hops. The boundary is usually the part readers most misunderstand, which
is what earns it a figure.

Draw the crossings as explicit arrows with what travels on them. An unlabelled
arrow across a boundary is the diagram equivalent of hand-waving.

## Pattern 4: scaling or convergence curve

A single curve against an axis, with the operating point marked. Use it when the
argument turns on a nonlinearity: error falling as one over the square root of
samples, cost rising with fan-out, latency degrading past a queue depth.

One curve, one marked point, one annotation naming what the shape means. Curves
tempt authors into plotting three series and a legend, at which point it stops
being a diagram in an argument and becomes a chart that needs its own explanation.

## Anti-patterns

- A box-and-arrow diagram with no quantities, which restates the section heading.
- Literal hex fills, so the figure is legible in light and invisible in dark.
- A caption that renames the diagram ("Fig 2. The pipeline.") instead of stating
  the conclusion it supports.
- Illustrative figures presented as measurements, with no note in the caption or
  the footer saying which is which.
- More than one idea per figure, so the reader cannot tell what they were meant to
  take away.
- A wide diagram without `.scroller`, squashing axis labels into overlap on a
  laptop.
- Missing or decorative `aria-label`, leaving the diagram's argument unavailable to
  anyone not looking at it.
- Six diagrams where two carry the document, which is the default outcome of
  drawing before deciding what each one answers.
