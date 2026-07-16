# Experiment: Codex Token/Cost Surface

## Question

Does the interactive-tmux Codex harness expose enough hook, log, transcript, or
session data to normalize token/cost observability with parity to Claude?

## No Hypothesis: Mapping Probe

This is a mapping probe. The Codex observability surface is not known well enough
to make a falsifiable token/cost prediction yet. The output should identify the
available data sources and whether a follow-up implementation experiment is
ready.

## Setup

- Branch: `feat/observability-exporter-primitive`
- Bead: `okrs-51p.6`
- Harness: Codex inside `interactive-tmux`
- Exporter under test: file JSONL for normalized run events

## Conditions

- Run a simple Codex task through `itmux run`.
- Inspect staged auth/log/session directories that are safe to read.
- Capture pane transcript and any Codex-owned log files produced during the run.

## Expected Signals

- `runs/codex-stdout.jsonl`
- `runs/codex-events.jsonl`
- `runs/codex-result.json`
- `runs/codex-files.txt` listing relevant generated files
- `results.md` mapping table of data source, fields, and usability

## Out of Scope

- Implementing Codex token/cost parser.
- Sending Codex data to LangFuse.
- Reading or storing secrets.
