"""Host-side driver for the `interactive-tmux` workspace provider.

Five public primitives (matches the EXP-05 contract the orchestrator
specified):

  start_workspace(name, host_auth, image, ...) -> InteractiveTmuxWorkspace
  ws.send_message(agent, text)
  ws.await_completion(agent, timeout)
  ws.capture_response(agent)
  ws.stop()

The driver encodes the per-agent matrix discovered in EXP-01..04 so callers
do NOT see per-agent quirks:

  * Claude:
      - submit  = `send-keys -l text` then `send-keys Enter` (two-step)
      - init    = pre-seed ~/.claude.json with hasCompletedOnboarding/theme/
                  projects.<workspace>.hasTrustDialogAccepted (avoids the
                  theme picker and the per-project trust dialog)
      - auth    = mount ~/.claude (for .credentials.json) AND ~/.claude.json
                  (for oauthAccount metadata — without it, claude falls back
                  to API Usage Billing instead of Max plan)
      - ready   = three-signal heuristic: no "esc to interrupt", empty `❯ `
                  prompt line, "? for shortcuts" footer present
  * Codex:
      - submit  = `send-keys text` then `C-j C-m` (first-send gotcha:
                  bare C-m alone often does not dispatch the first message)
      - init    = `codex --no-alt-screen`, then `1` Enter for trust banner,
                  then Escape to close hooks-review screen
      - auth    = mount ~/.codex
      - ready   = `• Working` marker absent and a known idle-state marker
                  visible
  * Gemini:
      - submit  = `send-keys text Enter` (NEVER C-m — confirmed by EXP-03)
      - init    = pre-patch ~/.gemini/settings.json with
                  security.folderTrust.enabled = false, then `gemini` Enter
      - auth    = mount ~/.gemini
      - ready   = `Type your message` prompt indicator present

Standard library only (Python 3.11+). Designed to be importable AND runnable
as a CLI (`python -m interactive_tmux`).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases and constants

AgentName = Literal["claude", "codex", "gemini"]
AGENTS: tuple[AgentName, ...] = ("claude", "codex", "gemini")

DEFAULT_IMAGE = "agentic-workspace-interactive-tmux:latest"
DEFAULT_TMUX_SIZE = (200, 50)
TMUX_SESSION = "agents"

# Claude readiness — empty `❯ ` prompt line (whitespace tolerated). Pre-
# compiled because await_completion polls this 2x/sec per agent.
_CLAUDE_EMPTY_PROMPT_RE = re.compile(r"^❯\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Structured results (M3 from EXP-05 codex cross-review)
#
# Before the review, `await_completion` returned a bare bool and the startup
# phase swallowed readiness failures as `logger.warning`. Syntropic137 needs
# to distinguish "timed out" / "never ready yet" / "agent errored" + reason.
# The `AwaitResult` shape mirrors `agentic_isolation.ExecuteResult` so an
# adapter (see `lib/python/agentic_isolation/.../interactive_tmux/`) can map
# 1-to-1 without a translation step.


@dataclass
class AwaitResult:
    """Result of waiting for an agent pane to reach a ready/idle state.

    The `ready` boolean is what existing call sites care about; the other
    fields exist so Syntropic137 (or any orchestrator) can distinguish
    failure modes that used to be invisible:

      - timed_out=True, ready=False         → deadline hit before idle
      - ready=False, reason="never_ready"   → never reached even one ready frame
      - ready=False, reason="unstable"      → ready frames seen but pane kept changing
      - ready=True                          → adapter is_ready() held stable

    `pane` carries the last captured pane text so callers don't have to
    re-capture to inspect post-mortem.
    """

    ready: bool
    timed_out: bool
    reason: str  # "ready" | "timeout_never_ready" | "timeout_unstable" | "error"
    duration_ms: float
    stable_polls_observed: int
    pane: str = ""
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.ready

    def to_dict(self) -> dict:
        return asdict(self)


class StartupReadinessError(RuntimeError):
    """Raised by `start_workspace(..., strict_startup=True)` (default) when
    one or more agent panes did not reach their per-adapter `is_ready()`
    state within `startup_timeout_s`.

    The attached `startup_status` is a {agent: AwaitResult} dict so callers
    can inspect which panes failed and why without re-running the workspace.
    """

    def __init__(self, startup_status: dict[str, AwaitResult]):
        failed = [a for a, r in startup_status.items() if not r.ready]
        super().__init__(
            f"start_workspace: per-agent readiness failed for {failed} "
            f"(see .startup_status for details)"
        )
        self.startup_status = startup_status


# ---------------------------------------------------------------------------
# tmux send-keys helpers (the only place that talks to docker exec tmux)


def _run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess; return CompletedProcess. Raises on non-zero unless
    `check=False`."""
    logger.debug("exec: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
    )


