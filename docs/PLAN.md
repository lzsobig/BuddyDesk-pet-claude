# BuddyDesk 优化实施计划

> 制定时间：2026-06-03
> 主要参考：[basionwang-bot/HermesPet](https://github.com/basionwang-bot/HermesPet)（v1.2.9 macOS 主力 + v0.1.0 Windows 尝鲜版）
> 次要参考：`hermes-pet-win-final-version-roadmap.md`（已 70% 完成）
> 阶段目标：**只做体验与内容优化**，不涉及推广/上架/路线图

---

## 0. 当前 BuddyDesk 现状（一句话）

v0.2.x，Windows PySide6 桌面 AI 伴侣，~7000 行 / 17 个模块，最大单文件 1317 行（chat_window.py）。**核心特性已差异化**：[APP:/SHELL:/CLAUDE:] 标签解析 + 真执行 + ConfirmDialog 兜底、橘猫 7 状态桌宠、5 状态交叉淡入淡出灵动岛、3 个 AI 后端（ClaudeCode/OpenAI/AnthropicDirect）、Markdown 流式、多对话历史、音效、剪贴板监听、自动更新、PyInstaller 打包。

---

## 1. 与 HermesPet 关键差距（已对照）

详见附表。核心判断：

| HermesPet 大杀器 | 是否要做 | 理由 |
|------|------|------|
| 5 引擎真正并行 | ❌ | 工程成本数量级，且 BuddyDesk 已有 3 后端"够用" |
| 知识云图 v1.3.0 | ❌ | 概念好，但实施成本太高（关键词引力、液态玻璃、入场动画），不解决"现有用户用得更爽" |
| 中英双语即时切换 | ❌ | 已和用户确认不做 |
| 早报/周报/共享记忆 | ❌ | 隐私负担重，采集范围敏感 |
| push-to-talk 语音 | ❌ | Windows 没 SFSpeechRecognizer，需本地 Whisper，模型加载慢 |
| 跨 AI 共享上下文 | ❌ | 实现复杂，多 backend 历史要序列化 |
| **Pin 桌面卡片** | ✅ | 易实现，1.5d，体感好 |
| **截图快门 + 附加对话** | ✅ | 易实现，1d |
| **5 事件音独立开关 + 自定义** | ✅ | 现有 audio.py 太简陋，0.5d |
| **字号缩放 5 档** | ✅ | 仅影响 Markdown 渲染，0.5d |
| **AI 编号列表 → 可点选项卡片** | ✅ | 0.5d，UX 大提升 |
| **拖文件 → 桌宠吞** | ✅ | 1d |
| **崩溃一键上报** | ✅ | 0.5d |
| **文件敏感词黑名单** | ✅ | 0.5d |
| 桌宠嗅桌面图标 | 🟡 选做 | 2d，Windows 桌面图标 API 麻烦 |
| 任务派发（tasks YAML 卡片） | 🟡 选做 | 1.5d，需要 AI prompt 也跟着改 |
| 桌宠跨岛传送门 | 🟡 选做 | 1.5d，视觉惊喜 |
| 桌宠避让灵动岛 | 🟡 选做 | 0.5d，小细节 |
| 上下文用量进度条 | 🟡 选做 | 0.5d |

---

## 2. 实施路径（按依赖顺序）

**总工作量预估：~8-9 天**（10 项高 ROI + 5 项中 ROI 选做）

### Phase 1：低成本高 ROI（先把"明显的体验"补齐，3 天）

| # | 任务 | 改的文件 | 工作量 | 依赖 |
|---|------|---------|--------|------|
| **P1-1** | **5 事件音独立开关 + 自定义音频** | `audio.py`（重写）、`ui/settings_panel.py`（新增声音 Tab）、`main.py`（连接触发点）、`config.DEFAULT_USER_CONFIG`（加 5 个开关字段） | 0.5d | 无 |
| **P1-2** | **字号缩放 5 档** | `ui/markdown_renderer.py`、`ui/chat_window.py`（注册 ⌘+/⌘-/⌘0）、`config.py`（持久化）、`theme.py`（字号 token） | 0.5d | 无 |
| **P1-3** | **AI 编号列表 → 可点选项卡片** | `ui/markdown_renderer.py`（识别有序列表 + 检测"叙述性"vs"选项性"）、`ui/chat_window.py`（点击填入输入框） | 0.5d | 依赖 markdown_renderer 现有能力 |
| **P1-4** | **崩溃一键上报** | `ui/crash_reporter.py`（新文件，扫描本地崩溃日志）、`ui/settings_panel.py`（"关于"页加按钮）、`main.py`（启动时检查新崩溃） | 0.5d | 无 |
| **P1-5** | **文件敏感词黑名单** | `ui/drag_drop_util.py`（新文件，封装过滤逻辑）、`main.py`（拖入事件过滤）、`config.py`（黑名单常量） | 0.5d | 无 |

### Phase 2：中成本高 ROI（功能完整化，3 天）

| # | 任务 | 改的文件 | 工作量 | 依赖 |
|---|------|---------|--------|------|
| **P2-1** | **截图快门 + 附加对话** | `screen_capture.py`（新文件，Windows GDI/DirectX 截屏）、`ui/chat_window.py`（⌘⇧J 快捷键、添加附件到 pendingImages）、`main.py`（快捷键） | 1d | 无 |
| **P2-2** | **拖文件 → 桌宠吞** | `ui/pixel_pet.py`（接受 dragEnter、吞下动画）、`ui/chat_window.py`（接收桌宠传来的文件路径）、`ui/drag_drop_util.py`（复用 P1-5 的黑名单） | 1d | 依赖 P1-5 |
| **P2-3** | **Pin 桌面卡片** | `ui/pin_card.py`（新文件，独立 QWidget 无边框置顶）、`ui/chat_window.py`（⌘⇧P 触发、序列化为 JSON）、`config.py`（pins.json 持久化） | 1.5d | 无 |

### Phase 3：选做（细节打磨，3 天）

| # | 任务 | 改的文件 | 工作量 | 依赖 |
|---|------|---------|--------|------|
| **P3-1** | **桌宠避让灵动岛** | `ui/pixel_pet.py`（检测岛 x range，撞边界反向）、`config.py`（岛范围常量） | 0.5d | 无 |
| **P3-2** | **桌宠跨岛传送门** | `ui/pixel_pet.py`（传送门动画 + 坐标计算）、`ui/dynamic_island.py`（接收端"穿出"动画） | 1.5d | 依赖 P3-1 |
| **P3-3** | **上下文用量进度条** | `ui/chat_window.py`（header 加进度条）、`bridge.py`（暴露当前 token 用量 signal）、`ai/backend.py`（每个 backend 实现 token 计数） | 0.5d | 无 |
| **P3-4** | **任务派发卡片** | `ui/markdown_renderer.py`（识别 ` ```tasks ` YAML 块 → TaskCardList 渲染）、`ai/backend.py: SYSTEM_PROMPT`（追加 "任务派发" 段落）、`ui/chat_window.py`（卡片 3 按钮交互） | 1.5d | 依赖 P1-3 |
| **P3-5** | **桌宠嗅桌面图标** | `desktop_icon_reader.py`（新文件，Windows 用 IShellFolder COM）、`ui/pixel_pet.py`（拖到图标触发"嗅"动画）、`bridge.py`（短评请求） | 2d | 依赖 P2-2 |

---

## 3. 实施顺序总览（甘特图）

```
Day 1   │ P1-1 声音系统 │ P1-2 字号缩放 │ P1-3 选项卡片 │
Day 2   │ P1-4 崩溃上报 │ P1-5 黑名单   │              │
Day 3   │ P2-1 截图     │ P2-2 桌宠吞文件（依赖 P1-5） │
Day 4   │ P2-3 Pin 桌面卡片（独立大块） │
Day 5   │ P3-1 桌宠避让 │ P3-3 进度条   │ P3-4 任务派发（依赖 P1-3）│
Day 6   │ P3-2 跨岛传送门（依赖 P3-1）  │
Day 7-8 │ P3-5 嗅桌面图标（最后大块）   │
```

**P1 / P2 必须做**：8.5 天里有 5 天是必须的，3 天是选做。预算紧的话只做 P1 + P2，P3 全部砍。

---

## 4. 关键实现细节

### 4.1 声音系统（P1-1）

**现状问题**：`audio.py` 4 个提示音程序生成 WAV，`winsound` 播放；全局 1 个 `sound_enabled` 开关。

**改造**：
- 5 个事件独立开关：`voice_start / message_received / file_dropped / message_sent / error`
- 每个事件可选内置 WAV 或自定义音频文件（拖入设置面板）
- 持久化：`config.DEFAULT_USER_CONFIG` 加 5 个 bool 字段 + 5 个 `custom_path: str` 字段
- UI：`ui/settings_panel.py` 加"声音"Tab，每行 `[checkbox] 事件名 [选择内置音 ▼] [拖入自定义]`

**注意**：自定义音频用 `QSoundEffect`（PySide6 自带）替代 `winsound`，支持 mp3/wav/m4a/ogg。

### 4.2 字号缩放（P1-2）

**实现**：
- `config.py` 加 `FONT_SCALE_LEVELS = [0.85, 1.0, 1.15, 1.3, 1.5]` 常量
- `theme.py` 加 `FONT_SCALE_FACTOR` 动态计算的函数（不存常量）
- `ui/markdown_renderer.py` 渲染时乘 `FONT_SCALE_FACTOR`
- `ui/chat_window.py` 注册 `QShortcut`：`Ctrl++` / `Ctrl+-` / `Ctrl+0`
- 持久化：`user_config["font_scale_idx"]`（int 0-4）

**范围**：仅 Markdown 渲染的字号，不影响输入栏/灵动岛/桌宠（避免破坏布局）。

### 4.3 AI 编号列表 → 选项卡片（P1-3）

**问题**：AI 经常回"1. xxx 2. xxx 3. xxx"，用户得手动复制其中一条。

**实现**：
- `markdown_renderer.py` 检测有序列表
- 启发式判断"选项性"：连续 ≤7 条 + 每条 < 30 字 + 后面没有"第一步""第二步"等叙述词 → 视为选项
- 渲染成"按钮列表"（QToolButton），点击填入 chat_input
- **不自动发送**（避免误触），只填入等用户按 Enter

### 4.4 崩溃一键上报（P1-4）

**实现**：
- `ui/crash_reporter.py`：扫描 `%LOCALAPPDATA%\BuddyDesk\Crashpad\`（PyInstaller 标准崩溃目录）
- 找到新崩溃 → "发现 N 个新崩溃日志" 通知
- 用户点"复制并上报" → 把崩溃 stacktrace 复制到剪贴板 + 打开浏览器到 `https://github.com/lzsobig/BuddyDesk-pet-claude/issues/new?template=crash.md`，用户手动粘贴
- 零后端、零隐私顾虑

### 4.5 文件敏感词黑名单（P1-5）

**实现**：
- `config.py` 加 `SENSITIVE_KEYWORDS = ["薪资", "工资", "合同", "密码", ".env", "credentials", "secret", "id_rsa", "*.key", "*.pem"]`
- `ui/drag_drop_util.py` 提供 `filter_sensitive_filepaths(paths: list[str]) -> tuple[list[str], list[str]]` 返回 (通过的, 被过滤的)
- 桌宠吞文件时调用，**被过滤的文件**：显示"⚠️ 跳过敏感文件 X"通知 + 桌宠摇头
- 通过的文件正常附加

### 4.6 截图快门（P2-1）

**实现**：
- `screen_capture.py`：用 `mss` 库（PySide6 生态友好，比 pyautogui 快）
- `⌘⇧J` 触发：0.18s 白色闪光（QWidget 全屏 50ms） + 截图 + 添加到 `chat_window.pendingImages`
- 自动排除桌宠自己窗口（用 `winId()` 比对）
- 与剪贴板监听的区别：剪贴板是"被动发现"，截图是"主动捕获"

### 4.7 拖文件 → 桌宠吞（P2-2）

**实现**：
- `ui/pixel_pet.py` 开启 `setAcceptDrops(True)`
- `dragEnterEvent` / `dropEvent`：接住文件路径，调"吞下"动画（`frame_24..27` happy 帧 + 0.3s 缩放）
- 完成后 emit `file_dropped(paths)` signal
- `main.py` 接收 → 转给 `chat_window.add_files(paths)`（过滤敏感词）
- **复用** P1-5 的 `filter_sensitive_filepaths`

### 4.8 Pin 桌面卡片（P2-3）

**实现**：
- `ui/pin_card.py`：独立 `QWidget`，`Qt.WindowStaysOnTopHint` + 无边框 + 圆角 + 半透明
- 持久化：`config.PINS_PATH = ~/.buddydesk/pins.json`，存 `[{id, conversation_id, message_idx, content, x, y, created_at}]`
- 启动时加载所有 pin，重启后还在
- 拖动 pin 自由摆放；右键菜单"关闭" / "跳回对话"

### 4.9 桌宠避让灵动岛（P3-1）

**实现**：
- `ui/pixel_pet.py` 在 walk step 计算新 x 时检查：若新位置会进入 `[island_x - 30, island_x + island_w + 30]`，反向
- 岛范围从 `dynamic_island.py.get_geometry()` 拿（已在主屏上）
- 不影响 hover/click（桌宠离岛还有距离）

### 4.10 任务派发卡片（P3-4）

**实现**：
- `ai/backend.py:SYSTEM_PROMPT` 追加段落：
  ```
  当用户说"帮我列一下今天要做的事"或"派几个任务给 AI"时，
  输出一段 tasks YAML 块：
  ```tasks
  - title: 完成 X
    difficulty: 1-5
    mode: claude_code
  - title: ...
  ```
- `markdown_renderer.py` 识别 ```tasks 块 → 渲染为可操作卡片（每张 3 按钮：📌 Pin 到桌面 / 🤖 让 AI 做 / ✗ 跳过）
- 卡片数据挂在 `chat_window._task_cards` 列表，用户操作后从列表移除

---

## 5. 不做的事（明确列出，避免后续被反复提起）

| 想法 | 不做的理由 |
|------|------|
| 知识云图 | 实施成本太高，不解决"现有用户用得更爽" |
| i18n / 中英切换 | 用户明确说本阶段不做 |
| 早报/周报/共享记忆 | 隐私负担重，采集范围敏感 |
| push-to-talk 语音 | Windows 没 SFSpeechRecognizer，需本地 Whisper/Edge，模型加载慢 |
| 跨 AI 共享上下文 | 多 backend 历史序列化复杂 |
| 5 引擎真正并行 | 工程成本数量级，已有 3 后端够用 |
| 官方版本验证 / DMG 公证 | Windows 用不上 |
| 推广/上架/路线图/商业化 | 用户明确本阶段不做 |

---

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 桌宠吞文件时用户拖了一堆文件（>10） | 拖入时弹"已接收 N 个文件"提示，超过 5 个问"全部发送还是只发前 5 个" |
| Pin 桌面卡片太多遮屏 | 超过 10 个自动归到设置面板"已 Pin"列表，桌面只显示最近 5 个 |
| 截图 0.18s 闪光影响用户正在看的内容 | 加 `user_config["screenshot_flash"]` 开关，默认开 |
| 字号缩放破布局 | 缩放只作用于 Markdown 渲染的字体；气泡 padding/边框大小不变 |
| 黑名单误伤合法文件 | 关键词是"薪资/合同/密码/.env"，误伤率低；提供"我确认要发送"按钮绕过 |
| 桌宠避让灵动岛导致桌宠被困在一侧 | 检测被困（30s 内反向超过 3 次）→ 走传送门到另一侧 |
| 崩溃日志被杀毒软件拦截 | 读本地文件无风险；不上传；复制到剪贴板是用户主动操作 |

---

## 7. 完成定义（每项的"DoD"）

- [ ] **P1-1 声音系统**：5 事件可独立开关；自定义音频可拖入生效；设置面板有"声音"Tab
- [ ] **P1-2 字号缩放**：⌘+/⌘-/⌘0 切换 5 档；重启后保留
- [ ] **P1-3 选项卡片**：AI 回 1-7 条简短编号列表时自动渲染按钮；点击填入输入框不发送
- [ ] **P1-4 崩溃上报**：启动检测新崩溃 + 一键复制到剪贴板 + 跳 GitHub Issue
- [ ] **P1-5 黑名单**：拖入 .env/密码文件被过滤并显示提示
- [ ] **P2-1 截图快门**：⌘⇧J 触发；0.18s 闪光；图片附到当前对话
- [ ] **P2-2 桌宠吞文件**：拖文件到桌宠 → 吞下动画 → 文件附对话
- [ ] **P2-3 Pin 桌面**：⌘⇧P Pin 最新回复；重启后还在；可拖动摆放
- [ ] **P3-1 桌宠避让**：桌宠走路不遮挡灵动岛
- [ ] **P3-2 跨岛传送**：桌宠在岛一侧走到边界，触发传送门动画出现在另一侧
- [ ] **P3-3 进度条**：聊天窗 header 显示当前对话已用 token / 上下文窗口大小
- [ ] **P3-4 任务派发**：AI 回 ```tasks 块时渲染为可点卡片，3 按钮交互正常
- [ ] **P3-5 嗅桌面图标**：拖桌宠到桌面图标，桌宠停下嗅一下，AI 给短评（≤10 字）

---

## 8. 下一步

请用户审阅本计划 → 确认 P1/P2 必做 + P3 选做哪些 → 然后我按顺序逐项实施。每完成一项跑一次 `python -m unittest discover tests` 确认无回归。
