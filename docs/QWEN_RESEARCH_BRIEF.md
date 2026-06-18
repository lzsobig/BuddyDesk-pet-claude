# BuddyDesk 项目深度研究 —— 给 Qwen 的输入文档

> 目的：让 Qwen 在不直接读代码的情况下，理解本项目的全貌、关键设计决策、当前痛点与已知风险，并据此输出**可执行的产品/技术路线图与改进建议**。
>
> 文档语言：中文（项目注释与界面均为中文）
> 项目状态：v0.2.x，2026 年 6 月；公开仓库为合并整合后的最终版

---

## 0. 阅读须知（重要）

请把这份文档当作**给你（Qwen）的项目脑图** + **未完成事项的待办清单**来读。

### 怎么用这份文档

我（用户）已经验证了文档中所有的"现状"部分（§3-§7），你可以**直接引用具体行号、模块名、文件路径**。§5 的"roadmap vs 现状对照表"是直接告诉你**什么已经做完了、什么没做**——不要重复提议已做完的事。

§8.0 写了我对每个研究问题的**初步判断**。这是"锚定"用的：让你知道我从哪个方向出发。如果你觉得我判断错了，**直接说"我反对，理由是 X"**，比客客气气地"也可以考虑别的方案"有用。

请把回答写成**给一个有经验的 PySide6 桌面 AI Agent 维护者**的下季度方向决策文档，不是教学级建议。

### 关键约定
- 凡是我**实际验证过**的现状（行数、模块行为、文件存在与否），都已写明 —— 你可以直接引用
- 凡是**未确认**但有价值的猜测，我标了"⚠️ 需验证"
- 你的任务不是给"教学级建议"，而是**给一个有经验的 PySide6 桌面 AI Agent 维护者**做下季度方向决策
- 不必客套。如果某项你判断"过度设计"或"先别做"，**直接说"不做"**，并说理由

---

## 1. 一句话定位

**BuddyDesk** —— 桌面端常驻的"橘猫形态"AI 伴侣。基于 Python + PySide6，依赖最轻。**核心差异点**：用户说一句"打开微信"或"查看 IP"，AI 在回复末尾插入结构化标签 `[APP:xxx]` / `[SHELL:xxx]` / `[CLAUDE:xxx]`，由本地命令引擎解析并真正去执行（启动应用、跑 shell、调用 Claude Code CLI），结果回灌给用户。

它不是另一个聊天框 —— **它是一个能动手的 AI Agent 前端**，形态是 macOS 灵动岛 + 像素宠物。

## 2. 重要历史：已有两份路线图可参考

本项目经历过两次方向规划，请你**都读一下**作为上下文：

1. **`C:\Users\李振\Downloads\hermes-pet-win-final-version-roadmap (2).md`** —— 768 行，由 AI 生成的 v0.2 → v1.0 四阶段路线图（4 周计划 + 优先级矩阵）。**注：这份路线图中约 70% 的 P1/P2 任务已在 v0.2.x 中实际完成**（详见第 5 节"已完成 vs 未完成"对照表）。
2. **本项目根目录的 `FINAL_REPORT.md`** —— v1-A 与 v1-B 合并时的逐文件决策矩阵。

建议：先读那份 768 行的 roadmap，然后回到这里。我会在第 5 节把"roadmap 中的待办 ↔ 当前实际状态"标出来，避免你提建议时重复提议已做完的事。

## 3. 文件清单与代码规模（已验证）

```
源码总量: ~6,948 行（17 个 Python 模块，不含 tests、assets、gan-harness）

main.py                  330 行   BuddyDeskApp 主类
bridge.py                112 行   AIBridge (QObject) — AI↔UI 信号桥
config.py                169 行   配置 + 路径 + 默认值
theme.py                 276 行   设计 token (颜色/字体/阴影/缓动)

ai/
  backend.py             524 行   AIBackend ABC + 3 个实现 (ClaudeCode/OpenAI/AnthropicDirect)

engine/
  command_engine.py      796 行   标签解析 + 应用注册表 + Shell/Claude 执行
  event_engine.py        245 行   事件记录

ui/
  chat_window.py        1317 行   聊天主窗（Markdown 流式 + 橘猫头像 + 三角发送）
  launcher.py            741 行   启动器（后端卡片 + Claude CLI 检测 + 名字输入）
  dynamic_island.py      523 行   5 状态 + _IslandGroup 交叉淡入淡出
  pixel_pet.py           452 行   7 状态橘猫 + 静态防闪烁 + 拖拽 spring
  history_panel.py       384 行   会话历史浏览器
  settings_panel.py      343 行   设置面板（model 2 新增）
  icon_widgets.py        207 行   通用图标控件
  markdown_renderer.py   178 行   流式 Markdown 渲染
  tray.py                185 行   QSystemTrayIcon 托盘
  confirm_dialog.py      163 行   危险命令二次确认弹窗（git 中 untracked）

audio.py                  75 行   winsound 程序生成 WAV 提示音（untracked）
updater.py                54 行   GitHub Releases 检查更新（untracked；含占位符 _GITHUB_REPO="your-org/BuddyDesk"）
```

