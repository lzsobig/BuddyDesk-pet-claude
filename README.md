<p align="center">
  <img src="assets/cat_frames_v2/preview_idle.png" width="80" alt="BuddyDesk">
</p>

<h1 align="center">BuddyDesk</h1>

<p align="center">
  <strong>Windows 桌面 AI 伴侣</strong><br>
  灵动岛 · 像素橘猫 · 自然语言命令执行 · Claude Code 集成
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D4?style=flat-square&logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PySide6-Qt-41CD52?style=flat-square&logo=qt&logoColor=white" alt="PySide6">
  <img src="https://img.shields.io/badge/License-MIT-5CB89A?style=flat-square" alt="MIT">
</p>

---

## What is BuddyDesk

BuddyDesk 是一个住在 Windows 桌面上的 AI 助手。不是浏览器里的聊天框，也不是托盘里的图标——是一只**像素橘猫**，安静地待在桌面上，按一个快捷键就来，说完就走。

**核心能力：**

- 🏝️ **灵动岛** — 屏幕顶部浮动状态胶囊，AI 思考时脉动，任务完成时展开
- 🐱 **像素宠物** — 72 帧动画橘猫，闲逛、眨眼、跳跃，可拖拽
- ⚡ **自然语言命令** — 说"打开微信"就启动，说"查看 IP"就执行
- 🤖 **Claude Code 集成** — 已安装 CLI 零配置直接用
- 🔌 **多后端** — DeepSeek / NVIDIA / 硅基流动 / Moonshot / Ollama

---

## Screenshots

<table>
<tr>
<td align="center"><strong>启动配置</strong><br><img src="docs/images/launcher.png" width="280"></td>
<td align="center"><strong>灵动岛</strong><br><img src="docs/images/island_thinking.png" width="280"></td>
<td align="center"><strong>命令执行</strong><br><img src="docs/images/chat_commands.png" width="280"></td>
</tr>
<tr>
<td align="center"><strong>聊天界面</strong><br><img src="docs/images/chat_full.png" width="280"></td>
<td align="center"><strong>像素猫 · 待机</strong><br><img src="docs/images/cat_idle.png" width="120"></td>
<td align="center"><strong>像素猫 · 开心</strong><br><img src="docs/images/cat_happy.png" width="120"></td>
</tr>
</table>

---

## Quick Start

**1. 克隆**

```bash
git clone https://github.com/lzsobig/BuddyDesk-pet-claude.git
cd BuddyDesk-pet-claude
```

**2. 启动**

双击 `启动 BuddyDesk.bat`（自动检测 Python、安装依赖、启动）

或双击 `启动 BuddyDesk.vbs`（无命令行窗口）

**3. 选择后端**

| 后端 | 说明 | 配置 |
|------|------|------|
| Claude Code | 已安装 CLI → 零配置直接用 | ⭐ |
| OpenAI API | DeepSeek / NVIDIA / 硅基流动 / Moonshot / Ollama | ⭐⭐ |

---

## Usage

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Shift+H` | 呼出 / 隐藏 AI |
| `Ctrl+F` | 切换聊天窗口 |
| 点击灵动岛 | 打开聊天 |
| 双击像素猫 | 打开聊天 |
| 拖拽像素猫 | 移动位置 |

---

## Architecture

```
User Input → ChatWindow → AIBridge → AI Backend (Claude / OpenAI)
                    ↓
              CommandEngine
              ├── [APP:xxx]     启动应用
              ├── [SHELL:xxx]   执行命令
              └── [CLAUDE:xxx]  调用 Claude Code
```

| Component | Tech |
|-----------|------|
| UI Framework | PySide6 (Qt for Python) |
| Dynamic Island | QPainter All-Paint |
| Pet Animation | 72-frame sprite sheet |
| Hotkey | ctypes GetAsyncKeyState |
| Config | JSON (`~/.buddydesk/`) |

---

## Requirements

- Windows 10 / 11
- Python 3.10+（启动脚本会自动安装）

---

## FAQ

**Q：会执行危险命令吗？**
不会。三级安全机制：打开应用直接执行，系统命令展示结果，危险操作必须手动确认。

**Q：需要会编程吗？**
完全不需要。

**Q：数据会上传吗？**
Claude Code 走 Anthropic API，OpenAI 模式走你自己的 API Key，本地 Ollama 完全离线。

---

<p align="center">
  <img src="assets/cat_frames_v2/preview_wave.png" width="80" alt="wave">
  <br><br>
  <b>Made with Python and love for pixel cats</b><br>
  <sub>Inspired by <a href="https://github.com/nicepkg/HermesPet">HermesPet</a> for macOS</sub>
</p>
