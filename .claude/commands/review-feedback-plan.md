# /review-feedback-plan - Review Feedback Tickets and Plan Work

Review feedback tickets from the UI Feedback system and prioritize next work steps.

## Prerequisites

- Feedback API running at `http://localhost:8001` (or configured URL)
- Access to the codebase for creating project plans

## Quick Reference

```bash
# API Base URL
FEEDBACK_API="http://localhost:8001/api"

# Get all open tickets
curl -s "$FEEDBACK_API/feedback?status=open" | jq

# Get stats overview
curl -s "$FEEDBACK_API/feedback/stats" | jq
```

## Workflow

### Step 1: Get Feedback Overview

```bash
# Get statistics summary
curl -s "http://localhost:8001/api/feedback/stats" | python3 -c "
import json,sys
data=json.load(sys.stdin)
print('=== Feedback Overview ===')
print(f'Total: {data[\"total\"]}')
print()
print('By Status:')
for status, count in data['by_status'].items():
    emoji = {'open':'🔴','in_progress':'🟡','resolved':'🟢','closed':'⚫','wont_fix':'⚪'}
    print(f'  {emoji.get(status,\"\")} {status}: {count}')
print()
print('By Priority:')
for priority, count in data['by_priority'].items():
    emoji = {'critical':'🔥','high':'🔴','medium':'🟡','low':'🟢'}
    print(f'  {emoji.get(priority,\"\")} {priority}: {count}')
print()
print('By Type:')
for ftype, count in data['by_type'].items():
    emoji = {'bug':'🐛','feature':'✨','ui_ux':'🎨','performance':'⚡','question':'❓','other':'📝'}
    print(f'  {emoji.get(ftype,\"\")} {ftype}: {count}')
"
```

### Step 2: List Open Tickets by Priority

```bash
# Get open tickets sorted by priority (critical first)
curl -s "http://localhost:8001/api/feedback?status=open&limit=50" | python3 -c "
import json,sys
data=json.load(sys.stdin)
priority_order = {'critical':0,'high':1,'medium':2,'low':3}
items = sorted(data['items'], key=lambda x: priority_order.get(x['priority'],99))

print('=== Open Tickets (by priority) ===')
print()
for i, item in enumerate(items, 1):
    emoji = {'bug':'🐛','feature':'✨','ui_ux':'🎨','performance':'⚡','question':'❓','other':'📝'}
    priority_emoji = {'critical':'🔥','high':'🔴','medium':'🟡','low':'🟢'}
    
    print(f'{i}. [{item[\"id\"][:8]}] {priority_emoji.get(item[\"priority\"],\"\")} {emoji.get(item[\"feedback_type\"],\"\")} {item[\"feedback_type\"].upper()}')
    print(f'   Route: {item[\"route\"]}')
    comment = item.get('comment','')[:100]
    if len(item.get('comment','')) > 100:
        comment += '...'
    print(f'   Comment: {comment}')
    print()
"
```

### Step 3: Review Individual Ticket

```bash
# Get full ticket details with media
TICKET_ID="<ticket-id>"
curl -s "http://localhost:8001/api/feedback/$TICKET_ID" | python3 -c "
import json,sys
item=json.load(sys.stdin)

print('=== Ticket Details ===')
print(f'ID: {item[\"id\"]}')
print(f'Type: {item[\"feedback_type\"]}')
print(f'Priority: {item[\"priority\"]}')
print(f'Status: {item[\"status\"]}')
print(f'Created: {item[\"created_at\"]}')
print()
print('--- Location ---')
print(f'URL: {item[\"url\"]}')
print(f'Route: {item[\"route\"]}')
print(f'Viewport: {item.get(\"viewport_width\",\"?\")}x{item.get(\"viewport_height\",\"?\")}')
if item.get('click_x') and item.get('click_y'):
    print(f'Click: ({item[\"click_x\"]}, {item[\"click_y\"]})')
if item.get('component_name'):
    print(f'Component: <{item[\"component_name\"]}>')
if item.get('css_selector'):
    print(f'Selector: {item[\"css_selector\"]}')
print()
print('--- Comment ---')
print(item.get('comment','(no comment)'))
print()
print('--- Media ---')
media = item.get('media',[])
if media:
    for m in media:
        print(f'  - {m[\"media_type\"]}: {m[\"file_name\"]} ({m[\"id\"][:8]})')
        print(f'    URL: http://localhost:8001/api/feedback/{item[\"id\"]}/media/{m[\"id\"]}')
else:
    print('  (no media attached)')
"
```

