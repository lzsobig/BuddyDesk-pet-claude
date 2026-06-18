# BuddyDesk 改进计划（最终版）

> 制定时间：2026-06-16
> **每一条都已逐行复核源码**，标注了文件:行号、属实/误报、改法、验证方式。
> 本文档可直接拆成多轮 prompt 喂给 Claude Code 执行（见末尾「执行说明」）。

---

## 复核方法说明

- 「✅ 属实」= 我读了对应源码，确认问题存在
- 「❌ 误报」= 我读了源码，发现不存在该问题
- 「🟡 部分」= 问题部分存在，细节有出入

不采用「改进建议.md」的二手判断，全部独立验证。

---

## 第一部分：发布阻塞项（P0）

不修完这些，**不要**分发给陌生用户。

---

### P0-1　命令执行安全闸门收紧 ⭐ 最关键

**问题（✅ 属实）**：

`engine/command_engine.py` 的 `[SHELL:...]` / `[CMD:...]` 标签用 `subprocess.run(shell=True)` 执行（第 577 行）。防御只靠 `_is_dangerous` 正则黑名单（第 705 行）。两个事实叠加：

1. 命令标签来自 AI 的自由文本输出，提示注入（粘贴的网页、被嗅探的图标名、剪贴板内容）可诱导模型发出任意 shell 标签。
2. 黑名单本质漏检：`python -c "import os;os.system('...')"`、`cmd /c "..."`、`msiexec /i`、`certutil -decode`、未覆盖的编码绕过均不在列表里。

README 宣称「三级安全机制」，实际只有「危险命令确认」一道实质闸门。

**改法（分两步，可独立合入）**：

**P0-1a（最高优先级，半天）**：`[SHELL:]` / `[CMD:]` **默认全部走 ConfirmDialog**，不再只靠黑名单。仅 `[APP:]`（受 `AppRegistry` 白名单约束）免确认。

- 改 `CommandEngine.parse_and_execute`（第 453 行）：cmd / shell 分支调用 `execute_command(cmd, force_confirm=True)`。
- `execute_command` 加一个 `force_confirm: bool = False` 参数：为 True 时无条件弹确认，跳过 `_is_dangerous` 判断。
- 保留 `_is_dangerous` 作为「高危额外标红」：确认弹窗里，危险命令显示更醒目的警告。
- **不要**重构 `CommandEngine` 的其他逻辑，**不要**改 `AppRegistry`。

**P0-1b（1 天）**：补全防御覆盖面。

- shell 元字符清理（第 358 行 `safe_name`）当前漏 `^ < > % !`，补上。
- `DANGEROUS_PATTERNS` 增加：`python\s+-c`、`cmd\s+/c`、`msiexec`、`certutil\s+-decode`、`bitsadmin`（已有部分）。
- 目标是白名单，但白名单是 P3 的架构改造，这里先补黑名单。

**验证**：

- 扩展 `tests/test_command_engine.py`：加用例「任意 `[SHELL:echo hi]` 都返回 success=False 且 error 含『确认』」。
- 加用例「`[APP:notepad]` 仍可免确认执行」。
- 运行：`python -m unittest tests.test_command_engine -v`（注意此文件含集成测试，会启动 notepad，加超时）。

---

### P0-2　移除硬编码的个人开发环境

**问题（✅ 属实）**：

`ai/backend.py:390-391`：
```python
DEFAULT_PROXY = "http://127.0.0.1:15721"   # 作者本机代理
DEFAULT_MODEL = "mimo-v2.5"                 # 作者私有模型
```
`ClaudeCodeBackend` 第 168 行硬编码 `claude-sonnet-4-20250514`。别人 clone 后选 Claude 后端，会先去连这个本地端口。

**改法（1 小时）**：

- `DEFAULT_PROXY` 改为 `""`（空），`DEFAULT_MODEL` 改为 `""`。
- `AnthropicDirectBackend.__init__`：当 `api_base` 为空时，标记自身 `is_available()` 返回 False，让 `create_backend` 自然回退到 CLI。
- `ClaudeCodeBackend` 的 model 默认值改为从 `user_config["claude_model"]` 读，留空时传 `None` 让 CLI 用默认。
- `create_backend`（第 514 行）逻辑不变，但因为 proxy 默认空，会自动走 CLI 后端。

