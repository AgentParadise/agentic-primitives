# Results

## Headline

| Probe | Evidence | Result |
|---|---|---|
| Baseline readiness | `runs/baseline-doctor.json`, `runs/baseline-doctor-summary.json` | Passed: doctor reported Codex config ready after `plugin_hooks = true`. |
| Baseline trace discovery | `runs/baseline-codex-traces.json`, `runs/baseline-traces-summary.json` | Passed: latest pre-run Codex trace was `b3d2561d7c0557c12fd427c02a16e2f3`. |
| Fresh Codex exec run | `runs/codex-output.jsonl`, `runs/codex-exit.txt`, `runs/marker.txt` | Passed as a Codex run: exit 0, command tool executed, marker returned. |
| Automatic official-plugin export | `runs/treatment-codex-traces-final.json`, `runs/long-poll-latest.tsv`, `runs/fresh-rollout-sidecar-ls.txt` | Failed: after a longer poll, no new Codex trace appeared and no `.langfuse` sidecar existed next to the fresh rollout. |
| Direct official-plugin diagnostic | `runs/manual-hook-stderr.txt`, `runs/manual-hook-sidecar.txt`, `runs/manual-hook-trace-summary.json` | Passed: invoking the official plugin bundle directly against the fresh rollout uploaded trace `b928a86e0c44784896a2224778c339c4` with rich generation/tool/usage/cost data. |
| Hygiene | `runs/secret-scan.txt`, `runs/fallback-flag-scan.txt`, `runs/diff-check.txt` | Passed: no raw LangFuse key matches, no fallback exporter flags, and no whitespace errors. |

## Baseline

The doctor reported:

```json
{
  "codex_ready": true
}
```

The latest pre-run Codex trace was:

```text
b3d2561d7c0557c12fd427c02a16e2f3
```

## Fresh Codex Run

Marker:

```text
CODEX_OFFICIAL_HOOKS_READY_1783542866
```

`codex exec --json --sandbox read-only` exited 0 and produced:

- thread id `019f4370-6474-74a3-825b-2c70d782f3a5`
- one `exec_command` call printing the marker
- final answer exactly equal to the marker
- usage: 33,869 input tokens, 81 output tokens, 33,950 total tokens

## Automatic Hook Result

The recent Codex trace list remained stuck on the older official trace for all
poll attempts:

```text
b3d2561d7c0557c12fd427c02a16e2f3  Codex Turn
```

The fresh rollout file existed and contained the marker, but no sidecar was
created automatically:

```text
missing sidecar: ...rollout-2026-07-08T13-34-27-019f4370-6474-74a3-825b-2c70d782f3a5.jsonl.langfuse
```

This means static Codex readiness plus a successful `codex exec` process did
not prove automatic official-plugin Stop-hook export.

## Direct Official-Plugin Diagnostic

Running the official plugin bundle directly with the same environment and a
Stop hook payload for the fresh rollout exited 0 and wrote the sidecar:

```text
019f4370-6507-7812-b77f-9278d7f53151
```

The uploaded trace was:

```text
b928a86e0c44784896a2224778c339c4
```

`itmux langfuse-trace --api legacy-trace --output summary` reported:

```json
{
  "trace_id": "b928a86e0c44784896a2224778c339c4",
  "name": "Codex Turn",
  "session_id": "019f4370-6474-74a3-825b-2c70d782f3a5",
  "observations": ["AGENT", "GENERATION", "TOOL"],
  "models": ["gpt-5.5"],
  "usage": {
    "input_tokens": 33869,
    "output_tokens": 81,
    "total_tokens": 33950
  },
  "cost": {
    "calculated_total_usd": 0.171775
  },
  "agent_tools": {
    "names": ["exec_command"]
  }
}
```

So the plugin, credentials, rollout parser, LangFuse backend, and trace query
path are good. The missing piece is automatic Stop-hook invocation for this
non-interactive `codex exec` run.
