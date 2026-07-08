# Claude Official Plugin Summary

## Hook

- Exit: `0`
- Stdout bytes: `0`
- Stderr bytes: `0`
- State isolated under `runs/claude-home/`

## LangFuse Trace

- Trace id: `76a54f7c977ae138c22ebae34b05e047`
- Trace name: `Claude Code - Turn 1 (official-cla)`
- Environment: `official-plugin-e2e-local`
- Session id: `official-claude-e2e-1783535611`
- Root input: present (`Read the file.`)
- Root output: present (`The file starts with a heading.`)
- Observation count: 4

## Observation Shape

- `SPAN`: `Conversational Turn`
- `GENERATION`: `LLM Call 1`, model `claude-test`
- `TOOL`: `Tool: Read`, input `{ "file_path": "README.md" }`, output `# Example`
- `GENERATION`: `LLM Call 2`, model `claude-test`

## Verdict Against Probe B

Pass. The official Claude plugin produced the rich trace shape missing from the
current Rust OTLP path: root IO, generation observations, semantic tool
observation, and tool IO.

