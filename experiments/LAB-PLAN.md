# Flywheel Lab: Interactive Agents in Containerized tmux

**Lab opened:** 2026-06-10
**Lab lead (orchestration):** Mac orchestrator session `agentprims`
**Lab leads (per-agent):** cc_1 (Claude), cod_1 (Codex), gmi_1 (Gemini)
**Repo:** `AgentParadise/agentic-primitives`
**Drives the artifact at:** `providers/workspaces/` (new interactive provider type)
**Hypothesis-first protocol:** `plugins/experiments/skills/running-experiments/SKILL.md`

## The pressure that opened this lab

`providers/workspaces` today drives agents inside Docker workspace containers
via `claude -p` (programmatic / one-shot mode). In approximately 5 days,
**`-p` mode leaves the Max plan** and becomes API-billed-only. Continuing on
`-p` means abandoning the Max plan subsidy that makes the whole agentic-coding
flywheel economically viable for individual operators.

The escape hatch we want to validate: drive the **interactive** agent CLIs
(`claude`, `codex`, `gemini`) inside the workspace containers via a tmux
session, with the **host** poking input and reading output through
`docker exec <c> tmux send-keys` / `tmux capture-pane`. If this works
reliably, we get bidirectional control of a running workspace on the
subscription plan rather than the API plan — the same agents, the same
workspaces, the same observability, just a different transport.

End state we are building toward: a **new workspace provider type** under
`providers/workspaces/` (working name: `interactive-tmux`) that exposes the
same lifecycle contract as today's `claude-cli` provider but runs an
interactive agent inside an in-container tmux session. The existing
`claude-cli` provider stays as-is for backwards compatibility and for users
who genuinely want API billing. Downstream consumer: Syntropic137 integration.

## The shape of the lab

Six experiments. The first three (EXP-01..03) prove the **basic primitive**
works for each of the three target agents individually. EXP-04 proves the
**swarm-in-a-container** packaging. EXP-05 is the **provider design and
implementation**. EXP-06 is the **fresh-agent validation** of the provider
docs — the read-the-docs-from-scratch acceptance test.

Each individual experiment lives in its own `experiments/EXP-NN-<slug>.md`
file with its own hypothesis-commit-first cycle. This LAB-PLAN.md is the
roadmap; it is **not** itself an experiment under the four-file convention.

```
EXP-01 ──▶ EXP-04 ──▶ EXP-05 ──▶ EXP-06
EXP-02 ──▶
EXP-03 ──▶
       ^
       └ run in parallel via worktrees, one agent per CLI
```

## Per-experiment summary

### EXP-01 — claude interactive in tmux in docker

**Owner:** cc_1 (Claude lead agent).
**Hypothesis:** The interactive `claude` TUI, started inside a tmux pane
inside the existing `claude-cli` workspace image (augmented with `tmux` if
not already present), can be driven from the **host** via
`docker exec <c> tmux send-keys` / `tmux capture-pane`. Specifically: (a)
the TUI starts and authenticates against the Max plan when `~/.claude` is
mounted from a throwaway host copy; (b) `tmux send-keys ... Enter` submits
a prompt and the model executes it; (c) the model's response is capturable
via `tmux capture-pane -p` and prompt-readiness is detectable
programmatically (the TUI returns to its prompt-line ready state); (d) a
second follow-up prompt works — true back-and-forth, not just one-shot;
(e) the recipe survives `docker stop` + `docker start` (or container
restart) with the same `~/.claude` mount.

**Falsifiable failure modes (any one of these → no-go for the basic primitive):**
- Auth never completes inside the container even with the mount, or
  completes once and then breaks on restart.
- `send-keys` does not reliably submit (e.g., Enter timing requires
  arbitrary sleeps that fail under load).
- `capture-pane` cannot disambiguate "model still thinking" vs "model
  finished, ready for next prompt" without an out-of-band signal.
- Bracketed-paste / TTY-size assumptions in the TUI corrupt long prompts
  past N tokens (N to be measured, not assumed).

**Success criteria (all five must be checked):** five-tuple (a)..(e) above
demonstrably works in **N≥3 independent runs** of the protocol; gotchas
documented in `experiments/FRICTION-claude.md`.

