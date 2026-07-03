"""Regression tests for the full-scrollback capture + tail-based readiness.

Covers the two stress blockers from Syntropic137's stress run
(syntropic137 repo, `origin/exp/interactive-tmux-stress`,
`experiments/stress/STRESS-REPORT.md`):

- D-block-3: `tmux capture-pane` shipped without `-S - -E -`, so the
  visible 50-row window was returned instead of the full scrollback —
  long multi-paragraph replies got silently truncated (1834 chars
  captured vs 5716 actual).
- D-block-2: `is_ready` ran against the truncated visible pane, so when
  the response overflowed the window the idle sentinel scrolled away and
  the predicate took the full 240s timeout (16x waste). With the
  scrollback fix, the predicate now needs to evaluate against the tail
  of the captured pane, not the whole history, or older `esc to
  interrupt` text from prior generations would keep flipping it false.

Tests run against synthetic fixtures (no docker) — they verify the
driver's pure-Python helpers and per-agent predicates, not the tmux
shell-out.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_driver_module():
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = (
            ancestor
            / "providers"
            / "workspaces"
            / "interactive-tmux"
            / "driver"
            / "interactive_tmux.py"
        )
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("interactive_tmux", candidate)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules.setdefault("interactive_tmux", module)
            spec.loader.exec_module(module)
            return module
    pytest.skip("interactive_tmux driver not found in repo layout")


driver = _load_driver_module()


def _build_pane(
    history_substring: str,
    history_lines: int,
    idle_tail: list[str],
) -> str:
    """Build a pane buffer with EXACT line accounting.

    Each line is non-empty so `"\\n".join(lines).splitlines()` round-trips
    the list — that lets the test reason precisely about which lines fall
    inside the n_lines tail vs which sit in history.

    `history_lines` rows of filler each containing `history_substring`
    (a marker like "esc to interrupt" or "Thinking...") precede the
    `idle_tail` lines that should match a per-agent predicate.
    """
    filler = [f"  history-{i} {history_substring} END" for i in range(history_lines)]
    return "\n".join(filler + idle_tail)


def _claude_idle_tail(n: int = 50) -> list[str]:
    """Return `n` lines of a Claude post-turn idle pane.

    Order: a few divider/filler rows, the empty chevron line `❯ ` (must
    match `^❯\\s*$`), more filler, and the `? for shortcuts` footer.
    All "empty" rows are filled with a non-confusable filler so they
    don't trigger the absence checks and don't get stripped by
    `splitlines` semantics around trailing newlines.
    """
    lines: list[str] = []
    lines.extend(["  visible-filler-A"] * (n // 2 - 2))
    lines.append("❯ ")
    lines.append("─" * 80)
    lines.append("  ? for shortcuts")
    lines.extend(["  visible-filler-B"] * (n - len(lines)))
    return lines


def _codex_idle_tail(n: int = 50) -> list[str]:
    """Codex idle: no `• Working`, plus `› ` or `Write tests for` or `Tip:`."""
    lines: list[str] = []
    lines.extend(["  visible-filler-A"] * (n - 4))
    lines.append("› ")
    lines.append("  Tip: drive the model with /commands")
    lines.append("  visible-filler-B")
    lines.append("  visible-filler-C")
    return lines


def _gemini_idle_tail(n: int = 50) -> list[str]:
    """Gemini idle: `Type your message` present, no `Thinking...`/`esc to cancel`."""
    lines: list[str] = []
    lines.extend(["  visible-filler-A"] * (n - 3))
    lines.append(" >   Type your message or @path/to/file")
    lines.append("  visible-filler-B")
    lines.append("  visible-filler-C")
    return lines


class TestPaneTail:
    """`_pane_tail` returns the bottom N lines verbatim."""

    def test_short_pane_returned_as_is(self) -> None:
        pane = "line0\nline1\nline2\n"
        assert driver._pane_tail(pane, n_lines=50) == pane

    def test_long_pane_truncated_to_last_n_lines(self) -> None:
        pane = "\n".join(f"row{i}" for i in range(200))
        tail = driver._pane_tail(pane, n_lines=50)
        lines = tail.splitlines()
        assert len(lines) == 50
        assert lines[0] == "row150"
        assert lines[-1] == "row199"

    def test_empty_pane_yields_empty(self) -> None:
        assert driver._pane_tail("", n_lines=50) == ""

    def test_default_window_matches_pane_height(self) -> None:
        # Default n_lines = DEFAULT_TMUX_SIZE[1] = 50.
        assert driver._pane_tail.__defaults__[0] == driver.DEFAULT_TMUX_SIZE[1]


class TestClaudeReadinessAgainstTail:
    """Claude predicate evaluated against the tail of a long capture."""

    def test_full_buffer_with_stale_generation_breaks_predicate(self) -> None:
        """Sanity check: WITHOUT the tail fix (predicate over full buffer),
        an old `esc to interrupt` in history flips Claude's is_ready False.
        Documents D-block-2's failure mode before the fix."""
        full = _build_pane(
            history_substring="esc to interrupt",
            history_lines=200,
            idle_tail=_claude_idle_tail(),
        )
        assert not driver._ClaudeAdapter.is_ready(full), (
            "predicate over the whole scrollback should see stale "
            "`esc to interrupt` and return False"
        )

    def test_tail_correctly_reports_ready_on_multi_paragraph_history(self) -> None:
        """D-block-2 fix: tail is the visible window's worth of rows;
        the stale `esc to interrupt` in history doesn't reach it, and
        the live idle markers in the bottom rows do — predicate returns
        True."""
        full = _build_pane(
            history_substring="esc to interrupt",
            history_lines=200,
            idle_tail=_claude_idle_tail(),
        )
        tail = driver._pane_tail(full, n_lines=driver.DEFAULT_TMUX_SIZE[1])
        assert driver._ClaudeAdapter.is_ready(tail), (
            f"tail (last 50 lines) should match idle predicate; tail "
            f"starts with: {tail.splitlines()[0][:80]!r}"
        )

    def test_full_pane_taller_than_one_screen(self) -> None:
        """Stress reality check: 5716-actual / 1834-captured ratio from
        STRESS-REPORT.md corresponds to a pane ~3x the visible height.
        Predicate over the full buffer should never accidentally pass;
        predicate over the tail should still find idle markers."""
        full = _build_pane(
            history_substring="esc to interrupt + filler text",
            history_lines=300,  # ~3x the 50-row visible window
            idle_tail=_claude_idle_tail(),
        )
        assert not driver._ClaudeAdapter.is_ready(full)
        tail = driver._pane_tail(full, n_lines=driver.DEFAULT_TMUX_SIZE[1])
        assert driver._ClaudeAdapter.is_ready(tail)