测试：`tests/test_config.py`、`tests/test_backend.py`、`tests/test_command_engine.py`、`tests/test_event_engine.py` + `conftest.py`。
> ⚠️ `test_command_engine.py` 在 `TestNaturalCommand` / `TestParseAndExecute` 中真的会 `subprocess.Popen` 启动 `notepad.exe` 和 `chorme.exe`（注意拼写），CI 跑需 `timeout 10` 包装或跳过。

资源：`assets/` 约 7.5 MB，含 `cat_frames_v2/` 72 帧橘猫 PNG + `cat_sprite_sheet.png` 合并图 + `chubby-orange-cat.webp` 美术源文件 + `icons/`。

## 4. 技术栈与依赖（已验证 requirements.txt）

```python
# requirements.txt 实际内容
openai>=1.0.0       # 兼容 DeepSeek/Ollama/NVIDIA 等 OpenAI 协议后端
PySide6>=6.6.0      # Qt for Python —— 唯一 UI 框架
Pillow>=10.0.0      # 像素宠物精灵加载
pynput>=1.7.6       # 全局热键（注意：CLAUDE.md 中曾写 ctypes 实现，requirements.txt 是 pynput —— 文档与实现存在漂移）
pytest>=7.0.0       # 测试
```

**零系统依赖**：无 Node、无 Electron、无 WebView —— 这是产品的卖点之一。

## 5. 路线图已完成情况对照（重点！）

下表把那份 768 行 roadmap 里的 P1/P2/P3/P4 任务，**逐项**对照当前代码状态。结果是 **70% 已完成**：

| 路线图任务 | roadmap 阶段 | 当前状态 | 证据 |
|------|------|------|------|
| P1-1 对话持久化 | v0.3 | ✅ 已完成 | `chat_window.py:894, 918, 1012-1028` 有 `_save_conversation()`，用 `config.load_conversations()` |
| P1-2 Markdown 渲染接入 | v0.3 | ✅ 已完成 | `chat_window.py` 标题说"流式 Markdown 渲染"，`markdown_renderer.py` 存在；需 Qwen 验证是否真正接入 |
| P1-3 命令确认弹窗 | v0.3 | ✅ 已完成 | `ui/confirm_dialog.py:ConfirmDialog` 存在；`command_engine.py:690` 有 `confirm_pending()` / `cancel_pending()` |
| P1-4 运行时设置面板 | v0.3 | ✅ 已完成 | `ui/settings_panel.py:SettingsPanel` 存在；`main.py:148` 有 `_on_settings_saved` 重建 CommandEngine |
| P2-1 DWM 亚克力 | v0.4 | ❌ 未做 | `dwm_acrylic.py` 文件不存在；`theme.py` 与所有 UI 模块中无 `DwmSetWindowAttribute` 或 `enable_acrylic` 调用（用户已验证） |
| P2-2 sad 状态 + 联动 | v0.4 | ⚠️ 部分 | `main.py:206` `state == "error"` 时调 `set_state("sad")`，但 `pixel_pet.py:STATE_MAP` 需 Qwen 确认是否含 sad；CLAUDE.md 提到 7 状态（idle/walk/happy/sleep/love/thinking/error）未含 sad |
| P2-3 音效系统 | v0.4 | ✅ 已完成 | `audio.py` 存在，含 4 种提示（message/success/error/click） |
| P2-4 动画一致性 | v0.4 | ❓ 不明 | `theme.py` 需 Qwen 验证是否含 ANIM_* tokens |
| P3-1 多对话管理 | v0.5 | ✅ 已完成 | `ui/history_panel.py` 存在 |
| P3-2 文件拖放 | v0.5 | ❓ 不明 | 需 Qwen 验证 `chat_window.py` 是否实现 `dragEnterEvent` |
| P3-3 剪贴板监听 | v0.5 | ✅ 已完成 | `main.py:109-111, 227-245` 有 `_start_clipboard_monitor()` + `_poll_clipboard()`，2 秒一次 QTimer |
| P3-4 快捷指令系统 | v0.5 | ❓ 不明 | 需 Qwen 验证是否实现 |
| P3-5 AppRegistry 国内软件 | v0.5 | ⚠️ 部分 | `command_engine.py:99+` 有 WINDOWS_APPS dict，但需验证是否含 WPS/百度网盘/迅雷/网易云 等 |
| P4-1 PyInstaller 打包 | v1.0 | ✅ 已完成 | `build.spec` 存在；git log 提到 "fix: correct asset paths for PyInstaller onedir bundle" |
| P4-2 开机自启 | v1.0 | ❓ 不明 | 需 Qwen 验证 `settings_panel.py` 是否含 autostart 开关 |
| P4-3 自动更新 | v1.0 | ✅ 已完成 | `updater.py` 存在 |
| P4-4 完善文档 | v1.0 | ✅ 已完成 | README.md / CHANGELOG.md / LICENSE 都已 git 跟踪 |

