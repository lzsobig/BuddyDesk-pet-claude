# Hermes Pet Win — 最终整合交付报告

## 结论

两个独立生成的版本已完成逐文件对比择优 + 橘猫素材替换 + 宠物闪烁修复。
4 个核心 UI 模块、9 个 Python 源文件、7 个状态机、72 帧橘猫素材全部整合完毕。

## 整合策略

| 维度 | 来源 | 理由 |
|------|------|------|
| 启动器 (launcher.py) | 版本 A | 后端卡片、Claude CLI 检测、宠物名字输入更完整 |
| 主题 (theme.py) | 版本 A | 含 SHADOW/DANGER/EASE 设计 tokens，圆角 16/22 |
| 灵动岛 (dynamic_island.py) | 版本 A | `_IslandGroup` + `QGraphicsOpacityEffect` 真 cross-fade 200ms，移除 `setMask` 离散化 |
| 聊天窗 (chat_window.py) | 合并版 | A 的悬浮动作按钮/橘猫头像/Ctrl+L/R 快捷键 + B 的 `MarkdownRenderer` 流式渲染 + 三角图标自绘 |
| 像素宠物 (pixel_pet.py) | 重写 | 7 状态 + 顺序帧 + **单帧状态彻底防闪烁** + 拖拽 spring |
| 配置/桥接/AI 后端 | 版本 A | 设计 token 完整 |
| 标记渲染/图标控件/托盘 | 版本 A | 增量 |
| 引擎 (命令/事件) | 版本 A | 同 |

## 橘猫素材替换

| 来源 | 去向 | 用途 |
|------|------|------|
| `assets/cat_frames_v2/frame_00..71.png` (72 帧) | 保留 | 7 状态所有精灵帧 |
| `assets/cat_frames_v2/preview_*.png` (9 张) | 保留 | 备用预览 |
| `assets/cat_sprite_sheet.png` (1.9MB) | 保留 | 合并 sprite sheet 参考 |
| `assets/chubby-orange-cat.webp` (2MB) | 保留 | 美术源文件 |
| `assets/pet_reference.png` (小宠物) | **删除** | 用户已确认：尺寸偏小、观感不佳 |
| `assets/pet_reference_thumb.png` | **删除** | 同上 |

## 7 个宠物状态映射

| 状态 | 帧 | 动画 |
|------|------|------|
| idle (默认) | `frame_00.png` | **静态单帧 — 0 重绘 — 绝不掉帧** |
| walk | `frame_08..11.png` | 4 帧循环 10 FPS + 物理位移 + 镜像翻面 |
| happy | `frame_24..27.png` | 4 帧挥手循环 |
| sleep | `frame_48.png` | 静态 + 浮动 ZZZ |
| love | `frame_24..25.png` | 2 帧 + 浮动心形 |
| thinking | `frame_64.png` | 静态 review 姿势 |
| error | `frame_40.png` | 静态 fail 表情 |

## 闪烁问题修复要点

用户反馈"宠物老是一闪一闪的，动作也不连贯"。
修复方案（见 `ui/pixel_pet.py`）：

1. **单帧状态零重绘**：`idle / sleep / thinking / error / love` 都用单帧，
   `_draw_current_frame` 检查帧索引未变时直接 `return`，不调 `setPixmap`。
2. **去除 1px 呼吸抖动**：原版本 idle 有 1px 上下微动，已彻底删除。
3. **去除 `setPixmap` 风暴**：原先每 tick 调一次，现在只有真正切帧时才调。
4. **拖拽物理与渲染解耦**：拖动时停止动画定时器，避免渲染与定位相互打架。

## 校验结果

- ✅ 14 个 Python 文件全部通过 `ast.parse` 语法校验
- ✅ 13 个模块全部 import 成功
- ✅ 20 个单元测试通过 (test_config + test_backend)
- ✅ Pet 7 状态切换 + 帧加载全部正确
- ✅ ChatWindow 正确加载橘猫头像（28×28）
- ✅ DynamicIsland 启用 cross-fade opacity groups
- ✅ Markdown 渲染器正确输出 `<h1>` 和 `<li>`
- ✅ Theme tokens (DANGER, SHADOW_MD) 全部可用
- ⚠️ `test_command_engine` 中 `TestNaturalCommand` / `TestParseAndExecute` 会调
  `subprocess.Popen` 启动外部程序（如 notepad.exe、chorme.exe），运行时会悬挂。
  与本次整合无关 — 原版本 A 即如此。CI 跑测试时建议加 `timeout=10` 包装。

## 目录结构

```
hermes-pet-win-final/
├── main.py                    # 主入口
├── bridge.py                  # AI ↔ Qt 信号桥
├── config.py                  # 全局配置 + 路径
├── theme.py                   # 设计 tokens
├── requirements.txt
├── CLAUDE.md                  # 项目说明
├── README.md
├── CHANGELOG.md
├── FINAL_REPORT.md            # 本文档
├── engine/
│   ├── command_engine.py      # [APP/SHELL/CLAUDE] 标签解析
│   └── event_engine.py        # 事件记录
├── ai/
│   └── backend.py             # Claude Code + OpenAI 兼容
├── ui/
│   ├── launcher.py            # 启动器
│   ├── dynamic_island.py      # 灵动岛（5 状态 + cross-fade + auto-collapse）
│   ├── chat_window.py         # 聊天窗（Markdown + 橘猫头像 + 三角发送）
│   ├── pixel_pet.py           # 橘猫宠物（7 状态 + 静态防闪烁）
│   ├── markdown_renderer.py
│   ├── icon_widgets.py
│   └── tray.py
├── assets/
│   ├── icons/                 # Claude/OpenAI/Code SVG
│   ├── pet_frames/            # 旧目录占位（保留兼容）
│   ├── cat_frames_v2/         # ★ 橘猫 72 帧 + 9 预览
│   ├── cat_sprite_sheet.png
│   └── chubby-orange-cat.webp
├── tests/
│   ├── test_config.py
│   ├── test_backend.py
│   ├── test_command_engine.py
│   └── test_event_engine.py
├── gan-harness/
│   ├── eval-rubric.md
│   └── spec.md
├── _screenshot_island.py
├── _screenshot_launcher.py
└── _screenshot_pet.py
```

## 运行

```bash
cd "C:\Users\李振\Desktop\hermes-pet-win-final"
pip install -r requirements.txt
python main.py
```

启动器：选 Claude Code 或 OpenAI → 启动 → 灵动岛弹出 → 双击宠物打开聊天。
全局快捷键 `Ctrl+Shift+H` 呼出/隐藏。