**验证**：默认配置下 `create_backend({"backend":"claude_code"})` 应返回 `ClaudeCodeBackend` 而非尝试连 127.0.0.1。

---

### P0-3　settings_panel 缺 QMessageBox import（用户可触发崩溃）

**问题（✅ 属实 —— 我此前一次核查误判，现更正）**：

`ui/settings_panel.py` 第 13-15 行的 import 块：
```python
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QComboBox, QCheckBox, QFileDialog,
)
```
**没有 `QMessageBox`**。但第 494、500、509、511 行用了 `QMessageBox.information` / `.warning`。

用户点「设置 → 崩溃上报」按钮 → `NameError: name 'QMessageBox' is not defined` → 崩溃。

**改法（2 分钟）**：第 13-15 行的 import 列表加 `QMessageBox`。

**验证**：`python -c "from ui.settings_panel import SettingsPanel"` 不报错；手动打开设置点崩溃上报按钮不崩。

---

### P0-4　_refresh_md 未定义变量（用户可触发崩溃）

**问题（✅ 属实）**：

`ui/chat_window.py:559`：
```python
def _refresh_md(self, renderer):
    if self._role != "ai":
        return
    self._renderer = renderer
    if hasattr(self, "_text"):
        self._bubble.setText(self._renderer.render(self._text))
    self._text = text   # ← text 未定义，NameError
```
第 558 行已经用 `self._text` 渲染完了，第 559 行是多余的、且引用了不存在的 `text`。用户调字号缩放（触发 `_refresh_md`）→ 崩溃。

**改法（2 分钟）**：删除第 559 行 `self._text = text`。

**验证**：加一个针对 `_refresh_md` 的测试，或手动调字号缩放确认不崩。

---

### P0-5　快捷键文档自相矛盾

**问题（✅ 属实）**：

- `main.py:397` 实际实现 `Ctrl+Shift+H`（VK_CONTROL 0x11 + VK_SHIFT 0x10 + VK_H 0x48）
- README 快捷键表写 `Ctrl+Shift+H`（对）
- CHANGELOG v0.2.0 写「Hotkey changed from `Ctrl+Shift+H` **to** `Ctrl+F`」（错，与代码不符）

**改法（5 分钟）**：以代码为准，改 `CHANGELOG.md` 那一行，删掉或改成「Hotkey: `Ctrl+Shift+H` (unchanged)」。

**验证**：grep 全仓库 `Ctrl+F` 确认无残留误述。

---

### P0-6　git 跟踪卫生

**问题（✅ 属实）**：

`git status` 显示一堆未跟踪文件混在仓库根：`.obsidian/`、`ass/`（疑似 assets 拼错）、`未命名.canvas`、`find_window.ps1`、`minimize_clutter.ps1`、`restore_windows.ps1`、`_screenshot_*.py`。

**改法（半小时）**：

- `.gitignore` 增加：`.obsidian/`、`*.canvas`、`ass/`。
- 开发期脚本 `find_window.ps1` / `minimize_clutter.ps1` / `restore_windows.ps1` / `_screenshot_*.py` 移到 `tools/` 子目录或删除（确认无用后）。
- `CLAUDE.md` 测试说明里 `chorme.exe` → `chrome.exe`。

**验证**：`git status` 在干净工作区下无多余 untracked。

---

## 第二部分：稳定性 Bug（P1）

---

### P1-1　bridge 取消机制失效

**问题（✅ 属实）**：

`bridge.py:125-129`：
```python
prev_cancelled = self._cancelled   # 此时 _cancelled 已被第 79 行 reset 为 False
def guarded_worker():
    cancelled_flag[0] = prev_cancelled   # 恒为 False
    worker()
```
`send()` 第 77-79 行在加锁块里把 `_cancelled` 先设 True 再设 False，等到第 125 行读它时**永远是 False**。所以 `guarded_worker` 永远不会标记取消，旧请求的回调照常执行 → 过期回复覆盖新回复。

**改法（1-2 小时）**：

用**单调递增的 request_id** 替代 boolean flag：

- `AIBridge` 加 `self._request_counter = 0`。
- `send()` 开头 `my_id = self._request_counter += 1`（在锁内）。
- `on_chunk` / `on_done` / `on_error` 回调闭包捕获 `my_id`，执行前检查 `if my_id != self._request_counter: return`。
- 删除 `prev_cancelled` / `guarded_worker` 那套绕弯逻辑，直接 `thread = Thread(target=worker)`。
- `cancel()` 仍调 `backend.cancel()`，但真正生效靠的是 id 失效检查。

