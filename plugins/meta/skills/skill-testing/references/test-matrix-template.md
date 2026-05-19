# Test Matrix Template

How to construct a test matrix that actually exercises a plugin's routing
surface. Covers prompt selection, positive / negative / seam ratios, realism
guidance, and the TSV format the runner consumes.

This file is auto-discoverable beside the runner: the matrix lives in (or near)
`scripts/`, and the runner reads it as a TSV. A worked example is in
`../scripts/prompts.tsv.example`, drawn from the harness-engineering v0.2.1
validation that produced 40 / 40 PASS. The runner itself is
`../scripts/run-all.sh`. The chassis is `../SKILL.md`.

A test matrix is not a documentation artifact. It is the routing contract of
the plugin's descriptions, written down in a form a shell script can grade. If
the matrix passes, the routing claims in every `SKILL.md` description hold
empirically. If it fails, the failing row names the prompt and the expected
skill, and the fix lands in the same PR.

## TSV format

Three columns, tab-separated, no header row, one prompt per line:

```
<id>\t<expected-skill-name-or-NONE>\t<prompt-text>
```

- `id`: a short, stable identifier (e.g., `P01`, `N03`, `S07`). Used in result
  reporting and in single-prompt re-runs via `run-one.sh`. Stability matters:
  once a prompt has an id, keep that id across matrix revisions so historical
  results stay comparable.
- `expected-skill-name`: the bare skill name (e.g., `worktree-isolation`),
  NOT the prefixed form. The runner filters by `${PLUGIN_NAME}:<skill>`
  internally. Use the literal string `NONE` for negative controls, meaning
  "no skill from this plugin should fire".
- `prompt-text`: the literal user message. Real phrasings, not meta-questions
  about the skill. Tabs and newlines inside the prompt break the format; keep
  prompts on one line and avoid literal tabs.

Use the id prefix as a category marker so a glance at `results.tsv` tells you
which kind of failure you are looking at:

- `P` = positive trigger
- `N` = negative control
- `S` = seam prompt

A small example:

```
P01	worktree-isolation	Two agents started parallel tasks and they're both trying to bind to port 3000.
P02	worktree-isolation	How do I clean up orphaned worktrees from yesterday's runs?
S01	telemetry-pipeline	How do I propagate trace IDs through background jobs?
N01	NONE	Refactor this Python module to use dependency injection.
N02	NONE	Write a unit test for this function.
N03	NONE	Add JSON formatting to our logger.
```

Note that `S01` is a seam prompt: it sits between `application-legibility`
(propagation inside the app) and `telemetry-pipeline` (collector-side
enrichment). Which side it belongs to is exactly what the description's
non-trigger phrasing is supposed to decide.

## Prompt categories

Three categories cover the routing surface. Skip any of them and the matrix
measures less than it appears to.

### Positive triggers

Prompts that match the skill's description's trigger phrases or natural user
phrasings. Two to three per skill is the comfortable range. Each one should
exercise a different facet:

- One verbatim trigger phrase from the description (proves the literal text
  routes).
- One paraphrase a real user might use (proves the description generalizes).
- One symptom phrasing where the user describes what is broken, not the
  feature name (proves the description handles indirect entry).

Positive triggers alone catch over-pulling within the skill but miss
under-pulling and cross-skill confusion. They are necessary, not sufficient.

### Negative controls

Prompts that explicitly belong to an adjacent skill, to a different plugin, or
to general practice outside the plugin's scope. The expected route is `NONE`.

Aim for at least five per matrix. More if the plugin overlaps with widely
known practice (testing, logging, security, etc.) where descriptions are
likely to pattern-match on common verbs.

A matrix with zero negative controls cannot detect descriptions that have
quietly grown too broad. That is the most common drift mode.

### Seam prompts

Prompts that sit on the boundary between two skills (or between this plugin
and another plugin). The expected route is the one the description tightens
to. The test catches description drift that would cause the prompt to route
to the wrong sibling.

One seam prompt per adjacent-skill pair is the floor. Skills with three or
more close neighbors warrant more.

## Writing realistic prompts

Realism is the single biggest determinant of whether a matrix surfaces real
drift or just confirms the author's mental model.

- **Use the way a user actually phrases the task.** "The agent keeps asking
  me for screenshots when it can't tell what the page looks like" beats
  "Configure browser legibility for an agent harness." The first is what
  appears in transcripts. The second is what appears in design docs.
- **Symptom over solution.** Users describe what is broken, not what to do.
  "My agent ran for 3 hours and never converged on a fix" beats "Set up
  iteration-budget enforcement." The skill description has to handle the
  symptom phrasing or the user never reaches the skill.
- **Include the tools and terms users would say out loud.** OTLP, Playwright,
  Vector, Prometheus, p95, AGENTS.md, k6, Envoy. Real users name real tools,
  and descriptions that ignore tool names route worse than descriptions that
  include them.
- **Mix verb and noun framings.** "Audit this repo for X" and "Help me set
  up X" both happen in real sessions. So do "X is broken" and "What does X
  even do?". Mix them in the matrix so the description cannot pattern-match
  on a single verb.
- **Avoid the author's own phrasing.** The skill author overfits the
  description. Matrices written entirely by the author confirm the author's
  taste without surfacing trigger gaps. Pull prompts from real transcripts,
  from other users, or from another agent's phrasing.

The fastest way to a realistic matrix is to scroll back through real sessions
and copy the user turns verbatim, then anonymize.

## Choosing seam prompts

For each pair of adjacent skills (skills with overlapping concerns), construct
one prompt that lives on the boundary. The prompt is constructed so that the
description's non-trigger phrasing is the only thing that pushes it to the
right sibling. Examples from harness-engineering:

