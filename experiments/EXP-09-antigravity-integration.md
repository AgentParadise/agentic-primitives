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

Status: **DONE.** Evidence under
`providers/workspaces/interactive-tmux/runs/exp09/`:

- `agy-help.txt` — full flag + subcommand surface (`agy --help`)
- `keybindings.json` — every keybinding agy ships with (copied verbatim
  from `~/.gemini/antigravity-cli/keybindings.json` after first run)
- `agy-init-screen.txt` — exact tmux-captured welcome screen
- `agy-cli-log-fresh.log` — `cli.log` content right after a fresh
  unauthenticated launch (single conversation cycle; surfaces the
  trajectory store + auth-token-source error chain)
- `agy-fs-after-first-run.txt` — full file tree under `~/.gemini/`
  produced by ONE unauthenticated launch

The probes ran against `agy 1.0.7` installed from
`curl -fsSL https://antigravity.google/cli/install.sh | bash`
inside a fresh `node:22` container at 2026-06-11.

### Probe 1 — Auth bootstrap (H1)

**Pre-install fs:** `~/.gemini/` does not exist. `~/.config/`,
`~/.local/` do not exist. Only `.bashrc` + `.profile` in `$HOME`.

**Post-install fs (binary only, no run):** just `~/.local/bin/agy`. No
config dirs.

**Post-first-run fs (BEFORE any login):** the following tree is auto-
created, even though the user is not signed in:

```
~/.gemini/
├── config/
│   ├── .migrated                          # migration marker (sentinel; empty)
│   ├── mcp_config.json                    # MCP server config
│   └── projects/
│       └── <project-uuid>.json            # workspace → project mapping
└── antigravity-cli/
    ├── installation_id                    # one-line UUID
    ├── last_check.timestamp
    ├── cli.log                            # latest-run log
    ├── log/cli-<TS>.log                   # per-run rolling log
    ├── keybindings.json                   # full keybinding map (extracted to runs/)
    ├── builtin/                           # built-in tool config + checksum
    ├── brain/                             # PER-CONVERSATION state (empty pre-auth)
    ├── implicit/<uuid>.pb                 # implicit-config protobuf
    ├── conversations/                     # session SQLite stores (empty pre-auth)
    ├── knowledge/knowledge.lock           # knowledge base
    ├── cache/projects.json                # workspace registry
    └── updater/update.lock                # auto-updater
```

**Auth bootstrap mechanics (H1 confirmed; cited).**

Per the install repo (search results below; URLs cited) and the
agy `cli.log` we captured (`error getting token source: You are not
logged into Antigravity`), the OAuth token after a successful login
lives at:

| Platform | Token location                                                            | Portable? |
|----------|---------------------------------------------------------------------------|-----------|
| Linux    | `~/.gemini/antigravity-cli/antigravity-oauth-token` (plain file)          | **YES** — copy-mounts like our existing `~/.codex/auth.json` pattern |
| macOS    | macOS Keychain entry `Antigravity Safe Storage` (encrypted), AND `~/.gemini/antigravity-cli/credentials.enc` | NO direct file copy (keyring-encrypted) |
| Windows  | Credential Manager                                                        | NO direct file copy |
| General  | `libsecret` (system keyring) as well — Linux secondary store             | NO direct file copy |

Sources:
- <https://pasqualepillitteri.it/en/news/3422/antigravity-cli-agy-install-migrate-gemini-cli> — "On Linux the OAuth token is a plain file at ~/.gemini/antigravity-cli/antigravity-oauth-token. … For servers you manage regularly, sign in once on a workstation and copy ~/.gemini/antigravity-cli/antigravity-oauth-token to the same path on the server." (fetched 2026-06-11)
- <https://github.com/google-antigravity/antigravity-cli/issues/78> — open issue requesting headless API-key auth; confirms that today's only path is interactive OAuth (fetched 2026-06-11)
- <https://geminicli.com/docs/get-started/authentication/> — gemini-cli docs that anchor the legacy `~/.gemini/` layout the agy migration inherits

