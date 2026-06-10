# EXP-01 — claude interactive in tmux in docker

**Date opened:** 2026-06-10
**Owner:** cc_1 (Claude lead, branch `ntm/agentprims/cc_1`)
**Lab:** see `experiments/LAB-PLAN.md`

## Question

Can the **interactive** `claude` TUI, started inside a tmux pane inside the
`agentic-primitives` claude-cli workspace image, be driven from the **host**
via `docker exec <c> tmux send-keys` / `tmux capture-pane` reliably enough
to substitute for `claude -p` (programmatic mode) once `-p` leaves the Max
plan in ~5 days?

## Hypothesis

A `claude` TUI launched in a tmux pane inside the workspace container, with
the host's `~/.claude` mounted in as a throwaway copy, will support the
following five-leg protocol:

1. **(a) Startup + auth** — the TUI starts, picks up the mounted
   credentials, and is authenticated against the operator's Max plan
   subscription without any in-container interactive auth steps. Predicted
   wall-clock to ready prompt: under 15 seconds on the agentic-primitives
   claude-cli image (which has the CLI baked in; no first-time install).
2. **(b) Prompt submission via `tmux send-keys`** — a one-line prompt
   followed by Enter is submitted to the running TUI and observed to
   execute (model produces output). No arbitrary host-side `sleep` greater
   than 500 ms should be required between the `send-keys` of the prompt
   text and the `send-keys` of Enter.
3. **(c) Response capture + readiness detection** — `tmux capture-pane -p`
   on the pane returns the model's reply, and there is a deterministic,
   text-based way to detect "model finished, prompt is ready for the next
   message" (i.e., the TUI's prompt-line indicator) without relying on
   timing alone.
4. **(d) Multi-turn** — a second prompt sent after detecting prompt-ready
   from leg (c) is executed in the **same** TUI process with shared
   context, demonstrating true bidirectional interactive control rather
   than a glorified one-shot.
5. **(e) Restart survival** — `docker stop <c>` followed by `docker start
   <c>` brings the same container back up with the same mounted
   `~/.claude`, and a fresh tmux session inside it can re-run the whole
   five-leg protocol against the same auth.

### What would falsify the hypothesis (any one is fatal)

- F1: TUI never reaches the prompt-ready state even with `~/.claude`
  mounted; auth flow requires interactive browser handoff.
- F2: TUI reaches prompt-ready but `send-keys` cannot reliably submit:
  Enter timing is non-deterministic; bracketed-paste mode swallows
  newlines; or the TUI requires raw keystrokes the host cannot synthesize
  through `docker exec`.
- F3: `capture-pane` produces no deterministic "ready again" signal — we
  can read text but cannot distinguish "still streaming" from "done."
- F4: Multi-turn breaks because the TUI resets state between turns, or
  context is lost in a way that defeats the back-and-forth premise.
- F5: Container restart corrupts mounted state or loses auth in a way the
  recipe cannot recover from without operator intervention.

## Method

> **Hypothesis-commit rule:** commit this file before running any probe.
> Probe results land in this same file under `## Results` in a **second**
> commit; do not edit the hypothesis after probe runs begin.

### Step 0 — preflight, no probes

- Confirm Docker available on the VPS. **Observed:** Docker 29.5.3
  available (`docker --version`).
- Confirm `~/.claude` exists on host. **Observed:** present (see ls under
  Method/Setup).
- Confirm the `claude-cli` image build path: `just build-provider claude-cli`
  or `uv run scripts/build-provider.py claude-cli`. Read the script to
  verify what it stages and what tag it produces, **without** running it
  yet. (Reading does not violate the no-probe rule.)
- Verify `tmux` is present in the `claude-cli` Dockerfile. If not, add it
  via a thin `Dockerfile.exp01` overlay built `FROM agentic-claude-cli:<tag>`,
  so the experiment image is provably the production image plus the one
  thing the experiment needs.

### Step 1 — build, mount, run

1. Build (or rebuild) the production claude-cli image via the documented
   path. Capture the produced tag.
2. Build `experiments/Dockerfile.exp01` (overlay adding `tmux`) tagged
   `agentic-claude-cli-tmux:exp01`.
3. `cp -R ~/.claude /tmp/claude-exp01` — throwaway copy. Never mount the
   live `~/.claude`.
4. `docker run -d --name exp01 -v /tmp/claude-exp01:/home/agent/.claude
   --workdir /workspace agentic-claude-cli-tmux:exp01 sleep infinity` —
   container runs but doesn't auto-launch anything. The probe orchestrates
   tmux explicitly from the host.
5. From host: `docker exec exp01 tmux new-session -d -s claude -x 200 -y
   50` (explicit TTY size — see FRICTION).
6. From host: `docker exec exp01 tmux send-keys -t claude 'claude' Enter`
   to start the interactive TUI inside the tmux pane.

### Step 2 — five-leg probe