- `application-legibility` and `telemetry-pipeline` seam:
  "How do I propagate trace IDs through background jobs?"
  In-app propagation is `application-legibility`. Collector-side enrichment
  is `telemetry-pipeline`. The expected route is the one the description
  tightens to; the test catches drift either direction.
- `approved-scenarios` and `autonomous-validation-loop` seam:
  "When should the agent escalate to a human vs just proceed?"
  Policy-level is `approved-scenarios`. The loop mechanic of "when to stop
  and ask" is `autonomous-validation-loop`.
- `browser-legibility` and `telemetry-query` seam:
  "Agent caught a failed request and needs to look up the backend trace."
  Browser captures the failure. `telemetry-query` reads the trace. The
  seam is where the agent crosses from front-end perception to backend lookup.

List adjacent-skill pairs in the matrix's comment header (a leading comment
line in the TSV, ignored by the runner if blank-id rows are skipped, or as a
sibling `README.md`) so reviewers know what is being tested without having to
reverse-engineer the boundaries.

## Choosing negative controls

Negative prompts are the over-pull catchers. Construct them by walking the
plugin's neighbors:

- One prompt that should belong to a specific software-leverage-points skill
  (testing, logging, configuration, etc.). Verifies the description does not
  pull general practice into the plugin.
- One prompt that is general programming, unrelated to the plugin's domain.
  Verifies the description does not pull arbitrary code work.
- One prompt that is operational but for a different concern (production
  monitoring rather than agent perception, for example). Verifies the
  description does not pull adjacent operational work.
- One prompt that is plausibly related but explicitly outside the plugin's
  declared scope. Verifies the description holds its declared boundary.
- Mix verbs and nouns so the descriptions cannot pattern-match on a single
  trigger word. If every negative starts with "refactor", the test only
  proves the description does not say "refactor".

A useful sanity check: a negative control should be a prompt the author would
be embarrassed to see route to the plugin. If the author hesitates ("well,
maybe `harness-review` could touch that"), the prompt is a seam prompt, not a
negative control. Promote it.

## Matrix size guidance

The right size depends on the number of skills in the plugin. The cost is
roughly linear in prompt count; the value of additional prompts diminishes
once the matrix covers each skill's facets and each adjacent-skill pair.

- For a 10-skill plugin: 30 to 45 positive (three per skill, plus a handful
  of seam prompts) and 5 to 10 negative. The harness-engineering v0.2.1
  matrix is 35 + 5 = 40 prompts and produced 40 / 40 PASS.
- For a 3 to 5 skill plugin: 10 to 20 positive and 5 negative is comfortable.
- For a 1 to 2 skill plugin: 5 to 10 positive and 3 to 5 negative is enough.

Bigger matrices catch more drift but cost more to run. The sweet spot is when
adding a prompt no longer surfaces new findings: when the next ten prompts
all pass and you cannot articulate what facet they would have proved, stop.

A practical floor for any skill: three positive triggers and one negative
control. Below that the routing claim is anecdotal.

## When to update the matrix

The matrix is the routing contract written down. Update it whenever the
contract changes:

- Always when a new skill is added. Floor: three positive triggers and one
  negative control for the new skill, plus a seam prompt against each
  adjacent existing skill.
- Always when a description's trigger phrases change. Add at least one
  prompt that exercises each new trigger phrase.
- Always when a description's non-trigger phrasing changes (the "Do NOT use
  for..." clauses). Add or update the seam prompt that pivots on that
  non-trigger.
- Periodically when user transcripts reveal new phrasings. Real-world
  phrasing drift is the slow erosion of a routing contract; folding new
  transcripts back into the matrix is how the contract stays honest.
- Never silently. Matrix updates land in the same PR as the description
  change they validate, with the `results.tsv` showing PASS for the new
  rows.

A description change without a matrix update is an untested routing change.
Treat it the same way schema changes without migration tests are treated.

## Where the matrix lives

Two valid placements:

- **Plugin-local:** `<plugin>/test/prompts.tsv` or `<plugin>/prompts.tsv`.
  Simplest and most discoverable. The plugin owns its tests, one file,
  reviewable in any PR.
- **Skill-local:** `<plugin>/skills/<skill>/test/prompts.tsv`, one matrix per
  skill. Useful when one skill has a much richer matrix than its siblings,
  or when matrices need to evolve at different rates. Aggregated via a
  top-level runner that concatenates the per-skill TSVs before invoking
  `run-all.sh`.

The harness-engineering convention as of v0.3.0 is plugin-local at the plugin
root. See `../scripts/prompts.tsv.example` for the worked example. The runner
accepts any path via its positional argument or the `PROMPTS` env var, so
the placement is a convention question, not a tooling constraint.

Whichever placement is chosen, the matrix and its `results.tsv` belong in git
next to the skill(s) they test. A matrix in `/tmp` or in a chat scrollback is
not evidence; only a committed matrix is.

## Cross-references

- `routing-test-methodology.md`: the full procedure for running the matrix,
  parsing stream-json, and grading results.
- `body-usefulness-methodology.md`: the paired-run procedure for validating
  that a skill body earns its lines, distinct from routing.
- `flake-handling.md`: the meta-routing-table phenomenon and the
  single-rerun policy for distinguishing flakes from real failures.
- `../scripts/prompts.tsv.example`: the harness-engineering v0.2.1 matrix
  (40 prompts, 40 PASS), usable as a template for new plugins.
- `../SKILL.md`: the chassis skill that ties routing tests, body usefulness
  tests, and the pre-merge gate together.
