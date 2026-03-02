# Changelog

## 0.2.0 — 2026-03-02

- Add sound themes: `default`, `ocean`, `minimal`, `alert`
- `CLAUDE_NOTIFY_THEME` env var for theme selection
- Sound resolution priority: per-event > theme > global > built-in
- Interactive theme picker in `setup.sh`
- Custom per-event sound prompts in setup
- Updated `config.example.json` with theme field

## 0.1.0 — 2026-03-02

- Initial release
- Providers: macOS native, ntfy.sh, Pushover
- Hooks: Notification, Stop, TaskCompleted
- Zero-config: auto-detects macOS, env vars for push providers
- `setup.sh` for secure ntfy topic generation