class TestCodexReadinessAgainstTail:
    """Codex's `• Working` absent + idle marker present, against the tail."""

    def test_codex_full_buffer_with_stale_working_breaks_predicate(self) -> None:
        full = _build_pane(
            history_substring="• Working (esc to interrupt)",
            history_lines=200,
            idle_tail=_codex_idle_tail(),
        )
        assert not driver._CodexAdapter.is_ready(full), (
            "predicate over the whole scrollback should see stale `• Working` and return False"
        )

    def test_codex_tail_correctly_reports_ready(self) -> None:
        full = _build_pane(
            history_substring="• Working (esc to interrupt)",
            history_lines=200,
            idle_tail=_codex_idle_tail(),
        )
        tail = driver._pane_tail(full, n_lines=driver.DEFAULT_TMUX_SIZE[1])
        assert driver._CodexAdapter.is_ready(tail)


class TestGeminiReadinessAgainstTail:
    """Gemini's `Thinking...` absent + `Type your message` present, on tail."""

    def test_gemini_tail_correctly_reports_ready(self) -> None:
        full = _build_pane(
            history_substring="Thinking... esc to cancel",
            history_lines=200,
            idle_tail=_gemini_idle_tail(),
        )
        # Whole-buffer predicate fooled by historical `Thinking...`.
        assert not driver._GeminiAdapter.is_ready(full)
        # Tail predicate sees the live idle state correctly.
        tail = driver._pane_tail(full, n_lines=driver.DEFAULT_TMUX_SIZE[1])
        assert driver._GeminiAdapter.is_ready(tail)


class TestCaptureResponseReturnsFullBuffer:
    """`capture_response` returns the FULL scrollback (the `-S - -E -`
    side of the fix), so smoke harnesses grepping for tokens that
    overflowed the visible window still find them.

    Verified by patching `_tmux_capture` to return a known long buffer and
    asserting `capture_response` returns it byte-equal (no truncation).
    """

    def test_capture_response_byte_equal_to_capture(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        long_buffer = "\n".join(f"row{i} TOKEN-A" for i in range(500))
        monkeypatch.setattr(
            driver,
            "_tmux_capture",
            lambda container, window, **kwargs: long_buffer,  # type: ignore[arg-type]
        )

        ws = driver.InteractiveTmuxWorkspace(
            name="test",
            container="test-container",
            image="test-image",
            workdir="/workspace",
            tmux_size=(200, 50),
            host_throwaway_dir=Path("/tmp/test-throwaway"),
            enabled_agents=("claude",),
        )

        result = ws.capture_response("claude")
        assert result == long_buffer
        # Sanity: result has WAY more than one pane-height of rows.
        assert len(result.splitlines()) == 500
