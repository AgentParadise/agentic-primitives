#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Replay one existing Claude transcript through the official LangFuse hook.

The official hook is incremental: it records an offset and a turn counter for
one growing JSONL file.  Historical transcripts are already complete, so this
tool creates a private append-only replay copy and invokes the hook after a
bounded number of source turns.  It never synthesizes transcript rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


STATE_ROOT = Path.home() / ".local/state/agentic-primitives/langfuse-claude-backfill"


def is_tool_result(row: dict[str, Any]) -> bool:
    content = row.get("message", {}).get("content")
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for block in content
    )


def is_turn_start(row: dict[str, Any]) -> bool:
    """Match the official hook's user-turn semantics, excluding tool results."""
    return row.get("type") == "user" and not row.get("isMeta") and not is_tool_result(row)


def load_rows(source: Path) -> list[tuple[dict[str, Any], bytes]]:
    rows: list[tuple[dict[str, Any], bytes]] = []
    with source.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at {source}:{line_number}: {error}") from error
            if isinstance(row, dict):
                rows.append((row, raw if raw.endswith(b"\n") else raw + b"\n"))
    return rows


def session_id_for(rows: Iterable[tuple[dict[str, Any], bytes]]) -> str:
    for row, _ in rows:
        value = row.get("sessionId")
        if isinstance(value, str) and value:
            return value
    raise ValueError("source transcript has no sessionId")


@dataclass(frozen=True)
class Chunk:
    index: int
    first_turn: int
    last_turn: int
    rows: list[bytes]


def chunks(rows: list[tuple[dict[str, Any], bytes]], chunk_turns: int) -> list[Chunk]:
    """Split raw rows at user-turn starts while keeping every row verbatim."""
    starts = [index for index, (row, _) in enumerate(rows) if is_turn_start(row)]
    if not starts:
        raise ValueError("source transcript has no complete Claude user turns")

    out: list[Chunk] = []
    prefix_end = starts[0]
    for chunk_index, first in enumerate(range(0, len(starts), chunk_turns), start=1):
        last = min(first + chunk_turns, len(starts))
        row_start = starts[first]
        row_end = starts[last] if last < len(starts) else len(rows)
        selected = [raw for _, raw in rows[row_start:row_end]]
        if chunk_index == 1 and prefix_end:
            selected = [raw for _, raw in rows[:prefix_end]] + selected
        out.append(Chunk(chunk_index, first + 1, last, selected))
    return out


def find_hook() -> Path:
    cache_root = Path.home() / ".claude/plugins/cache/langfuse-observability/langfuse-observability"
    hooks = sorted(cache_root.glob("*/hooks/langfuse_hook.py"))
    if not hooks:
        raise FileNotFoundError("official Claude LangFuse plugin hook is not installed")
    return hooks[-1]


def config_from_codex() -> dict[str, str]:
    config_path = Path.home() / ".codex/langfuse.json"
    if not config_path.exists():
        return {}
    value = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        return {}
    result = {
        "LANGFUSE_BASE_URL": str(value.get("base_url") or ""),
        "LANGFUSE_PUBLIC_KEY": str(value.get("public_key") or ""),
        "LANGFUSE_SECRET_KEY": str(value.get("secret_key") or ""),
        "LANGFUSE_USER_ID": str(value.get("user_id") or ""),
        "LANGFUSE_TRACING_ENVIRONMENT": str(value.get("environment") or ""),
    }
    tags = value.get("tags")
    host_tag = next((tag for tag in tags or [] if isinstance(tag, str) and tag.startswith("host:")), "")
    result["CC_LANGFUSE_TAGS"] = f"harness:claude{',' + host_tag if host_tag else ''}"
    return result