def _docker_exec(container: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return _run(["docker", "exec", container, *args], check=check)


def _tmux_send_keys(container: str, window: str, *keys: str) -> None:
    target = f"{TMUX_SESSION}:{window}"
    _docker_exec(container, "tmux", "send-keys", "-t", target, *keys)


def _tmux_send_literal(container: str, window: str, text: str) -> None:
    """Send `text` byte-for-byte (no special-key interpretation)."""
    target = f"{TMUX_SESSION}:{window}"
    _docker_exec(container, "tmux", "send-keys", "-t", target, "-l", text)


def _tmux_capture(container: str, window: str) -> str:
    target = f"{TMUX_SESSION}:{window}"
    return _docker_exec(container, "tmux", "capture-pane", "-p", "-t", target).stdout


# ---------------------------------------------------------------------------
# Per-agent adapters
#
# Each adapter is responsible for:
#   prepare_host_auth(src) -> Path | None  : produce a throwaway dir/file
#                                            for bind-mount; returns the
#                                            host path (or None to skip).
#   launch_in_window(container, window)    : tmux send-keys to start the CLI
#                                            and walk init gates
#   submit(container, window, text)        : encode the submit pattern
#   is_ready(pane_text) -> bool            : readiness heuristic
#
# The dispatcher (InteractiveTmuxWorkspace) calls these via the agent name.


@dataclass
class _AdapterContext:
    """What a per-agent adapter needs from the workspace at runtime."""

    container: str
    workdir: str  # container path (e.g., /workspace)
    host_throwaway_dir: Path  # per-workspace temp dir on the host


class _ClaudeAdapter:
    """Encodes EXP-01 friction findings.

    Auth surface: ~/.claude/ (directory, for .credentials.json) AND
    ~/.claude.json (file, for oauthAccount metadata + onboarding markers).
    See EXP-05's "Open contradiction" section for the empirical resolution
    of where the OAuth token lives, and EXP-05a for the full 2×2 mount
    matrix proving BOTH files are required.

    Synthetic ~/.claude.json policy (EXP-05 codex cross-review m1):
    -------------------------------------------------------------
    EXP-05a tested four mount combinations on the host (`none`, `.claude`
    only, `.claude.json` only, both). Only "both" yielded an authenticated
    start. This adapter, however, ALWAYS synthesizes ~/.claude.json in
    the container even when the host's ~/.claude.json is absent. The
    synthesized file carries onboarding-skip markers, the workspace's
    project-trust map, and (when available) the host's `oauthAccount`
    metadata copied through. Token material is never synthesized — only
    `~/.claude/.credentials.json` carries tokens, and it MUST exist on
    the host. Concretely:

      - host has `.claude/` + `.claude.json` → both copied; behaves
        identically to EXP-05a's "both" cell (authenticated start, no
        wizards).
      - host has `.claude/` only             → `.claude/.credentials.json`
        copied; `.claude.json` is SYNTHESIZED. This case is OUTSIDE
        EXP-05a's matrix; it works because the synthesized file supplies
        the onboarding/trust markers Claude expects, while the tokens
        come from `.credentials.json`. Functionally equivalent to "both"
        for this provider.
      - host has neither                     → `prepare_host_auth`
        raises (we never start a container that can't authenticate).

    Net: callers do not need to manage `.claude.json` themselves; this
    adapter's fallback is the recommended path. If a consumer wants to
    suppress synthesis and mount their own `.claude.json` byte-for-byte,
    they should call `host_auth["claude"] = …` with a directory that
    contains both `.credentials.json` AND a sibling `.claude.json` — but
    the synthesized file is the path EXP-05a's "both" outcome generalizes
    to inside this container image.
    """

    window = "claude"

    @staticmethod
    def prepare_host_auth(
        host_src: Path | None,
        ctx: _AdapterContext,
    ) -> dict[str, tuple[Path, str]]:
        """Return {mount_id: (host_path, container_path)} for the bind mounts.

        host_src is the path to the live `~/.claude` directory; the sibling
        `~/.claude.json` is auto-resolved at `{host_src.parent}/.claude.json`.
        Throwaway copies live under ctx.host_throwaway_dir.
        """
        if host_src is None:
            return {}
        if not host_src.is_dir():
            raise FileNotFoundError(f"claude auth dir not found: {host_src}")
        creds = host_src / ".credentials.json"
        if not creds.is_file():
            raise FileNotFoundError(
                f"claude .credentials.json missing under {host_src}; "
                "cannot mount Max-plan auth"
            )

        # Throwaway ~/.claude/ — copy .credentials.json only to avoid leaking
        # session history. Runtime claude will recreate cache/sessions/etc.
        dst_dir = ctx.host_throwaway_dir / "claude.dir"
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(creds, dst_dir / ".credentials.json")
        os.chmod(dst_dir / ".credentials.json", 0o600)
        # Ownership matches the in-container agent user (uid 1000).
        _chown_recursive(dst_dir, 1000, 1000)

        # Throwaway ~/.claude.json — pre-seeded with onboarding-skip markers,
        # the workspace project trust pre-accepted, and (if available) the
        # host's oauthAccount metadata copied through so "Welcome back" lands
        # cleanly instead of triggering a fresh-account flow.
        dotjson_src = host_src.parent / ".claude.json"
        dotjson_dst = ctx.host_throwaway_dir / "claude.json"
        seeded = _build_seeded_claude_dotjson(dotjson_src, ctx.workdir)
        dotjson_dst.write_text(json.dumps(seeded, indent=2))
        os.chmod(dotjson_dst, 0o600)
        _chown_path(dotjson_dst, 1000, 1000)

        return {
            "claude_dir": (dst_dir, "/home/agent/.claude"),
            "claude_dotjson": (dotjson_dst, "/home/agent/.claude.json"),
        }

    @staticmethod
    def launch_in_window(container: str, _workdir: str) -> None:
        _tmux_send_keys(container, _ClaudeAdapter.window, "claude", "Enter")

    @staticmethod
    def submit(container: str, text: str) -> None:
        # EXP-01: two-step is the documented default. -l makes the bytes
        # land literally (no special-key interpretation in the text body),
        # then a separate Enter dispatches.
        _tmux_send_literal(container, _ClaudeAdapter.window, text)
        _tmux_send_keys(container, _ClaudeAdapter.window, "Enter")

    @staticmethod
    def is_ready(pane_text: str) -> bool:
        # EXP-01 FRICTION F-5 three-signal heuristic for *post-turn* idle.
        # The codex cross-review flagged that the old code only checked 2
        # of the 3 codified signals despite the class docstring claiming
        # three; fixed here:
        #   1. `esc to interrupt` absent (no generation in progress)
        #   2. `? for shortcuts` present (steady-state TUI footer, not a modal)
        #   3. `^❯\s*$` matches somewhere in the capture (input box prompt
        #      line is empty — only the chevron, optional whitespace)
        # NOTE: this predicate is intentionally strict on the empty-prompt
        # signal so it can distinguish "just finished a turn" from "model
        # still rendering". The startup welcome screen shows the chevron
        # with a placeholder hint (e.g., `❯ Try "..."`), which fails this
        # check — that is why `is_started()` below has its own (looser)
        # predicate for the startup phase.
        return (
            "esc to interrupt" not in pane_text
            and "? for shortcuts" in pane_text
            and _CLAUDE_EMPTY_PROMPT_RE.search(pane_text) is not None
        )

    @staticmethod
    def is_started(pane_text: str) -> bool:
        # Startup-phase readiness: the TUI is past the splash/trust/login
        # gates and is willing to accept input, regardless of whether the
        # chevron line is empty or showing the placeholder hint. Used by
        # `_wait_for_started` during `start_workspace`; once the workspace
        # is running, `is_ready` is the predicate that matters per turn.
        return (
            "esc to interrupt" not in pane_text
            and "? for shortcuts" in pane_text
            and "❯" in pane_text
        )

    @staticmethod
    def response_marker() -> str:
        # Used by the smoke to distinguish the model's response from the
        # echoed prompt. The TUI prefixes the model's reply with a filled
        # bullet (U+25CF). Prompts use `❯`.
        return "● "


class _CodexAdapter:
    """Encodes EXP-02 friction findings.

    Submit gotcha: first user message often does not dispatch with bare
    C-m alone; reliable pattern is C-j C-m. After the first turn, the
    same pattern keeps working.

    Init gotchas: trust banner (numbered prompt) and hooks-review screen
    fire on every fresh container start.
    """

    window = "codex"

    @staticmethod
    def prepare_host_auth(
        host_src: Path | None,
        ctx: _AdapterContext,
    ) -> dict[str, tuple[Path, str]]:
        if host_src is None:
            return {}
        if not host_src.is_dir():
            raise FileNotFoundError(f"codex auth dir not found: {host_src}")
        dst_dir = ctx.host_throwaway_dir / "codex.dir"
        dst_dir.mkdir(parents=True, exist_ok=True)
        # Copy the .codex/ tree but skip the live tmp/ subdir — codex races
        # there (creates and deletes argv files during normal operation), so
        # copytree against it sees vanished files. The auth lives in
        # auth.json / config.toml / sessions/ at the top level.
        skip = {"tmp", "log", "logs"}
        for item in host_src.iterdir():
            if item.name in skip:
                continue
            target = dst_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True, ignore_dangling_symlinks=True)
            else:
                shutil.copy2(item, target)
        _chown_recursive(dst_dir, 1000, 1000)
        return {"codex_dir": (dst_dir, "/home/agent/.codex")}

    @staticmethod
    def launch_in_window(container: str, _workdir: str) -> None:
        # --no-alt-screen so capture-pane sees the same buffer the TUI uses.
        _tmux_send_keys(container, _CodexAdapter.window, "codex --no-alt-screen", "Enter")
        # Trust banner: select option 1 ("Yes, trust"), confirm with Enter.
        time.sleep(2)
        _tmux_send_keys(container, _CodexAdapter.window, "1", "Enter")
        # Hooks-review modal: close with Escape.
        time.sleep(1)
        _tmux_send_keys(container, _CodexAdapter.window, "Escape")
        time.sleep(1)

    @staticmethod
    def submit(container: str, text: str) -> None:
        # EXP-02: literal text first (so the body's bytes don't get
        # tmux-special-key-interpreted), then C-j C-m to dispatch.
        # C-j C-m is the gotcha — bare C-m alone often does not submit
        # the first message.
        _tmux_send_literal(container, _CodexAdapter.window, text)
        _tmux_send_keys(container, _CodexAdapter.window, "C-j", "C-m")

    @staticmethod
    def is_ready(pane_text: str) -> bool:
        # Codex marks generation with `• Working (...)`. Idle state shows
        # the input box marker `›` (U+203A) on a line by itself, plus the
        # footer suggestion line (the "Tip:" or "Write tests for @filename"
        # hint that codex shows once at idle). Two positive signals OR'd
        # together so a transient hint loss doesn't false-fail.
        if "• Working" in pane_text:
            return False
        return ("› " in pane_text) or ("Write tests for" in pane_text) or ("Tip:" in pane_text)

    @staticmethod
    def is_started(pane_text: str) -> bool:
        # Codex's idle markers already cover the startup case (post-trust,
        # post-hooks-review the TUI shows the input box + tip line).
        return _CodexAdapter.is_ready(pane_text)

    @staticmethod
    def response_marker() -> str:
        # Codex prefixes the model reply with U+2022 (bullet operator). The
        # prompt uses `›` so the two are distinguishable in capture.
        return "• "


