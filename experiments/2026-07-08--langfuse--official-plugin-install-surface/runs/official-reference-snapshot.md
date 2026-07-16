# Official Reference Snapshot

Captured after hypothesis commit `0542332`.

## Claude Code

Source artifacts:

- <https://github.com/langfuse/Claude-Observability-Plugin>
- <https://langfuse.com/integrations/developer-tools/claude-code>

Current install/config contract:

```bash
claude plugin marketplace add langfuse/Claude-Observability-Plugin
claude plugin install langfuse-observability@langfuse-observability
```

Then restart Claude Code and configure from Claude Code:

```text
/plugin configure langfuse-observability@langfuse-observability
```

Alternative install-time config:

```bash
claude plugin install langfuse-observability@langfuse-observability \
  --config LANGFUSE_PUBLIC_KEY=pk-lf-... \
  --config LANGFUSE_SECRET_KEY=sk-lf-... \
  --config LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

Requirements and knobs from the upstream README:

- `uv` on `PATH`, or Python 3.10+ with `langfuse>=4.0,<5`.
- Required/accepted config: `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`,
  `LANGFUSE_BASE_URL`, `LANGFUSE_USER_ID`, `CC_LANGFUSE_DEBUG`,
  `CC_LANGFUSE_MAX_CHARS`, `CC_LANGFUSE_SKILL_TAGS`,
  `CC_LANGFUSE_CAPTURE_SKILL_CONTENT`.

## Codex

Source artifacts:

- <https://github.com/langfuse/codex-observability-plugin>
- <https://langfuse.com/integrations/developer-tools/codex>

Current install/config contract:

```bash
codex plugin marketplace add langfuse/codex-observability-plugin
```

Enable plugin hooks and the tracing plugin:

```toml
[features]
plugin_hooks = true

[plugins."tracing@codex-observability-plugin"]
enabled = true
```

Enable tracing with env:

```bash
export TRACE_TO_LANGFUSE="true"
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_SECRET_KEY="sk-lf-..."
export LANGFUSE_BASE_URL="https://cloud.langfuse.com"
```

Requirements and knobs from the upstream README:

- Node.js >= 22.
- Config can come from `~/.codex/langfuse.json`,
  `<project>/.codex/langfuse.json`, or env.
- Precedence: defaults, global JSON, project JSON, environment variables.
- `LANGFUSE_CODEX_*` overrides matching standard `LANGFUSE_*` values.
- Notable optional values: `LANGFUSE_CODEX_ENVIRONMENT`,
  `LANGFUSE_CODEX_USER_ID`, `LANGFUSE_CODEX_TAGS`,
  `LANGFUSE_CODEX_METADATA`, `LANGFUSE_CODEX_MAX_CHARS`,
  `LANGFUSE_CODEX_DEBUG`, `LANGFUSE_CODEX_FAIL_ON_ERROR`.

## Noise-Control Implication

Both official plugins use `TRACE_TO_LANGFUSE=true` as the user/operator signal
that canonical rich tracing is active. The agentic-primitives fallback OTLP
writer should continue using that signal to suppress duplicate LangFuse export
unless `--observability-langfuse-force` is supplied.
