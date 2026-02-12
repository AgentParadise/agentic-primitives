Perfect — I’ll distill the ENTIRE Claude Code hook system into **clean Markdown tables**, organized by *hook event group*, with concise, POC-relevant descriptions.

This is the master reference you can drop into your repo.

---

# ✅ Claude Code Hooks – Complete Reference (Markdown Tables)

Below are **tables** for each hook type, followed by **clarifying notes**.

---

# 1. **Lifecycle Hooks**

These run when a Claude Code **session** starts or ends.

## SessionStart & SessionEnd

| Hook Event       | Trigger                                                                             | Key Fields in Input                                          | Typical Uses                                                                          |
| ---------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| **SessionStart** | When Claude Code begins a new session (or resumes, which also starts a new session) | `session_id`, `transcript_path`, `source`, `permission_mode` | Load context, set env vars, initialize agent session, analytics session_started event |
| **SessionEnd**   | When a session ends                                                                 | `session_id`, `transcript_path`, `reason`                    | Cleanup, analytics session_completed event, save final state                          |

---

# 2. **Tool Execution Hooks**

Fire before and after Claude Code uses internal tools (Write, Edit, Bash, Search, Read, etc.)

## PreToolUse

| Hook Event     | Trigger                     | Key Fields                                                    | Use Cases                                                                                 |
| -------------- | --------------------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **PreToolUse** | Before any tool is executed | `session_id`, `tool_name`, `tool_input`, `tool_use_id`, `cwd` | Logging intended operations, permissions, analytics for planned actions, block unsafe ops |

## PostToolUse

| Hook Event      | Trigger                | Key Fields                                                | Use Cases                                                                     |
| --------------- | ---------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------- |
| **PostToolUse** | After a tool completes | `tool_name`, `tool_response`, `tool_input`, `tool_use_id` | Log actual file writes, diffs applied, test results, classify tool operations |

---

# 3. **Permission Hooks**

| Hook Event            | Trigger                                            | Key Fields                                   | Uses                                                                                    |
| --------------------- | -------------------------------------------------- | -------------------------------------------- | --------------------------------------------------------------------------------------- |
| **PermissionRequest** | When Claude asks user for permission to run a tool | `tool_name`, `tool_input`, `permission_mode` | Auto-approve certain tools, auto-deny dangerous ones, analytics on “blocked vs allowed” |

---

# 4. **User Instruction Hooks**

| Hook Event           | Trigger                                                 | Key Fields                                | Uses                                                              |
| -------------------- | ------------------------------------------------------- | ----------------------------------------- | ----------------------------------------------------------------- |
| **UserPromptSubmit** | When user submits a prompt (before Claude processes it) | `prompt`, `session_id`, `transcript_path` | Validate prompts, inject additional context, classify user intent |

---

# 5. **Stop Hooks** (Agent completion events)

| Hook Event       | Trigger                         | Key Fields                       | Uses                                                                            |
| ---------------- | ------------------------------- | -------------------------------- | ------------------------------------------------------------------------------- |
| **Stop**         | When Claude thinks it’s done    | `stop_hook_active`, `session_id` | Decide if Claude should continue, evaluate completeness, analytics for autonomy |
| **SubagentStop** | When a subagent (Task) finishes | same as Stop + Task context      | Same as Stop but scoped to subagents; classify task-level termination           |

---

# 6. **Notification Hooks**

| Hook Event       | Trigger                                     | Notification Type                                                        | Uses                                                 |
| ---------------- | ------------------------------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------- |
| **Notification** | Whenever Claude sends a system notification | `permission_prompt`, `idle_prompt`, `auth_success`, `elicitation_dialog` | Observe system states, idle durations, permission UX |

---

# 7. **Compact / Memory Hooks**

| Hook Event     | Trigger                                   | Key Fields                                     | Uses                                                      |
| -------------- | ----------------------------------------- | ---------------------------------------------- | --------------------------------------------------------- |
| **PreCompact** | When Claude performs a context compaction | `trigger` (manual/auto), `custom_instructions` | Logging compaction operations, analytics on long sessions |

---

# 8. **MCP-Related Hooks**

Tools exposed via MCP appear inside `PreToolUse/PostToolUse` using special naming:

| Example MPC Tool Name              | Meaning                |
| ---------------------------------- | ---------------------- |
| `mcp__memory__create_entities`     | Memory server tool     |
| `mcp__filesystem__read_file`       | Filesystem server tool |
| `mcp__github__search_repositories` | GitHub search tool     |

Handled automatically by PreToolUse/PostToolUse matchers.

---

# 🔥 SUMMARY TABLE — ALL CLAUDE HOOK EVENTS

| Hook Event            | Description                 | Matchers?       | Best Use for Analytics                                  |
| --------------------- | --------------------------- | --------------- | ------------------------------------------------------- |
| **SessionStart**      | New session begins          | Yes             | analytics: session_started event                        |
| **SessionEnd**        | Session ends                | No              | analytics: session_completed event                      |
| **UserPromptSubmit**  | User submits prompt         | No              | “human intervention” detection, prompt classification   |
| **PreToolUse**        | Before tool is executed     | Yes             | operation_intent events, planned writes/tests           |
| **PostToolUse**       | After tool finishes         | Yes             | file_modified/file_created, test results, tool outcomes |
| **PermissionRequest** | Claude asks user permission | Yes             | autonomy tracking, permission friction analytics        |
| **Stop**              | Main agent stops            | No              | classify session success/termination                    |
| **SubagentStop**      | Subagent stops              | No              | classify task-level outcomes                            |
| **Notification**      | Various notifications       | Optional        | track idle time, permissions, auth events               |
| **PreCompact**        | Before compaction           | `manual`/`auto` | analytics on long sessions / memory use                 |

---

# 📦 Additional Key Fields Always Available

These appear in *all* hook inputs:

| Field             | Meaning                                         |
| ----------------- | ----------------------------------------------- |
| `session_id`      | Unique Claude session ID (your ES `session_id`) |
| `transcript_path` | Path to JSONL transcript file for this session  |
| `cwd`             | Current working directory inside the project    |
| `permission_mode` | Level of automatic permissioning                |
| `hook_event_name` | Name of the hook event                          |

These give you **everything you need** to:

* trace sessions
* load full logs
* analyze behavior
* connect metrics to your event store

---

# 🚀 Okay… what next?

If you want, I can now generate:

### **1. A complete table mapping → YOUR ANALYTICS EVENTS**

| Claude Hook | Your Event | Analytics Unlocked |
| ----------- | ---------- | ------------------ |

### **2. A ready-to-paste “analytics collector” script**

A single TypeScript/Python script that:

* reads stdin hook payload
* extracts needed fields
* emits correct events to Supabase (`events` table)
* appends conversation logs (`conversation_logs`)

### **3. A minimal `.claude/settings.json` hook configuration**

That plugs all relevant hooks into your collector script.

---

If you want that next → tell me **"generate hook→event mapping"** or **"generate full collector POC"**.
