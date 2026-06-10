# EXP-09 — Antigravity integration research (gemini lane migration)

Status: **HYPOTHESIS** (frozen 2026-06-11, before any probing)
Branch: `agentprims-exp09`
Off:    `feat/interactive-tmux-workspace-provider` @ `f671a2e`
Date:   2026-06-11
Deadline driver: **2026-06-18 — Gemini CLI stops serving Google One / unpaid tiers** (banner
in our own gemini probes; cf. EXP-06 transcripts and EXP-07 §1).

## Context (one sentence)

**Antigravity is the plan of record** (operator decision, 2026-06-11):
the gemini lane in `providers/workspaces/interactive-tmux/` is being
replaced by an antigravity (`agy`) lane on or before 2026-06-18, when
Gemini CLI stops serving Google One / unpaid tiers. EXP-07 proved
`agy` is TUI-installable and tmux-drivable but hit an unattended auth
blocker (bead `ptu1`); EXP-09 produces the **migration checklist as
the primary deliverable** and reframes EXP-08's gemini observability
row as the new antigravity row (gemini's recipe becomes reference-only
/ EOL).

## Hypothesis (frozen 2026-06-11 before any probing)

> **H1 (operator-once auth bootstrap is mechanical).** A single
> interactive `agy` login on the operator's host produces a small set
> of files under `~/.gemini/` (per EXP-07 §1's
> `~/.gemini/antigravity-cli/settings.json` reference) and/or a system
> keyring entry. Once produced, those files can be **copy-mounted**
> into containers exactly like the existing `~/.gemini/`, `~/.codex/`,
> `~/.claude/` patterns — i.e. the EXP-07 blocker is "we never ran the
> operator-once login," not "the credentials are non-portable." If H1
> holds, the existing provider auth-mount scaffolding (the
> `_GeminiAdapter.prepare_host_auth` shape with throwaway copies) is
> reusable; the only new thing is a single documented operator step.
>
> **H2 (the driving matrix mostly carries over).** The launch flags
> are different (`agy` vs `gemini`, possibly `--no-alt-screen`-style
> options), and the init gate may include a migration banner, but the
> submit / readiness model survives: `agy` is keyboard-first TUI per
> EXP-07's evidence. Specifically: literal text submit via tmux
> `send-keys -l`, Enter dispatches, and there's a steady-state idle
> marker visible in the bottom rows that we can pattern-match. Any
> place this hypothesis breaks (e.g., agy uses a non-tmux-friendly
> framebuffer, or requires alt-screen) is recorded as a matrix gap.
>
> **H3 (observability layout breaks at least partially).** Gemini CLI
> writes session state under `~/.gemini/tmp/<session>/` (logs.json,
> shell-history, telemetry). Antigravity's namespace is
> `~/.gemini/antigravity-cli/` per EXP-07. **Best case:** agy reuses
> the same `~/.gemini/tmp/` layout and the EXP-08 gemini extraction
> recipe survives verbatim. **Plausible case:** agy keeps its own
> session dir under `~/.gemini/antigravity-cli/` and the recipe needs
> a path swap but the JSONL shape is similar. **Worst case:** agy
> doesn't write a session transcript at all and we have to fall back
> to tmux-capture-only, with no per-tool / token telemetry.
>
> **H4 (no native OTel — but env-var support might exist).** Gemini
> CLI never exposed an OTel env var surface that worked under
> EXP-03/EXP-08 conditions. Antigravity is new code that might or
> might not have inherited it. I expect **no native OTel** — but
> there may be a `--print` / `--prompt` non-interactive mode that
> emits structured stdout (per EXP-07's `agy --print` mention) which
> the provider could capture instead.
>
> **H5 (migration is feature-flag-friendly and ships in one release
> cycle).** With a single operator login + a thin matrix row + the
> auth-mount pattern + an observability fallback, the provider can
> ship an `antigravity` lane parallel to the gemini lane behind a
> flag, with the gemini lane remaining the default until 06-18.
> After 06-18 the flag flips default-on for `agy`, the gemini image
> entry is marked deprecated, and the gemini-specific image baking +
> matrix row are removed in the cleanup release after the soak.

If H1 holds, the unattended-auth blocker is closeable with one operator
action. If H2 holds, the driver matrix work is mechanical. If H3 lands
in best-or-plausible case, EXP-08's gemini design ports forward. If H4
breaks against us, observability for the Antigravity lane is hooks-and-
tmux-only (no JSONL) — still acceptable, just lower fidelity. H5
is the deliverable shape.

## Method

1. **Hypothesis commit before probing** (this file is the hypothesis
   commit; runs land in the second commit).

2. **Probes (empirical where possible, web research where auth-gated).**

   - **Probe 1 — Auth bootstrap.** Install `agy` in a throwaway
     container (mirroring EXP-07's `node:22 + tmux + curl install`
     recipe). BEFORE any login: snapshot `~/.gemini/` + `~/.config/` +
     `~/.local/share/` listing. Then run `agy --version`, `agy --help`,
     and `agy` (interactive) and capture the on-disk delta WITHOUT
     completing OAuth. Web-research what a completed OAuth flow
     produces on disk: search release notes, the install repo's README
     / docs, and any community migration write-ups. Cite URLs and
     fetched-at timestamps. Document the operator-once procedure +
     copy-mount feasibility.
   - **Probe 2 — Driving matrix.** Test what we can without auth:
     launch flags (`agy`, `agy --print`, `agy --prompt-interactive`,
     `agy --print-timeout`), the init-screen content (welcome /
     migration banner / login menu), submit key sequences (Enter vs
     C-m vs C-j-C-m), the readiness signal when stuck at login
     (since steady-state idle is auth-gated). Mark any post-auth
     unknown explicitly as `UNKNOWN (auth-gated)`.
   - **Probe 3 — Observability.** Inspect what `agy` writes to disk:
     compare `~/.gemini/tmp/` vs `~/.gemini/antigravity-cli/`. Look
     for OTel env-var support via `env | grep` and `--help | grep`.
     Test whether `agy --print` emits structured stdout. Establish
     which of the three EXP-08 observability channels (session JSONL,
     hooks, native OTel) port forward to agy, and which need a
     fallback.
   - **Probe 4 — Migration plan.** Combine the three probes into a
     concrete, dated checklist: pre-06-18 (parallel lane, feature
     flag, operator-once login, validation matrix); post-06-18
     (default-flip, gemini-lane deprecation, image cleanup). Call out
     auth-gated UNKNOWNs that must close before each milestone.

3. **Constraints.**
   - Stay on `agentprims-exp09`. Never push `main`.
   - No actual OAuth flow run by this agent — only research what the
     flow produces. The operator-once step is documented for the human
     to run later (this is exactly bead `ptu1`'s blocker).
   - Throwaway containers only; never bake credentials.
   - Treat 06-18 as the hard deadline for HAVING a plan, not for
     completing the migration — the gemini lane stays alive until the
     replacement is proven.

## Results

_(Will be populated in the run commit; this section is empty in the
hypothesis commit.)_

## Verdict

_(Will be populated in the run commit.)_

## Cross-references

- EXP-07 — `experiments/EXP-07-antigravity-readiness.md` (TUI
  installability + tmux drivability proven; auth-bootstrap blocker
  documented).
- EXP-08 — `experiments/EXP-08-observability.md` on
  `agentprims-exp08` (three-channel observability contract; gemini row
  is currently a placeholder pending sibling-pane / Antigravity migration).
- Bead `ptu1` (the auth-bootstrap blocker EXP-09 closes the research
  half of).
- PR #202 (the provider this experiment instruments).
- 06-18 deadline source: the deprecation banner shipped inside the
  current `gemini` CLI (visible in every EXP-06 transcript:
  `"Gemini CLI will stop serving requests to Google One and unpaid
  tiers on June 18. Please migrate to Antigravity CLI before then..."`).
