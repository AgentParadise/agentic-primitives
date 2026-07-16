# Codex Official Plugin Summary

## Hook

- Exit: `0`
- Sidecar: present (`<turn-id-recorded>`)
- State isolated under `runs/codex-home/`

## LangFuse Trace

- Trace id: `6905cfb7d1b969a0214e613383748ce7`
- Trace name: `Codex Turn`
- Environment: `official-plugin-e2e-local`
- Session id: `official-codex-e2e-1783535611`
- Root input: present (`List the files in the repo`)
- Root output: present (`There are two files: file1.txt and file2.txt.`)
- Observation count: 4
- Total cost: `0.001374999999`

## Observation Shape

- `AGENT`: `Codex Turn`
- `GENERATION`: `gpt-5.4`, usage `input=100`, `output=20`, `total=120`
- `TOOL`: `exec_command`, input `{ "command": ["ls"] }`, output
  `file1.txt\nfile2.txt`
- `GENERATION`: `gpt-5.4`, usage `input=150`, `output=30`, `total=180`

## Verdict Against Probe C

Pass. The official Codex plugin produced agent/generation/tool observations,
root IO, semantic tool IO, usage details, cost, and completed-turn sidecar
state.