### Step 4: View Screenshots/Audio

```bash
# Download screenshot
TICKET_ID="<ticket-id>"
MEDIA_ID="<media-id>"
curl -o "screenshot.png" "http://localhost:8001/api/feedback/$TICKET_ID/media/$MEDIA_ID"

# Open screenshot (macOS)
open screenshot.png

# Play audio (macOS)
curl -o "voice-note.webm" "http://localhost:8001/api/feedback/$TICKET_ID/media/$MEDIA_ID"
open voice-note.webm
```

### Step 5: Update Ticket Status

When starting work on a ticket:

```bash
# Mark as in_progress with work tracking info
TICKET_ID="<ticket-id>"
curl -X PATCH "http://localhost:8001/api/feedback/$TICKET_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "in_progress",
    "assigned_to": "agent-claude",
    "resolution_notes": "Branch: feature/fix-issue-123\nPlan: PROJECT-PLAN_20251205_FIX-ISSUE.md\nPR: #pending"
  }'
```

When completing work:

```bash
# Mark as resolved with completion info
curl -X PATCH "http://localhost:8001/api/feedback/$TICKET_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "resolved",
    "resolution_notes": "Fixed in PR #123\nBranch: feature/fix-issue-123\nCommit: abc1234"
  }'
```

## Work Tracking Format

Use `resolution_notes` field to track work progress:

```
Branch: feature/<branch-name>
Plan: PROJECT-PLAN_YYYYMMDD_<TASK-NAME>.md
PR: #<number> or "pending"
Commit: <short-hash>
Notes: <additional context>
```

### Example Status Updates

**Starting Work:**
```json
{
  "status": "in_progress",
  "assigned_to": "agent-claude",
  "resolution_notes": "Branch: feature/ui-feedback-ux\nPlan: PROJECT-PLAN_20251205_FEEDBACK-UX.md\nPR: pending"
}
```

**Work In Progress (update):**
```json
{
  "resolution_notes": "Branch: feature/ui-feedback-ux\nPlan: PROJECT-PLAN_20251205_FEEDBACK-UX.md\nPR: #7\nProgress: 3/5 milestones complete"
}
```

**Completed:**
```json
{
  "status": "resolved",
  "resolution_notes": "Branch: feature/ui-feedback-ux\nPR: #7 (merged)\nCommit: c6d23fa\nNotes: Added badge dropdowns, compact UI, Shift+Enter hotkey"
}
```

**Won't Fix:**
```json
{
  "status": "wont_fix",
  "resolution_notes": "Reason: Duplicate of ticket abc123\nSee: #456 for related work"
}
```

## Prioritization Framework

### Priority Matrix

| Priority | Response Time | Description |
|----------|--------------|-------------|
| 🔥 Critical | Immediate | App broken, data loss, security issue |
| 🔴 High | Same day | Major feature broken, blocking users |
| 🟡 Medium | This week | Important but workarounds exist |
| 🟢 Low | Backlog | Nice to have, minor improvements |

### Type Priority (default)

1. **Bug** - Fix broken functionality first
2. **Performance** - Address slowdowns affecting UX
3. **UI/UX** - Improve user experience
4. **Feature** - Add new capabilities
5. **Question** - Respond/document
6. **Other** - Evaluate case by case

### Decision Tree

