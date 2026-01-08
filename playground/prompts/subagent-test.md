# Subagent Concurrency Test

Spawn THREE subagents concurrently to complete these tasks:

1. **First subagent**: List all files in /workspace using `ls -la`
2. **Second subagent**: Check the current date and time using `date`
3. **Third subagent**: Create a file at /workspace/hello.txt with content "Hello from subagent 3"

Wait for all three subagents to complete, then summarize their results in a brief response.

This test verifies:
- Concurrent subagent spawning works
- Each subagent can execute tools independently
- Results are properly collected and summarized
