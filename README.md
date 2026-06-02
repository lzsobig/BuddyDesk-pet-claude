<div align="center">

<img src="assets/cat_frames_v2/preview_idle.png" width="80" alt="BuddyDesk Cat">

# BuddyDesk

### Windows 桌面 AI 伴侣

快捷键一按，AI 即来。说"打开微信"就能打开，说"查看IP"就能执行。

<br>

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![PySide6](https://img.shields.io/badge/PySide6-Qt_for_Python-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![License: MIT](https://img.shields.io/badge/License-MIT-5CB89A?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows_10%2F11-0078D4?style=for-the-badge&logo=windows&logoColor=white)]()
[![GitHub Stars](https://img.shields.io/github/stars/lzsobig/hermes-pet-win?style=for-the-badge&logo=github)](https://github.com/lzsobig/hermes-pet-win/stargazers)

<br>

**[English](#features) · [中文](#features-1)**

</div>

---

<div align="center">

### "AI 工具界有个不成文的规则：越专业，界面越严肃。但当你面对一只像素橘猫的时候，你不会觉得'这个问题太蠢了不好意思问'。"

</div>

---

## Features

> **Dynamic Island** · **Pixel Pet** · **Command Execution** · **Multi-Conversation** · **Claude Code Integration**

### Dynamic Island

屏幕顶部的浮动胶囊是 AI 的存在证明。五种状态，实时反馈：

| State | Appearance | Trigger |
|:------|:-----------|:--------|
| `idle` | Green pulsing dot + cat emoji | Default |
| `thinking` | Spinning ring + bouncing dots | AI processing |
| `result` | Green checkmark + task complete | Task finished |
| `notify` | Gold bell + reminder text | Notification |
| `error` | Red cross + error info | Error occurred |

> All-Paint architecture — zero child widgets, single QTimer, QPainterPath anti-aliased edges.

### Pixel Pet

一只 128px 像素橘猫陪你工作：

| State | Description |
|:------|:------------|
| `idle` | 静静待着 |
| `walk` | 桌面闲逛，自动转向 |
| `happy` | 开心跳动 |
| `sleep` | 打瞌睡，ZZZ 飘浮 |
| `love` | 冒爱心 |
| `thinking` | 跟着 AI 一起思考 |
| `error` | 出错时心疼你 |

> 72 帧精灵图 + spring easing 拖拽 + 双击打开聊天

### Command Execution — The Killer Feature

AI 不只是聊天，**能直接操作你的电脑**：

```
你: 打开微信
AI: 好的，帮你打开微信~ [APP:微信]
   已打开: 微信
```

| 你说 | AI 做什么 |
|:-----|:----------|
| "打开微信" | 启动微信 |
| "打开Chrome" | 启动浏览器 |
| "查看IP地址" | 执行 `ipconfig` |
| "帮我创建一个React项目" | 调用 Claude Code |
| "把这个文件重构一下" | Claude Code 直接操作 |

> AI 回复中的标签（`[APP:微信]`、`[SHELL:dir]`、`[CLAUDE:...]`）由引擎自动解析执行。

---

## Quick Start

### Option 1 — One-Click (Recommended)

Double-click `启动 BuddyDesk.bat` in the project directory. It auto-installs dependencies on first run.

### Option 2 — Manual

```bash
pip install -r requirements.txt
python main.py
```

### Option 3 — Silent Launch

Double-click `启动 BuddyDesk.vbs` — no terminal window.

---

## AI Backend

<div align="center">

| Backend | Setup | Best For |
|:--------|:------|:---------|
| **Claude Code** | Zero config (needs `claude` CLI) | System operations, coding tasks |
| **OpenAI API** | Paste API key | DeepSeek, NVIDIA, Ollama, etc. |

</div>

<details>
<summary><b>Supported API Platforms (Click to expand)</b></summary>

| Platform | Base URL |
|:---------|:---------|
| OpenAI | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| NVIDIA | `https://integrate.api.nvidia.com/v1` |
| SiliconFlow | `https://api.siliconflow.cn/v1` |
| Moonshot | `https://api.moonshot.cn/v1` |
| Ollama (local) | `http://localhost:11434/v1` |

</details>

---

## Controls

<div align="center">

| Action | Effect |
|:-------|:-------|
| `Ctrl+F` | Toggle chat window |
| Click island | Open chat |
| Double-click pet | Open chat |
| Drag pet | Move position |
| Hover island | State preview |
| "打开XXX" | Launch app |
| "查看XXX" | Run command |
| "帮我XXX" | Claude Code task |

</div>

---

## Architecture

```
User Input
    │
    ▼
ChatWindow._send()
    │
    ▼
AIBridge.send() ──► Background Thread
    │                      │
    │              AI Backend streams chunks
    │                      │
    ▼                      ▼
chunk_received signal ◄────┘
    │
    ▼
ChatWindow renders in real-time
    │
    ▼
stream_done signal
    │
    ▼
CommandEngine parses [APP:/SHELL:/CLAUDE:] tags
    │
    ▼
Execute → Show result in chat
```

<div align="center">

| Component | Technology |
|:----------|:-----------|
| UI Framework | PySide6 (Qt for Python) |
| Dynamic Island | QPainter All-Paint |
| Pet Animation | 72-frame sprite sheet + QPropertyAnimation |
| AI Backend | Claude Code CLI / OpenAI API |
| Hotkey | ctypes GetAsyncKeyState polling |
| Config | JSON (`~/.buddydesk/`) |
| Testing | pytest |

</div>

---

## Project Structure

```
buddydesk/
├── main.py                     # Entry point (BuddyDeskApp)
├── bridge.py                   # Qt Signal Bridge (AI → UI)
├── config.py                   # Persistent config (~/.buddydesk/)
├── theme.py                    # Design tokens (colors, fonts, radius)
├── 启动 BuddyDesk.bat          # One-click launcher
│
├── ai/
│   └── backend.py              # Claude Code / OpenAI backends
│
├── engine/
│   ├── command_engine.py       # [APP:/SHELL:/CLAUDE:] parser
│   └── event_engine.py         # Event recording
│
├── ui/
│   ├── dynamic_island.py       # All-Paint island (5 states)
│   ├── pixel_pet.py            # 72-frame pixel cat
│   ├── chat_window.py          # Multi-tab chat + Markdown
│   ├── markdown_renderer.py    # Streaming Markdown renderer
│   ├── launcher.py             # Config dialog
│   └── tray.py                 # System tray
│
├── assets/
│   ├── cat_frames_v2/          # 81 sprite frames
│   └── icons/                  # SVG icons
│
└── tests/
    └── test_*.py               # Unit tests
```

---

## Roadmap

- [x] Dynamic Island + Pixel Pet + Hotkey
- [x] Natural language command execution
- [x] Dual backend (Claude Code + OpenAI API)
- [x] Multi-conversation tabs + persistence
- [x] One-click launcher
- [ ] Plugin system (community skins, custom commands)
- [ ] Voice interaction
- [ ] Pet learning (proactive reminders)
- [ ] Cross-platform (macOS / Linux)

---

## Acknowledgements

Inspired by [HermesPet](https://github.com/nicepkg/HermesPet) for macOS

UI design: Dynamic Island + Glass Morphism style

Pixel cat sprite derived from [chubby-orange-cat](assets/chubby-orange-cat.webp)

---

<div align="center">

**Made with Python and love for pixel cats**

MIT License · 2026

</div>
