# Design Brief: Hermes Pet Win — UI Overhaul

## Project
Hermes Pet Win — a Windows desktop AI companion app (Python/PySide6) with:
- **Dynamic Island**: floating status capsule at top of screen
- **Chat Window**: AI chat with streaming, command execution
- **Launcher**: startup config dialog (backend selection, API keys)
- **Pixel Pet**: small cat sprite on desktop

## What to redesign
Three UI surfaces need deep visual optimization:

### 1. Chat Window (`ui/chat_window.py`)
Current: flat dark background, basic text, no visual hierarchy.
Goal: premium dark glass aesthetic. Think macOS Messages meets ChatGPT desktop.
- Message bubbles with real visual weight (not just colored text)
- Smooth streaming animation
- Command execution results styled as inline cards
- Input area with subtle glow on focus

### 2. Launcher (`ui/launcher.py`)
Current: basic form with radio buttons.
Goal: sleek startup screen. Think iOS settings meets a premium SaaS onboarding.
- Visual hierarchy between sections
- Backend cards that feel like real cards (shadow, hover states)
- Launch button that feels alive (gradient, pulse on hover)
- Cat emoji header that's charming, not cheap

### 3. Dynamic Island (`ui/dynamic_island.py`)
Current: black capsule with text.
Goal: iOS Dynamic Island quality. Think about:
- The capsule should feel like it's floating (subtle shadow beneath)
- Breathing dot should be mesmerizing
- Companion phrases should feel warm and personal
- Expand/collapse should feel physical (spring physics already there, polish it)
- Three-dot loader should match iOS quality

## Tech Stack
- Python 3.12 + PySide6 (Qt for Python)
- QPainter for custom painting
- QSS (Qt Style Sheets) for widget styling
- QPropertyAnimation for animations
- No external image assets — everything code-drawn
- Windows 11 target

## Design Direction
- **Pure black** (#080810 range) as base, NOT blue/purple
- **Single accent**: cyan (#7dd3fc) — sparingly used
- **Typography**: Segoe UI with intentional weight/size hierarchy
- **Micro-interactions**: everything should respond to hover/focus
- **Density**: information-dense but not cluttered
- **iOS Dynamic Island** as the north star for the island

## Constraints
- Must work on Windows 11 (no macOS-only APIs)
- No external dependencies beyond PySide6 + PIL
- Frameless windows (custom title bar behavior)
- All text must be clearly readable (no low-contrast)

## Files to modify
- `C:\Users\李振\Desktop\hermes-pet-win - 副本\ui\chat_window.py`
- `C:\Users\李振\Desktop\hermes-pet-win - 副本\ui\launcher.py`
- `C:\Users\李振\Desktop\hermes-pet-win - 副本\ui\dynamic_island.py`
- `C:\Users\李振\Desktop\hermes-pet-win - 副本\theme.py` (design tokens)