class _GeminiAdapter:
    """Encodes EXP-03 friction findings.

    Submit gotcha: must use literal `Enter` keyword; `C-m` does not
    reliably dispatch through `docker exec tmux send-keys`.
    Init gotcha: must pre-patch ~/.gemini/settings.json with
      security.folderTrust.enabled = false
    or the trust modal blocks startup (the `--yolo` flag does NOT skip it).
    """

    window = "gemini"

    @staticmethod
    def prepare_host_auth(
        host_src: Path | None,
        ctx: _AdapterContext,
    ) -> dict[str, tuple[Path, str]]:
        if host_src is None:
            return {}
        if not host_src.is_dir():
            raise FileNotFoundError(f"gemini auth dir not found: {host_src}")
        dst_dir = ctx.host_throwaway_dir / "gemini.dir"
        dst_dir.mkdir(parents=True, exist_ok=True)
        for item in host_src.iterdir():
            target = dst_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
        # Patch settings.json with folderTrust.enabled=false (EXP-03 fix).
        settings_path = dst_dir / "settings.json"
        settings: dict = {}
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text())
            except json.JSONDecodeError:
                settings = {}
        security = settings.setdefault("security", {})
        folder_trust = security.setdefault("folderTrust", {})
        folder_trust["enabled"] = False
        settings_path.write_text(json.dumps(settings, indent=2))
        _chown_recursive(dst_dir, 1000, 1000)
        return {"gemini_dir": (dst_dir, "/home/agent/.gemini")}

    @staticmethod
    def launch_in_window(container: str, _workdir: str) -> None:
        _tmux_send_keys(container, _GeminiAdapter.window, "gemini", "Enter")
        time.sleep(1)

    @staticmethod
    def submit(container: str, text: str) -> None:
        # EXP-03: text first, then Enter — never C-m.
        _tmux_send_literal(container, _GeminiAdapter.window, text)
        _tmux_send_keys(container, _GeminiAdapter.window, "Enter")

    @staticmethod
    def is_ready(pane_text: str) -> bool:
        # EXP-03: idle = `Type your message` prompt indicator present AND
        # the model is not currently `Thinking...`. The bare presence-of
        # `Type your message` is NOT sufficient: the prompt-hint line stays
        # visible at the bottom of the pane even while the model is mid-
        # generation, so smoke runs were observed to false-pass on it. The
        # active-generation indicator `Thinking...` (or `esc to cancel`)
        # must also be absent.
        if "Thinking..." in pane_text or "esc to cancel" in pane_text:
            return False
        return "Type your message" in pane_text

    @staticmethod
    def is_started(pane_text: str) -> bool:
        # Gemini's idle marker `Type your message` is the same signal we
        # want at startup (no separate splash/auth gate that hides it).
        return _GeminiAdapter.is_ready(pane_text)

    @staticmethod
    def response_marker() -> str:
        # Gemini prefixes the model reply with a four-pointed star (U+2726).
        # The prompt indicator is `›` / `>` so the two are distinguishable.
        return "✦ "


