# BuddyDesk - Changelog

## v0.2.0 (2026-06-02)

### Breaking Changes
- Renamed from "Hermes Pet Win" to **BuddyDesk**
- Config directory moved from `~/.hermes_pet_win/` to `~/.buddydesk/`
- Hotkey changed from `Ctrl+Shift+H` to `Ctrl+F`
- Replaced `keyboard` library with `ctypes.GetAsyncKeyState` (no admin required)

### Features
- **Dynamic Island All-Paint rewrite**: All states drawn in `paintEvent`, single QTimer, zero child widgets
- **Multi-conversation tabs**: Create, switch, close, and rename conversations
- **Conversation persistence**: All conversations auto-saved, restored on restart
- **One-click launcher**: `启动 BuddyDesk.bat` + silent `.vbs` version
- **Windows DPI awareness**: Per-Monitor V2 for crisp rendering on high-DPI displays
- **Pet state sync**: Thinking/error states synced between island and pet
- **Chat UI improvements**: Transparent rounded corners, glass morphism, QSS override fix

### Bug Fixes
- Fixed `*.png` gitignore blocking sprite assets in `assets/`
- Fixed chat window QSS solid background overriding transparent corners
- Removed redundant `_apply_rounded_mask` on resize event

## v0.1.0 (2026-05-31)

### Features
- Dynamic Island: Top-screen floating capsule with 5 states (idle/thinking/result/notify/error)
- Pixel Pet: Desktop pixel cat with idle/walk/sleep/happy/love/thinking/error states
- AI Chat: Markdown rendering, streaming output, file attachments
- Command Engine: Natural language command execution via `[APP:/SHELL:/CLAUDE:]` tags
- Dual Backend: Claude Code CLI + OpenAI-compatible API (DeepSeek, NVIDIA, Ollama, etc.)
- Event Engine: Event recording and state tracking
- System Tray: Tray icon with state indicator
- Global Hotkeys: Quick chat access
- Launcher: AI backend selection and configuration dialog
