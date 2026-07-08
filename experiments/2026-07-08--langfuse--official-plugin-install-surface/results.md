# Results

## Headline

| Probe | Evidence | Result |
|---|---|---|
| Official reference snapshot | `runs/official-reference-snapshot.md` | Current Claude and Codex plugin install/config contracts captured from official LangFuse sources. |
| Repo setup-surface audit | `runs/repo-setup-surface-audit.md` | Found doc drift only; no exporter code change needed. |
| Noise-control verification | `runs/cli-exporters-test.txt`, `runs/cli-exporters-test-exit.txt` | Passed: 5 focused CLI exporter tests, including suppression/force/Syntropic exporter cases. |
| Whitespace check | `runs/diff-check.txt`, `runs/diff-check-exit.txt` | Passed: `git diff --check` exit 0. |
| Secret-safety scan | `runs/secret-scan.txt`, `runs/secret-scan-exit.txt` | Exit 0. Hits are placeholder examples (`sk-lf-...`) and Keychain export syntax, not real keys. |

## Observations

The architecture prediction was correct. The repo already encoded the main
boundary:

- official LangFuse plugins are canonical for rich Claude/Codex traces;
- JSONL fanout is safe to run in parallel;
- `syntropic_jsonl` serves Syntropic137's HookWatcher shape separately;
- fallback Rust OTLP is suppressed when `TRACE_TO_LANGFUSE=true` unless forced.

The setup-surface drift prediction was also correct. The docs needed alignment
on:

- Claude plugin config being managed by Claude Code's plugin install/configure
  flow, not by the same runtime env block used for fallback OTLP;
- Claude plugin requirements: `uv` or Python 3.10+ with `langfuse>=4.0,<5`;
- Claude optional `CC_LANGFUSE_*` controls;
- Codex requirement for Node.js 22+ and plugin-hook-capable Codex;
- Codex JSON config precedence and `LANGFUSE_CODEX_*` overrides.

## Treatment

Patched:

- `docs/guides/langfuse-observability-setup.md`
- `plugins/observability/README.md`

No Rust code was changed.

## Remaining Evidence Gap

This run improves install/config correctness and protects the noise-control
boundary, but it does not prove a real interactive marketplace-installed
Claude or Codex session writes a new trace into the target LangFuse backend.
That remains a separate .9 close gate.