_ADAPTERS = {
    "claude": _ClaudeAdapter,
    "codex": _CodexAdapter,
    "gemini": _GeminiAdapter,
}


# ---------------------------------------------------------------------------
# Helpers


def _chown_path(path: Path, uid: int, gid: int) -> None:
    try:
        os.chown(path, uid, gid)
    except PermissionError:
        # Non-fatal when running as non-root host user — docker will run as
        # the requested uid inside the container regardless. Worst case: the
        # in-container agent can't write to the mount. We warn; smoke will
        # surface this fast enough.
        logger.warning("chown %s to %s:%s failed (continuing)", path, uid, gid)


def _chown_recursive(path: Path, uid: int, gid: int) -> None:
    _chown_path(path, uid, gid)
    for sub in path.rglob("*"):
        _chown_path(sub, uid, gid)


def _build_seeded_claude_dotjson(host_dotjson: Path, workspace_path: str) -> dict:
    """Build the synthetic ~/.claude.json the container should see.

    Carries over the host's `oauthAccount` (so claude shows "Welcome back"
    instead of triggering a fresh-account flow) and forces the onboarding
    and per-workspace trust markers so the TUI lands on the prompt rather
    than a wizard or trust dialog.
    """
    base: dict = {}
    if host_dotjson.is_file():
        try:
            base = json.loads(host_dotjson.read_text())
        except json.JSONDecodeError:
            base = {}

    seeded = {
        "numStartups": int(base.get("numStartups", 5) or 5),
        "installMethod": "npm-global",
        "autoUpdates": False,
        "hasCompletedOnboarding": True,
        "theme": base.get("theme", "dark"),
    }
    # Carry oauthAccount through if present (account uuid/email/org) — this is
    # what makes claude say "Welcome back Neural" instead of running fresh.
    if "oauthAccount" in base:
        seeded["oauthAccount"] = base["oauthAccount"]

    # Pre-accept the workspace project. claude looks up `projects.<absolute
    # path>` keyed by the workspace dir.
    seeded["projects"] = {
        workspace_path: {
            "hasTrustDialogAccepted": True,
            "hasCompletedProjectOnboarding": True,
        }
    }
    return seeded


