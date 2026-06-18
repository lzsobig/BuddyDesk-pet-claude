# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

BuddyDesk 是一款 Windows 桌面 AI 伴侣应用（Python/PySide6），包含灵动岛、像素宠物、AI 聊天、命令执行和 Claude Code CLI 集成。**这是合并后的最终发布版** —— 融合了两个独立生成的 v1 版本，统一采用橘猫精灵图。

**核心创新**：AI 能理解自然语言命令（"打开微信"、"查看IP"），通过命令引擎从 AI 响应中解析特殊标签并执行。

## 常用命令

```bash
python main.py                                    # 运行应用
pip install -r requirements.txt                   # 安装依赖
python -m unittest discover tests -v              # 运行所有测试
python -m unittest tests.test_config -v           # 运行单个测试文件
python -m unittest tests.test_backend.TestX.test_y -v  # 运行单个测试方法
```

**Windows 用户** —— 优先用启动脚本（自动装依赖、无黑窗口）：
- `启动 BuddyDesk.bat` —— 显示控制台输出
- `启动 BuddyDesk.vbs` —— 静默启动

**视觉冒烟测试** —— 仓库包含整合时使用的独立截图脚本。它们离屏实例化单个 widget、渲染一帧后退出：
```bash
python _screenshot_pet.py
python _screenshot_island.py
python _screenshot_launcher.py
```

**测试注意** —— `tests/test_command_engine.py` 会真实调用外部程序（`notepad.exe`、`chrome.exe`）。CI 跑测试时请加超时或跳过：`timeout 10 python -m unittest tests.test_command_engine`。

## 整合历史

