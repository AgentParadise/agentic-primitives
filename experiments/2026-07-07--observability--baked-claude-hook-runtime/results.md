# Results

| Probe | Evidence | Result |
|---|---|---|
| Temporary image build | `runs/docker-build-exit.txt`, `runs/docker-build-stderr.txt` | Passed: build exited 0 and produced `itmux-obs-runtime-test:20260707`. |
| Direct hook handler runtime | `runs/manual-hook-exit.txt`, `runs/manual-hook-stdout.txt`, `runs/manual-hook-stderr.jsonl` | Passed: handler exited 0, stdout was empty, stderr contained one valid JSONL event with `event_type = session_started`. |
| Claude plugin runtime through `itmux run` | `runs/stdout.jsonl`, `runs/events.jsonl`, `runs/result.json`, `runs/summary.json` | Passed for auth/launch: exit 0, result success true, session contained `BAKED_HOOK_RUNTIME_OK`, no 401, and launch contained `claude --plugin-dir /opt/agentic/plugins/observability`. |
| Hook capture classification | `runs/stdout.jsonl`, `runs/events.jsonl`, `runs/stderr.txt`, `runs/result.json`, `runs/summary.json` | No hook `event_type` appeared in stdout, exporter, stderr, or session log. |

## Key Data

| Field | Value |
|---|---|
| Docker build exit | 0 |
| Direct handler event type | `session_started` |
| Direct handler stdout bytes | 0 |
| `itmux run` exit | 0 |
| Result success | true |
| Session contains expected response | true |
| Session contains baked plugin launch | true |
| Stdout event lines | 11 |
| Exporter event lines | 11 |
| Hook `event_type` seen in stdout/exporter/stderr/session | false / false / false / false |

## Classification

Packaging `plugins/observability` and `agentic_events` into the image is enough
for the handler to emit hook JSONL directly. It is not enough for `itmux run`
to observe those hooks from the Claude TUI.

The architecture needs an explicit hook sink/capture path, such as a
container-side JSONL file written by the hook handler and collected by the
driver, before `.6` can claim Claude hook observability.