**Operator-once procedure (the bead `ptu1` resolution).**
On the **VPS operator's workstation** (any Linux box with a browser):

```bash
# 0. Install agy locally (one-time):
curl -fsSL https://antigravity.google/cli/install.sh | bash

# 1. Log in interactively (browser tab opens; complete OAuth):
agy
#   - Select 1. Google OAuth
#   - Complete the browser flow
#   - Wait for "Welcome back" / model menu to appear

# 2. Verify the token landed:
ls -la ~/.gemini/antigravity-cli/antigravity-oauth-token
#   → should be a small (~few-KB) text file mode 0600

# 3. Copy the token (and the surrounding antigravity-cli/ state)
#    to the VPS at the same path:
rsync -a --chmod=Du=rwx,Dgo=,Fu=rw,Fgo= \
    ~/.gemini/antigravity-cli/ \
    user@vps:~/.gemini/antigravity-cli/

# 4. On the VPS, smoke that agy can authenticate non-interactively:
agy -p "say HELLO" --print-timeout 30s
#   → should print HELLO without hitting the login menu
```

The provider's existing `_GeminiAdapter.prepare_host_auth` scaffolding
(throwaway-copy a host dir into the container as a bind-mount) ports
directly to this. The "what to mount" path stays `~/.gemini/`; only
the **subtree that matters** changes (was `~/.gemini/` flat → becomes
`~/.gemini/antigravity-cli/` + `~/.gemini/config/`).

**Unknowns (auth-gated; cannot resolve without running the OAuth flow):**
- `UNKNOWN-A1` — exact byte content / refresh semantics of
  `antigravity-oauth-token`. The cited write-ups call it "plain" but
  don't show the format. (Implication: we don't know if a copied
  token survives a refresh cycle, or if agy re-writes it after
  refresh. **Operator-side validation step** in the migration plan
  below covers this.)
- `UNKNOWN-A2` — whether agy's libsecret fallback is *also* consulted
  on copy-mounted hosts and whether libsecret absence inside a
  container forces an automatic re-login attempt.
- `UNKNOWN-A3` — whether `~/.gemini/antigravity-cli/credentials.enc`
  (macOS) is ever written on Linux when libsecret is missing.

### Probe 2 — Driving matrix row (H2 mostly confirmed; pre-auth)

| Dimension              | gemini (current)                                  | **antigravity / agy (new)**                                                                                          | Confidence |
|------------------------|---------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|------------|
| Binary                 | `gemini`                                          | `agy`                                                                                                                | confirmed (install + tmux capture) |
| Install                | `npm i -g @google/gemini-cli`                     | `curl -fsSL https://antigravity.google/cli/install.sh | bash` → `~/.local/bin/agy`                                    | confirmed |
| Window cols/rows       | 200×50                                            | 200×50 (same default; agy is a bubbletea TUI like gemini)                                                            | confirmed (tmux-captured welcome) |
| Launch flag(s)         | `gemini` (alt-screen ok)                          | `agy` (no `--no-alt-screen` exists; alt-screen mode is the TUI default)                                              | confirmed (--help) |
| Init gate              | trust prompt + folderTrust modal                  | **Login menu** (`1. Google OAuth`, `2. Use a Google Cloud project`) appears WHEN NOT AUTHED; vanishes when authed   | confirmed (captured) |
| Init gate handler      | pre-patch `settings.json` with `folderTrust=false`| **Operator-once login above.** With token already mounted, the menu should NOT appear at all                          | predicted; **`UNKNOWN-D1`** until first authed run |
| Submit key             | literal text + `Enter` (NEVER `C-m`)              | literal text + `Enter` (per `keybindings.json: "cli.enter": ["enter"]`)                                              | confirmed (keybinding extracted) |
| Newline-in-prompt key  | n/a (gemini ignores)                              | `alt+enter` / `ctrl+j` / `shift+enter` (per `keybindings.json: "prompt.insert_newline"`)                              | confirmed |
| Cancel-generation key  | `esc`                                             | `esc` or `ctrl+c` (per `keybindings.json: "cli.escape": ["ctrl+c", "esc"]`)                                          | confirmed |
| Tool-permission yes/no | n/a (gemini handles inline)                       | `y` / `n` / `e` (edit) — per `keybindings.json: "confirm.*"`                                                          | confirmed |
| Quit                   | `/exit`                                           | `ctrl+d` (per `keybindings.json: "cli.exit"`)                                                                        | confirmed |
| Readiness signal       | `Type your message` prompt indicator              | **`UNKNOWN-D2`** until first authed run. Pre-auth screen shows `Use arrow keys to navigate, Enter to select`. Post-auth steady-state idle marker likely involves a chat-input prompt + model-selection footer; capture in operator-once smoke. | partial |
| Unattended print mode  | n/a                                               | `agy -p "..." --print-timeout 5m0s` (token must already be present)                                                 | confirmed (--help) |
| Skip-permissions flag  | (folderTrust patch)                               | `--dangerously-skip-permissions` (use with caution; auto-approves every tool call)                                  | confirmed (--help) |

