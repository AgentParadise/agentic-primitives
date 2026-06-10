# FRICTION log — EXP-01 (claude interactive in tmux in docker)

Items observed while running the EXP-01 probe (`experiments/scripts/exp01-run.sh`,
N=3 runs). Each tagged: `tooling-bug` / `docs-gap` / `config` / `workaround-found`.

The experiment as a whole verdicted `go` — every friction item below has a
working workaround. None of them blocked the five-leg validation; together
they form the spec for what the EXP-05 `interactive-tmux` provider must hide
from callers.

## F-1 — Onboarding wizard fires on first interactive launch in a fresh workspace image

**Tag:** `config` → `workaround-found`. (Observed in N=3 runs before the
workaround; N=3 runs after.)

**What happens.** Launching `claude` (interactive) inside the
`agentic-workspace-claude-cli` image with only the throwaway `.credentials.json`
mounted at `/home/agent/.claude/.credentials.json` boots into the
**theme-picker wizard** (`Choose the text style that looks best with your
terminal`) instead of the prompt-ready state. This is on top of (and *before*)
the project-trust dialog (`Quick safety check: Is this a project you created
or one you trust?`).

**Why.** The interactive TUI gates the prompt behind two onboarding markers
that `~/.claude/.credentials.json` does NOT carry:
- `hasCompletedOnboarding: true` lives in `~/.claude.json` (top-level,
  **not** under `~/.claude/`).
- Per-project `hasTrustDialogAccepted` + `hasCompletedProjectOnboarding`
  live under `~/.claude.json` → `projects.<absolute-path>.*`.
The provider's `entrypoint.sh` writes a fresh `~/.claude/settings.json`
each container start with only `attribution` and `enabledPlugins.*-lsp.*=true`
— it has no concept of `~/.claude.json` because the `-p` mode it was
designed for doesn't gate on onboarding.

**Workaround (in `exp01-run.sh`).** After `docker run`, `docker cp` a
minimal `~/.claude.json` into `/home/agent/.claude.json` that pre-sets
both flags:

```json
{
  "numStartups": 5,
  "installMethod": "npm-global",
  "autoUpdates": false,
  "hasCompletedOnboarding": true,
  "theme": "dark",
  "projects": {
    "/workspace": {
      "hasTrustDialogAccepted": true,
      "hasCompletedProjectOnboarding": true
    }
  }
}
```

Then launch `claude` in the tmux pane. With this in place the TUI lands
directly on the `❯ ` prompt — no keys-into-wizard needed.

**Follow-up for EXP-05.** The new `interactive-tmux` provider entrypoint
should write **both** `~/.claude.json` (with onboarding-skip flags for the
known workspace path) AND `~/.claude/settings.json`. Pick the workspace
path from `${WORKSPACE_DIR}` (the existing env var) so the trust map is
keyed correctly.

## F-2 — Entrypoint clobbers `~/.claude/settings.json` on every container start

**Tag:** `config` (intentional; documents an interaction).

**What happens.** The provider's `entrypoint.sh` unconditionally does
`cat > ~/.claude/settings.json` on every start, overwriting whatever the
mount carries. After `docker stop` + `docker start`, my mounted settings
file (with `theme: "dark"`, `hasTrustDialogAccepted: true`,
`bypassPermissionsModeAccepted: true`) was reverted to the LSP-only default.

**Why this is the right call for `-p`-mode but the wrong call for
interactive-mode.** In `-p` mode, auth and tool-permission flow through
flags + env vars (`CLAUDE_CODE_OAUTH_TOKEN`, `--allowedTools`, etc.), so
overwriting settings.json doesn't lose anything. In interactive mode,
settings.json is the only place to express per-session preferences that
don't have a CLI flag (theme, trust map for non-default workspaces).

**Workaround.** Put onboarding flags into `~/.claude.json` (which the
entrypoint does not touch) rather than `~/.claude/settings.json`. Confirmed
across restart in leg (e) of N=3 runs.

**Follow-up for EXP-05.** Either (a) interactive provider entrypoint uses
a different settings template that preserves user-supplied overrides via
deep-merge, or (b) interactive provider keeps the file in `~/.claude.json`
which is naturally on the container's writable layer.

## F-3 — Default tmux TTY size of 80×24 truncates the Claude TUI

