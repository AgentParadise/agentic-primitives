# Verdict

**Go for CLI-level LangFuse setup; no-go for claiming real backend
ingestion.**

The local setup path is now direct enough for a new machine: configure
`LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and
`LANGFUSE_TRACING_ENVIRONMENT`, then pass `--observability-langfuse` to
`itmux run` or `itmux codex-exec`. `--langfuse-project-id` or
`LANGFUSE_PROJECT_ID` adds trace links, but is not required for export.

| Hypothesis | Observation | Verdict | Evidence |
| --- | --- | --- | --- |
| `itmux run` exposes LangFuse setup flags | Help includes all four flags | correct | `runs/run-help.txt` |
| `itmux codex-exec` exposes the same flags | Help includes all four flags | correct | `runs/codex-exec-help.txt` |
| CLI maps flags to typed exporter config with env-only secrets | Unit tests assert `LangFuseOtlp` config and env refs | correct | `runs/cli-exporter-tests.txt` |
| Project id remains optional | Unit tests assert no project id is required | correct | `runs/cli-exporter-tests.txt` |

## Next Decision

- Keep `.9` open until real LangFuse ingestion and trace discoverability are
  proven.
- The real smoke can now use the CLI path directly instead of requiring a
  hand-written `AgentRunSpec`.