def write_manifest(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    path.chmod(0o600)


def run_hook(hook: Path, replay: Path, session_id: str, environment: dict[str, str]) -> None:
    payload = json.dumps({
        "hook_event_name": "SessionEnd",
        "session_id": session_id,
        "transcript_path": str(replay),
    })
    process = subprocess.run(
        ["uv", "run", "--quiet", "--script", str(hook)],
        input=payload,
        text=True,
        env=environment,
        capture_output=True,
        check=False,
    )
    if process.returncode:
        raise RuntimeError(process.stderr.strip() or process.stdout.strip() or "official hook failed")


def hook_turn_count(hook_home: Path, session_id: str, replay: Path) -> int:
    state_file = hook_home / ".claude/state/langfuse_state.json"
    if not state_file.exists():
        return 0
    state = json.loads(state_file.read_text(encoding="utf-8"))
    key = hashlib.sha256(f"{session_id}::{replay}".encode()).hexdigest()
    value = state.get(key, {})
    return int(value.get("turn_count", 0)) if isinstance(value, dict) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="existing Claude JSONL transcript")
    parser.add_argument("--chunk-turns", type=int, default=10, help="source turns per hook invocation (default: 10)")
    parser.add_argument("--max-turns", type=int, default=100, help="maximum source turns to submit; 0 is unlimited")
    parser.add_argument("--apply", action="store_true", help="submit the replay; preview is the default")
    parser.add_argument("--reset-replay", action="store_true", help="discard this tool's replay state before starting")
    args = parser.parse_args()
    if args.chunk_turns < 1 or args.max_turns < 0:
        parser.error("--chunk-turns must be positive and --max-turns must be non-negative")
    source = args.source.expanduser().resolve()
    if not source.is_file():
        parser.error(f"source does not exist: {source}")

    rows = load_rows(source)
    session_id = session_id_for(rows)
    turn_starts = [index for index, (row, _) in enumerate(rows) if is_turn_start(row)]
    source_turns = len(turn_starts)
    # Stop at the next source-turn boundary so a capped replay never appends
    # rows from an unselected turn. This is deliberately based on raw rows,
    # not a reconstructed representation of the conversation.
    limited_rows = rows
    if args.max_turns and args.max_turns < source_turns:
        limited_rows = rows[:turn_starts[args.max_turns]]
    selected = chunks(limited_rows, args.chunk_turns)

    replay_id = hashlib.sha256(f"{session_id}::{source}".encode()).hexdigest()[:16]
    replay_root = STATE_ROOT / replay_id
    replay = replay_root / "transcript.jsonl"
    hook_home = replay_root / "hook-home"
    manifest = replay_root / "manifest.jsonl"
    if args.reset_replay:
        if replay_root.exists():
            shutil.rmtree(replay_root)
    print(f"source={source}")
    print(f"session_id={session_id}")
    print(f"source_turns={source_turns} selected_turns={selected[-1].last_turn if selected else 0}")
    print(f"chunks={len(selected)} replay_state={replay_root}")
    for chunk in selected:
        print(f"  chunk={chunk.index} turns={chunk.first_turn}-{chunk.last_turn} rows={len(chunk.rows)}")
    if not args.apply:
        print("preview only; pass --apply to invoke the official Claude LangFuse hook")
        return 0

    hook = find_hook()
    config = config_from_codex()
    environment = os.environ.copy()
    environment.update({key: value for key, value in config.items() if value and not environment.get(key)})
    missing = [key for key in ("LANGFUSE_BASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY") if not environment.get(key)]
    if missing:
        raise RuntimeError(f"missing LangFuse configuration: {', '.join(missing)}")
    environment["HOME"] = str(hook_home)
    environment["CC_LANGFUSE_DEBUG"] = environment.get("CC_LANGFUSE_DEBUG", "false")
    replay_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    hook_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    completed = 0
    if replay.exists():
        # Resume only from an explicit manifest checkpoint; never infer delivery.
        if manifest.exists():
            for line in manifest.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                if entry.get("status") in {"submitted", "recovered"}:
                    completed = max(completed, int(entry["chunk"]))
        else:
            # A process can finish the official hook after this wrapper has
            # been interrupted. The official state is the only safe recovery
            # signal: recover only whole, already-emitted chunks.
            emitted_turns = hook_turn_count(hook_home, session_id, replay)
            full_chunks = [chunk for chunk in selected if chunk.last_turn <= emitted_turns]
            if emitted_turns and full_chunks:
                completed = full_chunks[-1].index
                write_manifest(manifest, {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "status": "recovered",
                    "source_path": str(source),
                    "session_id": session_id,
                    "chunk": completed,
                    "turn_range": [full_chunks[-1].first_turn, full_chunks[-1].last_turn],
                    "replay_path": str(replay),
                    "reason": "official_hook_state",
                })
            else:
                raise RuntimeError(f"replay exists without a recoverable manifest: {replay}; use --reset-replay after review")
    for chunk in selected:
        if chunk.index <= completed:
            continue
        with replay.open("ab") as handle:
            handle.writelines(chunk.rows)
        before = hook_turn_count(hook_home, session_id, replay)
        run_hook(hook, replay, session_id, environment)
        after = hook_turn_count(hook_home, session_id, replay)
        if after < before:
            raise RuntimeError("official hook turn counter moved backwards")
        write_manifest(manifest, {
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "submitted",
            "source_path": str(source),
            "session_id": session_id,
            "chunk": chunk.index,
            "turn_range": [chunk.first_turn, chunk.last_turn],
            "replay_path": str(replay),
        })
        print(f"submitted chunk {chunk.index} ({chunk.first_turn}-{chunk.last_turn})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