**Qwen 你的判断空间在表格里 ❓ 标记的项**。但我建议你不局限于补完 roadmap —— roadmap 解决的是"产品可用性"，**真正的下一阶段挑战**是不同的（见第 8 节）。

## 6. 架构总览

### 6.1 数据流

```
用户输入消息
  ↓ ChatWindow._send()
bridge.send(messages)  ──→  threading.Thread(daemon)
  ↓                                 ↓
  AIBackend (ClaudeCode/OpenAI/AnthropicDirect)  ↓ 流式
  ↓                                 ↓
bridge.chunk_received signal  ←────┘
  ↓
ChatWindow._on_chunk() → 增量更新 _live_widget
  ↓
bridge.stream_done signal
  ↓
main._process_commands()
  ↓
CommandEngine.parse_and_execute(full_text)
  ↓ 解析 [APP:xxx] [SHELL:xxx] [CLAUDE:xxx] 标签
  ↓ 危险命令 → bridge.command_needs_confirm → ConfirmDialog 用户确认
  ↓
subprocess.Popen (应用) / subprocess.run(shell, timeout=30) / claude CLI (timeout=120)
  ↓
ChatWindow.append_command_result()  显示到聊天
```

### 6.2 核心模块职责

| 模块 | 职责 | 关键点 |
|------|------|--------|
| `bridge.AIBridge` | AI 与 UI 的线程安全桥 | Qt signals/slots；暴露 `chunk_received` / `stream_done` / `state_changed` / `command_needs_confirm` |
| `ai.backend.AIBackend` | 抽象基类 | 三个实现：`ClaudeCodeBackend`、`OpenAIBackend`、`AnthropicDirectBackend` |
| `engine.command_engine.CommandEngine` | **本项目最复杂的单文件（796 行）** | 标签解析、危险命令过滤、AppRegistry、Shell 执行、快捷指令注册 |
| `engine.event_engine.EventEngine` | 事件流 | `threading.Lock` 线程安全；可订阅 |
| `ui.dynamic_island.DynamicIsland` | 灵动岛 | `_IslandGroup` 透明度交叉淡入淡出（不用 setMask 避免锯齿）；200ms 过渡；4-5s 自动收起 |
| `ui.pixel_pet.PixelPet` | 橘猫宠物 | 7 状态映射到 72 帧 PNG；**单帧状态零重绘防闪烁规则** |
| `ui.chat_window.ChatWindow` | 聊天 UI | 1317 行最重；Markdown 流式；Ctrl+L/R 切换；橘猫头像；三角发送 |
| `ui.launcher.LauncherDialog` | 启动配置 | 后端卡片选择 + Claude CLI 自动检测 + 宠物名输入 |
| `ui.confirm_dialog.ConfirmDialog` | 危险命令确认 | 阻断 SHELL/CLAUDE 中的破坏性操作 |
| `ui.settings_panel.SettingsPanel` | 设置面板 | emits `saved(dict)`，main 中重建 CommandEngine |
| `ui.history_panel.HistoryPanel` | 历史回看 | 读取 `~/.buddydesk/conversations.json` |
| `audio.py` | 提示音 | winsound；4 种提示（message/success/error/click） |
| `updater.py` | 自动更新 | 仅检测 GitHub Releases，**不下载** |

