# Verdict

**Inconclusive for Claude hook observability; go for file fanout.**

The experiment validates the reusable file exporter slice but does not validate
Claude hook-derived observability. The blocker is not the file fanout path; it is
the harness environment: Claude launches but returns `API Error: 401` before the
plugin can produce meaningful lifecycle/tool evidence.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Plugin-loaded Claude run emits session and tool lifecycle events | Only driver-level phase events observed; no hook-derived events proven | wrong | `runs/treatment-result.json` shows plugin dir launch but also Claude 401. |
| File exporter mirrors normalized stdout events without breaking stdout JSONL | 11 stdout events and 11 exported events in both probes | correct | See `runs/summary.json`. |
| Final result reports `status = "ok"`, `events_exported >= 3`, and `file://` link | Status/count correct; relative path produced relative link | partial | Use absolute paths when a `file://` link is required. |

## Design Impact

- `.6` should keep file fanout as the first backend-independent exporter.
- `.6` cannot be closed on Claude observability until credential transfer/auth
  is made healthy and a plugin hook event is observed.
- Acceptance tests should explicitly cover relative vs absolute exporter link
  behavior.