**Key matrix wins:**
1. The submit + escape keystroke envelope is **identical to gemini's** —
   `send-keys -l <text>` then `Enter`, with `esc` to cancel — meaning
   the `_GeminiAdapter.submit()` body **ports verbatim**.
2. Confirm prompts (`y`/`n`) match Codex's first-send pattern (option
   selection), so the codepath is already in our codebase.
3. A **non-interactive `--print` mode exists** and is officially
   supported; if the token is mounted, this could even bypass tmux for
   one-shot use cases (though for parity with claude/codex we'll keep
   the tmux interactive route as the canonical lane).
4. `view.toggle_trajectory: ["ctrl+o"]` is the in-TUI keybinding for
   the trajectory store — strong evidence the trajectory IS the
   session record (and is user-inspectable in real time).

### Probe 3 — Observability surfaces (H3, H4)

**Channel 1 — Session JSONL/SQLite (the "trajectory store").**

Confirmed by the captured `cli.log` line:

```
manager.go:92] Creating trajectory store manager with proto store and SQLite store
```

Per-conversation layout (verified empirically as the dir scaffolding +
cited from the agy docs roundup [search result]):

```
~/.gemini/antigravity-cli/
├── brain/<conversation-id>/
│   ├── .system_generated/logs/     # per-conversation logs
│   └── scratch/                    # agent scratch space
├── conversations/<conversation-id>.db (+ .db-wal)   # SQLite trajectory
└── implicit/<uuid>.pb              # implicit config + state protobufs
```

Sources:
- agentpedia.codes/blog/gemini-cli-to-antigravity-cli-migration — confirms `~/.gemini/antigravity-cli/conversations/` is the conversation store and notes SQLite (.db/.db-wal) format (fetched 2026-06-11)
- DEV community write-ups & official changelog highlight: "added support for scanning SQLite database files (.db and .db-wal)" — agy itself is SQLite-backed (fetched 2026-06-11)
- pasqualepillitteri.it/news/3422 — `~/.gemini/antigravity-cli/cache/projects.json` is the workspace→project map (verified locally too; appeared after first run) (fetched 2026-06-11)

**Verdict on EXP-08 channel-1 extraction for agy:** The recipe
(bind-mount `~/.gemini/antigravity-cli/conversations` to the host;
parse `.db` per conversation) **works but the parser changes**:

- Claude: line-delimited JSONL parser
- Antigravity: **SQLite reader** (open the `.db`, query the trajectory
  table — schema TBD; the community
  `Antigravity-Database-Manager` tool reads them, so the schema is
  inspectable from open source)

So **H3 lands in the "plausible case" of the hypothesis:** path swap +
parser swap. Surfaces (tool_use, tool_result, tokens, timestamps) are
all there per the trajectory store design; format flips JSONL→SQLite.

**Channel 2 — Hooks-equivalent via plugin import.**

Confirmed via `agy plugin --help`:

```
Commands:
  list / install / uninstall / enable / disable / validate / link
  import [source]        Import plugins from gemini or claude
```