**Deliverables:** `experiments/EXP-01-claude-tmux-workspace.md` (the
experiment file), `experiments/FRICTION-claude.md` (gotcha log), and
inline-quoted captures of the tmux output proving each leg of (a)..(e).

### EXP-02 — codex interactive in tmux in docker

**Owner:** cod_1 (Codex agent).
**Hypothesis:** Same shape as EXP-01, substituting the `codex` CLI for
`claude`. The Codex CLI authenticates via `~/.codex/auth.json` (per host
runbook `docs/codex-setup.md` in the launchpad repo) mounted as a
throwaway copy. Identical (a)..(e) success criteria.

**Why it might fail differently from EXP-01:** Codex's prompt-readiness
indicators, streaming output cadence, and TUI redraw model are not
guaranteed to match Claude Code's. Many of the gotchas in
FRICTION-claude.md will recur as a different shape, not the same shape.

**Deliverables:** `experiments/EXP-02-codex-tmux-workspace.md`,
`experiments/FRICTION-codex.md`.

### EXP-03 — gemini interactive in tmux in docker

**Owner:** gmi_1 (Gemini agent).
**Hypothesis:** Same shape as EXP-01..02 for the `gemini` CLI. Authenticated
via `GEMINI_API_KEY` env var (not a credential file).

**Why it might fail differently:** Gemini CLI is the youngest of the three
and its TUI conventions are the least settled.

**Deliverables:** `experiments/EXP-03-gemini-tmux-workspace.md`,
`experiments/FRICTION-gemini.md`.

### EXP-04 — one image, three CLIs, one tmux session (swarm-in-a-container)

**Owner:** rotating; spawned after EXP-01..03 land their verdicts.
**Hypothesis:** A single workspace image bundling `claude`, `codex`, and
`gemini` CLIs, with a single tmux session containing three windows (or
panes), can host all three interactive agents simultaneously. The host
can address each by tmux pane id and drive them independently. No agent
starves another for TTY or stdin attention.

**Falsifiable failure modes:**
- Mounting all three credential dirs simultaneously creates a conflict
  (e.g., Claude and Codex both want to write the same shared logs file).
- One agent's full-screen redraws (e.g., Claude's TUI clearing the pane)
  break capture-pane assumptions for the other panes — should not happen
  in tmux's per-pane buffer model, but worth verifying empirically.
- Combined image size or memory footprint passes the threshold where it
  stops being a "workspace" and starts being a "VM" — quantify in MB and
  in steady-state RSS.

**Success criteria:** Same five-leg protocol (a)..(e) verified on each of
the three CLIs concurrently in the same container, across N≥3 runs. Plus
two new criteria specific to the swarm shape: (f) no cross-pane corruption
under simultaneous prompt-and-capture from the host; (g) startup, image
size, and idle RSS all reported with concrete numbers.

**Deliverables:** `experiments/EXP-04-swarm-tmux-workspace.md`,
swarm-shaped `Dockerfile`, friction notes consolidated across all three
CLIs into a `FRICTION-swarm.md` if and only if cross-cutting issues
appear.

### EXP-05 — design + implement the `interactive-tmux` workspace provider

**Owner:** TBD by orchestrator once EXP-01..04 verdicts are in.
**Hypothesis:** The lifecycle contract that `providers/workspaces/claude-cli`
exposes today (build, start, exec, capture, stop, observability hooks) can
be satisfied by a new provider that, under the hood, drives an interactive
in-container tmux pane via the protocol validated in EXP-01..04. From the
caller's perspective the provider type is the only thing that changes —
the same Python orchestrator calling the same lifecycle methods works
against either provider.

**Falsifiable failure modes:**
- The lifecycle contract assumes a synchronous `exec(prompt) → response`
  shape that cannot be cleanly mapped onto a tmux-driven async TUI without
  leaking state machine details to the caller. (If so: the contract
  itself needs an interactive-shaped variant, not just a provider
  swap-in.)
- Observability hooks (the JSONL event stream that today comes out of
  `claude -p --output-format stream-json`) cannot be reconstructed from
  the TUI output without lossy parsing.
