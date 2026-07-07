# Eval Pack

## Probe A: Codex Run Artifact Capture

Run a minimal Codex recipe through `itmux run` with the file exporter enabled.

Capture:

- stdout JSONL
- exporter JSONL
- result JSON
- final session log

## Probe B: Codex Surface Inventory

Inside the workspace or staged host auth copy, inventory non-secret Codex files
that may contain session/log/transcript data.

Rules:

- Do not print or store auth tokens.
- Redact any credential-like field before writing evidence.
- Prefer filenames, schema snippets, and field names over full raw content.

## Scoring

This mapping probe passes if it produces a clear table:

| Source | Contains lifecycle? | Contains tool events? | Contains token/cost? | Parser viable? |
|---|---|---|---|---|

It should end with a recommendation for the first Codex observer implementation.
