# The decision-explainer method

What this file covers: how to decide what goes in a guide of this genre and in
what order, before any markup exists. Read it during workflow steps 1 through 4,
when you are still interviewing and outlining. For the visual system read
`aesthetic-system.md`; for the diagrams read `diagram-patterns.md`.

The genre is narrow: **a guide that exists so a specific person can make a
specific decision.** It is not a tutorial (the reader will not perform the task),
not reference documentation (they will not return to look up a signature), and
not an overview (they need to act, not appreciate). Everything below serves the
decision.

## Verify the premise before writing a word

The most expensive failure in this genre is a correct guide anchored to the wrong
constraint. In the origin case the entire first version was built on 60Hz and
16.6ms; the project targeted VR, so the real floor was 90Hz and 11.1ms. That is
not an edit. Every number, every diagram annotation, every budget, and half the
conclusions changed. Call it a re-spine, and price it as a rewrite.

The premise questions, asked before outlining:

- **What exactly are you deciding, and when?** A date makes scope concrete. "This
  week" forbids the encyclopedia.
- **What is the real target?** Platform, scale, hardware, load, tier. Ask for the
  number even when the reader has not said one. This is where the wrong premise
  hides.
- **What have you already ruled in or out?** Saves you arguing a settled point.
- **What is the failure you are actually worried about?** See below.
- **What do you already know?** Establishes the vocabulary floor, and prevents
  both condescension and hand-waving.

If an answer is unavailable, state the assumption in the masthead deck and in the
footer, so a wrong premise is visible rather than buried.

## Write for a competent person with no vocabulary

The useful reader model is not a skill level. It is: expert in their own field,
zero vocabulary in this one, needs to decide something soon. "Explain it like I am
16" is what people say, but taken literally it produces condescension.

That combination has two consequences. Assume the reader can hold a hard idea, so
do not simplify the mechanism. Assume they know none of the words, so never use
one before defining it. Most drafts get exactly one of these right.

## Pick the anchoring constraint

Choose the single constraint the reader is genuinely up against, state it in the
first section, and make every later section a visible consequence of it. This is
the choice that makes a document readable rather than encyclopedic, because it
gives the reader a test for relevance: does this help me live inside the
constraint?

The constraint has to be real, singular, and quantified. "Performance matters" is
not a constraint; "you have 11.1 milliseconds" is.

| Domain | Likely anchoring constraint |
| --- | --- |
| Real-time rendering | Frame budget in milliseconds |
| Consensus protocols | What you give up under partition |
| Type systems | What must be provable at compile time |
| Billing and metering | Which number the customer disputes |
| ML training | Compute budget, or labelled-data ceiling |
| API design | The request budget per user action |
| Storage engines | Read, write, and space amplification, pick two |
| Caching | Staleness the product can tolerate |
| Streaming systems | Delivery semantics under retry |

Two tests that a candidate constraint is the right one. Cost: missing it has a
consequence the reader can feel, not just a metric that degrades. Reach: at least
two thirds of the sections you were going to write are consequences of it. If
reach fails, you picked a topic rather than a constraint.

## State the human consequence, not the number

A number is inert. "11.1ms" tells a reader nothing about why they should refuse
to trade it. "A missed frame in VR is not ugly, it is nauseating, because an image
that does not track head motion causes simulator sickness" is what makes the
constraint survive contact with a feature request.

Do this immediately after introducing the constraint, and again wherever a
section implies a trade. The consequence is the load-bearing part; the number is
the handle.

## Order sections by when a term is needed

Not alphabetically, and not by topic taxonomy. Walk the argument and note where
each term first becomes necessary; that order is the section order. A guide that
groups all the material about one subsystem together forces the reader to hold
undefined terms, which is the exact failure the genre exists to prevent.

Then put the **vocabulary table near the top**, right after the opening framing.
In the origin case the first draft had a glossary at the bottom and the reader hit
unfamiliar terms for ten sections before the definitions arrived. Near the top it
is a lookup table: scannable, skippable by anyone who does not need it, with a
pointer from each entry to the section that explains it properly.

## Split overloaded terms into both senses

Loaded domain words usually name both a phenomenon and the machinery that
approximates it. "Global illumination" is light that bounced, and also the system
that fakes light that bounced. Conflating the two is why the reader was confused
before they asked.

Give such a term two glossary entries and two definitions. The pattern recurs:
"consistency" (a property, and a protocol), "type" (a set of values, and a
compiler annotation), "cache" (a copy, and a subsystem), "latency" (a duration,
and a budget line).

## Give the reader's fear its own section

Behind most requests of this kind is one unspoken worry, and it is usually the
reason they asked. In the origin case it was "is what we are building a band-aid
we will have to rip out?" The guide answers it in a dedicated late section that
runs the arithmetic rather than reassuring.

Recurring shapes: are we about to be locked in, will this survive scale, is this
the thing everyone else already abandoned, am I being sold the expensive option,
will I have to rewrite this. Name the fear in the reader's own words, then settle
it with numbers, then say explicitly what survives if the decision is revisited.
That last part is what makes a decision safe to make now.

## Accuracy beats clean prose

The reader is going to act on this, so a tidy falsehood is worse than an awkward
sentence. Where the explanation is lossy, flag it in a clause or a caveat callout
rather than smoothing it over. Where a figure is illustrative rather than
measured, say so in the caption and in the footer.

This is also the discipline that keeps a guide useful after the decision: the
reader who acts on it and then discovers a simplification you did not flag stops
trusting the whole document.

## Anti-patterns

Observations from the origin case and from drafts of this genre.

- The glossary sits at the end, so the reader meets terms for many sections
  before the definitions arrive.
- The guide is anchored on a constraint the project does not actually have,
  because nobody asked for the real target number.
- The constraint is stated as a number with no human consequence, so the first
  feature request trades it away.
- Sections are ordered by subsystem, so terms arrive after the paragraphs that
  need them.
- Diagrams restate the prose instead of carrying quantities, so they are
  decoration that costs scroll.
- An overloaded term is used in both senses without ever being split, preserving
  the confusion the reader arrived with.
- The reader's actual worry is addressed in scattered reassurances rather than one
  section that runs the arithmetic.
- Simplifications are presented as clean facts, so the reader acts on a tidy
  falsehood.
- The guide reads as a tutorial: it teaches the reader to perform the task rather
  than to choose between options.
- Revision is handed to a second agent or a second pass over a stale copy, so the
  file races and the numbers drift out of agreement with the diagrams.

## Revision

Expect two rounds and fold each round's requests into one pass. Revising a
document of this genre one request at a time invites inconsistency between prose,
figures, and captions, because the numbers appear in several places.

When a revision changes the premise, re-derive rather than patch: search for every
occurrence of the old number, including inside SVG text nodes and figure captions,
and check the conclusions that depended on it. A premise change that leaves one
stale figure annotation destroys confidence in all of them.
