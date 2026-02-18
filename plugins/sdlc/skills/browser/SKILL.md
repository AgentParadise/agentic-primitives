---
description: Headless browser automation using Playwright CLI for UI testing, visual QA, and web scraping
argument-hint: "<url> [headed] [vision]"
model: sonnet
allowed-tools: Bash
---

# Browser Automation

Automate browsers using `playwright-cli` — a token-efficient CLI wrapper for Playwright. Runs headless by default, supports parallel sessions via named sessions (`-s=`), and persistent browser profiles.

## Dependencies

- `playwright-cli` — must be installed and on PATH

## Key Details

- **Headless by default** — pass `--headed` to `open` to see the browser
- **Parallel sessions** — use `-s=<name>` to run multiple independent browser instances
- **Persistent profiles** — cookies and storage state preserved between calls with `--persistent`
- **Token-efficient** — CLI-based, no accessibility trees or tool schemas in context
- **Vision mode** (opt-in) — set `PLAYWRIGHT_MCP_CAPS=vision` to receive screenshots as image responses

## Variables

URL: $1 || ""
HEADED: $2 || "false"   # "true" or "headed" for visible browser
VISION: $3 || "false"   # "true" or "vision" for screenshot-in-context mode

## Sessions

Always use a named session. Derive a short, descriptive kebab-case name from the task context:

```bash
# Examples:
# "test the checkout flow on mystore.com" → -s=mystore-checkout
# "validate deploy on staging"            → -s=staging-deploy
# "scrape API docs from example.com"      → -s=example-docs

playwright-cli -s=mystore-checkout open https://mystore.com --persistent
playwright-cli -s=mystore-checkout snapshot
playwright-cli -s=mystore-checkout click e12
```

Managing sessions:
```bash
playwright-cli list                        # list all sessions
playwright-cli close-all                   # close all sessions
playwright-cli -s=<name> close             # close specific session
playwright-cli -s=<name> delete-data       # wipe session profile
```

## Quick Reference

```
Core:       open [url], goto <url>, click <ref>, fill <ref> <text>, type <text>, snapshot, screenshot [ref], close
Navigate:   go-back, go-forward, reload
Keyboard:   press <key>, keydown <key>, keyup <key>
Mouse:      mousemove <x> <y>, mousedown, mouseup, mousewheel <dx> <dy>
Tabs:       tab-list, tab-new [url], tab-close [index], tab-select <index>
Save:       screenshot [ref], pdf, screenshot --filename=<path>
Storage:    state-save, state-load, cookie-*, localstorage-*, sessionstorage-*
Network:    route <pattern>, route-list, unroute, network
DevTools:   console, run-code <code>, tracing-start/stop, video-start/stop
Sessions:   -s=<name> <cmd>, list, close-all, kill-all
Config:     open --headed, open --browser=chrome, resize <w> <h>
```

## Workflow

### 1. Open a Session

Always set the viewport via env var. Use `--persistent` to preserve cookies/state:

```bash
PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 playwright-cli -s=<session> open <url> --persistent
```

With headed mode:
```bash
PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 playwright-cli -s=<session> open <url> --persistent --headed
```

With vision mode (screenshots returned as image responses):
```bash
PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 PLAYWRIGHT_MCP_CAPS=vision playwright-cli -s=<session> open <url> --persistent
```

### 2. Get Element References

```bash
playwright-cli -s=<session> snapshot
```

### 3. Interact

```bash
playwright-cli -s=<session> click <ref>
playwright-cli -s=<session> fill <ref> "text"
playwright-cli -s=<session> type "text"
playwright-cli -s=<session> press Enter
```

### 4. Capture Results

```bash
playwright-cli -s=<session> screenshot
playwright-cli -s=<session> screenshot --filename=output.png
```

### 5. Close (Required)

Always close the session when done:

```bash
playwright-cli -s=<session> close
```

## SDLC Use Cases

- **Testing UI changes** — open a feature branch deploy, walk through flows, screenshot results
- **Validating deploys** — smoke-test production after deploy, verify key pages load
- **Scraping docs** — extract API documentation or changelogs from vendor sites
- **Visual regression** — screenshot before/after comparisons
- **Form testing** — fill and submit forms, verify responses

## Configuration

If a `playwright-cli.json` exists in the working directory, it's used automatically:

```json
{
  "browser": {
    "browserName": "chromium",
    "launchOptions": { "headless": true },
    "contextOptions": { "viewport": { "width": 1440, "height": 900 } }
  },
  "outputDir": "./screenshots"
}
```

## Full Help

Run `playwright-cli --help` or `playwright-cli --help <command>` for detailed usage.