# ---------------------------------------------------------------------------
# The workspace


@dataclass
class InteractiveTmuxWorkspace:
    name: str
    container: str
    image: str
    workdir: str
    tmux_size: tuple[int, int]
    host_throwaway_dir: Path
    enabled_agents: tuple[str, ...]

    # M1 (codex cross-review): per-agent startup readiness status. Populated
    # by `_bootstrap_tmux_and_launch`; surfaced through the public attribute
    # `startup_status` for non-strict callers. With `strict_startup=True`
    # (the default), any per-agent failure raises `StartupReadinessError`
    # before this dict is observable, so the dict is always populated only
    # with successful AwaitResults in the strict path.
    startup_status: dict[str, AwaitResult] = field(default_factory=dict)

    # Internal: track per-agent first-send state for adapters that care
    # (e.g., Codex's first-send-needs-C-j-C-m can be relaxed after turn 1
    # in a future iteration; we keep C-j C-m always-on for now since it
    # works in both positions per EXP-02).
    _started: dict[str, bool] = field(default_factory=dict)

    # -----------------------------------------------------------------------
    # Lifecycle

    @classmethod
    def start_workspace(
        cls,
        name: str,
        host_auth: dict[str, Path | None] | None = None,
        image: str = DEFAULT_IMAGE,
        workdir: str = "/workspace",
        tmux_size: tuple[int, int] = DEFAULT_TMUX_SIZE,
        startup_timeout_s: float = 45.0,
        strict_startup: bool = True,
    ) -> InteractiveTmuxWorkspace:
        """Start a new interactive-tmux workspace.

        Args:
            name: workspace name (also used as a container name suffix).
            host_auth: per-agent host paths to live credential dirs / files.
                Keys: "claude" (path to ~/.claude), "codex" (~/.codex),
                "gemini" (~/.gemini). A value of None disables that agent's
                pane (it is not launched).
            image: docker image tag to run.
            workdir: container working directory (also keyed into claude's
                project-trust map).
            tmux_size: (cols, rows) for the tmux session. The default 200x50
                fixes EXP-01 FRICTION F-3 (default 80x24 truncates the TUI).
            startup_timeout_s: how long to wait per agent for its idle/ready
                state before giving up.
            strict_startup: if True (default), raise `StartupReadinessError`
                when any enabled agent fails to reach `is_ready()` within
                `startup_timeout_s`. If False, log a warning and return the
                workspace with per-agent results on `ws.startup_status` —
                callers can inspect status before `send_message`. EXP-05
                cross-review M1: bare success on a missed readiness gate is
                a footgun for orchestrators like Syntropic137. Strict is the
                safer default; lax is opt-in for callers who already check
                `ws.startup_status` themselves.

        Returns:
            InteractiveTmuxWorkspace. In both strict and lax modes,
            `ws.startup_status` is populated with per-agent `AwaitResult`s.

        Raises:
            StartupReadinessError: in strict mode, when any agent pane fails
                to reach its is_ready() state within `startup_timeout_s`.
        """
        host_auth = host_auth or {}
        container = f"interactive-tmux-{name}-{uuid.uuid4().hex[:8]}"
        host_throwaway_dir = Path(tempfile.mkdtemp(prefix=f"interactive-tmux-{name}-"))

        # Decide which agents are enabled (passed in host_auth) and prepare
        # their per-agent mounts.
        enabled: list[str] = []
        all_mounts: list[tuple[Path, str]] = []
        ctx = _AdapterContext(container=container, workdir=workdir, host_throwaway_dir=host_throwaway_dir)
        for agent in AGENTS:
            adapter = _ADAPTERS[agent]
            src = host_auth.get(agent)
            if src is None:
                continue
            mounts = adapter.prepare_host_auth(Path(src), ctx)
            if not mounts:
                continue
            enabled.append(agent)
            for _mount_id, pair in mounts.items():
                all_mounts.append(pair)

        if not enabled:
            shutil.rmtree(host_throwaway_dir, ignore_errors=True)
            raise ValueError("start_workspace called with no enabled agents (host_auth empty)")

        # Run the container with bind mounts (each mount is a -v arg).
        run_cmd = [
            "docker", "run", "-d",
            "--name", container,
            "--workdir", workdir,
        ]
        for host_path, container_path in all_mounts:
            run_cmd.extend(["-v", f"{host_path}:{container_path}"])
        run_cmd.extend([image, "sleep", "infinity"])
        _run(run_cmd)

        # Container is up; bootstrap tmux + one window per enabled agent.
        ws = cls(
            name=name,
            container=container,
            image=image,
            workdir=workdir,
            tmux_size=tmux_size,
            host_throwaway_dir=host_throwaway_dir,
            enabled_agents=tuple(enabled),
        )
        try:
            ws._bootstrap_tmux_and_launch(startup_timeout_s, strict_startup)
        except Exception:
            ws.stop()
            raise
        return ws

    def _bootstrap_tmux_and_launch(
        self,
        startup_timeout_s: float,
        strict_startup: bool,
    ) -> None:
        cols, rows = self.tmux_size
        first = self.enabled_agents[0]
        # Create the session with the first agent's window name.
        _docker_exec(
            self.container, "tmux", "new-session", "-d", "-s", TMUX_SESSION,
            "-n", first, "-x", str(cols), "-y", str(rows),
        )
        # Create additional windows for the rest.
        for agent in self.enabled_agents[1:]:
            _docker_exec(
                self.container, "tmux", "new-window", "-t", TMUX_SESSION,
                "-n", agent,
            )

        # Launch each agent's CLI in its window, then wait until each pane
        # reports `is_started()` (M1 cross-review fix). Each adapter
        # exposes a startup-phase predicate that recognizes its welcome
        # screen — for claude this differs from the strict post-turn
        # `is_ready` because the welcome pane shows a placeholder `Try …`
        # in the input box; for codex/gemini, is_started == is_ready. This
        # replaces the prior `_wait_for_text(expects_welcome_marker)` and
        # removes the codex `gpt-` substring flake EXP-06 documented as a
        # benign warning.
        for agent in self.enabled_agents:
            adapter = _ADAPTERS[agent]
            adapter.launch_in_window(self.container, self.workdir)
            self._started[agent] = True
            self.startup_status[agent] = self._wait_for_started(agent, startup_timeout_s)

        failed = {a: r for a, r in self.startup_status.items() if not r.ready}
        if failed:
            if strict_startup:
                raise StartupReadinessError(self.startup_status)
            logger.warning(
                "start_workspace: %d agent(s) not ready within %.1fs (strict_startup=False): %s",
                len(failed), startup_timeout_s, sorted(failed),
            )

    def _wait_for_started(self, agent: str, timeout_s: float) -> AwaitResult:
        """Block until `agent`'s pane reports `is_started()`, or timeout."""
        adapter = _ADAPTERS[agent]
        start = time.monotonic()
        deadline = start + timeout_s
        pane = ""
        while time.monotonic() < deadline:
            pane = _tmux_capture(self.container, adapter.window)
            if adapter.is_started(pane):
                duration_ms = (time.monotonic() - start) * 1000
                return AwaitResult(
                    ready=True,
                    timed_out=False,
                    reason="ready",
                    duration_ms=duration_ms,
                    stable_polls_observed=1,
                    pane=pane,
                )
            time.sleep(0.5)
        duration_ms = (time.monotonic() - start) * 1000
        logger.warning(
            "wait_for_started(%s) timed out after %.1fs",
            agent, timeout_s,
        )
        return AwaitResult(
            ready=False,
            timed_out=True,
            reason="timeout_never_ready",
            duration_ms=duration_ms,
            stable_polls_observed=0,
            pane=pane,
        )

    # -----------------------------------------------------------------------
    # The five public primitives

    def send_message(self, agent: AgentName, text: str) -> None:
        """Submit `text` to `agent`'s tmux pane using the per-agent submit pattern."""
        self._check_agent(agent)
        _ADAPTERS[agent].submit(self.container, text)

    def await_completion(
        self,
        agent: AgentName,
        timeout: float = 60.0,
        stable_polls: int = 4,
        poll_interval: float = 0.5,
        warmup: float = 2.0,
    ) -> AwaitResult:
        """Block until `agent` returns to a stable ready state, or `timeout` passes.

        EXP-05 codex cross-review M3: returns an `AwaitResult` mirroring
        `agentic_isolation.ExecuteResult` (`timed_out`/`reason`/`duration_ms`)
        so orchestrators can distinguish failure modes. Existing call sites
        that only need a boolean should use `result.ready`.

        Two layered checks make this robust against transient redraw
        frames that single-poll heuristics get fooled by:

        1. The adapter's per-agent `is_ready(pane)` heuristic must return
           True (these are the per-agent matrix predicates).
        2. The pane content must be **identical** across `stable_polls`
           consecutive observations separated by `poll_interval` seconds.

        Codex specifically motivates check (2): its `• Working (Ns ...)`
        timer updates each second, and tmux capture occasionally catches
        a frame between updates where `Working` is briefly absent — a
        naive `is_ready` poll then false-passes. Requiring content
        identity across N captures filters those transients out
        (a still-rendering TUI doesn't produce identical captures).

        `warmup` skips the pre-generation window (the small gap between
        `send_message` and the agent rendering its generation marker)
        so the first ready observation isn't a stale idle frame.

        Returns an `AwaitResult`:
            - `.ready=True, .reason="ready"` when a stable ready state was
               reached;
            - `.ready=False, .timed_out=True, .reason="timeout_unstable"`
               when readiness was observed but never held stable;
            - `.ready=False, .timed_out=True, .reason="timeout_never_ready"`
               when readiness was never observed before deadline.
        """
        self._check_agent(agent)
        adapter = _ADAPTERS[agent]
        start = time.monotonic()
        deadline = start + timeout
        time.sleep(warmup)
        last_pane: str | None = None
        consecutive_stable_ready = 0
        ever_ready = False
        pane = ""
        while time.monotonic() < deadline:
            pane = _tmux_capture(self.container, adapter.window)
            if adapter.is_ready(pane):
                ever_ready = True
                if pane == last_pane:
                    consecutive_stable_ready += 1
                    if consecutive_stable_ready >= stable_polls:
                        duration_ms = (time.monotonic() - start) * 1000
                        return AwaitResult(
                            ready=True,
                            timed_out=False,
                            reason="ready",
                            duration_ms=duration_ms,
                            stable_polls_observed=consecutive_stable_ready,
                            pane=pane,
                        )
                else:
                    consecutive_stable_ready = 0
            else:
                consecutive_stable_ready = 0
            last_pane = pane
            time.sleep(poll_interval)
        duration_ms = (time.monotonic() - start) * 1000
        reason = "timeout_unstable" if ever_ready else "timeout_never_ready"
        logger.warning(
            "await_completion(%s) timed out after %.1fs (stable_ready=%d, reason=%s)",
            agent, timeout, consecutive_stable_ready, reason,
        )
        return AwaitResult(
            ready=False,
            timed_out=True,
            reason=reason,
            duration_ms=duration_ms,
            stable_polls_observed=consecutive_stable_ready,
            pane=pane,
        )

    def capture_response(self, agent: AgentName) -> str:
        """Return the current contents of `agent`'s tmux pane."""
        self._check_agent(agent)
        return _tmux_capture(self.container, _ADAPTERS[agent].window)

    def stop(self) -> None:
        """Tear down the container and remove throwaway credential copies."""
        subprocess.run(
            ["docker", "rm", "-f", self.container],
            check=False,
            capture_output=True,
        )
        shutil.rmtree(self.host_throwaway_dir, ignore_errors=True)

    # -----------------------------------------------------------------------
    # Helpers

    def _check_agent(self, agent: str) -> None:
        if agent not in self.enabled_agents:
            raise ValueError(
                f"agent {agent!r} not enabled for workspace {self.name!r} "
                f"(enabled: {self.enabled_agents})"
            )


