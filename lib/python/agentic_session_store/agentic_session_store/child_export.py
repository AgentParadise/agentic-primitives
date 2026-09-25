"""Read retained child changes without initializing or modifying their journal."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

from agentic_session_store.child_journal import ChildJournal, ChildPage


def export_page(page: ChildPage) -> dict[str, object]:
    """Keep v1 native records byte-compatible; v2 adds delegation lifecycle."""
    body = asdict(page)
    version = 1
    for change in body["changes"]:
        intent = change["intent"]
        for owner, names in (
            (intent, ("status", "exit_code", "reason")),
            (intent["call"], ("target_harness",)),
        ):
            for name in names:
                if owner[name] is None:
                    del owner[name]
                else:
                    version = 2
    return {"schema_version": version, "page": body}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path)
    parser.add_argument("--after", type=int, default=0)
    parser.add_argument("--watermark", type=int)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    try:
        journal = ChildJournal(args.journal, read_only=True)
        page = journal.page(args.after, watermark=args.watermark, limit=args.limit)
        payload = json.dumps(
            export_page(page), ensure_ascii=True, separators=(",", ":")
        )
    except (ValueError, OSError, sqlite3.Error):
        print("Child-session journal unavailable or invalid.", file=sys.stderr)
        return 1
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
