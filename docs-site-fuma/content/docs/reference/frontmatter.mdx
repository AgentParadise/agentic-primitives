# Frontmatter Reference

Complete reference for V2 primitive frontmatter fields.

## Command Frontmatter

```yaml
---
description: string (10-200 chars, required)
argument-hint: string (optional)
model: "haiku" | "sonnet" | "opus" (required)
allowed-tools: string (optional, comma-separated)
tags: array (optional)
---
```

### Fields

#### `description` (required)
Brief description of what the command does.

**Type**: String
**Length**: 10-200 characters
**Example**: `"Review code for quality and best practices"`

#### `model` (required)
Model to use for this command.

**Type**: Enum
**Values**: `haiku`, `sonnet`, `opus`
**Default**: N/A (must be specified)
**Guidelines**:
- `haiku`: Fast, simple tasks
- `sonnet`: Default, balanced
- `opus`: Complex reasoning

#### `argument-hint` (optional)
Hint for command arguments.

**Type**: String
**Example**: `"[file_path] [--recursive] - process files"`
**Use**: Shows users what arguments the command accepts

#### `allowed-tools` (optional)
Tools the command can use.

**Type**: String (comma-separated)
**Example**: `"Read, Grep, Bash"`
**Special**: `"*"` for all tools

#### `tags` (optional)
Tags for categorization and search.

**Type**: Array of strings
**Example**:
```yaml
tags:
  - code-quality
  - review
  - python
```

---

## Skill Frontmatter

```yaml
---
description: string (10-200 chars, required)
model: "haiku" | "sonnet" | "opus" (required)
allowed-tools: string (optional, comma-separated)
expertise: array (optional)
---
```

### Fields

#### `description` (required)
Brief description of the skill's expertise.

**Type**: String
**Length**: 10-200 characters
**Example**: `"Expert knowledge in application security"`

#### `model` (required)
Model to use for this skill.

**Type**: Enum
**Values**: `haiku`, `sonnet`, `opus`

#### `allowed-tools` (optional)
Tools the skill can use.

**Type**: String (comma-separated)
**Example**: `"Read, Grep"`

#### `expertise` (optional)
Areas of expertise.

**Type**: Array of strings
**Example**:
```yaml
expertise:
  - Test-Driven Development
  - Coverage Analysis
  - Integration Testing
```

---

## Tool Frontmatter

Tools don't use markdown frontmatter. Instead, they use `tool.yaml`:

```yaml
id: string (required, {category}/{name})
version: string (required, semver)
name: string (required, display name)
description: string (required)

interface:
  function:
    name: string (required, function name)
    description: string (required)
    parameters: array (required)
    returns: object (required)

implementation:
  language: string (required, e.g., "python")
  runtime: string (required, e.g., "python3.11+")
  entry_point: string (required, e.g., "impl.py:function_name")
  requirements: array (required)

execution:
  timeout_seconds: number (required)
  max_retries: number (required)
  async: boolean (required)

generator_hints:
  mcp: object (optional)
  langchain: object (optional)
```

See [tool-spec.v1.json](../../../schemas/tool-spec.v1.json) for complete schema.

---

## Validation Rules

### Description

- **Min length**: 10 characters
- **Max length**: 200 characters
- **Format**: Plain text, no markdown

**Valid**:
```yaml
description: Analyze code quality and suggest improvements
```

**Invalid**:
```yaml
description: Too short  # < 10 chars
description: This is a very long description that exceeds the maximum allowed length of two hundred characters and will fail validation because it's too verbose  # > 200 chars
```

### Model

- **Valid values**: `haiku`, `sonnet`, `opus`
- **Case-sensitive**: Must be lowercase

**Valid**:
```yaml
model: sonnet
```

**Invalid**:
```yaml
model: Sonnet      # Wrong case
model: gpt-4       # Not a valid model
```

### Allowed Tools

- **Format**: Comma-separated string
- **Whitespace**: Trimmed automatically
- **Special value**: `"*"` for all tools

**Valid**:
```yaml
allowed-tools: Read, Grep, Bash
allowed-tools: "*"
```

**Optional**:
```yaml
# Can be omitted entirely
```

### Tags / Expertise

- **Format**: YAML array
- **Item type**: String
- **Validation**: No special characters required

**Valid**:
```yaml
tags:
  - code-quality
  - review

expertise:
  - Test-Driven Development
  - BDD
```

---

## Common Patterns

### Minimal Command

```yaml
---
description: Format Python code with black
model: haiku
---
```

### Full-Featured Command

```yaml
---
description: Comprehensive code review with security analysis
argument-hint: "[directory] [--recursive] - review code in directory"
model: opus
allowed-tools: Read, Grep, Bash
tags:
  - code-quality
  - security
  - review
---
```

### Minimal Skill

```yaml
---
description: Expert in Python best practices
model: sonnet
---
```

### Full-Featured Skill

```yaml
---
description: Comprehensive testing expertise and methodology
model: sonnet
allowed-tools: Read, Bash
expertise:
  - Test-Driven Development
  - Behavior-Driven Development
  - Integration Testing
  - Coverage Analysis
  - Test Architecture
---
```

---

## Validation

Validate frontmatter:

```bash
# Single file
agentic-p validate primitives/v2/commands/qa/review.md

# All primitives
agentic-p validate --all
```

### Common Errors

**Missing required field**:
```
Error: description is required
```
Fix: Add the missing field.

**Invalid value**:
```
Error: model must be one of: haiku, sonnet, opus
```
Fix: Use a valid enum value.

**Length violation**:
```
Error: description must be between 10 and 200 characters
```
Fix: Adjust description length.

**Invalid YAML**:
```
Error: Failed to parse YAML
```
Fix: Check YAML syntax, ensure proper indentation.

---

## Schema Files

Frontmatter is validated against JSON schemas:

- **Commands**: `schemas/command-frontmatter.v1.json`
- **Skills**: `schemas/skill-frontmatter.v1.json`
- **Tools**: `tool-spec.v1.json`

---

## See Also

- [Authoring Commands](../authoring/commands.md)
- [Authoring Skills](../authoring/skills.md)
- [Authoring Tools](../authoring/tools.md)
- [Validation Guide](../authoring/validation.md)
- [CLI Reference](./cli.md)
