#!/usr/bin/env python3
"""
Generic observability handler — dispatches ALL Claude Code hook events.

Reads hook_event_name from stdin JSON and calls the appropriate
agentic_events emitter method. Pure logging — never blocks (exit 0 always).

Events are emitted as JSONL to stdout, captured by the workflow engine's stream reader.
Hook stdout is captured alongside Claude's stream-json output; parse_jsonl_line()
distinguishes hook events (have "event_type") from Claude's native events (have "type").
"""

import json
import os
import sys

# === EVENT EMITTER (lazy initialized) ===
_emitter = None


def _get_emitter(session_id: str | None = None):
    """Get event emitter, creating if needed."""
    global _emitter
    if _emitter is not None:
        return _emitter

    try:
        from agentic_events import EventEmitter

        _emitter = EventEmitter(
            session_id=session_id or os.getenv("CLAUDE_SESSION_ID", "unknown"),
            provider="claude",
            output=sys.stderr,
        )
        return _emitter
    except ImportError:
        return None


# === DISPATCH TABLE ===

def _handle_session_start(emitter, event):
    emitter.session_started(
        source=event.get("matcher", "startup"),
        transcript_path=event.get("transcript_path"),
        cwd=event.get("cwd"),
        permission_mode=event.get("permission_mode"),
    )


def _handle_session_end(emitter, event):
    emitter.session_completed(
        reason=event.get("reason", "normal"),
        duration_ms=event.get("duration_ms"),
    )


def _handle_user_prompt_submit(emitter, event):
    emitter.prompt_submitted(
        prompt_preview=event.get("prompt_preview", event.get("message", ""))[:200],
    )


def _handle_pre_tool_use(emitter, event):
    emitter.tool_started(
        tool_name=event.get("tool_name", "unknown"),
        tool_use_id=event.get("tool_use_id", ""),
        input_preview=str(event.get("tool_input", ""))[:500],
    )
    # Git-specific events come from real git hooks (post-commit, pre-push, etc.)
    # which fire after git operations complete and emit richer metadata (SHA,
    # branch, files_changed, etc.). Claude Code tool calls are recorded as
    # plain tool_started/tool_completed events — no git inference here.


def _handle_post_tool_use(emitter, event):
    emitter.tool_completed(
        tool_name=event.get("tool_name", "unknown"),
        tool_use_id=event.get("tool_use_id", ""),
        success=True,
        output_preview=str(event.get("tool_result", ""))[:500],
    )


def _handle_post_tool_use_failure(emitter, event):
    emitter.tool_failed(
        tool_name=event.get("tool_name", "unknown"),
        tool_use_id=event.get("tool_use_id", ""),
        error=event.get("error", ""),
    )


def _handle_permission_request(emitter, event):
    emitter.permission_requested(
        tool_name=event.get("tool_name", "unknown"),
        permission_type=event.get("permission_type", "unknown"),
    )


def _handle_notification(emitter, event):
    emitter.notification(
        message=event.get("message", ""),
        level=event.get("level", "info"),
    )


def _handle_subagent_start(emitter, event):
    emitter.subagent_started(
        subagent_id=event.get("subagent_id", "unknown"),
        agent_type=event.get("agent_type", "subagent"),
    )


def _handle_subagent_stop(emitter, event):
    emitter.subagent_stopped(
        subagent_id=event.get("subagent_id", "unknown"),
        reason=event.get("reason", "normal"),
    )


def _handle_stop(emitter, event):
    emitter.agent_stopped(
        reason=event.get("reason", "normal"),
    )


def _handle_teammate_idle(emitter, event):
    emitter.teammate_idle(
        teammate_id=event.get("teammate_id", "unknown"),
    )


def _handle_task_completed(emitter, event):
    emitter.task_completed(
        task_id=event.get("task_id", "unknown"),
    )


def _handle_pre_compact(emitter, event):
    emitter.context_compacted(
        before_tokens=event.get("before_tokens", 0),
        after_tokens=event.get("after_tokens", 0),
    )


DISPATCH = {
    "SessionStart": _handle_session_start,
    "SessionEnd": _handle_session_end,
    "UserPromptSubmit": _handle_user_prompt_submit,
    "PreToolUse": _handle_pre_tool_use,
    "PostToolUse": _handle_post_tool_use,
    "PostToolUseFailure": _handle_post_tool_use_failure,
    "PermissionRequest": _handle_permission_request,
    "Notification": _handle_notification,
    "SubagentStart": _handle_subagent_start,
    "SubagentStop": _handle_subagent_stop,
    "Stop": _handle_stop,
    "TeammateIdle": _handle_teammate_idle,
    "TaskCompleted": _handle_task_completed,
    "PreCompact": _handle_pre_compact,
}


def main() -> None:
    """Main entry point."""
    try:
        input_data = ""
        if not sys.stdin.isatty():
            input_data = sys.stdin.read()

        if not input_data:
            return

        event = json.loads(input_data)
        hook_event = event.get("hook_event_name", "")
        session_id = event.get("session_id")

        emitter = _get_emitter(session_id)
        if not emitter:
            return

        handler = DISPATCH.get(hook_event)
        if handler:
            handler(emitter, event)

    except Exception:
        pass  # Silent fail — observability never blocks


if __name__ == "__main__":
    main()