### 6.3 配置 / 持久化

- 路径：`~/.buddydesk/`（注意：从旧版 `~/.hermes_pet_win/` 迁移过来）
- `config.json` —— 用户设置，`config._deep_merge` 深度合并默认值
- `conversations.json` / `jobs.json` / `events.log`
- 设计 token 在 `theme.py`；布局常量在 `config.py`；`DEFAULT_USER_CONFIG` 是运行时可调设置的**唯一真源**

### 6.4 线程模型

- 所有 AI 调用在 `threading.Thread(daemon=True)` 中
- Qt 信号在主线程分发 UI 更新
- `updater.check_for_update()` 守护线程 + `QTimer.singleShot(0, ...)` 回主线程
- 剪贴板轮询：2 秒一次 QTimer
- 热键：pynput listener（最新）/ 30ms QTimer 轮询（早期 ctypes 版本）

## 7. 已知技术债务 / 风险

> 这一节**比 roadmap 章节更聚焦** —— roadmap 写的是"功能缺什么"，这里写的是"已实现但有隐患"。

### 7.1 安全
- `command_engine.py:530+`：`subprocess.Popen(cmd, shell=True)` 直接执行 SHELL 标签
- 已有"危险命令"正则白名单 + `ConfirmDialog`，但**白名单覆盖度不明**，且**确认弹窗的默认选项倾向不明**（用户按 Enter 会确认还是取消？）
- 用户输入会进 AI 上下文（系统提示 + 历史），**prompt injection 风险未评估**
- `subprocess.run(shell=True, timeout=30)` 在 Windows 下超时子进程树未必会一起回收

### 7.2 大文件
- `chat_window.py` **1317 行**，`command_engine.py` **796 行**，单文件远超 800 行红线
- `launcher.py` 741 行，`dynamic_island.py` 523 行
- 这是 v0.2.x 的硬上限 —— 不拆分则新功能改动风险持续累积

### 7.3 测试
- `test_command_engine.py` 真实启动外部程序 → CI 不可跑
- 缺 UI 测试、缺桥接层集成测试、缺事件引擎订阅测试
- 覆盖率未量化

### 7.4 文档漂移
- `CLAUDE.md`（中文版）曾记录快捷键用 `ctypes.GetAsyncKeyState`，实际是 `pynput`
- `requirements.txt` 历史上有 `keyboard` + `pystray`，已移除但文档里仍提到
- `updater.py:11` 仓库名占位符 `your-org/BuddyDesk` 未替换为实际 `lzsobig/BuddyDesk-pet-claude`

### 7.5 平台锁定
- 启动器 `.bat`/`.vbs` —— **实质仅支持 Windows**
- README 暗示 macOS/Linux 支持但实际未提供
- `subprocess.CREATE_NO_WINDOW` 的 Win32 特化有，但主程序大量 `sys.platform == "win32"` 守护

### 7.6 性能
- 剪贴板轮询 2 秒一次，100 字符截断
- 大量流式输出时 Markdown 渲染性能未量化
- 灵动岛在 4K 屏的边距与字体缩放未自测

### 7.7 隐私
- `~/.buddydesk/conversations.json` **明文存敏感对话**
- `events.log` 内容未规约
- AI 请求是否带用户位置/宠物名等字段未明示

### 7.8 国际化（i18n）
- **零 i18n 抽象**：项目内 `grep gettext|i18n|_(` 0 命中，所有 UI 文案硬编码中文
- **系统提示写死中文**：`ai/backend.py:32` 的 `SYSTEM_PROMPT` 全文中文，含命令格式说明（`[APP:xxx] [SHELL:xxx] [CLAUDE:xxx]`）和应用名映射（"微信 → [APP:微信]"）
- **宠物名默认中文**：`config.DEFAULT_USER_CONFIG["pet_name"] = "小橘"`，用户首次启动会看到中文名
- **AppRegistry 是中文键**：`command_engine.py:WINDOWS_APPS` 的 key 就是"微信/钉钉/飞书"这种中文，AI 提示中要匹配必须用中文
- **影响**：英文用户要么硬扛中文界面，要么 fork 全翻译。**不能热切换语言** —— 改语言要重启 + 改 SYSTEM_PROMPT
- **未来成本**：等用户基数起来后，i18n 是典型"现在不做、以后想补要返工 200+ 处"的技术债

