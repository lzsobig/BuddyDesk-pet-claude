<div align="center">

# BuddyDesk

**Windows 桌面 AI 伴侣** — 灵动岛 + 像素橘猫 + 命令执行

快捷键一按，AI 即来。说"打开微信"就能打开，说"查看IP"就能执行。

纯 Python (PySide6/Qt) 实现，零 Electron，零 Node.js。

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![PySide6](https://img.shields.io/badge/PySide6-Qt%20for%20Python-41cd52?style=flat-square&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![License: MIT](https://img.shields.io/badge/License-MIT-5cb89a?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078d4?style=flat-square&logo=windows&logoColor=white)]()

</div>

---

## Features

### Dynamic Island — AI 的脸

屏幕顶部浮动胶囊，5 种状态实时反馈：

| 状态 | 表现 |
|------|------|
| **Idle** | 绿色脉动圆点 + 猫咪 emoji + "小橘待命中" |
| **Thinking** | 旋转加载环 + "正在思考" + 弹跳指示点 |
| **Result** | 绿色勾号 + 任务完成 + 已完成标签 |
| **Notify** | 金色铃铛 + 提醒内容 |
| **Error** | 红色叉号 + 错误信息 |

悬停展开预览，点击打开聊天。All-Paint 架构 — 所有动画在 `paintEvent` 中绘制，零子控件。

### Pixel Pet — 你的桌面猫咪

一只 128px 像素橘猫陪你工作：

- **idle** — 静静待着
- **walk** — 桌面闲逛，自动转向
- **happy** — 开心跳动
- **sleep** — 打瞌睡，ZZZ 飘浮
- **love** — 冒爱心
- **thinking** — 跟着 AI 一起思考
- **error** — 出错时也会心疼你

拖拽移动，双击打开聊天。

### AI Chat — 命令执行

不只是聊天，**AI 能直接操作你的电脑**：

| 你说 | AI 做什么 |
|------|----------|
| "打开微信" | 启动微信 |
| "打开Chrome" | 启动浏览器 |
| "查看IP地址" | 执行 `ipconfig` |
| "帮我创建一个React项目" | 调用 Claude Code |
| "把这个文件重构一下" | Claude Code 直接操作 |

AI 回复中自动生成命令标签（`[APP:微信]`、`[SHELL:dir]`、`[CLAUDE:...]`），引擎解析执行。

### 多对话标签栏

- 多个对话同时管理
- 标签栏：新建、切换、关闭
- 自动从首条消息生成标题
- 关闭时自动保存，下次启动恢复

### Claude Code 集成

如果本地安装了 Claude Code CLI，零配置即可使用。编程任务、项目创建、代码重构，一句话搞定。

---

## Quick Start

### 方式一：一键启动（推荐）

双击目录下的 `启动 BuddyDesk.bat`，自动安装依赖并启动。

### 方式二：手动启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行
python main.py

# 3. 选择后端，填入配置，点击启动
```

### 方式三：静默启动

双击 `启动 BuddyDesk.vbs`，无命令行窗口。

---

## AI Backend

| 后端 | 说明 | 配置 |
|------|------|------|
| **Claude Code** | 本地 `claude` CLI，零配置 | 需安装 Claude Code CLI |
| **OpenAI API** | 兼容多平台 | 填入 API Key 即可 |

### 支持的 API 平台（一键预设）

| 平台 | Base URL |
|------|----------|
| OpenAI | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| NVIDIA | `https://integrate.api.nvidia.com/v1` |
| 硅基流动 | `https://api.siliconflow.cn/v1` |
| Moonshot | `https://api.moonshot.cn/v1` |
| Ollama (本地) | `http://localhost:11434/v1` |

---

## Usage

| 操作 | 说明 |
|------|------|
| `Ctrl+F` | 全局快捷键，呼出/隐藏聊天窗口 |
| 点击灵动岛 | 打开聊天窗口 |
| 双击宠物 | 打开聊天窗口 |
| 拖拽宠物 | 移动宠物位置 |
| 悬停灵动岛 | 展开状态预览 |
| 说"打开XXX" | 直接启动应用 |
| 说"查看XXX" | 执行系统命令 |
| 说"帮我XXX" | Claude Code 执行复杂任务 |

---

## Project Structure

```
buddydesk/
├── main.py                     # 主入口 (BuddyDeskApp)
├── bridge.py                   # Qt Signal Bridge (AI → UI)
├── config.py                   # 持久化配置 (~/.buddydesk/)
├── theme.py                    # 设计 token (颜色/字体/圆角)
├── requirements.txt            # 依赖列表
├── 启动 BuddyDesk.bat          # 一键启动脚本
├── 启动 BuddyDesk.vbs          # 静默启动脚本
│
├── ai/
│   └── backend.py              # AI 后端 (Claude Code / OpenAI)
│
├── engine/
│   ├── command_engine.py       # 命令执行引擎 ([APP:/SHELL:/CLAUDE:])
│   └── event_engine.py         # 事件记录引擎
│
├── ui/
│   ├── dynamic_island.py       # 灵动岛 (All-Paint 架构)
│   ├── pixel_pet.py            # 像素宠物 (72 帧精灵图)
│   ├── chat_window.py          # 聊天窗口 (多对话 + Markdown)
│   ├── markdown_renderer.py    # 流式 Markdown 渲染
│   ├── launcher.py             # 启动配置对话框
│   ├── tray.py                 # 系统托盘
│   └── icon_widgets.py         # SVG 图标控件
│
├── assets/
│   ├── cat_frames_v2/          # 81 帧猫咪精灵图
│   └── icons/                  # SVG 图标 (Claude/OpenAI/Code)
│
└── tests/
    ├── test_backend.py
    ├── test_command_engine.py
    ├── test_config.py
    └── test_event_engine.py
```

---

## Architecture

```
用户输入
   ↓
ChatWindow._send()
   ↓
AIBridge.send() → background thread
   ↓
AI 后端流式返回 chunks
   ↓
chunk_received signal → ChatWindow 实时渲染
   ↓
stream_done signal → _process_commands()
   ↓
CommandEngine 解析 [APP:/SHELL:/CLAUDE:] 标签
   ↓
执行命令 → 结果显示在聊天中
```

**线程安全**：所有 AI 操作在 `daemon` 线程中执行，通过 Qt Signal 桥接回主线程。`EventEngine` 使用 `threading.Lock` 保证并发安全。

---

## Tech Stack

| 组件 | 技术 |
|------|------|
| UI 框架 | PySide6 (Qt for Python) |
| 灵动岛 | QPainter 自绘 (All-Paint) |
| 宠物动画 | 72 帧精灵图 + QPropertyAnimation |
| AI 后端 | Claude Code CLI / OpenAI API |
| 快捷键 | ctypes GetAsyncKeyState 轮询 |
| 配置存储 | JSON (~/`.buddydesk/`) |
| 测试 | pytest |

---

## Roadmap

- [x] 灵动岛 + 像素宠物 + 快捷键
- [x] 自然语言命令执行
- [x] 双后端 (Claude Code + OpenAI API)
- [x] 多对话标签栏 + 持久化
- [x] 一键启动脚本
- [ ] 插件系统（社区宠物皮肤、自定义命令）
- [ ] 语音交互
- [ ] 宠物学习（主动提醒）
- [ ] 跨平台（macOS / Linux）

---

## License

MIT

## Acknowledgements

- Inspired by [HermesPet](https://github.com/nicepkg/HermesPet) for macOS
- UI 设计参考 Dynamic Island + Glass Morphism 风格
- 像素猫精灵图基于 [chubby-orange-cat](assets/chubby-orange-cat.webp) 制作