**验证**：加测试「连续调 `send()` 两次，第二次的回复到达时，第一次的 on_done 回调不应触发」。可 mock backend。

---

### P1-2　build.spec 排除 numpy 导致语音打包后崩

**问题（✅ 属实）**：

`build.spec` 的 `excludes` 列表含 `'numpy'`（约第 38 行）。但 `sensevoice_asr.py` / `voice_input.py` 依赖 numpy。打包后用语音功能 → ImportError 崩溃。

**改法（10 分钟）**：`excludes` 里删除 `'numpy'`。如果担心包体变大，后续用条件打包，而非硬排除。

**验证**：`pyinstaller build.spec` 后，打包目录里有 numpy；启动应用用语音不崩（需实机）。

---

### P1-3　event_engine._save_events 锁外写文件（竞态）

**问题（🟡 部分属实）**：

`engine/event_engine.py:225` 的 `_save_events` 在 `record()` 里于锁外调用（第 91 行）。它内部第 232-233 行遍历整个日志文件计数已有行数，多次并发 `record` 会重复追加。

不过实际触发概率低：UI 事件不会高频并发，且 `_save_events` 自己有 try/except 兜底。属于「不优雅 + 低概率数据重复」，不是高危崩溃。

**改法（30 分钟）**：

- 方案 A（简单）：把 `self._save_events()` 移进第 71 行的 `with self._lock` 块内。
- 方案 B（更好）：`_save_events` 改用「记录已写入计数」而非每次重数文件行。加 `self._saved_count`，只追加 `self.events[self._saved_count:]`。

建议先 A，后续再 B。

**验证**：多线程并发调 `record()` 100 次，日志文件无重复行、无异常。

---

## 第三部分：工程化（P2）

---

### P2-1　测试分层

**问题（✅ 属实）**：

`tests/test_command_engine.py` 的 `TestNaturalCommand` / `TestParseAndExecute` 会真启动 `notepad.exe` / 跑 `echo` / 调 `start`，混在单测里。CI 跑会挂或慢。

**改法（半天）**：

- 把 `CommandEngine` 的 subprocess 调用抽成可注入的 `_runner`（默认是 `subprocess.run`），单测里 mock。
- 真启动外部程序的用例加装饰器：`@unittest.skipUnless(os.environ.get("RUN_INTEGRATION"), "needs real OS")`，默认跳过。
- 优先补 `bridge.py`（取消逻辑，配合 P1-1）、`updater._version_gt`（纯函数，易测）、`audio.py`（WAV 生成）的覆盖。

**验证**：`python -m unittest discover tests` 默认不启动外部程序、全绿；`RUN_INTEGRATION=1` 才跑集成。

---

### P2-2　依赖锁定与元数据

**问题（✅ 属实）**：

`requirements.txt` 无版本锁定；CLAUDE.md 说「PySide6/openai/Pillow」，实际 requirements 列了 9 个（含 onnxruntime 等），两处对不上。

**改法（半天）**：

- `requirements.txt` 用 `~=` 锁定（允许 patch 升级）。
- CLAUDE.md 的依赖段与 requirements.txt 同步。
- 新增 `pyproject.toml`，放项目元数据 + ruff 配置（行宽、忽略规则）。

**验证**：`pip install -r requirements.txt` 在干净 venv 成功；`ruff check .` 无报错（修掉明显问题）。

---

### P2-3　CI 补测试

**问题（✅ 属实）**：

已有 `.github/workflows/build.yml`（仅打包 release），缺测试 CI。

**改法（1 小时）**：

新增 `.github/workflows/test.yml`：windows-latest + python 3.11，跑 `unittest discover tests`（默认跳过集成）+ `ruff check`。

**验证**：提一个 PR，确认 test.yml 跑绿。

---

### P2-4　结构化日志

**问题（✅ 属实，但可延后）**：

只有 `event_engine.py` 用 `logging`，其余全 `print` 或裸 `except: pass`（`main.py` 大量）。

**改法（1 天，v0.3 再做）**：

- 加 `logging.basicConfig` 到 `main.py` 入口。
- 全局把 `print(` 替换为 `logger.info/debug`。
- `except Exception: pass` 至少改成 `except Exception: logger.exception(...)`，别裸 pass。

