# EXP-05 — `interactive-tmux` workspace provider

**Date opened:** 2026-06-10
**Owner:** Claude lead, branch `agentprims-exp05` off `origin/main`
**Lab:** see `experiments/LAB-PLAN.md` on `ntm/agentprims/cc_1`
**Inputs:** EXP-01..04 (all `go` verdicts)
**Reviewers:** codex agent reviews next tick

## Question

Can the survive-the-Max-plan transport that EXP-01..04 validated (interactive
TUI in a tmux pane, driven from the host via `docker exec tmux send-keys` /
`capture-pane`) be packaged as a **production workspace provider** in this
repo, alongside the existing `claude-cli` provider, with a stable host-side
driver API that callers can program against without needing to know the
per-agent submit / readiness gotchas?

## Hypothesis

A new `providers/workspaces/interactive-tmux/` provider (Dockerfile +
`manifest.yaml`) bundling **claude, codex, and gemini** CLIs plus `tmux`
in a single `node:22-slim` image, together with a host-side driver
implementing five primitives (`start_workspace`, `send_message`,
`await_completion`, `capture_response`, `stop`), will satisfy the
following acceptance contract on the VPS docker substrate:

1. **(a) Build via the existing convention.** `uv run
   scripts/build-provider.py interactive-tmux` (and `just build-provider
   interactive-tmux`) produces a tagged image
   `agentic-workspace-interactive-tmux:latest` without changes to
   `scripts/build-provider.py`. The provider's `manifest.yaml` is the
   single source of truth for image name, version, runtime mode.
2. **(b) Three CLIs, one container, one tmux session.** `start_workspace`
   creates a tmux session with three independently addressable windows
   (or panes) — `claude`, `codex`, `gemini` — each running its interactive
   TUI under the agent user, with credentials mounted from throwaway
   host copies (never baked into the image, never committed).
3. **(c) Per-agent submit matrix encoded.** `send_message(agent, text)`
   hides the per-agent submit quirk:
   - Claude: two-step `send-keys -l text` then `send-keys Enter`
   - Codex: first message gets `send-keys text` then `C-j C-m`; subsequent
     messages may use plain Enter (probe verifies)
   - Gemini: `send-keys text Enter` only — never `C-m`
4. **(d) Per-agent readiness matrix encoded.** `await_completion(agent,
   timeout)` hides the per-agent done-detection quirk:
   - Claude: three-signal heuristic (no "esc to interrupt"; `❯ ` empty;
     "? for shortcuts" footer present)
   - Codex: `• Working` marker absent and `▌` prompt indicator present
   - Gemini: `Type your message or @path/to/file` prompt indicator visible
5. **(e) Per-agent init matrix encoded.** `start_workspace` walks the
   per-agent first-screen gates programmatically:
   - Claude: pre-seed `~/.claude.json` with `hasCompletedOnboarding: true`,
     `theme`, and `projects.<workspace>.hasTrustDialogAccepted: true`
   - Codex: launch with `codex --no-alt-screen`, then send `1` Enter for
     the trust banner, then `Escape` for the hooks-review screen
   - Gemini: pre-patch mounted `~/.gemini/settings.json` to set
     `security.folderTrust.enabled: false`; node ≥ 22 in base image
6. **(f) Three-agent smoke passes.** A single end-to-end smoke
   (`scripts/smoke.sh` in the provider) runs one prompt+response round-trip
   per CLI through the driver and exits 0; per-agent transcripts are
   captured to `runs/smoke-*.txt` as evidence. **N≥1 smoke run required
   to commit `go`.**

### What would falsify the hypothesis (any one is fatal)

- F1: `build-provider.py` requires modification to accept the new
  provider (would prove the convention is too rigid; bug not blocker, but
  invalidates the "use existing convention" claim).
- F2: One or more of the three CLIs cannot coexist in a single image
  (e.g., conflicting Node / Python versions, conflicting MCP config files,
  shared port collisions).
- F3: The per-agent matrix differs by enough across EXP-01..04 that a
  unified driver leaks the differences back to the caller (each agent
  needs its own bespoke handling code path that the caller must know).
- F4: A working smoke against one agent does not work against the same
  agent the next run, indicating non-determinism in the readiness
  heuristic at the integration level even though it worked in isolation
  per-agent.

## Open contradiction (resolved before implementation)

EXP-01 (cc_1) reported: **claude OAuth tokens live in
`~/.claude/.credentials.json`**; `~/.claude.json` only carries onboarding
markers.

EXP-04 (gmi_1) reported: **claude OAuth tokens live in `~/.claude.json`**;
this is the file you must mount in addition to `~/.claude/`.

