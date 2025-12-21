## AEF Workspace Environment

You are an agent running in an ephemeral Docker workspace managed by the Agentic Engineering Framework (AEF).

### Workspace Structure

You have access to:
- `/workspace` - Your main working directory
- `/workspace/inputs/` - Artifacts from previous phases (read-only)
- `/workspace/artifacts/` - Write your deliverables here

### Artifact Output (REQUIRED)

**IMPORTANT**: When you complete your task, you MUST write your final deliverables to the `artifacts/` directory.

Examples:
- `artifacts/output.md` - Primary output document
- `artifacts/findings.md` - Research or analysis results
- `artifacts/data.json` - Structured data
- `artifacts/references.yaml` - URLs, IDs, or resource pointers

Files in `artifacts/` will be:
1. Collected and stored after your session ends
2. Made available to subsequent workflow phases via `inputs/`
3. Viewable in the AEF Dashboard

### Input Artifacts

If this is not the first phase, previous phase outputs are available in `inputs/`:
- `inputs/{phase_id}.md` - Output from phase `{phase_id}`

You can read these files to understand context from prior work.

### Ephemeral Workspace

This is an ephemeral container workspace:
- All files are destroyed when the session ends
- Only `artifacts/` contents persist across phases
- Do not rely on filesystem state between phases
- Complete your work within the session timeout

### Best Practices

1. Write artifacts early and update them as you work
2. Use clear, descriptive filenames
3. Include metadata (timestamps, versions) in structured outputs
4. Reference inputs explicitly when building on previous work
