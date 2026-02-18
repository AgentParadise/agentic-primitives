---
description: Browser automation — open pages, interact with elements, take screenshots
argument-hint: "<url> [headed] [vision]"
model: sonnet
allowed-tools: Bash
---

# Browser

Direct browser automation via Playwright CLI. Opens a headless browser session, navigates to the target URL, and executes the requested interactions.

## Variables

URL: $1 || ""
HEADED: detected from $ARGUMENTS — if "headed" or "true" appears, pass `--headed` to open
VISION: detected from $ARGUMENTS — if "vision" appears, prefix commands with `PLAYWRIGHT_MCP_CAPS=vision`
PROMPT: remaining non-keyword arguments describing what to do

## Instructions

1. Parse the arguments to extract URL, headed/vision flags, and the task description
2. Derive a session name from the URL (e.g., `example-com` from `https://example.com/page`)
3. Open the browser session:
   ```bash
   PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 playwright-cli -s=<session> open <url> --persistent
   ```
4. Execute the requested task:
   - Use `snapshot` to discover element references
   - Use `click`, `fill`, `type`, `press` to interact
   - Use `screenshot` to capture results
5. Report what was done and any findings
6. **Always close the session:**
   ```bash
   playwright-cli -s=<session> close
   ```

## Examples

```
/browser https://example.com — take a screenshot of the homepage
/browser https://myapp.com/login headed — fill in the login form and verify dashboard loads
/browser https://docs.api.com vision — scrape the API reference and summarize endpoints
```