```
Is the app broken or unusable?
├─ Yes → Critical priority, fix immediately
└─ No
   ├─ Is it a security issue?
   │  ├─ Yes → Critical priority
   │  └─ No
   │     ├─ Does it block core workflows?
   │     │  ├─ Yes → High priority
   │     │  └─ No
   │     │     ├─ Do users complain frequently?
   │     │     │  ├─ Yes → Medium priority
   │     │     │  └─ No → Low priority
```

## Batch Operations

### Get All In-Progress Work

```bash
curl -s "http://localhost:8001/api/feedback?status=in_progress" | python3 -c "
import json,sys
data=json.load(sys.stdin)

print('=== In-Progress Work ===')
print()
for item in data['items']:
    print(f'[{item[\"id\"][:8]}] {item[\"feedback_type\"]}')
    print(f'  Assigned: {item.get(\"assigned_to\",\"unassigned\")}')
    notes = item.get('resolution_notes','')
    if notes:
        for line in notes.split('\n'):
            print(f'  {line}')
    print()
"
```

### Daily Standup Report

```bash
# Generate work summary
curl -s "http://localhost:8001/api/feedback/stats" > /tmp/stats.json
curl -s "http://localhost:8001/api/feedback?status=in_progress" > /tmp/in_progress.json
curl -s "http://localhost:8001/api/feedback?status=open&limit=5" > /tmp/open.json

python3 -c "
import json

with open('/tmp/stats.json') as f: stats = json.load(f)
with open('/tmp/in_progress.json') as f: in_progress = json.load(f)
with open('/tmp/open.json') as f: open_tickets = json.load(f)

print('# Daily Feedback Report')
print()
print('## Summary')
print(f'- Total tickets: {stats[\"total\"]}')
print(f'- Open: {stats[\"by_status\"].get(\"open\",0)}')
print(f'- In Progress: {stats[\"by_status\"].get(\"in_progress\",0)}')
print(f'- Resolved: {stats[\"by_status\"].get(\"resolved\",0)}')
print()
print('## Currently Working On')
for item in in_progress['items']:
    print(f'- [{item[\"id\"][:8]}] {item[\"feedback_type\"]}: {item.get(\"comment\",\"\")[:50]}...')
    if item.get('resolution_notes'):
        for line in item['resolution_notes'].split('\n')[:2]:
            print(f'  - {line}')
print()
print('## Next Up (Top 5 Open)')
for item in open_tickets['items'][:5]:
    print(f'- [{item[\"id\"][:8]}] {item[\"priority\"]} {item[\"feedback_type\"]}: {item.get(\"comment\",\"\")[:50]}...')
"
```

## Integration with RIPER-5

### Research Mode
- Review all open tickets
- Understand the scope and impact
- Gather context from screenshots/audio

### Innovate Mode
- Group related tickets
- Brainstorm solutions
- Consider architectural impact

### Plan Mode
- Create `PROJECT-PLAN_YYYYMMDD_<TASK>.md`
- Update ticket with plan reference
- Define milestones

### Execute Mode
- Update ticket to `in_progress`
- Link branch name
- Commit changes, update PR reference

### Review Mode
- Verify implementation against ticket
- Update ticket to `resolved`
- Link final commit/PR

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/feedback` | GET | List tickets (supports filters) |
| `/api/feedback/{id}` | GET | Get single ticket with media |
| `/api/feedback` | POST | Create ticket |
| `/api/feedback/{id}` | PATCH | Update ticket |
| `/api/feedback/{id}` | DELETE | Delete ticket |
| `/api/feedback/stats` | GET | Get aggregated statistics |
| `/api/feedback/{id}/media/{media_id}` | GET | Download media file |

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status |
| `feedback_type` | string | Filter by type |
| `priority` | string | Filter by priority |
| `app_name` | string | Filter by app |
| `page` | int | Page number (default: 1) |
| `page_size` | int | Items per page (default: 20) |

---

**Run `/review-feedback-plan` regularly to stay on top of user feedback and prioritize work effectively.**