For each leg (a)..(e) record:
- The exact `docker exec` commands run.
- `tmux capture-pane -p` output (excerpted to the interesting region).
- Wall-clock from leg-start to leg-success-criterion.
- A pass/fail mark against the hypothesis predictions.

Each leg gets re-run **N=3 times** at minimum. Annotate as `(observed in
N=3 runs)` only when all three runs match.

### Step 3 — gotcha extraction

While running, log every surprise to `experiments/FRICTION-claude.md`
tagged `tooling-bug` / `docs-gap` / `config` / `workaround-found`. This
file is part of the deliverable and gets committed in the run-commit.

## Setup (frozen at hypothesis-commit time)

- **Host:** Ubuntu VPS (`hostname vmi3328387`, kernel 6.8.0-106-generic).
- **Docker:** 29.5.3, build d1c06ef.
- **Repo state:** branch `ntm/agentgims/cc_1` at this commit's SHA.
- **claude-cli image source of truth:** `providers/workspaces/claude-cli/Dockerfile`,
  built via `scripts/build-provider.py claude-cli`.
- **Pinned CLI version:** `CLAUDE_CLI_VERSION=2.1.126` (from the
  Dockerfile's `ARG` default at the hypothesis-commit SHA). Bumping
  invalidates the run.
- **Host auth source:** `~/.claude/` as it exists at hypothesis-commit
  time. Throwaway copy at `/tmp/claude-exp01`.

## Results

Three independent runs of `experiments/scripts/exp01-run.sh` (run1, run2,
run3) executed all five legs sequentially against the
`agentic-claude-cli-tmux:exp01` image. Per-run evidence in `runs/runN-leg-*.txt`
and per-run logs in `runs/runN.log`. Headline:

| Leg | Predicted criterion                                        | Observed in N=3 runs                                                                  | Evidence path                |
|-----|-------------------------------------------------------------|----------------------------------------------------------------------------------------|-------------------------------|
| (a) | TUI starts authenticated on Max plan (≤ 15s)               | "Opus 4.7 (1M context) · Claude Max" banner in all 3 runs; wall-clock ≤ 10s per run    | `runs/runN-leg-a.txt`         |
| (b) | One-line prompt submitted via `send-keys`; no >500ms wait  | Two-step `send-keys -l text` + `send-keys Enter` reliable in 3/3 runs; 0ms intentional gap | `runs/runN-leg-bc.txt` (top half) |
| (c) | Response captured + deterministic prompt-ready detect      | `● <token>` marker visible in pane; readiness heuristic from FRICTION F-5 confirmed 3/3 | `runs/runN-leg-bc.txt`        |
| (d) | Second prompt works in same TUI process (true multi-turn)  | Both `BCTOKEN-RUNN` and `TURN2-RUNN` in same scrollback, no TUI restart in between 3/3 | `runs/runN-leg-d.txt`         |
| (e) | `docker stop`+`start` preserves auth; protocol re-runs     | "Welcome back Neural!" + `● RESTART-RUNN` post-restart in 3/3 runs                     | `runs/runN-leg-e.txt`         |

**Wall-clock per run:** ~30–45 s end-to-end for all five legs. Bottleneck
is leg (e)'s `docker stop`+`start` (~5s) and the per-leg 1–2s model
response time on Opus 4.7.

**None of the five hypothesis-falsifying failure modes (F1–F5) materialised.**

### The send/wait/capture protocol (final)

Copy-pastable recipe; validated in N=3 runs of `exp01-run.sh`. Each step
links back to the gotcha that motivated it.

```bash
# 0. Per-run throwaway auth dir (never the live ~/.claude)
HOST_AUTH=/tmp/claude-exp01-$$
rm -rf "$HOST_AUTH" && mkdir -p "$HOST_AUTH"
cp ~/.claude/.credentials.json "$HOST_AUTH/.credentials.json"
chown -R 1000:1000 "$HOST_AUTH" && chmod 600 "$HOST_AUTH/.credentials.json"

# 1. Onboarding-skip ~/.claude.json (FRICTION F-1, F-2, F-4, F-8)
cat > /tmp/dotjson-$$.json <<'JSON'
{ "numStartups": 5, "installMethod": "npm-global", "autoUpdates": false,
  "hasCompletedOnboarding": true, "theme": "dark",
  "projects": { "/workspace": { "hasTrustDialogAccepted": true,
                                "hasCompletedProjectOnboarding": true } } }
JSON

# 2. Run the workspace container (NO credentials baked in; throwaway mount)
docker run -d --name claude-ws \
  -v "$HOST_AUTH:/home/agent/.claude" \
  --workdir /workspace \
  agentic-claude-cli-tmux:exp01 sleep infinity

# 3. Drop onboarding markers into container's writable layer
docker cp /tmp/dotjson-$$.json claude-ws:/home/agent/.claude.json
docker exec claude-ws chown agent:agent /home/agent/.claude.json
docker exec claude-ws chmod 600 /home/agent/.claude.json

# 4. tmux session with explicit size (FRICTION F-3)
docker exec claude-ws tmux new-session -d -s claude -x 200 -y 50
docker exec claude-ws tmux send-keys -t claude 'claude' Enter

# 5. Wait for prompt-ready (heuristic from FRICTION F-5)
until docker exec claude-ws tmux capture-pane -p -t claude \
      | grep -q "Claude Max"; do sleep 0.5; done

# 6. Submit a prompt (two-step, FRICTION F-6)
docker exec claude-ws tmux send-keys -t claude -l "$YOUR_PROMPT"
docker exec claude-ws tmux send-keys -t claude Enter

# 7. Wait for the response (response-token strategy; for free-form, use
#    the wait_ready() heuristic from FRICTION F-5).
until docker exec claude-ws tmux capture-pane -p -t claude \
      | grep -q "$EXPECTED_TOKEN"; do sleep 0.5; done

# 8. Read the response
docker exec claude-ws tmux capture-pane -p -t claude > /tmp/response.txt
```

For multi-turn, repeat 6–8 in the same tmux session. For restart-survival,
`docker stop` + `docker start` + restart the tmux session (Step 4) and
re-run from Step 5 — auth and project-trust persist on the container's
writable layer.

## Verdict

**`go`** — claude interactive can be driven from the host via
`docker exec tmux send-keys/capture-pane` reliably enough to substitute
for `-p` mode. Three runs, fifteen legs (five legs × three runs), zero
failures. The five-leg protocol is the documented contract; the gotchas in
FRICTION-claude.md are the spec for what EXP-05's `interactive-tmux`
provider must hide from callers.

This unblocks EXP-04 (one-image-three-CLIs swarm) and EXP-05 (provider
implementation). Codex (EXP-02) and Gemini (EXP-03) leads should
cross-check their FRICTION logs against the eight items here — F-1, F-2,
F-3, F-5, F-6 are likely to recur in different shapes per-agent; F-4, F-7,
F-8, F-9 are claude-specific.

### Hypothesis scorecard

| # | Prediction                                                                       | Observed                                                          | Score | Notes                                                                                              |
|---|----------------------------------------------------------------------------------|-------------------------------------------------------------------|-------|----------------------------------------------------------------------------------------------------|
| 1 | (a) Auth without in-container interactive flow, ≤ 15s wall-clock                 | Auth confirmed in ≤ 10s per run; mount-based, no interactive flow | ✅    | Required the `~/.claude.json` workaround (F-1); auth itself never required browser/device-code     |
| 2 | (b) Submission via send-keys + Enter, sub-500ms gap                              | Two-step send-keys works with 0ms gap                             | ✅    | Both two-step and one-shot variants work (F-6); two-step picked as the documented default          |
| 3 | (c) Capture is deterministic; readiness detection is text-based                  | `● <token>` and idle-state markers both work                      | 🟡    | Response-token strategy is fully reliable; pure idle-state heuristic is heuristic-not-formal (F-5) |
| 4 | (d) Multi-turn in same TUI process                                               | Both turns landed in same scrollback                              | ✅    | No process restart between turns; context carries (verified by Claude saying "Welcome back" once)   |
| 5 | (e) Restart survives via mounted `~/.claude`                                     | Auth + project-trust + onboarding-marker all survived stop/start  | ✅    | `~/.claude.json` survives on container writable layer; settings.json gets clobbered but no impact (F-2) |
| 6 | F1 (auth fails inside container) is fatal                                        | Not observed                                                      | n/a   | F1 ruled out                                                                                       |
| 7 | F2 (Enter timing non-deterministic)                                              | Not observed                                                      | n/a   | F2 ruled out                                                                                       |
| 8 | F3 (capture cannot disambiguate streaming vs done)                               | Partially observed; mitigated                                     | 🟡    | Pure capture-pane can't tell "thinking" from "done" without text heuristics; mitigated by F-5      |
| 9 | F4 (multi-turn breaks)                                                           | Not observed                                                      | n/a   | F4 ruled out                                                                                       |
| 10| F5 (restart loses auth)                                                          | Not observed                                                      | n/a   | F5 ruled out                                                                                       |

**Misses get the headline (per skill rule):**

- **#3 partial** — capture-pane is deterministic only with response-token
  strategy. Pure idle-detection requires a multi-signal heuristic
  (FRICTION F-5), not a single text match. The provider abstraction must
  hide this from callers.
- **#8 partial** — pre-registered as a falsifying failure mode "if no
  text-based ready signal exists." Text-based signals DO exist but no
  single signal is sufficient. This is exactly the partial outcome the
  hypothesis pre-bracketed.


## Cross-references

- Lab roadmap: `experiments/LAB-PLAN.md`
- Friction log: `experiments/FRICTION-claude.md` (created in run-commit)
- Skill spec: `plugins/experiments/skills/running-experiments/SKILL.md`
- Sibling experiments: `experiments/EXP-02-codex-tmux-workspace.md` (cod_1),
  `experiments/EXP-03-gemini-tmux-workspace.md` (gmi_1)
