"""Shell guard for native child capture hooks, so the recorder cannot fail open.

Both pinned harnesses run a hook command through a POSIX shell (Claude Code
2.1.281: ``/bin/sh -c``; Codex 0.156.1: ``$SHELL -lc``, default ``/bin/sh``).
Both treat a hook that cannot start, exits with a status other than 2, or
exceeds its timeout as a non-blocking failure: the tool call proceeds. A bare
``python3 -m ...`` command therefore lets a child launch with no durable intent
whenever the interpreter is missing, cannot import this package, crashes, or
hangs past the harness timeout.

The guard keeps every such failure inside the shell it controls:

* the recorder's own exit status is mapped, so only an exit of 0 passes and
  every other outcome (127 for a missing interpreter, 1 for an import error,
  137 for a killed process) becomes the configured failure status;
* a watchdog kills the recorder after ``WATCHDOG_SECONDS``, well inside
  ``HARNESS_TIMEOUT_SECONDS``, so the guard, not the harness, decides the
  outcome of a hang. The recorder also enforces its own, shorter deadline;
* recorder output is discarded and one fixed message is written, so no payload,
  path or database error text reaches the model.

The watchdog only fires when ``sleep`` succeeds, so a missing ``sleep`` leaves
the recorder's own deadline in charge instead of denying every launch.
"""

from __future__ import annotations

from enum import StrEnum

HARNESS_TIMEOUT_SECONDS = 30
WATCHDOG_SECONDS = 20
RECORDER_DEADLINE_SECONDS = 15
FAILURE_MESSAGE = "Durable child-session recording failed."
# Exit 2 is the blocking status in both pinned harnesses (PreToolUse deny).
DENY_STATUS = 2
# Any other nonzero status is reported but never blocks, continues or rewrites.
REPORT_STATUS = 1


class HookHarness(StrEnum):
    CLAUDE = "claude"
    CODEX = "codex"


def guarded_command(
    harness: HookHarness, *, deny: bool, watchdog: int = WATCHDOG_SECONDS
) -> str:
    """Return the installed hook command for one harness.

    ``deny`` is only for PreToolUse. Post-tool, failure and stop hooks must not
    use the blocking status: after a launch it would hide the running child's
    result from the parent (Codex PostToolUse) or force a stopping subagent to
    continue (SubagentStop).
    """
    if not 0 < watchdog < HARNESS_TIMEOUT_SECONDS:
        raise ValueError("Watchdog must fire before the harness timeout")
    status = DENY_STATUS if deny else REPORT_STATUS
    # An asynchronous list reads /dev/null unless stdin is redirected
    # explicitly, so the hook payload is passed through descriptor 3.
    return (
        "exec 3<&0; "
        f"python3 -m agentic_session_store.child_hook --harness {harness.value} "
        "<&3 3<&- >/dev/null 2>&1 & p=$!; exec 3<&-; "
        f"(sleep {watchdog} && kill -9 $p) </dev/null >/dev/null 2>&1 & w=$!; "
        "wait $p 2>/dev/null; s=$?; kill $w 2>/dev/null; "
        f"[ $s -eq 0 ] && exit 0; echo '{FAILURE_MESSAGE}' >&2; exit {status}"
    )


# Commands written by agentic-session-store <= 0.4.0. Installation replaces a
# matcher group that carries one of these in place instead of adding a second.
LEGACY_COMMANDS = frozenset({"python3 -m agentic_session_store.child_hook"})
