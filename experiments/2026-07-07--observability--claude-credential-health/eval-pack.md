# Eval Pack

## Probe A: Host Claude Auth

Run host Claude non-interactively:

```bash
claude -p "Reply exactly: CLAUDE_HOST_AUTH_OK"
```

Capture stdout, stderr, and exit code.

## Probe B: Container Credential Shape

Run a Claude-only workspace:

```bash
itmux start --name <unique> --agents claude --strict-startup true
```

Then inspect, without printing secrets:

- `/home/agent/.claude/.credentials.json`
- `/home/agent/.claude.json`

Capture only key names, primitive types, string lengths, and booleans. Stop the
workspace after inspection.

## Probe C: Recipe-Driven Claude Run

Run a minimal Claude recipe through `itmux run` with the file exporter enabled.

Capture:

- stdout JSONL
- exporter JSONL
- result JSON
- exit code

## Scoring

Pass requires classifying the 401 source:

- host auth invalid
- staging shape missing credential material
- recipe-driven run path fails despite valid host and staged shape
- no repro