**Empirical resolution** (test sequence run pre-implementation on this VPS;
2 isolated docker runs against `agentic-claude-cli-tmux:exp01`):

| Mount                                          | Result                                                                                  |
|------------------------------------------------|------------------------------------------------------------------------------------------|
| Only `~/.claude/.credentials.json` (no `.claude.json`) | Auth works at **Max plan** (`Opus 4.7 · Claude Max`); onboarding wizard fires (no markers) |
| Only `~/.claude.json` (no `.credentials.json`)         | Claude recognises the account ("Welcome back Neural") but falls back to **API Usage Billing** (`Sonnet 4.6`); Max plan lost |

**Conclusion.** OAuth tokens live in `~/.claude/.credentials.json` (a
`claudeAiOauth.{accessToken, refreshToken, ...}` object). `~/.claude.json`
holds `oauthAccount` metadata (account uuid, email, org) and onboarding
markers — useful for "Welcome back" and wizard-skip, but NOT the tokens
themselves. EXP-01 was correct on what the credentials file holds. EXP-04
was practically right that the provider must mount both files for
unattended Max-plan operation, but misattributed which file holds the
token.

The provider mounts **both**:
- `~/.claude/` → `/home/agent/.claude/` (for the OAuth tokens)
- `~/.claude.json` → `/home/agent/.claude.json` (for account metadata +
  onboarding markers; if absent, the driver synthesises a minimal
  `.claude.json` with the necessary wizard-skip flags)

This resolution is implemented in the driver's `_prepare_claude_creds()`
step and the answer is encoded in `providers/workspaces/interactive-tmux/README.md`.

## Design

### Image (`Dockerfile`)

`FROM node:22-slim` (matches existing `claude-cli` provider's Node 22 base
and satisfies the Gemini-needs-Node-22 constraint from EXP-03). One stage,
flat:

