# 🔔 Notifications Plugin

Get notified when Claude Code needs your attention, finishes a task, or stops. Supports macOS native notifications, [ntfy.sh](https://ntfy.sh) push notifications (any device), and [Pushover](https://pushover.net). Zero config on macOS — just install and go. For mobile push, run `/notifications:configure`.

## Quick Start

```bash
# 1. Install the plugin (symlink or copy into your Claude Code plugins dir)
ln -s /path/to/agentic-primitives/plugins/notifications ~/.claude/plugins/notifications

# 2. (Optional) Configure push notifications interactively
#    In Claude Code, run the slash command:
/notifications:configure

# 3. Done. Claude Code will notify you automatically.
```

## `/notifications:configure` Command

Run `/notifications:configure` inside Claude Code for an interactive setup experience. It will:

1. **Show current status** — which providers are active, current sound theme
2. **Set up ntfy push** — generates a secure topic, writes to your shell RC
3. **Change sound theme** — pick from 4 themes (default/ocean/minimal/alert)
4. **Disable a provider** — cleanly remove env vars from your shell RC
5. **Test notifications** — send a test through each active provider

## First Run

On **macOS**, notifications work immediately — no setup required. Native desktop notifications fire automatically.

On **Linux/remote machines**, the plugin prompts you on first session start to run `/notifications:configure`.

## Hooked Events

| Event | Emoji | When |
|-------|-------|------|
| `Notification` | 🟡 | Claude is idle or needs permission |
| `Stop` | 🟢 | Session stopped |
| `TaskCompleted` | 🟢 | Task finished |

## Providers

### macOS Native (auto-detected)

If `osascript` is available, you get native macOS notifications with sound. No config needed.

### ntfy.sh

Free, open-source push notifications. Works on iOS, Android, and web.

1. Run `/notifications:configure` and choose "Set up ntfy push"
2. Subscribe to your topic in the [ntfy app](https://ntfy.sh)
3. Notifications arrive on all your devices

### Pushover

Paid push notification service with rich features.

Set `PUSHOVER_TOKEN` and `PUSHOVER_USER` to enable.

## 🎵 Sound Themes (macOS)

Choose a theme to change all notification sounds at once, or override individually.

### Available Themes

| Theme | Idle | Permission | Complete |
|-------|------|------------|----------|
| `default` | Ping | Basso | Glass |
| `ocean` | Submarine | Sonar | Blow |
| `minimal` | Tink | Pop | Purr |
| `alert` | Hero | Sosumi | Fanfare |

### Setting a Theme

Run `/notifications:configure` and choose "Change sound theme", or set manually:

```bash
export CLAUDE_NOTIFY_THEME="ocean"
```

### Sound Resolution Priority

Sounds are resolved in this order (highest priority first):

1. **Per-event override** — `CLAUDE_NOTIFY_SOUND_IDLE`, `CLAUDE_NOTIFY_SOUND_PERMISSION`, `CLAUDE_NOTIFY_SOUND_COMPLETE`
2. **Theme** — `CLAUDE_NOTIFY_THEME` maps to a set of three sounds
3. **Global sound** — `CLAUDE_NOTIFY_SOUND` applies to all events
4. **Built-in defaults** — same as the `default` theme (Ping / Basso / Glass)

### Custom Per-Event Sounds

Override individual sounds while using a theme for the rest:

```bash
export CLAUDE_NOTIFY_THEME="ocean"
export CLAUDE_NOTIFY_SOUND_COMPLETE="Fanfare"  # overrides just the complete sound
```

### Available macOS Sounds

Basso, Blow, Bottle, Frog, Funk, Glass, Hero, Morse, Ping, Pop, Purr, Sosumi, Submarine, Tink, Sonar, Fanfare

You can also use any `.aiff` file in `/System/Library/Sounds/`.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NTFY_TOPIC` | *(unset)* | ntfy topic name — enables ntfy provider when set |
| `NTFY_SERVER` | `https://ntfy.sh` | ntfy server URL (for self-hosted) |
| `PUSHOVER_TOKEN` | *(unset)* | Pushover API token — enables pushover when both set |
| `PUSHOVER_USER` | *(unset)* | Pushover user key |
| `CLAUDE_NOTIFY_THEME` | *(unset)* | Sound theme: `default`, `ocean`, `minimal`, or `alert` |
| `CLAUDE_NOTIFY_SOUND` | `Ping` | macOS notification sound name (global fallback) |
| `CLAUDE_NOTIFY_SOUND_IDLE` | *(unset)* | Override sound for idle notifications |
| `CLAUDE_NOTIFY_SOUND_PERMISSION` | *(unset)* | Override sound for permission requests |
| `CLAUDE_NOTIFY_SOUND_COMPLETE` | *(unset)* | Override sound for task completion |
| `CLAUDE_NOTIFY_MACHINE` | `$(hostname)` | Machine identifier in notification messages |

## Message Format

**Push providers** (ntfy, Pushover) show the full formatted message:

```
my-machine: 🟡 Notification — Needs permission to run command
my-machine: 🟢 TaskCompleted — Task completed
```

**macOS native** notifications display differently due to system constraints: the title is always "Claude Code", the subtitle shows the event type (e.g., "Notification"), and the body shows the summary text.

## Config File (Optional)

For power users, see `config.example.json`. Environment variables always take precedence.

## Security

⚠️ **ntfy topics are public by default.** Anyone who knows your topic name can read your notifications. The `/notifications:configure` command generates a topic with 64 random hex characters — this makes it unguessable (256 bits of entropy). For sensitive environments, consider [self-hosting ntfy](https://docs.ntfy.sh/install/) with access control.