## 8. roadmap 之后的真正挑战（请 Qwen 重点分析）

roadmap 解决的是"产品从 demo 到可用"。**v0.3 → v1.0 后，下一阶段挑战是不同的**：

### 8.0 我的初步判断（仅供参考，欢迎反驳）

> 我在写这份 brief 时的倾向，目的是让你知道我从哪个方向出发 —— 如果你觉得我说错了，**直接说"我反对，理由是 X"**，比客客气气地"也可以考虑别的方案"有用。

- **Q1（roadmap 评估）**：DWM 亚克力我倾向**砍** —— Win11 22H2 普及率有限，PySide6 集成坑多（dark mode 冲突、动画掉帧），与"零依赖"卖点冲突。键盘降级方案 P4 我**缓** —— pynput 现在能跑就别折腾
- **Q2（产品方向）**：我倾向先做**多模态（截图/OCR）**而不是操作员型 AI。理由：截图理解的 ROI 在"我看到了这个报错"这类用户故事上**立刻可见**，而操作员型 AI 需要 UI 自动化基建（坐标树、控件识别），投入是数量级的
- **Q3（架构拆分）**：我倾向**先拆 command_engine.py**（796 行，纯逻辑，好测），**缓拆 chat_window.py**（1317 行，但拆的时候必然改 UI 行为，回归测试覆盖低反而危险）
- **Q4（安全加固）**：**OS 级沙箱我反对现在就做**。理由：(a) Windows Job Objects + Restricted Token 在 PySide6 进程下兼容性差，pynput/hwnd 都可能拿到受限句柄；(b) 用户当前最大风险是"误装野鸡后端 + 把 API Key 交出去"，这个靠 `ConfirmDialog` 模板化和 **「后端来源标识」**比沙箱更直接；(c) 真要做沙箱应该等用户基数起来、有明确攻击面数据后再决策
- **Q5（工程改进）**：测试我倾向**先把 `test_command_engine.py` 拆成 "纯解析测试" + "执行器集成测试（用 mock 替 subprocess）"**两块，让 CI 能跑前者
- **Q6（商业化）**：先别想
- **Q7（i18n 潜伏债）**：我倾向**现在不做、但要标记为"下次用户量起来必须重新评估"**。理由：(a) 用户数 < 100 时做 i18n 是给空气做产品；(b) 真要做至少要拆出 `locale/` 目录 + 占位符，比单纯翻译工作量大 3 倍；(c) **但要避免现在继续往 `chat_window.py` 写硬编码中文字串** —— 哪怕不做 i18n，至少把字串集中到一个 `ui/strings.py` 的常量文件里，以后翻译就是替换文件的事

### 8.1 产品定位（取代原"增长"问题）
- **凭什么让用户从 ChatBox / Cherry Studio 切过来？** 这是 v0.2.x 用户数 < 100 时唯一值得问的产品问题
- **橘猫 + 命令执行**的差异化在 2026 年还够吗？同质竞品越来越多
- **目标用户中文 Windows** 是个垂直市场 —— 是该守住垂直还是扩到英文/跨平台？

### 8.2 技术维度
- **多模态**：截图理解、屏幕 OCR —— 用户场景强（"看一下这个报错"），但当前 backend 仅文本
- **操作员型 AI**：录制一次操作 → AI 重放（如"把这段代码重构并提交"）—— 桌面 Agent 的圣杯
- **本地 LLM 集成**：Ollama 兼容已声明，但实测性能、流式、function call 稳定性未量化
- **沙箱化命令执行**：从"危险命令 + 确认"演进到 OS 级隔离（Windows Job Objects、Restricted Token）

### 8.3 工程维度
- **1317 行的 chat_window.py 拆分**：UI 组件、消息渲染、消息存储、输入处理、设置桥接 —— 边界怎么划
- **测试策略**：UI 测试 vs 单元测试比例；PySide6 集成测试框架选型（pytest-qt / squish）
- **CI/CD**：Windows runner + pynput 测试 + PyInstaller 打包 + GitHub Release

## 9. 给 Qwen 的具体研究问题（按优先级）

