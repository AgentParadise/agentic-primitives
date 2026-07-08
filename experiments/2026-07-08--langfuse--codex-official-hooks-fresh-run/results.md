# Results

## Headline

| Probe | Evidence | Result |
|---|---|---|
| Baseline | `runs/baseline-doctor.json`, `runs/baseline-langfuse-status.txt`, `runs/baseline-codex-traces.json` | Passed: local LangFuse was reachable, the doctor reported Codex config ready, and recent Codex traces were discoverable. |
| Fresh Codex run | `runs/codex-stderr.txt`, `runs/codex-output.jsonl`, `runs/codex-command.redacted.txt` | Inconclusive: the frozen eval-pack command used `codex exec --ask-for-approval never`, but this Codex version rejects `--ask-for-approval` for `exec`. No model turn ran and no trace assertion is valid. |

## Details

The baseline trace query returned five recent Codex traces. The latest before
the attempted treatment was:

```text
b3d2561d7c0557c12fd427c02a16e2f3
```

The attempted treatment failed before a Codex session started:

```text
error: unexpected argument '--ask-for-approval' found
```

Because the eval pack is frozen after the hypothesis commit, the correct move is
to score this probe as inconclusive and run a follow-up with the corrected
`codex exec` command shape.
