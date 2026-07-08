# Eval Pack

## Frozen Probes

1. **Official reference snapshot**
   - Capture the current official Claude and Codex install/config requirements
     into `runs/official-reference-snapshot.md`.
   - Record source URLs and the specific commands/settings that matter.

2. **Repo setup-surface audit**
   - Inspect `docs/guides/langfuse-observability-setup.md`,
     `plugins/observability/README.md`, ADR-038, and relevant CLI help.
   - Record matches, drift, and missing cautions in
     `runs/repo-setup-surface-audit.md`.

3. **Noise-control verification**
   - Run the focused Rust CLI tests that cover `TRACE_TO_LANGFUSE`,
     `--observability-langfuse-force`, and `--observability-syntropic-file`.
   - Store output in `runs/cli-exporters-test.txt` and exit status in
     `runs/cli-exporters-test-exit.txt`.

4. **Secret-safety scan**
   - Scan changed docs and experiment artifacts for real-looking LangFuse
     keys.
   - Store output in `runs/secret-scan.txt` and exit status in
     `runs/secret-scan-exit.txt`.

## Success Criteria

- Claude setup references the current marketplace plugin install/config path.
- Codex setup references plugin hooks, plugin enablement, opt-in tracing, and
  config/env precedence accurately enough for a fresh install.
- Docs separate official plugin env needs from fallback Rust OTLP env needs.
- CLI tests still prove the fallback OTLP writer is suppressed when official
  plugin tracing is active.

## Invalidating Evidence

- Official docs contradict the architecture pivot.
- The CLI suppression behavior no longer passes focused tests.
- Updating docs would require exporter implementation changes to avoid
  duplicate LangFuse traces.
