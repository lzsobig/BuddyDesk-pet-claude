# Hermes Pet Win

<div align="center">

🐱 **Windows 桌面 AI 伴侣** —— 灵动岛 + 像素宠物 + 命令执行

快捷键一按，AI 即来。说"打开微信"就能打开，说"查看IP"就能执行。

基于 macOS [HermesPet](https://github.com/nicepkg/HermesPet) 的设计思路，用纯 Python (PySide6 / Qt) 实现的 Windows 版本。

</div>

---

## ✨ Features

- **Dynamic Island** — 顶部浮动胶囊，实时显示 AI 状态，hover 展开预览，呼吸灯动画
- **Pixel Pet** — 128px 高清像素猫咪，idle 眨眼 / walk 闲逛 / eat 吃东西 / happy 开心跳动
- **AI Chat** — Markdown 渲染，流式输出，文件附件
- **🆕 命令执行** — 说"打开微信"就能打开，说"查看IP"就能执行
- **🆕 Claude Code 集成** — 编程任务、项目创建，Claude Code 直接搞定
- **🆕 多平台 API 预设** — DeepSeek / NVIDIA / 硅基流动 / Ollama 一键配置
- **Event Engine** — 事件记录与状态追踪
- **System Tray** — 托盘图标 + 状态指示
- **Global Hotkeys** — Ctrl+Shift+H 呼出聊天

## 🚀 核心亮点：命令执行

这是 Hermes Pet Win 和普通 AI 聊天最大的区别——**AI 不仅能聊天，还能直接操作你的电脑**：

| 你说 | AI 做什么 |
|------|----------|
| "打开微信" | ✅ 直接启动微信 |
| "打开Chrome" | ✅ 直接启动浏览器 |
| "打开VS Code" | ✅ 直接启动编辑器 |
| "查看IP地址" | ✅ 执行 `ipconfig` 并返回结果 |
| "帮我创建一个React项目" | ✅ 调用 Claude Code 执行 |
| "把这个文件里的代码重构一下" | ✅ Claude Code 直接操作 |

AI 会在回复中自动识别你的意图，生成命令标签并执行：

```
你: 打开微信
AI: 好的，帮你打开微信~ 🐱 [APP:微信]
✅ 已打开: 微信
```

## AI Backend

| Backend | 说明 |
|---------|------|
| Claude Code | 直接调用本地 `claude` CLI，零配置，支持系统操作 |
| OpenAI API | 填入 API Key，支持多平台 |

### 支持的 API 平台（一键预设）

| 平台 | Base URL |
|------|----------|
| OpenAI | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| NVIDIA | `https://integrate.api.nvidia.com/v1` |
| 硅基流动 | `https://api.siliconflow.cn/v1` |
| Moonshot | `https://api.moonshot.cn/v1` |
| Ollama (本地) | `http://localhost:11434/v1` |

## Quick Start

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行
python main.py

# 3. 选择后端，填入配置，点击启动
```

## Usage

| 操作 | 说明 |
|------|------|
| `Ctrl+Shift+H` | 全局快捷键，呼出/隐藏聊天窗口 |
| 点击灵动岛 | 打开聊天窗口 |
| 双击宠物 | 打开聊天窗口 |
| 拖拽宠物 | 移动宠物位置 |
| 悬停灵动岛 | 展开状态预览 |
| 说"打开XXX" | 直接启动应用 |
| 说"执行XXX" | 运行系统命令 |
| 说"帮我XXX" | Claude Code 执行复杂任务 |

## Project Structure

```
hermes-pet-win/
├── main.py                     # 主入口
├── config.py                   # 全局配置
├── requirements.txt            # 依赖列表
├── user_config.json            # 用户配置（自动生成）
├── ui/
│   ├── dynamic_island.py       # 灵动岛（圆角 + 呼吸灯动画）
│   ├── pixel_pet.py            # 像素宠物（16x16 高清像素画）
│   ├── chat_window.py          # AI 聊天（命令执行反馈）
│   ├── launcher.py             # 启动器（API 预设 + Claude 检测）
│   └── tray.py                 # 系统托盘 + 快捷键
├── ai/
│   └── backend.py              # AI 后端（含强大 System Prompt）
├── engine/
│   ├── command_engine.py       # 命令执行引擎（核心！）
│   └── event_engine.py         # 事件引擎
└── assets/
    └── pet_frames/             # 宠物动画帧（预留）
```

## 命令执行工作原理

```
用户输入 "打开微信"
    ↓
AI 后端处理（System Prompt 指导 AI 生成 [APP:微信] 标签）
    ↓
命令引擎解析 AI 回复中的标签
    ↓
执行对应操作（查找微信路径 → subprocess.Popen 启动）
    ↓
在聊天中显示执行结果（✅ 已打开: 微信）
```

## License

MIT

## Acknowledgements

- Inspired by [HermesPet](https://github.com/nicepkg/HermesPet) for macOS
- Command execution inspired by desktop AI assistants