# ---------------------------------------------------------------------------
# CLI (for shell-script consumers — e.g., scripts/smoke.sh)


def _default_host_auth_from_env() -> dict[str, Path | None]:
    """Build a host_auth dict from $HOME defaults; missing dirs are dropped."""
    home = Path(os.path.expanduser("~"))
    candidates = {
        "claude": home / ".claude",
        "codex": home / ".codex",
        "gemini": home / ".gemini",
    }
    return {a: p if p.is_dir() else None for a, p in candidates.items()}


_WORKSPACE_REGISTRY_DIR = Path(tempfile.gettempdir()) / "interactive-tmux-workspaces"


def _save_workspace(ws: InteractiveTmuxWorkspace) -> None:
    _WORKSPACE_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": ws.name,
        "container": ws.container,
        "image": ws.image,
        "workdir": ws.workdir,
        "tmux_size": list(ws.tmux_size),
        "host_throwaway_dir": str(ws.host_throwaway_dir),
        "enabled_agents": list(ws.enabled_agents),
    }
    (_WORKSPACE_REGISTRY_DIR / f"{ws.name}.json").write_text(json.dumps(payload, indent=2))


def _load_workspace(name: str) -> InteractiveTmuxWorkspace:
    path = _WORKSPACE_REGISTRY_DIR / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"no registered workspace {name!r} at {path}")
    p = json.loads(path.read_text())
    return InteractiveTmuxWorkspace(
        name=p["name"],
        container=p["container"],
        image=p["image"],
        workdir=p["workdir"],
        tmux_size=tuple(p["tmux_size"]),  # type: ignore[arg-type]
        host_throwaway_dir=Path(p["host_throwaway_dir"]),
        enabled_agents=tuple(p["enabled_agents"]),
    )