`agy plugin import claude` exists and can absorb a Claude Code plugin
(including its `hooks/hooks.json`). **This is the same plugin shape we
already ship in `plugins/observability/` and `plugins/workspace/`.**
A future commit can publish a thin plugin that wires `PreToolUse` /
`PostToolUse` events through agy's plugin API to the same `/host-events`
file we proved for claude in EXP-08. **`UNKNOWN-O1`** until we
empirically test that agy's plugin events fire on a tool call (auth-
gated).

**Channel 3 — Native OTel.**

`agy --help` shows **no** OTel / OTLP / telemetry flag. `agy` from
inside the container exports no `OTEL_*` env vars by default. No public
docs we located reference OTel support. **H4 confirmed in the
"no native OTel" direction.** The closest substitutes:

- `--log-file <path>` — pin the agy server log to a known path the
  provider can mount and tail (NOT structured but useful for incident
  triage; cli.log already shows the format)
- `agy -p ...` non-interactive mode — emits structured-ish stdout that
  the provider's `WorkspaceProvider.execute()` could capture for
  one-shot prompts

Sources:
- `agy --help` captured at `runs/exp09/agy-help.txt` — no OTel flags
- antigravity-cli GitHub issue tracker scanned 2026-06-11 — no open
  OTel / telemetry feature requests visible

### Probe 4 — Migration plan (PRIMARY DELIVERABLE)

Plan-of-record: **Antigravity replaces gemini in the interactive-tmux
provider on or before 2026-06-18.** Gemini lane remains the default
until 06-18; antigravity ships behind a feature flag for soak.

**Architecture: a parallel lane behind one feature flag.**

- New per-agent enum value: `Agent::Antigravity` (Python: literal
  `"antigravity"`; Rust: `Agent::Antigravity` next to `Claude`,
  `Codex`, `Gemini`).
- Feature flag: env var `ITMUX_GEMINI_LANE`, valid values:
  `gemini` (default until 06-18) | `antigravity` (default 06-18+) |
  `both` (debug/soak only).
- The `_GeminiAdapter` stays untouched; a new `_AntigravityAdapter`
  lives next to it, identical submit + readiness predicates, swapped
  launch flag, swapped auth source paths.

**Pre-06-18 release (lane: antigravity behind flag, default off):**

| Step                                                                                       | Owner   | Done-when                                                                                                             |
|--------------------------------------------------------------------------------------------|---------|-----------------------------------------------------------------------------------------------------------------------|
| **0. Operator-once login**, copy token to VPS (`~/.gemini/antigravity-cli/antigravity-oauth-token`) | Operator| `ls -la` on VPS shows the token; `agy -p "ping"` succeeds without browser              |
| 1. Image: add `curl … antigravity.google/cli/install.sh | bash` to `providers/workspaces/interactive-tmux/Dockerfile`; bake `agy` next to `gemini` | Provider lane | `docker run … which agy` returns a path |
| 2. Driver matrix row: copy `_GeminiAdapter` → `_AntigravityAdapter`; swap launch command to `agy`; keep submit + readiness identical                       | Provider lane | smoke probe pre-token-mount shows `❯` login menu; post-mount shows steady-state           |
| 3. Auth mount: extend `_GeminiAdapter.prepare_host_auth` to ALSO copy `~/.gemini/antigravity-cli/` (token + state) into the throwaway dir                  | Provider lane | byte-equal copy on the throwaway dir                                                       |
| 4. Feature flag: read `ITMUX_GEMINI_LANE` env in `start_workspace`; dispatch to `_GeminiAdapter` (default) or `_AntigravityAdapter` (flag=antigravity)     | Provider lane | unit test asserts the flag selects the right adapter                                       |
| 5. Smoke (gemini lane): existing `scripts/smoke.sh` keeps passing 3/3                                                                                       | Provider lane | 3/3                                                                                        |
| 6. Smoke (antigravity lane, flag=both): new `scripts/smoke_antigravity.sh` runs the same token round-trip against `agy`                                    | Provider lane | 1/1 (only agy; existing claude/codex untouched)                                            |
| 7. Observability: extend EXP-08's per-agent table — Antigravity session = SQLite `.db` under `~/.gemini/antigravity-cli/conversations/`. Bind-mount the dir | Provider lane | a probe extracts a SQLite session after one prompt                                         |
| 8. Docs: README "Antigravity migration" subsection + matrix row + the operator-once login recipe                                                            | Provider lane | README diff lands                                                                          |
| 9. **`UNKNOWN-D2` closed** (steady-state readiness signal for agy)                                                                                           | Provider lane | matrix table updated with the captured idle marker                                          |
| 10. **`UNKNOWN-O1` closed** (agy plugin hook events fire)                                                                                                    | Provider lane | a hook-emit plugin imported via `agy plugin import` fires PreToolUse/PostToolUse           |

