# Results

## Probe A: Baseline

Captured under `runs/baseline-*`.

Codex official plugin status before remediation:

```json
{
  "command_present": true,
  "node22_plus": true,
  "plugin_hooks_enabled": false,
  "tracing_plugin_configured": true,
  "config": {
    "plugin_hooks_found": false,
    "tracing_plugin_found": true,
    "ready": false
  }
}
```

Focused config excerpt showed the tracing plugin enabled and `[features]`
present, but no `plugin_hooks = true`.

## Probe B: Remediation

Applied the minimal user config change in `~/.codex/config.toml`:

```toml
[features]
js_repl = false
plugin_hooks = true
```

No LangFuse credentials were added.

## Probe C: Treatment Doctor

Captured under `runs/treatment-*`.

Codex official plugin status after remediation:

```json
{
  "command_present": true,
  "node22_plus": true,
  "plugin_hooks_enabled": true,
  "tracing_plugin_configured": true,
  "config": {
    "plugin_hooks_found": true,
    "tracing_plugin_found": true,
    "ready": true
  }
}
```

The text-mode doctor also reports:

```text
Codex plugin_hooks: true
Codex tracing plugin configured: true
```

The bare shell still reports missing `LANGFUSE_*` and `TRACE_TO_LANGFUSE`,
which is expected for this probe. This experiment only validates Codex hook
activation in the user config.

## Probe D: Hygiene

- `git diff --check`: exit 0
- secret scan for raw LangFuse keys under `runs/`: exit 1, no matches
- repo status: only the pre-existing untracked `docs/handoffs/` and this
  experiment's run artifacts
