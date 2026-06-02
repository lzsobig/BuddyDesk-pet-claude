<p align="center">
  <img src="assets/cat_frames_v2/preview_idle.png" width="100" alt="BuddyDesk">
</p>

<h1 align="center">BuddyDesk</h1>

<p align="center">
  <strong>Windows 桌面 AI 伴侣</strong><br>
  灵动岛 · 像素橘猫 · 自然语言命令执行 · Claude Code 集成
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PySide6-Qt_for_Python-41CD52?style=flat-square&logo=qt&logoColor=white" alt="PySide6">
  <img src="https://img.shields.io/badge/License-MIT-5CB89A?style=flat-square" alt="MIT">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D4?style=flat-square&logo=windows&logoColor=white" alt="Windows">
</p>

<p align="center">
  快捷键一按，AI 即来。<br>
  说"打开微信"就能打开，说"查看IP"就能执行。<br>
  纯 Python，零 Electron，零 Node.js。
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> · <a href="#features">Features</a> · <a href="#architecture">Architecture</a> · <a href="#roadmap">Roadmap</a>
</p>

---

## Why BuddyDesk

> AI 工具界有个不成文的规则：越专业，界面越严肃。但当你面对一只像素橘猫的时候，你不会觉得"这个问题太蠢了不好意思问"。

BuddyDesk 不是另一个聊天框。它住在你的桌面上 —— 顶部有灵动岛，角落有像素猫，快捷键一按就来，说完就走。

---

## Features

<table>
<tr>
<td width="33%" valign="top">
<h3>🏝️ Dynamic Island</h3>
屏幕顶部的浮动胶囊。5 种状态实时反馈：<br>
<code>idle</code> <code>thinking</code> <code>result</code> <code>notify</code> <code>error</code><br><br>
All-Paint 架构 — 所有动画在 paintEvent 中绘制，零子控件，QPainterPath 抗锯齿。
</td>
<td width="33%" valign="top">
<h3>🐱 Pixel Pet</h3>
一只 128px 像素橘猫陪你工作。<br>
7 种状态，72 帧精灵图。<br><br>
闲逛 · 眨眼 · 睡觉 · 冒爱心 · 跟着 AI 一起思考。<br>
拖拽移动，双击打开聊天。
</td>
<td width="33%" valign="top">
<h3>⚡ Command Execution</h3>
AI 不只是聊天，<b>能直接操作你的电脑</b>。<br><br>
<code>[APP:微信]</code> 启动应用<br>
<code>[SHELL:dir]</code> 执行命令<br>
<code>[CLAUDE:...]</code> Claude Code
</td>
</tr>
<tr>
<td width="33%" valign="top">
<h3>💬 Multi-Conversation</h3>
多对话标签栏，新建 / 切换 / 关闭。<br><br>
自动从首条消息生成标题。<br>
关闭时保存，启动时恢复。
</td>
<td width="33%" valign="top">
<h3>🤖 Claude Code</h3>
本地安装了 Claude Code CLI？<br>
<b>零配置</b>，打开就用。<br><br>
编程 · 重构 · 项目创建，一句话搞定。
</td>
<td width="33%" valign="top">
<h3>🔌 Multi-Backend</h3>
DeepSeek / NVIDIA / 硅基流动 /<br>
Moonshot / Ollama 一键预设。<br><br>
填一个 API Key，选个模型，开聊。
</td>
</tr>
</table>

---

## How It Works

```
你: 打开微信
AI: 好的，帮你打开微信~  [APP:微信]
   已打开: 微信

你: 查看 IP 地址
AI: 正在查询...  [SHELL:ipconfig]
   IPv4: 192.168.1.xxx

你: 帮我写一个贪吃蛇
AI: 让 Claude Code 来帮你！  [CLAUDE:创建贪吃蛇游戏]
   snake_game.py 已创建
```

---

## Quick Start

<details open>
<summary><b>One-Click Launch</b> (recommended)</summary>

<br>

双击 `启动 BuddyDesk.bat` — 自动检测 Python、安装依赖、启动应用。

静默版（无命令行窗口）：双击 `启动 BuddyDesk.vbs`

</details>

<details>
<summary><b>Manual Setup</b></summary>