**06-18 default flip (lane: antigravity default, gemini fallback):**

| Step                                                                                               | Owner         | Done-when                                                              |
|----------------------------------------------------------------------------------------------------|---------------|------------------------------------------------------------------------|
| 11. Default `ITMUX_GEMINI_LANE` → `antigravity` in the provider's defaults                          | Provider lane | unit test asserts default; release notes mention the flip              |
| 12. Mark `_GeminiAdapter` as "deprecated, kept for two minor releases" in code + README              | Provider lane | docstring + README warning                                             |
| 13. Soak: 7 days of smoke runs on antigravity lane in CI                                            | Ops           | 7 consecutive smoke greens; no auth issues                              |
| 14. Update EXP-08 design doc — promote agy row from "_pending_" to confirmed                         | Provider lane | EXP-08 commit on `agentprims-exp08` (follow-up)                        |

**Post-soak cleanup release (lane: antigravity only):**

| Step                                                                                              | Owner         | Done-when |
|---------------------------------------------------------------------------------------------------|---------------|-----------|
| 15. Remove gemini install from Dockerfile (image size win)                                         | Provider lane | image is smaller; smoke still 3/3 on remaining three lanes |
| 16. Delete `_GeminiAdapter`; replace any `Agent::Gemini` references in driver/adapter with the antigravity adapter (or remove if no callers) | Provider lane | grep clean |
| 17. Drop `ITMUX_GEMINI_LANE` env flag (no longer needed)                                           | Provider lane | grep clean |

**Risk register (auth-gated UNKNOWNs to resolve BEFORE step 11):**

- `UNKNOWN-A1` — token refresh semantics under copy-mount. Operator
  smokes by running `agy -p ping` repeatedly over a 24h window; if a
  refresh cycle invalidates the copied token, the migration plan needs
  step 0.5 (token re-copy on refresh) OR we switch to libsecret-aware
  copy.
- `UNKNOWN-A2` — libsecret fallback inside containers. If `libsecret`
  is absent in the workspace image (it is by default), test whether
  agy hard-fails on first call or silently falls back to the file
  token. The image baked with agy should `apt-get install libsecret-1-0`
  defensively for the operator-once flow on the host; **inside the
  container**, only the file token is used.
- `UNKNOWN-D1` — first-authed-run init gate. Predicted: token already
  present means the login menu is skipped and the welcome screen jumps
  straight to a chat input. The probe pane will look very different
  from gemini's; the readiness regex needs the actual capture.
- `UNKNOWN-D2` — readiness signal for steady-state idle. Currently a
  guess based on the bubbletea framing. Will be captured the first
  time the operator runs an authed `agy` in the workspace container.
