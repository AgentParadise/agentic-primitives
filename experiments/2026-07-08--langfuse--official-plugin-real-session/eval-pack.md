# Eval Pack

## Frozen Probes

1. **Preflight**
   - Record:
     - `git status --short`
     - `scripts/langfuse-local.sh status`
     - `claude --version`
     - `claude plugin list`
     - `codex --version`
     - `codex plugin list`
     - `node --version`, `uv --version`, `python3 --version`
   - Record redacted local LangFuse project config from
     `.agentic/langfuse/langfuse/.env`.

2. **Claude official plugin session**
   - Add/update the official Claude marketplace if needed.
   - Install/configure `langfuse-observability@langfuse-observability` in the
     narrowest feasible scope.
   - Run one real Claude Code prompt that requests an exact marker.
   - Query local LangFuse for traces after the run and identify a trace that
     contains the marker or corresponding session metadata.

3. **Codex official plugin session**
   - Add/update the official Codex marketplace if needed.
   - Install/enable `tracing@codex-observability-plugin` in the narrowest
     feasible config scope.
   - Run one real Codex prompt with `TRACE_TO_LANGFUSE=true` and local
     LangFuse credentials.
   - Query local LangFuse for traces after the run and identify a trace that
     contains the marker or corresponding session metadata.

4. **Noise audit**
   - Confirm no `itmux --observability-langfuse` or
     `--observability-langfuse-force` command was required to create the
     official-plugin traces.
   - If any fallback exporter is used for comparison, store it in a separate
     explicitly labeled run artifact.

5. **Verification**
   - Run focused `cli_exporters` tests to keep the suppression contract green.
   - Run a secret scan over this experiment's committed artifacts and changed
     docs/config examples.

## Success Criteria

- Both Claude and Codex official marketplace-plugin paths produce queryable
  traces in local LangFuse from real sessions.
- Trace summaries show root IO and semantic generation/tool observations.
- Codex includes usage/cost when available.
- No fallback Rust OTLP rich trace is required or accidentally paired with the
  same run.

## Inconclusive Criteria

- A plugin install command is unavailable or fails because the marketplace
  format changed.
- A harness auth problem prevents running a real session.
- Local LangFuse is unavailable.
- A plugin writes traces but the current query tooling cannot identify them
  confidently.