- The interactive transport requires per-call cleanup that defeats
  multi-task reuse of one container (i.e., we lose the "one container,
  many phases" advantage of the existing provider).

**Success criteria:** The new provider lives at
`providers/workspaces/interactive-tmux/` with: a `Dockerfile`, a
`manifest.yaml`, a thin driver under `lib/python/agentic_isolation/` or
the appropriate package, and parity tests in `tests/` that run the **same**
acceptance suite the `claude-cli` provider passes today, against the new
provider, with no caller-side branching. `claude-cli` provider stays
in-place and untouched, demonstrating backwards-compat.

**Deliverables:** the new provider code, a passing parity test run,
`experiments/EXP-05-provider-design.md`, and an ADR under `docs/adrs/`
capturing the design decision.

### EXP-06 — fresh-agent validation of the provider docs

**Owner:** a freshly-spawned agent (no prior context from this lab) acting
as the acceptance tester for the EXP-05 deliverable.
**Hypothesis:** A reader who has never seen this lab can, **using only the
EXP-05 deliverables** (provider README, manifest, ADR, parity tests), stand
up a working `interactive-tmux` workspace and drive a successful
prompt/response cycle through the documented public API in under 30 minutes
of wall-clock. No tribal-knowledge fallback to the lab leads.

**Falsifiable failure modes:**
- Fresh agent gets stuck on a step that "everyone in the lab knows"
  (any such step is a documentation gap, recorded in FRICTION).
- The docs require reading source code to find an env var, a tmux flag,
  or a mount path. (Provider should be invokable through documented
  surface area only.)
- The acceptance test passes only because the fresh agent improvised
  around a gap rather than because the docs covered it.

**Success criteria:** Fresh agent's transcript shows the documented happy
path worked end-to-end without dropping out to source code. All
improvisations are recorded as FRICTION items and become docs PRs.

**Deliverables:** `experiments/EXP-06-fresh-agent-validation.md` and a
post-mortem PR adding any docs gaps found.

## Cross-cutting protocol

- **Hypothesis-first commit per experiment** — never write probe output
  before the hypothesis README is in a committed state on the agent's
  branch. The skill spec is the contract.
- **Evidence count in every empirical claim** — annotated as `(observed
  in N runs)` inline. Single-observation claims are explicitly flagged
  `(observed in 1 run; not yet replicated)`.
- **Throwaway credential mounts only** — `cp -R ~/.claude /tmp/claude-<slug>`
  then `-v /tmp/claude-<slug>:/home/agent/.claude` at `docker run` time.
  Never bake credentials into an image. Never commit them. (Same for
  `~/.codex` and `~/.gemini` in their respective experiments.)
- **FRICTION files tag every item** as one of: `tooling-bug`, `docs-gap`,
  `config`, `workaround-found`. Categories drive the follow-up: bugs become
  upstream issues, gaps become docs PRs, workarounds become provider
  defaults if generalisable.
- **No `-p` mode anywhere in the experiment runs.** That's the whole point.
  If a run accidentally falls back to `-p`, it does not count toward N.

## Out of scope for this lab

- Quality of the agents' answers. We measure transport, not intelligence.
- Performance benchmarking vs `-p` mode. That's a follow-up lab once the
  transport is proven.
- Multi-host orchestration (k8s, fly.io, etc.). Single-host docker on the
  VPS is the substrate here.
- Authentication automation (e.g., headless re-auth on token expiry). We
  document the manual recipe and defer the automation to a separate probe.

## Status board

| Exp     | Owner | Hypothesis-committed | Run-committed | Verdict |
|---------|-------|----------------------|---------------|---------|
| EXP-01  | cc_1  | d62ff55              | (this commit) | `go`    |
| EXP-02  | cod_1 | _open_               | _open_        | _open_  |
| EXP-03  | gmi_1 | _open_               | _open_        | _open_  |
| EXP-04  | TBD   | _open_               | _open_        | _open_  |
| EXP-05  | TBD   | _open_               | _open_        | _open_  |
| EXP-06  | fresh | _open_               | _open_        | _open_  |

Updated by each owner on commit; orchestrator audits at lab close.