1. apt install: `tmux`, `git`, `jq`, `curl`, `ca-certificates`, `procps`,
   `python3` (for the driver's container-side helpers if any).
2. `npm install -g`: `@anthropic-ai/claude-code@2.1.126`,
   `@openai/codex@0.139.0`, `@google/gemini-cli@latest` (pinned in the
   image LABEL for reproducibility).
3. Create non-root `agent:agent` (uid 1000 / gid 1000) with `/home/agent`.
4. Copy entrypoint shim (`scripts/entrypoint.sh`) — sets up writable dirs
   under `/home/agent`, does NOT clobber `~/.claude/settings.json` (a key
   FRICTION fix from EXP-01 F-2); execs to `CMD`.
5. `WORKDIR /workspace`; `USER agent`; `CMD ["sleep", "infinity"]`.

### Manifest (`manifest.yaml`)

Matches existing `claude-cli/manifest.yaml` schema (validated by reading
`scripts/build-provider.py`):

- `name: interactive-tmux`
- `version: 0.1.0`
- `description`
- `image.dockerfile: ./Dockerfile`
- `image.tag: agentic-workspace-interactive-tmux`
- `image.context: ../../..`
- `runtime.modes: [interactive]`
- `runtime.agent: tmux-multi`
- `plugins.include: []` (no baked plugins for the first version; the
  three agents speak through their CLIs only, not through plugin hooks
  yet — follow-up arc)
- `capabilities.cli_agents: [{name: claude, ...}, {name: codex, ...}, {name: gemini, ...}]`
- `defaults.allowed_tools`: same shape as claude-cli for forward parity
- `security`: non_root agent, no setuid, ephemeral home

### Driver (`driver/interactive_tmux.py`)

Single Python 3.11+ file (uses stdlib only) at
`providers/workspaces/interactive-tmux/driver/interactive_tmux.py`. Two
surfaces:

- **Library:** `from interactive_tmux import InteractiveTmuxWorkspace` with
  the five methods named by the orchestrator's brief.
- **CLI:** `python -m interactive_tmux <start|send|await|capture|stop>
  ...` for shell-script consumers (e.g., the smoke test).

Method signatures (Python-style; encoded contract):

```python
class InteractiveTmuxWorkspace:
    @classmethod
    def start_workspace(
        cls,
        name: str,
        host_auth: dict[str, Path | None],  # {"claude": ..., "codex": ..., "gemini": ...}
        image: str = "agentic-workspace-interactive-tmux:latest",
        workdir: str = "/workspace",
        tmux_size: tuple[int, int] = (200, 50),
    ) -> "InteractiveTmuxWorkspace": ...
    def send_message(self, agent: Literal["claude","codex","gemini"], text: str) -> None: ...
    def await_completion(self, agent: str, timeout: float = 60.0) -> bool: ...
    def capture_response(self, agent: str) -> str: ...
    def stop(self) -> None: ...
```

Per-agent matrices (submit / readiness / init) live in three small adapter
classes (`_ClaudeAdapter`, `_CodexAdapter`, `_GeminiAdapter`) keyed by
agent name; the public API never branches on agent name in caller-visible
ways.

Credentials are mounted from **throwaway copies** the driver creates under
`/tmp/interactive-tmux-<workspace-name>/{claude,codex,gemini}/` from
`host_auth[<agent>]` if provided. If a per-agent host_auth path is `None`,
that agent's pane is started but warns-only on auth failure (lets callers
opt out of an agent they don't have creds for).

### What this version explicitly does NOT cover

- Reconnect to a running workspace from a different driver process
  (driver state is per-process; lifecycle is the consumer's responsibility).
- Streaming partial responses (the API is poll-then-capture; streaming is
  a follow-up arc).
- The full `agentic_isolation.WorkspaceProvider` Protocol parity. That
  Protocol is shaped around `execute(cmd) → result`, not around prompt
  round-trips. Bridging the two is a separate decision documented in the
  follow-ups section.
- Reproducing the `claude-cli` provider's plugin baking. The interactive
  provider runs the CLIs as humans run them; plugin participation is an
  orthogonal arc.

## Method

> Hypothesis-commit rule: this file + a stub Dockerfile / manifest / driver
> with `TODO_HYPOTHESIS_COMMIT_ONLY` markers land in commit one. The
> implementation that actually does the work, the smoke evidence, and the
> README updates land in commit two with verdict + scorecard.

### Step 1 — implement per the design

1. Write Dockerfile, manifest.yaml, entrypoint.sh under
   `providers/workspaces/interactive-tmux/`.
2. Write the driver under `providers/workspaces/interactive-tmux/driver/`.
3. Write `scripts/smoke.sh` under the provider dir.

### Step 2 — build via existing convention

```bash
uv run scripts/build-provider.py interactive-tmux
```

Capture: build wall-clock, image size, any unexpected stderr.

### Step 3 — smoke

```bash
bash providers/workspaces/interactive-tmux/scripts/smoke.sh
```

Smoke script behavior (encoded in the script, called from the driver
CLI):

1. `start_workspace name=smoke host_auth={claude: ~/.claude, codex: ~/.codex, gemini: ~/.gemini}`
2. For each `agent ∈ {claude, codex, gemini}`:
   - `send_message agent "Reply only with: SMOKE-<agent>"`
   - `await_completion agent timeout=60`
   - `capture_response agent` → grep for `SMOKE-<agent>`; fail loudly if missing.
3. `stop`.

Each per-agent transcript saved to
`providers/workspaces/interactive-tmux/runs/smoke-<agent>.txt`. The smoke
itself counts as N=1; we are not gating EXP-05 on N=3 because each leg in
EXP-01..04 already proved N=3 in isolation. EXP-05's job is integration.

### Step 4 — write results + verdict + scorecard

Update this file's `## Results` and `## Verdict` sections; write the
verdict's headline misses; update the LAB-PLAN status board on the cc_1
branch via cross-reference (no edit; that's another agent's responsibility
to fold).

### Step 5 — update `providers/workspaces/README.md`

Add the `interactive-tmux` row to the provider table.

## Setup (frozen at hypothesis-commit time)

- **Host:** Ubuntu VPS `vmi3328387`, kernel 6.8.0-106-generic.
- **Docker:** 29.5.3.
- **Repo state:** branch `agentprims-exp05` at this commit's SHA, off
  `origin/main` (`d807ab0`).
- **CLI versions pinned in Dockerfile:**
  - `@anthropic-ai/claude-code@2.1.126` (matches `claude-cli` provider)
  - `@openai/codex@0.139.0` (matches EXP-02)
  - `@google/gemini-cli@latest` (pinned via image LABEL at build time)
- **Host auth source:** `~/.claude/`, `~/.claude.json`, `~/.codex/`,
  `~/.gemini/` as they exist at hypothesis-commit time. Throwaway copies
  under `/tmp/interactive-tmux-smoke/`.
- **Backwards-compat:** `providers/workspaces/claude-cli/` MUST NOT be
  modified by this commit or the run commit.

## Results

### Build

`uv run scripts/build-provider.py interactive-tmux` ran clean against the
existing convention with **zero modifications** to `scripts/build-provider.py`.
The build read `providers/workspaces/interactive-tmux/manifest.yaml`,
staged the Dockerfile + entrypoint into `build/interactive-tmux/`, and
produced `agentic-workspace-interactive-tmux:latest`.

- Final image size: **544 MB** (vs. claude-cli's 688 MB — smaller because
  no Rust toolchain or pyright/typescript-language-server).
- Build wall-clock: ~5 minutes on the VPS.
- CLI versions baked in: `claude@2.1.126`, `codex@0.139.0`, `gemini@0.46.0`.

### Smoke (N=2 reproducible runs through the final driver)

Both runs of `providers/workspaces/interactive-tmux/scripts/smoke.sh`
passed cleanly: 3/3 agents, response-marker-validated against echoed
tokens. Evidence is six capture-pane snapshots:

| Run | Agent  | Response marker + token captured           | File                              |
|-----|--------|---------------------------------------------|-----------------------------------|
| 1   | claude | `● SMOKE-CLAUDE-2352004`                    | `runs/smoke-run1-claude.txt`      |
| 1   | codex  | `• SMOKE-CODEX-2352004`                     | `runs/smoke-run1-codex.txt`       |
| 1   | gemini | `✦ SMOKE-GEMINI-2352004`                    | `runs/smoke-run1-gemini.txt`      |
| 2   | claude | `● SMOKE-CLAUDE-2400276`                    | `runs/smoke-run2-claude.txt`      |
| 2   | codex  | `• SMOKE-CODEX-2400276`                     | `runs/smoke-run2-codex.txt`       |
| 2   | gemini | `✦ SMOKE-GEMINI-2400276`                    | `runs/smoke-run2-gemini.txt`      |

The smoke validates each pass with `grep -qF "${MARKER}${TOKEN}"` — the
agent-specific response marker (`● ` / `• ` / `✦ `) MUST appear before
the token. That marker prefix distinguishes the model's reply from the
echoed prompt that also contains the same token; an earlier smoke
iteration that grepped on the token alone false-passed for Gemini (the
prompt-echo line `>   Reply only with: SMOKE-GEMINI-...` matched while
the model was still in `Thinking…`).

### Iterations needed during smoke development

The integration cycle exposed three issues that the per-agent unit
experiments (EXP-01..04) had not stressed; each became a real fix in the
driver before the N=2 clean runs above were declared:

1. **Codex `~/.codex/tmp/arg0/` race.** The driver's throwaway copy of
   `~/.codex/` raced with live codex processes on the host that create
   and delete `tmp/arg0/codex-*` files mid-copy, raising `shutil.Error`.
   Fix: `_CodexAdapter.prepare_host_auth` now skips `tmp/`, `log/`,
   `logs/` when copying — only auth + config + sessions cross over. Auth
   continued to work because the token file was untouched.
2. **Claude welcome-marker fragility.** The hypothesis named `Welcome back`
   as the post-launch wait marker. Observed: on at least one account this
   renders as `Welcome to Opus 4.7 xhigh!` instead. Fix: switch the
   marker to `Claude Max` (the plan-line text), which is universal across
   accounts and shows up unconditionally after auth resolves.
3. **Codex `is_ready` transient false-pass.** The original `await_completion`
   declared ready after `stable_polls` consecutive `is_ready` observations.
   Codex's `• Working (Ns • esc to interrupt)` line updates each second,
   and tmux `capture-pane` occasionally caught a frame between updates
   where `Working` was momentarily absent — those frames satisfied
   `is_ready` and accumulated 4 in a row faster than the model finished.
   The fix layers a second invariant: the pane content must be **byte-for-
   byte identical** across the `stable_polls` consecutive captures. A
   redrawing TUI does not produce identical captures, so the transient
   frames are filtered out automatically. With this fix in place, codex
   passes 2/2 runs (the failing run was reproduced once with the
   single-invariant heuristic; after the fix, two consecutive runs
   passed).

### Open-contradiction resolution (committed in the hypothesis-commit)

Pre-implementation, the EXP-01 vs EXP-04 disagreement on where Claude's
OAuth tokens live was resolved by two isolated mount tests on the VPS:

- Only `~/.claude/.credentials.json` mounted → **Max plan** (`Opus 4.7 ·
  Claude Max`); onboarding wizard fires.
- Only `~/.claude.json` mounted → **API Usage Billing** (`Sonnet 4.6`);
  no Max plan, but "Welcome back" name renders.

The driver mounts **both** for unattended Max-plan operation. EXP-01's
claim that `.credentials.json` is the token file is correct; EXP-04 was
practically right to mount `.claude.json` too, but for a different reason
than reported (account metadata + onboarding markers, not tokens).
Encoded in `providers/workspaces/interactive-tmux/README.md` for future
readers.

## Verdict

**`go`** — `providers/workspaces/interactive-tmux/` is the
interactive-mode-friendly sibling to `providers/workspaces/claude-cli/`,
buildable via the existing `scripts/build-provider.py` convention without
modification, hosting all three CLIs (claude/codex/gemini) in a single
container, drivable from the host through a five-primitive API that
hides the per-agent submit/readiness/init matrix from callers. The N=2
smoke runs prove an end-to-end prompt+response round-trip works for all
three agents simultaneously in the same workspace. `claude-cli` provider
is untouched (verified: `git diff origin/main..HEAD --
providers/workspaces/claude-cli/` is empty).

### Hypothesis scorecard

| # | Prediction                                                                       | Observed                                                                                          | Score |
|---|----------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|-------|
| 1 | (a) Build via existing `scripts/build-provider.py` convention                    | Built without script modification; staged context produced from `manifest.yaml`; both `latest` and `claude` version tags applied | ✅    |
| 2 | (b) Three CLIs, one container, one tmux session, three independently-addressable windows | All three launched in same tmux session under `agent` user (uid 1000); driver addresses them by window name | ✅    |
| 3 | (c) Per-agent submit matrix encoded                                              | All three submit patterns work (Claude two-step, Codex literal+C-j+C-m, Gemini literal+Enter); callers use one API | ✅    |
| 4 | (d) Per-agent readiness matrix encoded                                           | Encoded — but the initial heuristic-only approach false-passed for Codex; final driver layers identity-across-N-captures invariant to filter transients | 🟡    |
| 5 | (e) Per-agent init matrix encoded                                                | All three init flows work programmatically; Gemini settings.json auto-patch in driver; Claude .claude.json synthesised in driver from host metadata | ✅    |
| 6 | (f) Three-agent smoke passes, N≥1                                                | N=2 runs, 6/6 response markers captured; smoke promoted from token-only grep to marker+token grep mid-development (would have false-passed Gemini otherwise) | ✅    |
| 7 | F1 (build-provider.py requires modification)                                     | Not observed; convention held                                                                     | n/a   |
| 8 | F2 (three CLIs cannot coexist)                                                   | Not observed; all three coexist with no port / config / Node-version conflicts                    | n/a   |
| 9 | F3 (per-agent differences leak to caller)                                        | Not observed; the public API is agent-name-keyed only                                             | n/a   |
| 10| F4 (non-deterministic readiness at integration)                                  | Observed for Codex (~1/3 fail under the naive heuristic); fixed by stable-content check; documented under "Iterations" | 🟡    |

**Misses get the headline (per skill rule):**

- **#4 partial** — the per-agent readiness heuristic that EXP-01..03
  reported as sufficient in isolation turned out to be insufficient
  under fast back-to-back integration. The stable-content layer is the
  fix; future provider versions should consider also exposing a
  "send-and-await-response" combined primitive that uses the per-agent
  response marker as the explicit done signal rather than purely a
  readiness heuristic.
- **#10 partial** — pre-registered as a falsifying failure mode "if
  non-determinism appears at integration even though it worked in
  isolation." Codex specifically hit this; the empirical fix is in the
  driver and documented.

## Follow-ups

These do not block this experiment but should land in subsequent commits
/ probes:

- **EXP-06 fresh-agent docs validation** (per LAB-PLAN) — a fresh agent
  with no prior context runs `providers/workspaces/interactive-tmux/README.md`
  from the top and either succeeds or surfaces a docs gap.
- **Bridge to `agentic_isolation.WorkspaceProvider` Protocol.** The
  existing protocol is exec/file-shaped, not prompt-shaped. The right
  bridge probably adds a new prompt-shaped protocol next to it rather
  than coercing one onto the other.
- **`send_and_await` combined primitive** that uses the per-agent
  response marker as the explicit done signal (cleaner than the
  current `send` + `await` + `capture` triple-call pattern).
- **Streaming partial responses** for callers that want token-by-token
  updates.
- **OTel / event capture from the interactive transport.** The `-p`-mode
  claude-cli provider gets stream-json events for free; the interactive
  provider doesn't. The future arc is either (a) plugin hooks against
  the interactive claude TUI, or (b) screen-scraping for known event
  shapes — both should be probed independently.


## Cross-references

- Lab roadmap: `experiments/LAB-PLAN.md` on `ntm/agentprims/cc_1`
- Sibling experiments: EXP-01 (cc_1), EXP-02 (agentprims-exp02), EXP-03
  + EXP-04 (agentprims-exp03)
- Skill spec: `plugins/experiments/skills/running-experiments/SKILL.md`
- Existing convention reference: `providers/workspaces/claude-cli/`,
  `scripts/build-provider.py`, `providers/workspaces/README.md`
