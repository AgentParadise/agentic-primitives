"""Run a delegate with durable intent, native binding and its own exit status.

Parent identity comes from the harness hook or native shell environment. Shell
text is never scanned to decide whether delegation happened.
"""

from __future__ import annotations

import argparse
import os
import selectors
import signal
import sqlite3
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from agentic_session_store.child_hook import InvocationEnv, _identity, _parse
from agentic_session_store.child_journal import ChildCall, ChildJournal
from agentic_session_store.contract import METADATA_NAMESPACE, SessionStoreContract

MAX_LINE_BYTES = 1024 * 1024
RECORD_ERRORS = (ValueError, TypeError, OSError, sqlite3.Error)


def launch_context(
    target: str, environment: Mapping[str, str]
) -> tuple[ChildJournal, ChildCall]:
    contract = SessionStoreContract.from_env(environment)
    if contract is None:
        raise ValueError("Durable delegation requires session capture")
    harness = environment.get("AGENTIC_PARENT_HARNESS")
    parent = environment.get("AGENTIC_PARENT_NATIVE_ID")
    if harness is None and parent is None:
        # Codex supplies this for shell execution. Never infer parentage from a process list or command text.
        harness, parent = "codex", environment.get("CODEX_THREAD_ID")
    call = ChildCall(
        invocation_id=_identity(environment.get(InvocationEnv.INVOCATION_ID)),
        attempt_id=_identity(environment.get(InvocationEnv.ATTEMPT_ID)),
        harness=_identity(harness),
        parent_native_id=_identity(parent),
        tool_call_id=str(uuid4()),
        target_harness=target,
    )
    journal = ChildJournal(
        Path(contract.spool)
        / METADATA_NAMESPACE
        / contract.partition
        / "children.sqlite"
    )
    journal.register(call)
    return journal, call


def native_identity(line: bytes, harness: str) -> str | None:
    try:
        event = _parse(line)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return None
    if harness == "codex" and event.get("type") == "thread.started":
        return _identity(event.get("thread_id"))
    if (
        harness == "claude"
        and event.get("type") == "system"
        and event.get("subtype") == "init"
        and event.get("parent_tool_use_id") is None
    ):
        return _identity(event.get("session_id"))
    return None


def _record(action, *args) -> None:
    try:
        action(*args)
    except RECORD_ERRORS:
        print(
            "Delegate capture record failed; retained intent requires recovery.",
            file=sys.stderr,
        )


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def _bind_line(line: bytes, journal: ChildJournal, call: ChildCall) -> None:
    if len(line) > MAX_LINE_BYTES:
        print("Delegate capture frame exceeded its byte limit.", file=sys.stderr)
        return
    try:
        native = native_identity(line, call.target_harness or call.harness)
        if native is not None:
            _record(journal.bind, call, native)
    except RECORD_ERRORS:
        print("Delegate emitted an invalid native identity.", file=sys.stderr)


def _stream(
    process: subprocess.Popen, journal: ChildJournal, call: ChildCall, timeout: float
) -> int:
    deadline = time.monotonic() + timeout
    pending = b""
    discard = False
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate(process)
                return process.returncode
            if not selector.select(min(remaining, 1)):
                continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                if pending and not discard:
                    _bind_line(pending, journal, call)
                break
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            frames = (pending + chunk).split(b"\n")
            pending = frames.pop()
            for line in frames:
                if not discard:
                    _bind_line(line, journal, call)
                discard = False
            if len(pending) > MAX_LINE_BYTES:
                pending = b""
                discard = True
                print(
                    "Delegate capture frame exceeded its byte limit.", file=sys.stderr
                )
    remaining = deadline - time.monotonic()
    try:
        return process.wait(timeout=max(0, remaining))
    except subprocess.TimeoutExpired:
        _terminate(process)
        return process.returncode


def run(
    command: list[str], journal: ChildJournal, call: ChildCall, timeout: float
) -> int:
    environment = dict(os.environ)
    for key in (
        "AGENTIC_PARENT_HARNESS",
        "AGENTIC_PARENT_NATIVE_ID",
        "CODEX_THREAD_ID",
        "CLAUDECODE",
    ):
        environment.pop(key, None)
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            start_new_session=True,
            env=environment,
        )
    except OSError:
        _record(journal.launch_failed, call)
        print("Delegate process could not start.", file=sys.stderr)
        return 127
    _record(journal.launched, call)
    previous = {}

    def cancel(signum, _frame):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass
        _terminate(process)

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.signal(signum, cancel)
    try:
        code = _stream(process, journal, call, timeout)
    finally:
        _terminate(process)
        process.stdout.close()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        _record(journal.finished, call, process.returncode)
    return code if code >= 0 else 128 - code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("harness", choices=("claude", "codex"))
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    if not 0 < args.timeout <= 86400:
        parser.error("timeout must be between zero and one day")
    try:
        journal, call = launch_context(args.harness, os.environ)
    except RECORD_ERRORS:
        print(
            "Delegate launch denied: durable parent context or storage unavailable.",
            file=sys.stderr,
        )
        return 70
    command = (
        ["codex", "exec", "--json", "--skip-git-repo-check"]
        if args.harness == "codex"
        else ["claude", "-p", "--output-format", "stream-json", "--verbose"]
    )
    if args.model:
        command.extend(["--model", args.model])
    command.append(args.prompt)
    return run(command, journal, call, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