### Q1. 路线图 5/8/7 评估（最重要）
- 上面 §5 表格里 ❓ 标记的项（DWM 亚克力 / 动画一致性 / 文件拖放 / 快捷指令 / 开机自启），**哪些值得做、哪些可以砍？** 给出每个的 ROI 评分（1-5）和砍/做/缓的判断。
- 已有功能里有没有**已经做了但没体现在 roadmap 的**？比如 v0.2.x 的实际能力是否超出 roadmap 描述？

### Q2. 下季度产品方向
- 站在 2026 年中，**桌面 AI 伴侣**这个品类的**用户真实需求**是什么？BuddyDesk 当前的差异化够吗？
- 接下来 3-6 个月，**最值得投入的 5 个功能**是什么？给出 ROI 排序。
- 是否值得做"操作员型 AI"（录制重放）？还是先做多模态（截图理解）？
- 多模态落地的技术选型：paddleocr / qwen-vl / 本地 LLaVA / 直接调 OpenAI vision？

### Q3. 架构拆分
- `chat_window.py`（1317 行）应如何拆分？给出具体边界（类/函数/模块名）。
- `command_engine.py`（796 行）既是解析器又是执行器还是注册表 —— 是否违反单一职责？拆分建议？
- `bridge.py` 4 个 signal 是否过载？是否需要 `AIEventBus` 拆 `StreamBus` + `CommandBus`？

### Q4. 安全加固
- 评估当前"危险命令正则 + 二次确认"机制的**实际安全性**。SHELL 注入风险点清单。
- 是否应引入 OS 级沙箱（Windows Job Objects、Restricted Token）？给出 1-2 个具体技术方案的对比。
- `subprocess.run(shell=True, timeout=30)` 的 timeout 行为是否合理？Windows 下子进程树会一起回收吗？
- prompt injection 风险评估：用户消息进入 AI 上下文，恶意用户能否构造命令注入？

### Q5. 工程改进
- 测试缺口最大的 3 个模块是哪些？每个模块最该写的 5 个测试用例。
- CI 应如何配置（Windows runner、pynput 测试坑、PyInstaller 打包）？
- `updater.py` 占位符 `your-org/BuddyDesk` —— 实际 `lzsobig/BuddyDesk-pet-claude`，修法。
- 打包（PyInstaller onedir 模式，`build.spec` 已存在）的常见陷阱（图标、QSS 资源、winsound 兼容、onedir 资源路径）—— 给出踩坑清单。
- 如何从"个人项目"演进为"可被社区贡献"？需要补哪些基础设施（CONTRIBUTING.md、issue 模板、CI、release 流程、CLA）？

### Q6. 商业化与生态（可选）
- 合理开源协议（MIT 已用） + 商业化路径（赞助 / SaaS / 插件市场）的已验证先例。
- 同类项目（Open Interpreter、AutoGen、LangChain Agents 桌面端、cherry-studio）的差异化对标分析。

### Q7. 国际化潜伏债（必答）
项目当前**完全没做 i18n**，详见 §7.8。问题清单：
- 是不是该做？什么触发条件（非用户量？某个 PR 提了？）
- 如果**不做**，至少要做什么防御性工作（字串集中到 `ui/strings.py`？SYS_PROMPT 拆成模板？）
- 如果**要做**，路径是什么：自研 `i18n.py` / 引入 `gettext` / 用 `Qt.linguist`（与 PySide6 原生集成）？工作量评估
- 怎么衡量"现在做 vs 以后做"的成本差异

## 10. 期望的输出格式

请按以下结构组织回答（**每节不必长，但要有判断**）：

1. **整体评价**（1 段，200 字内）—— 第一印象与核心判断
2. **roadmap 5/8/7 评估**（直接给答案：哪些做/缓/砍，理由）
3. **架构问题清单**（按 P0/P1/P2 标注优先级，每条 1-2 句原因）
4. **下季度产品路线图**（3 / 6 / 12 月三个时间窗）
5. **具体功能 Top 5 推荐**（每个含：用户故事、技术难度、ROI 评分 1-5）
6. **安全加固清单**（最多 10 条，按风险从高到低）
7. **测试 / CI / 打包**的具体动作（每条 1 行命令级别）
8. **对 7 个研究问题的逐一回答**（Q1-Q7）
9. **附录：你最想看到但本背景没提供的项目信息**（让我补什么）

请直接给建议，不必客套。如果某项你判断"过度设计"或"先别做"，**直接说"不做"** 并说理由。
