# agentic-workspace

Workspace prompts and contracts for agentic systems.

## Overview

This package provides type-safe access to system prompts that define the contract
between orchestrators (like AEF) and agents running in containerized workspaces.

## Usage

```python
from agentic_workspace import Prompt, load_prompt, AEF_WORKSPACE_PROMPT

# Type-safe prompt loading with enum
prompt_text = load_prompt(Prompt.AEF_WORKSPACE)

# Pre-loaded constant for convenience
print(AEF_WORKSPACE_PROMPT)
```

## Prompts

| Prompt | Description |
|--------|-------------|
| `AEF_WORKSPACE` | AEF ephemeral workspace contract with artifact output instructions |

## Adding New Prompts

1. Create a markdown file in `agentic_workspace/prompts/`
2. Add the prompt name to the `Prompt` enum in `__init__.py`
3. Mypy will enforce type safety for all consumers

## Integration with AEF

AEF uses these prompts via `--append-system-prompt`:

```python
from agentic_workspace import AEF_WORKSPACE_PROMPT

claude_cmd = [
    "claude", "--print",
    "--append-system-prompt", AEF_WORKSPACE_PROMPT,
    user_prompt,
    ...
]
```
