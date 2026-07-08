# Official Codex Plugin Trace Contract

Source: `/tmp/langfuse-codex-plugin`
Commit: `6882ab7e117409265e233124ec2008fed8fc227c`

## Evidence

- `plugins/tracing/hooks/hooks.json` registers a Codex `Stop` hook.
- `src/index.ts` reads the hook payload, requires `TRACE_TO_LANGFUSE` and
  credentials, and converts `hookInput.transcript_path`.
- `src/parse.ts` reconstructs a session from rollout JSONL into turns, model
  steps, tool calls, subagent thread ids, final output, usage, and aborted
  status.
- `src/trace.ts` creates root `Codex Turn` observations with `asType: "agent"`,
  root `input`, root `output`, metadata, and backdated `startTime`.
- `src/trace.ts` creates one `asType: "generation"` observation per model step,
  with input, output, model, `usageDetails`, metadata, and backdated timing.
- `src/trace.ts` creates one `asType: "tool"` observation per tool call, named
  from the actual tool name, with tool args as input, result as output,
  error/status fields, and start/end timing.
- `src/trace.ts` nests subagent rollouts below the spawning turn root.
- `src/sidecar.ts` records uploaded completed turn ids in
  `<rolloutFile>.langfuse`, avoiding duplicate completed-turn uploads when
  sessions resume.
- `src/instrumentation.ts` uses `LangfuseSpanProcessor` and the LangFuse TS
  tracing SDK on top of OpenTelemetry, rather than hand-building generic spans.

## Runtime Test

`runs/official-codex-tests.txt`:

- `pnpm install --frozen-lockfile` installed dependencies.
- `pnpm test` could not start locally because the `/tmp` shell used Node 20.12
  and pnpm 9.1.4 despite the plugin requiring Node >=22 and pnpm 9.5, then
  Vitest failed on a missing `@rolldown/binding-darwin-arm64` optional native
  binding.
- This is a local test-environment blocker. It does not contradict the
  source-level trace-contract evidence.

## Scoring Against Probe B

- Stop hook: pass.
- Rollout transcript JSONL reader: pass.
- Root `Codex Turn` agent observation with input/output: pass.
- Generation observations with model/usage: pass.
- Tool observations with names/input/output/error/timing: pass.
- Deduplication sidecar: pass.
- Runtime test: inconclusive due local Node/pnpm/native binding setup.