**Tag:** `workaround-found`.

**What happens.** Without `-x 200 -y 50`, `tmux new-session -d` inside a
daemonized container starts at 80×24 (tmux's default with no parent TTY).
The Claude TUI's welcome card + the side-panel tips column overflows the
80-char width; the box-drawing characters wrap and `capture-pane -p`
returns a visually scrambled snapshot. None of the readiness heuristics
(`❯ ` prompt indicator, `● <response>` marker) become harder to detect,
but the auth-confirmation banner ("Claude Max", model name) gets clipped
out, which breaks leg (a)'s heuristic.

**Workaround.** `tmux new-session -d -s claude -x 200 -y 50`. 200×50 is
arbitrary but generous; the right answer is to size the pane to whatever
text width the orchestrator captures with. (Resizing post-creation with
`tmux resize-window` works too if the consumer wants a specific size.)

**Follow-up for EXP-05.** Bake the size into the provider's
`open_session()` lifecycle method (or equivalent). Don't leave it
implicit.

## F-4 — `installMethod: "native"` in `~/.claude.json` triggers a footer warning when CLI is npm-installed

**Tag:** `tooling-bug` (low severity; cosmetic, not blocking).

**What happens.** During the first manual run I copied `installMethod:
"native"` into the throwaway `~/.claude.json` because that's what my host's
file has (host claude was installed via the native installer at
`~/.local/bin/claude`). Inside the container, claude is installed by `npm
install -g @anthropic-ai/claude-code` and lives at `/usr/local/bin/claude`.
The TUI's footer briefly displayed `installMethod is native, but claude
command not found at /home/agent/.local/bin/claude`.

This did not break submit/capture/multi-turn — but it polluted the bottom
row of the pane, which (in a stricter readiness heuristic that looks for
the `? for shortcuts` footer marker) could cause a false-positive
"something's wrong" signal in `wait_ready()`.

**Workaround.** Set `installMethod: "npm-global"` in the bootstrapped
`~/.claude.json` (matches reality inside the container). Verified across
N=3 runs: no footer warning, footer reads cleanly as `? for shortcuts ...
◉ xhigh · /effort`.

**Follow-up upstream.** The footer warning is well-intentioned (it warns
about misconfigured installs) but it should detect from the actual `$0`
of the running process, not from `installMethod` in config. Filable as a
small UX bug against `@anthropic-ai/claude-code`.

## F-5 — Prompt-ready detection is heuristic; the TUI redraws on every keystroke

**Tag:** `workaround-found` (no upstream bug; this is just what TUIs do).

**What happens.** `tmux capture-pane -p` returns the **current** visible
content, not a history of events. The Claude TUI uses Ink/React-style
re-renders: while generating a response, the TUI shows `✻ Cogitated for
Ns` (or `Churned for Ns`) animations and a transient spinner. While idle,
the bottom block looks like:

```
─────...─────
❯
─────...─────
  ? for shortcuts                  ◉ xhigh · /effort
```

While the model is generating, the same region typically shows
`✻ <verb> for Ns ... esc to interrupt` and the spinner. The clean idle
state — empty input box with the `❯ ` and the footer row visible — is the
positive readiness signal.

**Workaround used in the probe.** Bypass the readiness ambiguity entirely
by **waiting for the response token itself** to appear in the captured
pane (e.g., `grep -q "● BCTOKEN-RUN${RUN}"`). This works because every
test prompt asks the model to echo a unique token. For real workloads
where the response can't be pre-shaped, the readiness heuristic
recommended below should be used. Both legs verified in N=3 runs.

**Recommended `wait_ready()` heuristic (post-token wait, in priority
order):**
1. `! grep -q "esc to interrupt"` in capture — generation in progress
   gets called out by this exact phrase in the bottom-row hint.
2. `grep -qE "^❯[[:space:]]*$"` — the input box's prompt line is empty
   (only the chevron, optional whitespace).
3. `grep -q "? for shortcuts"` — the footer row is the steady-state
   indicator that the TUI is not in a modal (Esc menu, /command picker,
   trust dialog).

Combine all three for high confidence. Wall-clock for `READY-LEG-B` to
`● READY-LEG-B` in N=3 runs: 1–2 s on Opus 4.7. Use 30 s timeout for
short prompts, longer for real workloads.

**Follow-up for EXP-05.** The provider should expose `wait_ready(timeout)`
as a primitive, with the heuristic baked in. Don't make every caller
re-derive it.

## F-6 — `send-keys -l` for text + separate `send-keys Enter` is reliable; one-shot is also fine in practice

**Tag:** `workaround-found` (documents what worked, not a bug).

**What happens.** Two equivalent submission patterns both worked across
N=3 runs:

```bash
# Two-step (used in exp01-run.sh):
docker exec C tmux send-keys -t claude -l "$PROMPT"
docker exec C tmux send-keys -t claude Enter

# One-shot (used in the original manual exploration):
docker exec C tmux send-keys -t claude "$PROMPT" Enter
```

The two-step variant is preferred because (a) it avoids any tmux-side
quoting interaction between the prompt text and the special-key token,
and (b) for very long prompts, you can chunk the text portion across
multiple `send-keys -l` calls without the Enter firing mid-chunk.

**Bracketed-paste note.** The Claude TUI accepts both single-line and
pasted multi-line input. `send-keys -l` sends the bytes literally
(letter by letter as if typed), so no bracketed-paste escape sequence
gets injected. For genuinely large prompts (>4KB), bracketed-paste mode
would be the right transport — see follow-up below; not exercised in
this probe.

**Follow-up.** Probe large-prompt behavior (≥10KB) in a follow-up
experiment. The hypothesis predicted a token-count threshold for
bracketed-paste issues "to be measured, not assumed"; this experiment
deliberately did not test it.

## F-7 — `docker exec` is the natural transport; no need for `docker attach` or a side-channel socket

**Tag:** `workaround-found`.

**What was investigated.** The host can drive the in-container TUI via
either:
- `docker exec C tmux send-keys/capture-pane` (used here)
- `docker attach C` to a foreground container (heavier, single-attach)
- A `tmux -S /var/tmp/claude.sock` Unix socket bind-mounted to the host,
  letting the host's tmux talk to the container's tmux directly

The `docker exec` route worked end-to-end without any of the
complications of the other two. `tmux` is the in-container coordinator,
not a host-↔-container protocol; the host's tmux is not involved.

**Note.** This is also the path with the cleanest security story (no
shared socket on the host filesystem). For EXP-05 the provider's
"send a prompt" and "capture output" lifecycle methods should be thin
shells over `docker exec ... tmux ...`.

## F-8 — `~/.claude.json` lives at HOME, not inside `~/.claude/`

**Tag:** `docs-gap`.

**What surprised me.** Most of `~/.claude/` is what you'd expect:
sessions, history, plugins, settings. The onboarding-completion marker
is a peer at `$HOME/.claude.json` — a single file alongside the directory
of the same name. The two are easy to conflate when grepping for "claude
config."

**Workaround.** Treat them as two distinct surfaces:
- `~/.claude/` (directory) — runtime state, hooks config, credentials,
  per-session transcripts. Bind-mountable for cross-restart persistence.
- `~/.claude.json` (file) — first-run / onboarding markers, project
  trust map, install-method, telemetry counters. Lives on the container
  writable layer in the experiment; survives `docker stop`/`start` but
  NOT `docker rm` + `docker run`. Recreate via `docker cp` on every
  fresh `run`.

**Follow-up.** Add a note to the workspace-provider docs pointing at the
two-surface split when the EXP-05 provider docs land.

## F-9 — Telemetry / .last-update-result.json appears post-launch and is harmless

**Tag:** `config` (informational).

After the first interactive launch, several files appear inside the
mounted `~/.claude/` directory: `backups/`, `cache/`, `history.jsonl`,
`mcp-needs-auth-cache.json`, `plugins/`, `projects/`, `sessions/`. These
are runtime artifacts and are expected. They DO get written to the host
bind-mount and therefore persist across `docker stop`/`start` AND across
the `rm -rf "$HOST_AUTH_DIR"` step in `exp01-run.sh`'s per-run isolation
(because the script re-creates a fresh dir). No leak between runs.

**Recommendation for production.** Treat the bind-mounted `~/.claude/`
as ephemeral per-run state. Don't reuse it across unrelated workspaces —
the `history.jsonl` and `sessions/` artifacts persist conversation history
and could cross-contaminate.