def _forget_workspace(name: str) -> None:
    path = _WORKSPACE_REGISTRY_DIR / f"{name}.json"
    if path.exists():
        path.unlink()


def _cli() -> int:
    parser = argparse.ArgumentParser(prog="interactive_tmux")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s_start = sub.add_parser("start", help="start a workspace")
    s_start.add_argument("--name", required=True)
    s_start.add_argument("--image", default=DEFAULT_IMAGE)
    s_start.add_argument("--workdir", default="/workspace")
    s_start.add_argument(
        "--agents",
        default="claude,codex,gemini",
        help="comma-separated list of agents to enable (default: all three)",
    )
    s_start.add_argument(
        "--strict-startup",
        action="store_true",
        help="raise on any agent's startup readiness miss (default: lax — print "
             "structured per-agent status in the JSON output and exit non-zero "
             "only if no agent is ready)",
    )

    s_send = sub.add_parser("send", help="send a message to an agent")
    s_send.add_argument("--name", required=True)
    s_send.add_argument("--agent", required=True, choices=AGENTS)
    s_send.add_argument("--text", required=True)

    s_await = sub.add_parser("await", help="block until agent is ready or timeout")
    s_await.add_argument("--name", required=True)
    s_await.add_argument("--agent", required=True, choices=AGENTS)
    s_await.add_argument("--timeout", type=float, default=60.0)

    s_cap = sub.add_parser("capture", help="print captured pane contents")
    s_cap.add_argument("--name", required=True)
    s_cap.add_argument("--agent", required=True, choices=AGENTS)

    s_stop = sub.add_parser("stop", help="stop a workspace")
    s_stop.add_argument("--name", required=True)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.cmd == "start":
        host_auth_all = _default_host_auth_from_env()
        wanted = set(args.agents.split(","))
        host_auth = {a: (host_auth_all[a] if a in wanted else None) for a in AGENTS}
        try:
            ws = InteractiveTmuxWorkspace.start_workspace(
                name=args.name,
                host_auth=host_auth,
                image=args.image,
                workdir=args.workdir,
                strict_startup=args.strict_startup,
            )
        except StartupReadinessError as exc:
            # M1: surface per-agent failure structurally instead of an
            # opaque non-zero exit. The CLI exit code is 3 (distinct from
            # 2 = await timeout) so smoke harnesses can tell them apart.
            print(json.dumps({
                "error": "startup_readiness",
                "startup_status": {a: r.to_dict() for a, r in exc.startup_status.items()},
            }))
            return 3
        _save_workspace(ws)
        print(json.dumps({
            "name": ws.name,
            "container": ws.container,
            "agents": list(ws.enabled_agents),
            "startup_status": {a: r.to_dict() for a, r in ws.startup_status.items()},
        }))
        # Exit non-zero only if NO agent reached ready — preserves the
        # historical "smoke continues to pass on benign per-agent misses"
        # behavior while exposing the structured status that the codex
        # cross-review (M1) called out as missing.
        all_failed = ws.startup_status and not any(r.ready for r in ws.startup_status.values())
        return 0 if not all_failed else 3

    if args.cmd == "send":
        ws = _load_workspace(args.name)
        ws.send_message(args.agent, args.text)
        return 0

    if args.cmd == "await":
        ws = _load_workspace(args.name)
        result = ws.await_completion(args.agent, timeout=args.timeout)
        # M3: emit the full structured result, not just `{"ready": bool}`.
        # Exit code stays bool-compatible so existing shells don't break.
        print(json.dumps({k: v for k, v in result.to_dict().items() if k != "pane"}))
        return 0 if result.ready else 2

    if args.cmd == "capture":
        ws = _load_workspace(args.name)
        sys.stdout.write(ws.capture_response(args.agent))
        return 0

    if args.cmd == "stop":
        try:
            ws = _load_workspace(args.name)
        except FileNotFoundError:
            return 0
        ws.stop()
        _forget_workspace(args.name)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(_cli())