```bash
# Clone
git clone https://github.com/lzsobig/BuddyDesk-pet-win.git
cd BuddyDesk-pet-win

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

</details>

<details>
<summary><b>AI Backend Configuration</b></summary>

**Option A: Claude Code (Recommended)**
- Install [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- Launch BuddyDesk → Select "Claude Code" → Done

**Option B: OpenAI API**
- Get an API key from any supported platform
- Launch BuddyDesk → Select "OpenAI API" → Paste key → Choose model

| Platform | Base URL |
|----------|----------|
| OpenAI | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| NVIDIA | `https://integrate.api.nvidia.com/v1` |
| SiliconFlow | `https://api.siliconflow.cn/v1` |
| Moonshot | `https://api.moonshot.cn/v1` |
| Ollama | `http://localhost:11434/v1` |

</details>

---

## Controls

| Action | Effect |
|--------|--------|
| `Ctrl+F` | Toggle chat window |
| Click island | Open chat |
| Double-click pet | Open chat |
| Drag pet | Move position |
| Hover island | Preview state |
| "打开XXX" | Launch app |
| "查看XXX" | Run command |
| "帮我XXX" | Claude Code task |

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  User Input │────▶│  ChatWindow  │────▶│   AIBridge    │
└─────────────┘     └──────────────┘     └───────┬───────┘
                                                  │
                    ┌──────────────┐              │ Thread
                    │ CommandEngine│◀─────────────┤
                    └──────┬───────┘              │
                           │                      ▼
                    ┌──────▼───────┐     ┌───────────────┐
                    │  [APP:xxx]   │     │  AI Backend   │
                    │  [SHELL:xxx] │     │  Claude/OpenAI│
                    │  [CLAUDE:xxx]│     └───────────────┘
                    └──────────────┘
```

| Component | Technology |
|-----------|-----------|
| UI Framework | PySide6 (Qt for Python) |
| Dynamic Island | QPainter All-Paint |
| Pet Animation | 72-frame sprite sheet |
| AI Backend | Claude Code CLI / OpenAI API |
| Hotkey | ctypes GetAsyncKeyState |
| Config | JSON (`~/.buddydesk/`) |
| Testing | pytest |

---

## Project Structure

```
buddydesk/
├── main.py                     # Entry point
├── bridge.py                   # Qt Signal Bridge
├── config.py                   # Config (~/.buddydesk/)
├── theme.py                    # Design tokens
├── 启动 BuddyDesk.bat          # One-click launcher
│
├── ai/
│   └── backend.py              # AI backends + system prompt
│
├── engine/
│   ├── command_engine.py       # Tag parser & executor
│   └── event_engine.py         # Event recorder
│
├── ui/
│   ├── dynamic_island.py       # All-Paint island
│   ├── pixel_pet.py            # Pixel cat (72 frames)
│   ├── chat_window.py          # Multi-tab chat
│   ├── markdown_renderer.py    # Streaming Markdown
│   ├── launcher.py             # Config dialog
│   └── tray.py                 # System tray
│
├── assets/
│   ├── cat_frames_v2/          # Sprite frames
│   └── icons/                  # SVG icons
│
└── tests/
```

---

## Roadmap

| Status | Feature | Description |
|--------|---------|-------------|
| ✅ | Dynamic Island | 5-state floating capsule |
| ✅ | Pixel Pet | 72-frame animated cat |
| ✅ | Command Execution | Natural language → system action |
| ✅ | Dual Backend | Claude Code + OpenAI API |
| ✅ | Multi-Conversation | Tab bar + persistence |
| ✅ | One-Click Launcher | .bat + .vbs |
| 🔜 | Plugin System | Community skins & commands |
| 🔜 | Voice Interaction | Talk to your pet |
| 🔜 | Pet Learning | Proactive reminders |
| 🔜 | Cross-Platform | macOS / Linux |

---

<p align="center">
  <img src="assets/cat_frames_v2/preview_wave.png" width="80" alt="wave">
  <br><br>
  <b>Made with Python and love for pixel cats</b><br>
  <sub>Inspired by <a href="https://github.com/nicepkg/HermesPet">HermesPet</a> for macOS</sub>
</p>
