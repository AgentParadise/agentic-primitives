# Aesthetic system: colors, fonts, and spines

Read this when choosing the look and the structure of a system infographic. It
covers the default semantic color system, font pairings that avoid generic
output, and the small set of structural "spines" most system explainers are
built from. The CSS that implements all of this lives in `../assets/template.html`.

## Semantic color: the core discipline

The thing that makes a system diagram readable is that color means something
and means the same thing everywhere. A reader should be able to decode the
graphic without a legend because the palette is consistent.

Default blueprint palette and what each accent means:

| Role | Meaning | Hex |
|------|---------|-----|
| amber | local, on-device, secret, keychain | `#ffb454` |
| teal | data flow, requests, the happy path | `#54d6cc` |
| red | a boundary, danger, "does not cross" | `#ff6b6b` |
| green | ok, healthy, authenticated, success | `#7ee787` |
| ink background | the canvas | `#080b10` |
| panel | raised surfaces, nodes, cards | `#121821` |
| text tiers | bright `#dfe8ef`, dim `#8595a3`, faint `#5d6b78` |

Rules that keep the mapping legible:

- Assign each accent one meaning at the start, then never reuse that hue
  decoratively. If amber means "secret," an amber border somewhere unrelated
  reads as "this is secret" and misleads.
- Keep one dominant accent plus one or two sharp supports. Evenly distributed
  rainbows flatten the hierarchy and read as decoration, not signal.
- Reserve red for the single most important constraint (the boundary nothing
  crosses). Overusing red dilutes the one place it should stop the eye.

When a different tone fits (an editorial light theme for a public explainer, a
warmer palette for a consumer product), change the palette but keep the
one-color-one-meaning discipline. The discipline travels; the specific hues do
not.

## Fonts: pick characterful, pair display with mono

Avoid Inter, Roboto, Arial, and the system stack. They read as a default and
strip the graphic of identity. Pair a characterful display face for headings
with a monospace for commands, labels, and pins (the mono signals "this is code
or a precise value").

Default pairing: `Chakra Petch` (display, technical and slightly HUD-like) with
`JetBrains Mono` (mono). Both load from a single Google Fonts link.

Other pairings that hold up, by tone:

- Technical or HUD: `Chakra Petch`, `Orbitron` (sparingly), `Major Mono Display`
  (extreme, headers only) with `JetBrains Mono` or `IBM Plex Mono`.
- Editorial or refined: `Archivo` or `Archivo Expanded`, `Fraunces` (display)
  with `Space Mono` or `Sometype Mono`.
- Geometric or bold: `Syne`, `Clash Display` (if available) with `Space Mono`.

Use the mono for every command, every pin label, and every section number. The
contrast between a soft display face and a precise mono is what gives the
schematic its instrument-panel feel.

## Spines: the structural vocabulary

Most system explainers are built from four blocks. Pick the spine that matches
the single most important thing the reader needs to understand.

- Pipeline (A to B to C). A horizontal row of nodes joined by flowing arrows.
  Best when the story is a transform: input goes through stages to output.
- Perimeter map (trust boundary). A bordered region labeled "inside" (for
  example "your machine") containing the local nodes, with labeled wires that
  cross the border, plus a seal callout for the invariant ("secrets never
  cross"). Best when the key insight is what stays local versus what leaves.
  This is usually the centerpiece for security and data-flow systems.
- Phase blocks. Cards or columns tagged by cadence: one-time, per-call,
  continuous. Best when the same system behaves differently depending on when a
  step runs.
- Numbered setup checklist. Ordered steps with copy-able command chips. Color
  the step number of any step that touches something risky or irreversible (a
  login, a keychain grant, an exposure) so the eye finds it.

A complete system explainer usually combines three of these: a perimeter map or
pipeline as the centerpiece, phase cards for the sequence, and a setup checklist
for "what the reader does." Invariant chips (small cards stating the rules that
make the system safe or correct) sit well between the phases and the checklist.

## Composition notes

- A faint blueprint grid plus a soft radial glow gives depth without clutter.
  Mask the grid so it fades at the edges rather than tiling flatly.
- Lead with one bold thesis in the hero: the single sentence a reader should
  remember. Color two or three words with the accents to preview the meaning
  map.
- Spend space generously between sections. An infographic is read in one scroll,
  so vertical rhythm carries the pacing.
- One staggered reveal on load (sections fade up as they enter) creates sequence
  without spectacle. Keep per-element micro-animations rare.