本代码库由两个 v1 候选版本（hermes-pet-win 和 hermes-pet-win-副本-副本）合并而成，每个版本由不同模型独立生成。详见 `FINAL_REPORT.md` 的逐文件决策矩阵。要点：
- **dynamic_island.py**：保留 v1-A 实现（`_IslandGroup` 透明度交叉淡入淡出，不用 setMask，整合时新增自动收起定时器）
- **chat_window.py**：合并版（v1-A 的悬停操作按钮 + Ctrl+L/R 快捷键 + 聊天头橘猫头像 + v1-B 的 `MarkdownRenderer` 用于流式 AI 气泡）
- **pixel_pet.py**：重写 —— 使用 `assets/cat_frames_v2/` 72 帧，单帧状态静态绘制（不每 tick 调 setPixmap、无呼吸微动），消除 v1 反馈的"闪烁"问题
- **launcher.py / theme.py / config.py / bridge.py / ai/ / engine/**：保留 v1-A（设计 token 更完整、Claude CLI 检测、README 完整）
- **assets/**：移除小图 `pet_reference.png`（评估"尺寸偏小、观感不佳"后弃用），采用 v1-B 的 `cat_frames_v2/` 72 帧精灵图，源自 `chubby-orange-cat.webp`

## 架构

### UI 框架：PySide6

所有 UI 使用 **PySide6**（Qt for Python）。从 tkinter 迁移而来。关键模式：
- 无边框半透明窗口，深色玻璃质感
- `QPropertyAnimation` + `QEasingCurve.OutBack` 实现弹簧动画
- 灵动岛胶囊用 `QPainter` 自定义绘制；宠物精灵用 `QPixmap`
- 灵动岛用 `_IslandGroup`（基于透明度）实现交叉淡入淡出
- 通过 `bridge.py` 的信号/槽在线程间安全传递 AI ↔ UI 数据

### 数据流

```
main.py (BuddyDeskApp)
    ↓ LauncherDialog → 用户选择后端与配置
    ↓ 创建：AIBridge（封装 AI + EventEngine）、CommandEngine
    ↓
用户输入消息 → ChatWindow._send()
    ↓ bridge.send(messages) → 后台线程
    ↓ AI 通过 bridge.chunk_received 信号流式返回片段
    ↓ ChatWindow._on_chunk() 通过直接引用更新 _live_widget
    ↓ bridge.stream_done → main._process_commands()
    ↓ command_engine.parse_and_execute() 提取 [APP:/SHELL:/CLAUDE:] 标签
    ↓ 危险命令 → bridge.command_needs_confirm → ConfirmDialog
    ↓ 结果通过 chat.append_command_result() 显示
```

启动时的边路任务：`SystemTray`、可选 `SettingsPanel`（通过托盘菜单）、`updater._check_update`（启动后 3 秒）、可选剪贴板轮询（2 秒一次）。

### 灵动岛

`ui/dynamic_island.py` —— 屏幕顶部胶囊，5 个状态：
- `idle / thinking / result / notify / error`
- 每个状态一个 `_IslandGroup`，各自用 `QGraphicsOpacityEffect` 实现交叉淡入淡出
- 200ms 大小+透明度过渡，瞬时状态 4-5 秒后自动收起为 idle
- 完全用 `QPainter` 绘制（不用 `setMask`，避免边缘锯齿）

### 像素宠物（橘猫）

`ui/pixel_pet.py` —— 7 个状态映射到 `assets/cat_frames_v2/frame_XX.png`：
- `idle` (frame_00)、`walk` (frame_08-11，4 帧)、`happy` (frame_24-27，4 帧)、`sleep` (frame_48)、`love` (frame_24-25)、`thinking` (frame_64)、`error` (frame_40)
- 单帧状态只绘制一次，绝不再调 setPixmap（防闪烁规则）
- 走路：10 FPS 4 帧循环 + 水平位移 + 方向变化时自动镜像
- 睡觉时浮 ZZZ，喜欢时浮爱心
- 拖拽用弹簧缓动

### 命令标签系统

AI 系统提示（`ai/backend.py:SYSTEM_PROMPT`）指示模型输出标签：
- `[APP:应用名]` → AppRegistry.find_app() → subprocess.Popen
- `[SHELL:命令]` → subprocess.run(shell=True, timeout=30s)
- `[CLAUDE:指令]` → claude CLI --print (timeout=120s)

`AppRegistry` 维护 Windows/Mac/Linux 应用查找字典。危险命令通过正则白名单阻止；不匹配的命令进入"待确认"状态，弹出 `ui/confirm_dialog.py:ConfirmDialog` 让用户确认。流程：`command_engine.parse_and_execute()` → `bridge.command_needs_confirm(command)` → `main._on_confirm_command()` → `command_engine.confirm_pending()` / `cancel_pending()`。

### AI 后端

`ai/backend.py` —— `AIBackend` 抽象基类，两个实现：
- `ClaudeCodeBackend`：本地 `claude` CLI，先尝试流式，失败回退
- `OpenAIBackend`：OpenAI 兼容 API（DeepSeek、NVIDIA、Ollama 等）

### 线程

- AI 调用在 `threading.Thread(daemon=True)` 中执行（`bridge.send()`）
- `AIBridge` 用 Qt 信号把结果传递到主线程
- `EventEngine` 用 `threading.Lock` 保证线程安全
- `updater.check_for_update()` 在守护线程中运行；通过 `QTimer.singleShot(0, ...)` 把结果投递回 UI 线程

### 全局快捷键

`Ctrl+Shift+H` 用 `ctypes.windll.user32.GetAsyncKeyState` 实现，由 `QTimer` 每 30ms 轮询一次（见 `main._setup_hotkeys`）。这样避开了 `keyboard` 包（Windows 下需要管理员权限），无第三方依赖。非 Windows 下自动 no-op。

### 配置

持久化数据在 `~/.buddydesk/` 下：
- `config.json` —— 用户设置（通过 `config._deep_merge` 深度合并默认值）
- `conversations.json`、`jobs.json`、`events.log`

UI 设计 token 在 `theme.py`（颜色、字体、阴影层级、缓动）。布局常量在 `config.py`（窗口尺寸、动画速度、默认后端）。`config.DEFAULT_USER_CONFIG` 是运行时可调设置的唯一来源 —— 新增设置应加到这里，不要散落为常量。

### 设置与历史面板

- `ui/settings_panel.py` —— 模态设置对话框，从托盘菜单或 `Ctrl+,` 打开；发送 `saved(dict)` 信号；`main._on_settings_saved` 重建 `CommandEngine` 并重新应用剪贴板/宠物名/声音开关
- `ui/history_panel.py` —— 会话历史浏览器；从 `config.load_conversations()` 读取

## 依赖

```
PySide6>=6.6.0      # Qt 框架（主 UI）
openai>=1.0.0       # OpenAI 兼容 API 客户端（也用于 DeepSeek、Ollama、NVIDIA 等）
Pillow>=10.0.0      # 图片加载回退（可选）
```

`keyboard` 和 `pystray` 已不再需要 —— 快捷键改用 `ctypes` 实现（见线程章节），托盘用 Qt 的 `QSystemTrayIcon` 直接在 `ui/tray.py` 中实现。

## 音效

`audio.py` 用 `wave` + `struct` 在内存中生成短 WAV 提示音，Windows 下用 `winsound` 播放。无需外部音频文件，无第三方依赖。四种提示音：`message`、`success`、`error`、`click`（启动时使用）。受 `sound_enabled` 用户配置开关控制。