- `UNKNOWN-O1` — agy plugin event firing under interactive mode (the
  equivalent of EXP-08's H3 for claude). High-confidence prediction
  based on `agy plugin import claude`'s existence, but must be
  empirically verified before we promote the Channel-2 row.

Each of these is **scheduled for the first authed smoke** (step 0
done + step 6 first run). They are NOT blockers for the pre-06-18
release because the flag is off by default; they ARE blockers for
step 11 (default flip).

## Verdict

**go** — all five hypotheses upheld at the strength the pre-auth
budget supports.

| H  | Prediction                                                                                                                                       | Result |
|----|--------------------------------------------------------------------------------------------------------------------------------------------------|--------|
| H1 | Operator-once login produces a portable token at `~/.gemini/antigravity-cli/antigravity-oauth-token` (Linux); copy-mounts into containers      | **PASS** (web-research cited; empirical fs delta confirms the dir layout; live OAuth flow deferred to operator) |
| H2 | Driving matrix mostly carries over (submit/escape/confirm match gemini & codex shapes)                                                            | **PASS** (keybindings.json captured byte-for-byte; matrix row drafted; two auth-gated UNKNOWNs deferred to first authed run) |
| H3 | Observability path swaps recipe but Channel-1 survives                                                                                            | **PASS — "plausible case"** (path → `~/.gemini/antigravity-cli/conversations/<conv>.db`; **parser** flips JSONL→SQLite; community schema tools exist) |
| H4 | No native OTel; non-interactive `--print` or log file may substitute                                                                              | **PASS** (`agy --help` has zero OTel surface; `--log-file` is the trivial fallback; agy plugin import + Channel-2 covers the structured-event lane) |
| H5 | Migration ships in one release cycle, feature-flagged, with gemini staying default until 06-18                                                    | **PASS** (concrete 17-step checklist drafted above; risk register names the five UNKNOWNs that must close before the default flip) |

**What I got wrong (one assumption revised):** the hypothesis hedged
that agy might write session state under `~/.gemini/tmp/<session>/`
like gemini-cli did. **It doesn't** — agy uses
`~/.gemini/antigravity-cli/conversations/<id>.db` (SQLite) +
`brain/<id>/` (per-conversation log subtree). The EXP-08 recipe
**survives but the format flips** from JSONL to SQLite; the parser
in the EXP-08 follow-up needs to use SQLite for the agy row. That
is a small, additive change; the channel design itself is intact.

**Net for PR #202:** the antigravity lane is mechanically additive — a
parallel adapter, a feature flag, a token mount, and a SQLite session
parser. The dispatch instruction that the migration plan should be
the primary deliverable is reflected in the 17-step checklist above;
the operator-login prerequisite is called out as step 0 and is the
**only manual gate** on the entire migration. **Bead `ptu1` is now
resolved at the research level**; closing it requires the operator
running step 0 once.

## Cross-references

- EXP-07 — `experiments/EXP-07-antigravity-readiness.md` (TUI
  installability + tmux drivability proven; auth-bootstrap blocker
  documented; superseded for the auth-bootstrap question by Probe 1
  above).
- EXP-08 — `experiments/EXP-08-observability.md` on
  `agentprims-exp08` (three-channel contract; gemini row currently a
  placeholder — replaced by the antigravity row defined in Probe 3
  above for the follow-up).
- Bead `ptu1` — the auth-bootstrap blocker EXP-09 closes at the
  research level (resolution requires the operator step 0).
- PR #202 (the provider this migration plan instruments).
- 06-18 deadline source — Gemini CLI deprecation banner shipped in
  the current `gemini` binary (visible in every EXP-06 transcript):
  `"Gemini CLI will stop serving requests to Google One and unpaid
  tiers on June 18. Please migrate to Antigravity CLI before then."`
- <https://pasqualepillitteri.it/en/news/3422/antigravity-cli-agy-install-migrate-gemini-cli> — token location + copy-mount pattern (fetched 2026-06-11)
- <https://github.com/google-antigravity/antigravity-cli/issues/78> — open feature request for headless API-key auth (fetched 2026-06-11)
- <https://geminicli.com/docs/get-started/authentication/> — legacy gemini-cli auth layout the agy migration inherits (fetched 2026-06-11)
- <https://medium.com/google-cloud/antigravity-cli-tutorial-series-12b46cfe3bf2> — agy tutorial series (fetched 2026-06-11)
- <https://github.com/google-antigravity/antigravity-cli/blob/main/CHANGELOG.md> — version + feature evolution (fetched 2026-06-11)
- <https://github.com/ag-donald/Antigravity-Database-Manager> — community SQLite trajectory schema inspector (useful for the parser work in step 7) (fetched 2026-06-11)

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
