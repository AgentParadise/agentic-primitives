---
description: Configure notification providers, sound themes, and test notifications
allowed-tools: Bash
---

# Notifications Configuration

You are helping the user configure the Claude Code notifications plugin interactively.

## Step 1: Show Current Status

Run these checks using Bash and display a status summary:

```bash
echo "=== 🔔 Notifications Status ==="

# Check ntfy
if [ -n "${NTFY_TOPIC:-}" ]; then
  echo "✅ ntfy push: active (topic: ${NTFY_TOPIC:0:8}…)"
else
  echo "⬚ ntfy push: not configured"
fi

# Check macOS
if command -v osascript &>/dev/null; then
  echo "✅ macOS notifications: active"
else
  echo "⬚ macOS notifications: not available (not macOS)"
fi

# Check Pushover
if [ -n "${PUSHOVER_TOKEN:-}" ] && [ -n "${PUSHOVER_USER:-}" ]; then
  echo "✅ Pushover: active"
else
  echo "⬚ Pushover: not configured"
fi

# Check theme
if [ -n "${CLAUDE_NOTIFY_THEME:-}" ]; then
  echo "🎵 Sound theme: ${CLAUDE_NOTIFY_THEME}"
else
  echo "🎵 Sound theme: default"
fi

# Check if anything is configured
if [ -z "${NTFY_TOPIC:-}" ] && ! command -v osascript &>/dev/null && [ -z "${PUSHOVER_TOKEN:-}" ]; then
  echo ""
  echo "⚠️  No providers configured — notifications won't fire"
fi
```

## Step 1b: Machine Name

Check the current machine label and offer to customize it:

```bash
CURRENT_MACHINE="${CLAUDE_NOTIFY_MACHINE:-$(hostname)}"
echo "📍 Machine label: $CURRENT_MACHINE"
```

If the hostname looks like a raw default (e.g., `Users-MacBook-Pro.local`), suggest a friendlier name like `"M3 Pro"` or `"Work Laptop"`. Ask if they'd like to set a custom name.

If they choose a name, detect the shell RC file (same as Option 1 below) and append:

```bash
if grep -q 'CLAUDE_NOTIFY_MACHINE' "$SHELL_RC" 2>/dev/null; then
  echo "⚠️ CLAUDE_NOTIFY_MACHINE already exists in $SHELL_RC"
  # Offer to replace it
else
  printf '\n# Claude Code Notifications — machine label\nexport CLAUDE_NOTIFY_MACHINE="%s"\n' "$CHOSEN_NAME" >> "$SHELL_RC"
  echo "✅ Machine label set to: $CHOSEN_NAME"
fi
```

This label appears in every notification so multi-machine setups are easy to distinguish. Skip if the user is happy with the current value.

---

## Step 2: Offer Options

After showing status, present these options and ask the user what they'd like to do:

1. **Set up ntfy push notifications** — get notifications on your phone
2. **Change sound theme** — pick a macOS notification sound theme
3. **Disable a provider** — remove a configured provider
4. **Test notifications** — send a test through each active provider

Wait for the user to choose, then follow the appropriate section below.

---

## Option 1: Set Up ntfy Push

1. Ask the user for an optional name prefix (e.g., their name). Generate a secure topic that fits within ntfy's **64-character limit**:
   ```bash
   PREFIX="${1:-claude}"  # user's chosen prefix, default "claude"
   # Calculate remaining space: 64 total - prefix length - 1 underscore
   REMAINING=$((64 - ${#PREFIX} - 1))
   # Each hex char = 4 bits, so REMAINING hex chars
   RANDOM_PART=$(openssl rand -hex 32 | head -c "$REMAINING")
   TOPIC="${PREFIX}_${RANDOM_PART}"
   echo "Your topic ($((${#TOPIC})) chars): $TOPIC"
   ```
   If the prefix is too long (would leave fewer than 16 random chars), warn the user and suggest a shorter one.

2. Detect the user's shell RC file:
   ```bash
   if [ "${SHELL:-}" = "$(which zsh 2>/dev/null)" ] || [[ "${SHELL:-}" == */zsh ]]; then
     SHELL_RC="$HOME/.zshrc"
   else
     SHELL_RC="$HOME/.bashrc"
   fi
   echo "Shell RC: $SHELL_RC"
   ```

3. Check if `NTFY_TOPIC` already exists in the RC file. If it does, ask the user if they want to replace it. If not, append:
   ```bash
   if grep -q 'NTFY_TOPIC' "$SHELL_RC" 2>/dev/null; then
     echo "⚠️ NTFY_TOPIC already exists in $SHELL_RC"
   else
     printf '\n# Claude Code Notifications (ntfy)\nexport NTFY_TOPIC="%s"\n' "$TOPIC" >> "$SHELL_RC"
     echo "✅ Written to $SHELL_RC"
   fi
   ```

4. Tell the user:
   - Install the **ntfy app** on their phone (iOS App Store / Google Play)
   - Subscribe to the topic shown above
   - Or open `https://ntfy.sh/<topic>` in a browser
   - Remind them to `source` their shell RC or restart their terminal

---

## Option 2: Change Sound Theme

