# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BuddyDesk is a Windows desktop AI companion app (Python/PySide6) featuring a Dynamic Island, pixel pet, AI chat with command execution, and Claude Code CLI integration. **This is the integrated final release** — taking the best of two independently generated v1 versions and unifying on the chubby orange cat sprite pack.

**Core Innovation**: AI understands natural language commands ("打开微信", "查看IP") and executes them via a command engine that parses special tags from AI responses.

## Quick Commands

```bash
python main.py                          # Run the app
pip install -r requirements.txt         # Install dependencies
python -m unittest discover tests -v    # Run tests
python -m unittest tests.test_config    # Run a single test file
```

## Integration History

This codebase was assembled by merging two v1 candidates (hermes-pet-win and hermes-pet-win-副本-副本), each generated independently by a different model. See `FINAL_REPORT.md` for the per-file decision matrix. Key choices:

- **dynamic_island.py**: kept the v1-A implementation (`_IslandGroup` opacity cross-fade, no setMask, auto-collapse timer added in integration)
- **chat_window.py**: merged (v1-A's hover action buttons + Ctrl+L/R shortcuts + cat avatar in chat header + v1-B's `MarkdownRenderer` for streaming AI bubbles)
- **pixel_pet.py**: rewritten — uses 72 frames from `assets/cat_frames_v2/`, single-frame states are statically drawn (no per-tick setPixmap, no breath bob) to eliminate the "flicker" reported in v1
- **launcher.py / theme.py / config.py / bridge.py / ai/ / engine/**: kept from v1-A (more design tokens, Claude CLI detection, complete README)
- **assets/**: removed the small `pet_reference.png` (rejected as "尺寸偏小、观感不佳") and adopted v1-B's `cat_frames_v2/` 72-frame sprite sheet derived from `chubby-orange-cat.webp`

## Architecture

### UI Framework: PySide6

All UI uses **PySide6** (Qt for Python). The app was migrated from tkinter. Key patterns:
- Frameless translucent windows with dark glass aesthetic
- `QPropertyAnimation` with `QEasingCurve.OutBack` for spring animations
- `QPainter` custom painting for dynamic island capsule; `QPixmap` for pet sprites
- `_IslandGroup` (opacity-based cross-fade) on the dynamic island
- Signals/slots for thread-safe AI → UI communication via `bridge.py`

### Data Flow

```
main.py (HermesPetApp)
    ↓ LauncherDialog → user selects backend & config
    ↓ Creates: AIBridge (wraps AI + EventEngine), CommandEngine
    ↓
User types message → ChatWindow._send()
    ↓ bridge.send(messages) → background thread
    ↓ AI streams chunks via bridge.chunk_received signal
    ↓ ChatWindow._on_chunk() updates _live_widget via direct ref
    ↓ bridge.stream_done → main._process_commands()
    ↓ command_engine.parse_and_execute() extracts [APP:/SHELL:/CLAUDE:] tags
    ↓ Results shown via chat.append_command_result()
```

### Dynamic Island

`ui/dynamic_island.py` — top-of-screen capsule with 5 states:
- `idle / thinking / result / notify / error`
- `_IslandGroup` per state with its own `QGraphicsOpacityEffect` for cross-fade
- 200ms size + opacity transition, 4-5s auto-collapse to idle for transient states
- Painted entirely with `QPainter` (no `setMask` — avoids edge jaggies)

### Pixel Pet (chubby orange cat)

`ui/pixel_pet.py` — 7 states mapped to `assets/cat_frames_v2/frame_XX.png`:
- `idle` (frame_00), `walk` (frame_08-11, 4 frames), `happy` (frame_24-27, 4 frames), `sleep` (frame_48), `love` (frame_24-25), `thinking` (frame_64), `error` (frame_40)
- Single-frame states draw once and never call setPixmap again (anti-flicker rule)
- Walk: 4 frames at 10 FPS + horizontal scroll + auto-mirror on direction change
- ZZZ floaters during sleep, hearts during love
- Drag with spring easing

### Command Tag System

The AI system prompt (`ai/backend.py:SYSTEM_PROMPT`) instructs the model to emit tags:
- `[APP:应用名]` → AppRegistry.find_app() → subprocess.Popen
- `[SHELL:命令]` → subprocess.run(shell=True, timeout=30s)
- `[CLAUDE:指令]` → claude CLI --print (timeout=120s)

`AppRegistry` maintains Windows/Mac/Linux app lookup dicts. Dangerous commands blocked by regex.

### AI Backend

`ai/backend.py` — `AIBackend` ABC with two implementations:
- `ClaudeCodeBackend`: local `claude` CLI, streaming then fallback
- `OpenAIBackend`: OpenAI-compatible API (DeepSeek, NVIDIA, Ollama, etc.)

### Threading

- AI calls in `threading.Thread(daemon=True)` via `bridge.send()`
- `AIBridge` uses Qt signals to marshal results to main thread
- `EventEngine` uses `threading.Lock` for thread-safe recording

### Config

Persistent data under `~/.hermes_pet_win/`:
- `config.json` — user settings (deep-merged with defaults)
- `conversations.json`, `jobs.json`, `events.log`

UI design tokens in `theme.py` (colors, fonts, shadow tiers, easing). Layout constants in `config.py`.

## Dependencies

```
PySide6>=6.6.0      # Qt framework (primary UI)
openai>=1.0.0       # OpenAI API client
Pillow>=10.0.0      # Image loading fallback (optional)
keyboard>=0.13.5    # Global hotkeys
pystray>=0.19.5     # System tray (fallback)
```
