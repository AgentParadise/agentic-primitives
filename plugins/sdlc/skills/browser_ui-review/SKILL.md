---
description: Parallel QA validation — discovers YAML user stories, fans out browser-qa agents, aggregates results
argument-hint: "[headed] [filename-filter] [vision]"
model: opus
allowed-tools: Read, Bash, Glob, Task, TeamCreate, TeamDelete, TaskCreate, TaskUpdate, SendMessage
---

# UI Review

Discover user stories from YAML files, fan out parallel `browser-qa-agent` instances to validate each story, then aggregate and report pass/fail results with screenshots.

## Variables

HEADED: $1 (default: "false" — set to "true" or "headed" for visible browser windows)
VISION: detected from $ARGUMENTS — if "vision" appears, enable vision mode
FILENAME_FILTER: remaining non-keyword arguments after removing "vision"
STORIES_DIR: "user_stories"
STORIES_GLOB: "user_stories/*.yaml"
AGENT_TIMEOUT: 300000
SCREENSHOTS_BASE: "screenshots/browser-qa"
RUN_DIR: "{SCREENSHOTS_BASE}/{YYYYMMDD_HHMMSS}_{short-uuid}" (generated once at start)

## Instructions

- Use TeamCreate to create a team, then spawn one `browser-qa-agent` teammate per story
- Launch ALL teammates in a single message so they run in parallel
- If FILENAME_FILTER is provided, only run stories from matching files
- If a YAML file fails to parse, log a warning and skip it
- If no stories are found, report that and stop
- Be resilient: if a teammate times out or crashes, mark that story as FAIL

## Workflow

### Phase 1: Discover

1. Glob for all files matching `STORIES_GLOB`
2. Filter by FILENAME_FILTER if provided
3. Read and parse each YAML file's `stories` array
4. Build a flat list of all stories, tracking source file
5. Generate RUN_DIR:
   ```bash
   RUN_DIR="screenshots/browser-qa/$(date +%Y%m%d_%H%M%S)_$(uuidgen | tr '[:upper:]' '[:lower:]' | head -c 6)"
   ```
6. For each story, compute SCREENSHOT_PATH: `{RUN_DIR}/{file-stem}/{slugified-name}/`

### Phase 2: Spawn

7. TeamCreate with name `ui-review`
8. TaskCreate for each story
9. Spawn `browser-qa-agent` per story with prompt:
   ```
   Execute this user story and report results:

   **Story:** {story.name}
   **URL:** {story.url}
   **Headed:** {HEADED}
   **Vision:** {VISION}

   **Workflow:**
   {story.workflow}

   Instructions:
   - Follow each step sequentially
   - Screenshot after each significant step
   - Save screenshots to: {SCREENSHOT_PATH}
   - Report each step as PASS or FAIL
   - Final line: RESULT: {PASS|FAIL} | Steps: {passed}/{total}
   ```

### Phase 3: Collect

10. Wait for teammate results
11. Parse each report for RESULT line and step counts
12. Mark tasks completed

### Phase 4: Report

13. Shutdown teammates, TeamDelete
14. Present summary:

```
# UI Review Summary

**Run:** {datetime}
**Stories:** {total} total | {passed} passed | {failed} failed
**Status:** ✅ ALL PASSED | ❌ PARTIAL FAILURE | ❌ ALL FAILED

## Results

| # | Story | Source File | Status | Steps |
|---|-------|-------------|--------|-------|
| 1 | {name} | {file} | ✅ PASS | {x}/{y} |
| 2 | {name} | {file} | ❌ FAIL | {x}/{y} |

## Failures
(only if failures exist)

### Story: {name}
**Source:** {file}
**Agent Report:**
{full report}

## Screenshots
All screenshots saved to: `{RUN_DIR}/`
```