Show the available themes:

| Theme | Idle | Permission | Complete |
|-------|------|------------|----------|
| `default` | Ping | Basso | Glass |
| `ocean` | Submarine | Sonar | Blow |
| `minimal` | Tink | Pop | Purr |
| `alert` | Hero | Sosumi | Fanfare |

Ask the user to pick one. Then:

1. Detect shell RC file (same as above)
2. Remove any existing `CLAUDE_NOTIFY_THEME` line:
   ```bash
   sed -i.bak '/CLAUDE_NOTIFY_THEME/d' "$SHELL_RC" 2>/dev/null || true
   rm -f "${SHELL_RC}.bak"
   ```
3. Append the new theme:
   ```bash
   echo "export CLAUDE_NOTIFY_THEME=\"<chosen_theme>\"" >> "$SHELL_RC"
   echo "✅ Theme set to <chosen_theme>"
   ```
4. Remind them to `source` their shell RC or restart their terminal.

---

## Option 3: Disable a Provider

Ask which provider to disable (ntfy or Pushover). Then:

1. Detect shell RC file
2. Remove the relevant env var lines:
   - **ntfy:** Remove lines matching `NTFY_TOPIC` and `NTFY_SERVER`
   - **Pushover:** Remove lines matching `PUSHOVER_TOKEN` and `PUSHOVER_USER`
   ```bash
   sed -i.bak '/NTFY_TOPIC\|NTFY_SERVER/d' "$SHELL_RC" 2>/dev/null || true
   rm -f "${SHELL_RC}.bak"
   echo "✅ ntfy removed from $SHELL_RC"
   ```
3. Remind them to restart their terminal for changes to take effect.

---

## Option 4: Test Notifications

Send a test through each active provider:

**ntfy:**
```bash
if [ -n "${NTFY_TOPIC:-}" ]; then
  curl -s \
    -H "Title: Claude Code Test" \
    -H "Tags: white_check_mark" \
    -d "Test notification from Claude Code 🔔" \
    "${NTFY_SERVER:-https://ntfy.sh}/${NTFY_TOPIC}"
  echo "✅ ntfy test sent"
fi
```

**macOS:**
```bash
if command -v osascript &>/dev/null; then
  osascript -e 'display notification "Test notification from Claude Code 🔔" with title "Claude Code" sound name "Ping"'
  echo "✅ macOS test sent"
fi
```

**Pushover:**
```bash
if [ -n "${PUSHOVER_TOKEN:-}" ] && [ -n "${PUSHOVER_USER:-}" ]; then
  curl -s --form-string "token=${PUSHOVER_TOKEN}" \
    --form-string "user=${PUSHOVER_USER}" \
    --form-string "title=Claude Code Test" \
    --form-string "message=Test notification from Claude Code 🔔" \
    https://api.pushover.net/1/messages.json
  echo "✅ Pushover test sent"
fi
```

Report which tests were sent and ask if the user received them.

---

## Step 0: Check for Conflicts (run before Step 1)

Before showing status, check for any notification-related hooks in the user's global or project settings that might clash with this plugin. This plugin should be the **single source of truth** for notifications.

```bash
echo "=== Checking for conflicting notification config ==="

# Check global settings
if [ -f "$HOME/.claude/settings.json" ]; then
  # Look for Notification hooks outside this plugin
  if grep -q '"Notification"' "$HOME/.claude/settings.json" 2>/dev/null; then
    echo "⚠️  Found Notification hooks in ~/.claude/settings.json"
    echo "   These may conflict with the notifications plugin."
    cat "$HOME/.claude/settings.json" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    hooks=d.get('hooks',{}).get('Notification',[])
    if hooks:
        print('   Hooks found:')
        for h in hooks:
            for hook in h.get('hooks',[]):
                print(f\"     - {hook.get('type','?')}: {hook.get('command',hook.get('prompt',''))[:60]}\")
except: pass
" 2>/dev/null
  fi
fi

# Check project settings
if [ -f ".claude/settings.json" ]; then
  if grep -q '"Notification"\|"Stop"\|"TaskCompleted"' ".claude/settings.json" 2>/dev/null; then
    echo "⚠️  Found notification-related hooks in .claude/settings.json (project)"
  fi
fi

# Check for conflicting env vars from other tools
for var in CLAUDE_NOTIFY_SOUND CLAUDE_NOTIFY_SOUND_IDLE CLAUDE_NOTIFY_SOUND_PERMISSION CLAUDE_NOTIFY_SOUND_COMPLETE; do
  if [ -n "${!var:-}" ]; then
    echo "ℹ️  Individual sound override active: $var=${!var}"
  fi
done
```

If conflicts are found, inform the user and offer to help clean them up (remove conflicting hooks from settings.json so the plugin is the single source of truth).

---

## Behavior Notes

- Be conversational. Ask one question at a time, wait for the user to answer.
- After completing any option, ask if they'd like to do anything else.
- Always check for existing entries before appending (idempotent).
- Use `sed -i.bak` + `rm .bak` for portable in-place editing (macOS sed compatibility).
- This plugin is the **single source of truth** for notifications. If conflicting notification hooks exist in settings files, offer to remove them.
