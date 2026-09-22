"""Read retained child changes without initializing or modifying their journal."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from agentic_session_store.child_journal import ChildJournal, ChildPage


@dataclass(frozen=True)
class ExportPage:
    schema_version: int
    page: ChildPage


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
            asdict(ExportPage(1, page)), ensure_ascii=True, separators=(",", ":")
        )
    except (ValueError, OSError, sqlite3.Error):
        print("Child-session journal unavailable or invalid.", file=sys.stderr)
        return 1
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
