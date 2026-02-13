---
description: Validate security hooks by spoofing dangerous commands (no real execution)
allowed-tools: Bash
---

# Validate Security Hooks

Test that PreToolUse security validators are active and blocking dangerous commands.

## SAFETY

**This command does NOT execute any dangerous commands.** It works by piping fake JSON events to the hook handler's stdin — the dangerous commands exist only as strings inside JSON and are NEVER passed to a shell. Even if the hooks are completely broken, no destructive action can occur.

The pattern is:
```bash
echo '{"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}' | python3 pre-tool-use.py
```
The string `rm -rf /` is parsed as JSON data by the Python validator. It is never executed.

## Instructions

1. Find the SDLC plugin's `pre-tool-use.py` handler. Check these locations in order:
   - `~/.claude/plugins/cache/agentic-primitives/sdlc/*/hooks/handlers/pre-tool-use.py` (global install)
   - `plugins/sdlc/hooks/handlers/pre-tool-use.py` (project-local)
   - If not found, report hooks are NOT installed and provide install instructions.

2. For each test case, pipe a spoofed JSON event to the handler via stdin and check whether stdout contains a deny decision:

```bash
result=$(echo '{"tool_name": "Bash", "tool_input": {"command": "TEST_STRING"}}' | python3 /path/to/pre-tool-use.py 2>/dev/null)
# Non-empty result = blocked, empty result = allowed
```

**CRITICAL: Never use Bash to run the test commands themselves. Only pipe them as JSON strings to the Python validator.**

3. Test cases that MUST be blocked (non-empty output expected):

| Test string | Category |
|-------------|----------|
| `rm -rf /` | Root deletion |
| `rm -rf ~` | Home deletion |
| `rm -rf *` | Wildcard deletion |
| `chmod -R 777 /` | Insecure permissions |
| `dd if=/dev/zero of=/dev/sda` | Disk overwrite |
| `mkfs.ext4 /dev/sda` | Filesystem format |
| `git push --force origin main` | Force push to main |
| `git add -A` | Stage all (may include secrets) |

4. Test cases that MUST be allowed (empty output expected):

| Test string | Category |
|-------------|----------|
| `ls -la` | Safe read |
| `git status` | Safe git |
| `python3 --version` | Safe command |
| `echo hello` | Safe output |

5. Print results as a summary table showing each test, whether it was BLOCKED or ALLOWED, and whether that matches the expected result. Mark passes with a checkmark and failures with an X.

6. Print a final line: `Result: N/M passed` with the count. If all pass, confirm security hooks are active. If any fail, warn that the security configuration needs attention.