**注意**：这个改动面广、diff 大，**单独一轮**给 Claude Code，且明确「只改日志，不改逻辑」。

---

## 第四部分：功能与架构（P3 —— 对接已有 PLAN.md）

这部分**不重复**，只指路：

- `docs/PLAN.md` 的 P1/P2 功能（声音/字号/Pin/截图/桌宠吞文件）**大多已在代码里实现**。剩余 P3 选做（避让岛、传送门、任务派发、嗅图标）按那份文档做。
- `docs/改进建议与发展路线.md` 的中期方向（插件化、对话管理、多模态、MCP）纳入 v0.4。

**我额外建议的一项（两份文档都没提）**：

### P3-1　命令 handler 插件化（架构改造，v0.4 核心）

把 `[APP/SHELL/CLAUDE]` 从 `parse_and_execute` 里的硬编码 `re.findall` 改成**可注册的 handler 注册表**。每个 handler 自带元数据：

```python
@command_tag("SHELL", needs_confirm=True)
class ShellHandler: ...
```

收益：一箭双雕 —— 既彻底解决 P0-1 的黑名单脆弱性（确认逻辑由 handler 声明），又打开社区扩展（`[SEARCH:]`、`[TRANSLATE:]`、`[SCREENSHOT]`）。

**注意**：这是大改，独立一轮、独立分支、要充分测试。

---

## 落地顺序

```
第一轮：P0 安全 + 崩溃修复（3 天 → v0.2.2 可发布）
  Day 1   │ P0-1a SHELL 默认确认 + 测试 │ P0-2 移除硬编码 │ P0-3 QMessageBox import │
  Day 2   │ P0-4 _refresh_md │ P0-5 文档统一 │ P0-6 git 清理 │
  Day 3   │ P1-1 bridge 取消机制 │ P1-2 build.spec numpy │

第二轮：P1/P2 工程化（3-4 天 → v0.3.0）
  Day 4   │ P1-3 event 锁 │ P2-1 测试分层 │
  Day 5   │ P2-2 依赖锁定 + pyproject │ P2-3 CI │
  Day 6+  │ P2-4 结构化日志（独立大改）│

第三轮：P3 功能（按 PLAN.md，看取舍 → v0.4）
```

**最小可发布**：只做第一轮 P0（约 2 天）即可让项目「可放心分发」。

---

## 完成定义（DoD）

- [ ] **P0-1a**：任意 `[SHELL:xxx]` 触发确认弹窗；测试验证；`[APP:]` 仍免确认
- [ ] **P0-1b**：`python -c` / `cmd /c` / `msiexec` / `certutil -decode` 被识别；元字符清理覆盖 `^ < > % !`
- [ ] **P0-2**：默认配置不连 127.0.0.1；Claude 后端回退 CLI
- [ ] **P0-3**：设置里点崩溃上报不崩
- [ ] **P0-4**：调字号缩放不崩
- [ ] **P0-5**：grep 全仓无 `Ctrl+F` 误述
- [ ] **P0-6**：`git status` 干净
- [ ] **P1-1**：连发两条消息，旧回复不覆盖新回复（有测试）
- [ ] **P1-2**：打包后语音可用
- [ ] **P1-3**：并发 record 无重复行
- [ ] **P2-1**：默认 unittest 不启动外部程序
- [ ] **P2-2**：干净 venv 安装成功
- [ ] **P2-3**：PR 自动跑 test+lint

---

## 执行说明（给 Claude Code 用）

**不要一次性执行本计划。** 按以下规则分轮：

1. **一轮只做一档**（P0 一轮，P1 一轮，…），每轮内也建议拆成更小的 commit。
2. **每轮 prompt 必须包含**：
   - 「只改 X，不要重构 Y」的明确边界
   - 「改完跑 `python -m unittest discover tests` 确认全绿」的验证指令
   - 「不要改其他文件」的约束
3. **第一轮建议只给 P0-1a**（最高价值、最小改动），用来摸清这台 Claude Code 的输出风格，再决定后续轮次粒度。
4. P0-3 / P0-4 / P0-5 这种「2 分钟改动」可以合并成一个 prompt。
5. P2-4（日志）改动面大，**必须单独一轮**，且明确「只改日志，不改逻辑」。
