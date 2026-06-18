"""
Chat Window — the main ChatWindow class.

Imports reusable widget components from chat_widgets.py.
"""
from __future__ import annotations
import os
import re
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QShortcut, QKeySequence, QColor, QPainter, QPalette
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QFrame, QWidget,
    QPushButton, QScrollArea, QApplication, QSizePolicy,
)

from bridge import AIBridge
from ui.history_panel import HistoryPanel
from theme import (
    BG_DEEP, BG_SUBTLE, BG_CARD, WHITE, BORDER, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_META, TEXT_ON_ACCENT,
    ACCENT, ACCENT_BRIGHT, ACCENT_SOFT, ACCENT_GLOW,
    GREEN, GREEN_SOFT, RED, RED_SOFT, GOLD, GOLD_SOFT, FONT_FAMILY, FONT_MONO,
    RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_PILL,
)
from config import ASSETS_DIR as _ASSETS, FONT_SCALE_LEVELS
import config as _cfg
from ui.markdown_renderer import MarkdownRenderer
from ui.chat_widgets import (
    ChatBaseWindow, ChatInput, _MessageBubble, _TypingBubble,
    _CommandResult, _make_triangle_icon, _load_cat_avatar,
)

class ChatWindow(ChatBaseWindow):
    """A frameless chat panel with a scrollable message list and conversation tabs."""

    settings_requested = Signal()  # emitted when gear icon is clicked

    def __init__(self, bridge: AIBridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._streaming = False
        self._typing_widget: _TypingBubble | None = None
        self._live_widget: _MessageBubble | None = None
        self._live_text: str = ""
        # Streaming render throttle: batch chunks, render at most every 80ms
        self._render_timer = QTimer()
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(80)
        self._render_timer.timeout.connect(self._flush_stream_render)
        # P1-2: 字号缩放（从 user_config 读 idx 还原 scale）
        self._font_scale_idx = int(bridge.user_config.get("font_scale_idx", 1))
        self._md = MarkdownRenderer(font_scale=FONT_SCALE_LEVELS[self._font_scale_idx])

        # ── Multi-conversation state ──
        self._conversations: list[dict] = []  # [{id, title, messages, created_at, updated_at}, ...]
        self._active_idx: int = 0  # index into _conversations

        self.setMinimumSize(400, 500)
        self.resize(480, 640)
        self.setAcceptDrops(True)
        self.setWindowTitle("BuddyDesk Chat")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        from PySide6.QtGui import QPalette
        pal = self.palette()
        pal.setBrush(QPalette.Window, Qt.BrushStyle.NoBrush)
        self.setPalette(pal)

        self._build_ui()
        self._wire()
        self._load_all_conversations()
        self._update_tab_bar()
        if not self.messages:
            self._sys_welcome()

    # ── messages property ─────────────────────────────────────────
    @property
    def messages(self) -> list[dict]:
        """Return the message list of the active conversation."""
        if 0 <= self._active_idx < len(self._conversations):
            return self._conversations[self._active_idx]["messages"]
        return []

    @messages.setter
    def messages(self, value: list[dict]) -> None:
        """Direct assignment — for backward compatibility during init."""
        if 0 <= self._active_idx < len(self._conversations):
            self._conversations[self._active_idx]["messages"] = value

    # ── UI ──────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        # ── Main body: history panel (hidden) + content ──
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # History panel (slide-in sidebar)
        self._history_panel = HistoryPanel()
        self._history_panel.rename_requested.connect(self._on_history_rename)
        self._history_panel.delete_requested.connect(self._on_history_delete)
        self._history_panel.restore_requested.connect(self._on_history_restore)
        self._history_panel.new_requested.connect(self._add_conversation)
        self._history_panel.closed.connect(self._on_history_closed)
        body.addWidget(self._history_panel)

        # Right side: tab bar + messages + input
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        # ── Tab bar (between header and scroll area) ──
        self._tab_bar_container = QFrame()
        self._tab_bar_container.setFixedHeight(36)
        self._tab_bar_container.setStyleSheet(
            f"QFrame {{ background:{BG_DEEP}; border:none; }}"
        )
        self._tab_bar_layout = QHBoxLayout(self._tab_bar_container)
        self._tab_bar_layout.setContentsMargins(12, 4, 8, 0)
        self._tab_bar_layout.setSpacing(4)
        self._tab_bar_layout.addStretch(1)
        content.addWidget(self._tab_bar_container)

        # Scrollable message area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background:{BG_DEEP};border:none; }}"
        )
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._message_container = QWidget()
        self._message_container.setStyleSheet(
            f"background:{BG_DEEP};border:none;"
        )
        self._messages_layout = QVBoxLayout(self._message_container)
        self._messages_layout.setContentsMargins(18, 16, 18, 16)
        self._messages_layout.setSpacing(14)
        self._messages_layout.addStretch(1)

        self._scroll.setWidget(self._message_container)
        content.addWidget(self._scroll, 1)

        content.addWidget(self._build_input())
        body.addLayout(content, 1)

        root.addLayout(body, 1)

    def _build_header(self) -> QFrame:
        hdr = QFrame()
        hdr.setFixedHeight(56)
        hdr.setStyleSheet(
            f"QFrame {{ background:{WHITE};border:none;border-bottom:1px solid {BORDER}; }}"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(18, 0, 14, 0)
        hl.setSpacing(10)

        # Header avatar — orange cat sprite if available, fallback to gradient+emoji
        avatar = QLabel()
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFixedSize(28, 28)
        cat_pm = _load_cat_avatar(28)
        if cat_pm is not None:
            avatar.setPixmap(cat_pm)
            avatar.setStyleSheet(
                f"border-radius:14px;border:1px solid {BORDER};"
                f"background:{ACCENT_SOFT};"
            )
        else:
            avatar.setText("🐱")
            avatar.setStyleSheet(
                f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {ACCENT},stop:1 {GREEN});"
                f"border-radius:14px;font-size:14px;"
            )
        hl.addWidget(avatar)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title = QLabel("BuddyDesk")
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:13px;font-weight:600;"
            f"background:transparent;border:none;"
        )
        sub = QLabel("Windows AI 伴侣")
        sub.setStyleSheet(
            f"color:{TEXT_META};font-size:10px;background:transparent;border:none;"
        )
        title_col.addWidget(title)
        title_col.addWidget(sub)
        hl.addLayout(title_col)
        hl.addStretch()

        self._status_dot = QLabel()
        self._status_dot.setFixedSize(6, 6)
        self._status_dot.setStyleSheet(f"background:{GREEN};border-radius:3px;")
        hl.addWidget(self._status_dot)

        self._status = QLabel("Ready")
        self._status.setStyleSheet(
            f"color:{GREEN};font-size:11px;font-weight:600;background:transparent;border:none;"
        )
        hl.addWidget(self._status)

        # History button
        hist_btn = QPushButton("历史")
        hist_btn.setFixedSize(52, 28)
        hist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hist_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(232,229,221,0.5); color: #4a4a46;
                border: 1px solid rgba(232,229,221,0.8); border-radius: 8px;
                font-size: 12px; font-weight: 600; padding: 2px 4px;
            }}
            QPushButton:hover {{ background: {ACCENT_SOFT}; color: {ACCENT}; border-color: {ACCENT}; }}
        """)
        hist_btn.clicked.connect(self._toggle_history)
        hl.addWidget(hist_btn)

        clr = QPushButton("清空")
        clr.setFixedSize(52, 28)
        clr.setCursor(Qt.CursorShape.PointingHandCursor)
        clr.setStyleSheet(f"""
            QPushButton {{
                background: rgba(232,229,221,0.5); color: #4a4a46;
                border: 1px solid rgba(232,229,221,0.8); border-radius: 8px;
                font-size: 12px; font-weight: 600; padding: 2px 4px;
            }}
            QPushButton:hover {{ background: {ACCENT_SOFT}; color: {ACCENT}; border-color: {ACCENT}; }}
        """)
        clr.clicked.connect(self._clear)
        hl.addWidget(clr)

        # Settings gear button
        gear_btn = QPushButton("设置")
        gear_btn.setFixedSize(52, 28)
        gear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        gear_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(232,229,221,0.5); color: #4a4a46;
                border: 1px solid rgba(232,229,221,0.8); border-radius: 8px;
                font-size: 12px; font-weight: 600; padding: 2px 4px;
            }}
            QPushButton:hover {{ background: {ACCENT_SOFT}; color: {ACCENT}; border-color: {ACCENT}; }}
        """)
        gear_btn.clicked.connect(self.settings_requested.emit)
        hl.addWidget(gear_btn)

        from ui.icon_widgets import WindowControlButton
        minimize = WindowControlButton(
            "min", color=ACCENT, hover_bg=ACCENT_SOFT, hover_fg=ACCENT,
        )
        minimize.setToolTip("最小化")
        minimize.mousePressEvent = lambda e: self.showMinimized() if e.button() == Qt.MouseButton.LeftButton else None
        hl.addWidget(minimize)

        cls = WindowControlButton(
            "close", color=ACCENT, hover_bg=RED_SOFT, hover_fg=RED,
        )
        cls.setToolTip("关闭")
        cls.mousePressEvent = lambda e: self.close() if e.button() == Qt.MouseButton.LeftButton else None
        hl.addWidget(cls)

        return hdr

    def _build_input(self) -> QFrame:
        wrap = QFrame()
        wrap.setStyleSheet(
            f"QFrame {{ background:{WHITE};border:none;border-top:1px solid {BORDER}; }}"
        )
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(18, 12, 18, 14)
        layout.setSpacing(6)

        # Input pill
        pill = QFrame()
        pill.setStyleSheet(f"""
            QFrame {{
                background: {BG_SUBTLE};
                border: 1.5px solid {BORDER};
                border-radius: {RADIUS_MD}px;
            }}
        """)
        pill_l = QHBoxLayout(pill)
        pill_l.setContentsMargins(14, 4, 4, 4)
        pill_l.setSpacing(8)

        self._input = ChatInput("说点什么…")
        self._input.send_signal.connect(self._send)
        pill_l.addWidget(self._input, 1)

        # Painted triangle icon — no font dependency
        self._send_btn = QPushButton()
        self._send_btn.setFixedSize(34, 34)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setToolTip("发送")
        self._send_btn.setIcon(_make_triangle_icon(34))
        self._send_btn.setIconSize(self._send_btn.size())
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT}; color: {WHITE};
                border: none; border-radius: 10px;
            }}
            QPushButton:hover {{ background: {ACCENT_BRIGHT}; }}
            QPushButton:disabled {{ background: {BORDER}; color: {TEXT_MUTED}; }}
        """)
        self._send_btn.clicked.connect(self._send)
        pill_l.addWidget(self._send_btn)
        layout.addWidget(pill)

        # Hint row
        hint = QHBoxLayout()
        hint.setContentsMargins(4, 0, 4, 0)
        h1 = QLabel(
            f'<span style="color:{TEXT_META};font-size:10px;">'
            f'<kbd style="background:{WHITE};border:1px solid {BORDER};'
            f'border-radius:4px;padding:1px 5px;font-family:{FONT_MONO};'
            f'font-size:10px;">Enter</kbd> 发送 · <kbd style="background:{WHITE};'
            f'border:1px solid {BORDER};border-radius:4px;padding:1px 5px;'
            f'font-family:{FONT_MONO};font-size:10px;">Ctrl+L</kbd> 清空 · '
            f'<kbd style="background:{WHITE};border:1px solid {BORDER};'
            f'border-radius:4px;padding:1px 5px;font-family:{FONT_MONO};'
            f'font-size:10px;">Ctrl+R</kbd> 重新生成</span>'
        )
        h1.setStyleSheet("background:transparent;border:none;")
        h2 = QLabel(
            f'<span style="color:{TEXT_META};font-size:10px;">'
            f'<kbd style="background:{WHITE};border:1px solid {BORDER};'
            f'border-radius:4px;padding:1px 5px;font-family:{FONT_MONO};'
            f'font-size:10px;">Ctrl+Shift+H</kbd> 呼出/隐藏</span>'
        )
        h2.setStyleSheet("background:transparent;border:none;")
        hint.addWidget(h1)
        hint.addStretch()
        hint.addWidget(h2)
        layout.addLayout(hint)

        return wrap

    # ── wire ──
    def _wire(self):
        self.bridge.chunk_received.connect(self._on_chunk)
        self.bridge.stream_done.connect(self._on_done)
        self.bridge.stream_error.connect(self._on_err)
        self.bridge.state_changed.connect(self._on_state)
        # P1-2: 字号缩放快捷键
        QShortcut(QKeySequence("Ctrl+="), self, activated=self._font_scale_up)
        QShortcut(QKeySequence("Ctrl++"), self, activated=self._font_scale_up)
        QShortcut(QKeySequence("Ctrl+-"), self, activated=self._font_scale_down)
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self._font_scale_reset)

        # P2-1: 截图快门
        QShortcut(QKeySequence("Ctrl+Shift+J"), self, activated=self._on_capture_screen)

        # P2-3: Pin 最新 AI 回答到桌面
        QShortcut(QKeySequence("Ctrl+Shift+P"), self, activated=self._on_pin_last)

    # ── P2-3 pin last AI answer ────────────────────────────────────
    def _on_pin_last(self):
        """⌘⇧P Pin 最新 AI 回答到桌面。"""
        self.pin_last_ai_answer()

    def pin_last_ai_answer(self) -> bool:
        """找到最近一条 AI 消息，调 main.py 暴露的 pin_manager 创建卡片。"""
        if not self.messages:
            self._sys("⚠️ 当前对话为空，没有可 Pin 的内容")
            return False
        # 从后往前找最后一条 AI 消息
        for m in reversed(self.messages):
            if m.get("role") == "ai" and m.get("content"):
                text = m["content"]
                # 通过 main app 暴露的 pin_manager
                main_app = self._find_main_app()
                if main_app and main_app.pin_manager:
                    pin_id = main_app.pin_manager.pin(text, self._active_idx)
                    self._sys(f"📌 已 Pin 回答到桌面（{pin_id}）")
                    return True
                else:
                    self._sys("⚠️ Pin 功能未启用")
                    return False
        self._sys("⚠️ 当前对话没有 AI 回答")
        return False

    def _find_main_app(self):
        """返回构造时注入的 BuddyDeskApp 引用。"""
        return getattr(self, "_main_app", None)

    def switch_to_conversation(self, idx: int):
        """P2-3: 切到指定 idx 的对话。"""
        if 0 <= idx < len(self._conversations):
            self._active_idx = idx
            self._update_tab_bar()
            self._render_active_conversation()
            self._sys(f"已切到对话 #{idx+1}")

    # ── P2-1 screen capture ────────────────────────────────────────
    def _on_capture_screen(self):
        """⌘⇧J 截屏：0.18s 闪光 + 截屏 + 写入输入框。"""
        try:
            import screen_capture
        except ImportError:
            self._sys("⚠️ 截图模块未加载")
            return

        def _on_done(result):
            pixmap, png_bytes = result
            if pixmap is None or not png_bytes:
                self._sys("⚠️ 截图失败")
                return
            # 保存到临时目录，给文件起个带时间戳的名字
            import tempfile
            from datetime import datetime
            tmp_dir = os.path.join(tempfile.gettempdir(), "buddydesk_screenshots")
            os.makedirs(tmp_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(tmp_dir, f"screen_{ts}.png")
            try:
                with open(path, "wb") as f:
                    f.write(png_bytes)
            except Exception:
                pass
            size_kb = len(png_bytes) / 1024
            # 把截图信息塞进输入框（仿文件 drop 风格）
            current = self._input.toPlainText().strip()
            new_text = f"[截图: {os.path.basename(path)} ({size_kb:.0f}KB)]\n路径: {path}"
            if current:
                new_text = current + "\n" + new_text
            self._input.setPlainText(new_text)
            self._input.setFocus()
            self._sys(f"📸 已截屏 ({size_kb:.0f}KB)，已附加到输入框")

        screen_capture.capture_screen_async(_on_done)

    # ── P1-2 font scale ────────────────────────────────────────────
    def _font_scale_up(self):
        if self._font_scale_idx >= len(FONT_SCALE_LEVELS) - 1:
            return
        self._font_scale_idx += 1
        self._apply_font_scale()

    def _font_scale_down(self):
        if self._font_scale_idx <= 0:
            return
        self._font_scale_idx -= 1
        self._apply_font_scale()

    def _font_scale_reset(self):
        self._font_scale_idx = 1
        self._apply_font_scale()

    def _apply_font_scale(self):
        scale = FONT_SCALE_LEVELS[self._font_scale_idx]
        self._md.set_font_scale(scale)
        # 重新渲染所有 AI 消息气泡
        for i in range(self._messages_layout.count()):
            item = self._messages_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, _MessageBubble) and getattr(w, "role", "") == "ai":
                w._refresh_md(self._md)
        # 持久化
        try:
            self.bridge.user_config["font_scale_idx"] = self._font_scale_idx
            import config as _cfg
            _cfg.save_user_config(self.bridge.user_config)
        except Exception:
            pass

    # ── message ops ──
    def _append_widget(self, w: QWidget):
        idx = self._messages_layout.count() - 1
        if idx < 0:
            self._messages_layout.addWidget(w)
        else:
            self._messages_layout.insertWidget(idx, w)
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ── P1-3 option card click ────────────────────────────────────
    def _on_option_clicked(self, text: str):
        """AI bubble 的可点击选项卡回调：填入输入框（不自动发送）。"""
        if not hasattr(self, "_input") or self._input is None:
            return
        self._input.setPlainText(text)
        self._input.setFocus()
        # 滚动到底部让用户看到填入的内容
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _sys_welcome(self):
        self._sys(
            '你好呀！我是小橘，你的 Windows AI 伴侣。\n'
            '• 说"打开微信" 打开应用\n'
            '• 说"查看IP" 执行系统命令\n'
            '• 说"帮我创建项目" 使用 Claude Code\n\n'
            f"Backend: {self.bridge.backend.get_name()}"
        )

    # ─────────────────────────────────────────────────────────────────
    # Tab bar management
    # ─────────────────────────────────────────────────────────────────

    def _update_tab_bar(self) -> None:
        """Rebuild the tab bar to reflect the current conversations list."""
        # Clear existing widgets from the layout
        while self._tab_bar_layout.count():
            item = self._tab_bar_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        # Tab buttons for each conversation
        for idx, conv in enumerate(self._conversations):
            title = conv.get("title", "新对话")
            is_active = (idx == self._active_idx)

            tab_btn = QPushButton()
            tab_btn.setFixedHeight(28)
            tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            display = title[:12] + "..." if len(title) > 12 else title
            tab_btn.setToolTip(title)
            tab_btn._conv_idx = idx  # store index for click handler

            if is_active:
                tab_btn.setText(display)
                tab_btn.setStyleSheet(
                    f"QPushButton {{ "
                    f"  background:{ACCENT}; color:{WHITE}; "
                    f"  border:none; border-radius:6px; "
                    f"  padding:0 10px; font-size:11px; font-weight:600; "
                    f"  font-family:{FONT_FAMILY}; "
                    f"  min-width:0; "
                    f"}} "
                    f"QPushButton:hover {{ background:{ACCENT_BRIGHT}; }}"
                )
            else:
                tab_btn.setText(display)
                tab_btn.setStyleSheet(
                    f"QPushButton {{ "
                    f"  background:transparent; color:{TEXT_MUTED}; "
                    f"  border:none; border-radius:6px; "
                    f"  padding:0 10px; font-size:11px; "
                    f"  font-family:{FONT_FAMILY}; "
                    f"  min-width:0; "
                    f"}} "
                    f"QPushButton:hover {{ background:{ACCENT_SOFT}; color:{TEXT_SECONDARY}; }}"
                )

            tab_btn.clicked.connect(lambda checked, i=idx: self._switch_conversation(i))
            self._tab_bar_layout.addWidget(tab_btn)

            # Close button (only if more than 1 conversation)
            if len(self._conversations) > 1:
                close_btn = QPushButton("x")
                close_btn.setFixedSize(18, 18)
                close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                close_btn.setToolTip("关闭对话")
                close_btn._close_idx = idx
                close_btn.setStyleSheet(
                    f"QPushButton {{ "
                    f"  background:transparent; color:{TEXT_MUTED}; "
                    f"  border:none; border-radius:4px; "
                    f"  font-size:10px; font-weight:600; "
                    f"  font-family:{FONT_FAMILY}; "
                    f"}} "
                    f"QPushButton:hover {{ background:{RED_SOFT}; color:{RED}; }}"
                )
                close_btn.clicked.connect(
                    lambda checked, i=idx: self._close_conversation(i)
                )
                self._tab_bar_layout.addWidget(close_btn)

        # "+" button to add new conversation
        add_btn = QPushButton("+")
        add_btn.setFixedSize(28, 28)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("新建对话")
        add_btn.setStyleSheet(
            f"QPushButton {{ "
            f"  background:transparent; color:{TEXT_MUTED}; "
            f"  border:1px dashed {BORDER}; border-radius:6px; "
            f"  font-size:14px; font-weight:600; "
            f"  font-family:{FONT_FAMILY}; "
            f"}} "
            f"QPushButton:hover {{ "
            f"  background:{ACCENT_SOFT}; color:{ACCENT}; "
            f"  border-color:{ACCENT}; "
            f"}}"
        )
        add_btn.clicked.connect(self._add_conversation)
        self._tab_bar_layout.addWidget(add_btn)

        self._tab_bar_layout.addStretch(1)

    def _switch_conversation(self, idx: int) -> None:
        """Save current conversation, then load the conversation at *idx*."""
        if idx == self._active_idx:
            return
        if idx < 0 or idx >= len(self._conversations):
            return

        # Save current messages to disk
        self._save_conversation()

        # Update active index
        self._active_idx = idx

        # Load messages from the newly active conversation
        self._render_messages_from_list(self.messages)

        # Update tab bar highlight
        self._update_tab_bar()

    def _add_conversation(self) -> None:
        """Create a new empty conversation and switch to it."""
        import uuid
        self._save_conversation()

        new_conv = {
            "id": f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
            "title": "新对话",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "messages": [],
        }
        self._conversations.append(new_conv)
        self._active_idx = len(self._conversations) - 1

        self._clear_message_display()
        self._sys_welcome()
        self._update_tab_bar()
        self._save_all_conversations()

    def _close_conversation(self, idx: int) -> None:
        """Archive conversation at *idx* and remove from tabs. Switch to adjacent if active."""
        if len(self._conversations) <= 1:
            return  # always keep at least one
        if idx < 0 or idx >= len(self._conversations):
            return

        # Archive non-empty conversations before removing
        conv = self._conversations.pop(idx)
        if conv.get("messages"):
            archive = _cfg.load_archive()
            archive.insert(0, conv)
            _cfg.save_archive(archive)

        # Adjust active index
        if self._active_idx == idx:
            self._active_idx = min(idx, len(self._conversations) - 1)
            self._render_messages_from_list(self.messages)
        elif self._active_idx > idx:
            self._active_idx -= 1

        self._update_tab_bar()
        self._save_all_conversations()

    def _rename_conversation(self, idx: int, title: str) -> None:
        """Rename conversation at *idx*."""
        if 0 <= idx < len(self._conversations):
            self._conversations[idx]["title"] = title
            self._update_tab_bar()
            self._save_all_conversations()

    def _generate_title(self, messages: list[dict]) -> str:
        """Auto-generate a title from the first user message (max 12 chars)."""
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "").strip()
                if content:
                    return content[:12] + "..." if len(content) > 12 else content
        return "新对话"

    # ─────────────────────────────────────────────────────────────────
    # Conversation persistence (multi-conversation)
    # ─────────────────────────────────────────────────────────────────

    def _load_all_conversations(self) -> None:
        """Load all conversations from disk. Falls back to creating one empty conversation."""
        import uuid
        import config as _cfg

        convs = _cfg.load_conversations()
        if convs:
            self._conversations = convs
            self._active_idx = len(convs) - 1  # default to the last conversation
            # Render messages from the active conversation
            self._render_messages_from_list(self.messages)
        else:
            # No saved conversations — create the first one
            self._conversations = [{
                "id": f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
                "title": "新对话",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "messages": [],
            }]
            self._active_idx = 0

    def _save_conversation(self) -> None:
        """Persist the current active conversation's messages and title to disk."""
        import config as _cfg
        if not (0 <= self._active_idx < len(self._conversations)):
            return
        conv = self._conversations[self._active_idx]
        # Auto-generate title from first user message if still default
        if conv.get("title") == "新对话" and self.messages:
            conv["title"] = self._generate_title(self.messages)
        conv["updated_at"] = datetime.now().isoformat()
        # Write entire list
        _cfg.save_conversations(self._conversations)

    def _save_all_conversations(self) -> None:
        """Persist the full conversation list to disk."""
        import config as _cfg
        _cfg.save_conversations(self._conversations)

    def _clear_message_display(self) -> None:
        """Remove all widgets from the message layout (but keep the trailing stretch)."""
        self._streaming = False
        self._send_btn.setEnabled(True)
        self._live_widget = None
        self._live_text = ""
        self._typing_widget = None

        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            else:
                sub = item.layout() if item else None
                if sub is not None:
                    while sub.count():
                        s = sub.takeAt(0)
                        sw = s.widget() if s else None
                        if sw is not None:
                            sw.setParent(None)
                            sw.deleteLater()

    def _render_messages_from_list(self, messages: list) -> None:
        """Clear the display and render all *messages* as _MessageBubble widgets."""
        self._clear_message_display()
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            time_str = msg.get("time", "")
            if role == "user":
                self._append_widget(_MessageBubble("user", content, time_str, renderer=self._md))
            elif role == "assistant":
                self._append_widget(_MessageBubble("ai", content, time_str, renderer=self._md))

    # ── message ops (continued) ──
    def _sys(self, text: str):
        lbl = QLabel()
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setWordWrap(True)
        lbl.setText(self._md.render(text))
        lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY};font-size:12px;line-height:1.6;"
            f"background:transparent;border:none;"
        )
        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        wrap = QFrame()
        wrap.setStyleSheet("background:transparent;border:none;")
        wrap_l = QVBoxLayout(wrap)
        wrap_l.setContentsMargins(0, 0, 0, 0)
        wrap_l.addWidget(lbl)
        outer.addWidget(wrap, 1)
        idx = self._messages_layout.count() - 1
        if idx < 0:
            self._messages_layout.addLayout(outer)
        else:
            self._messages_layout.insertLayout(idx, outer)

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M")

    def _send(self):
        text = self._input.toPlainText().strip()
        if not text or self._streaming:
            return
        self._input.clear()
        # 显示用户消息气泡
        self._append_widget(_MessageBubble("user", text, self._now(), renderer=self._md))
        self.messages.append({"role": "user", "content": text, "time": datetime.now().isoformat()})
        self._streaming = True
        self._send_btn.setEnabled(False)
        self._typing_widget = _TypingBubble()
        self._append_widget(self._typing_widget)
        self.bridge.send(self.messages)

    def _send_text(self, text: str) -> None:
        """P3-5: 外部（如桌宠嗅图标）直接发文本，跳过 input 清空逻辑。"""
        if not text or self._streaming:
            return
        self._input.setPlainText(text)
        self._send()
        # 恢复 input 高度
        if hasattr(self._input, "setFixedHeight"):
            self._input.setFixedHeight(self._input.LINE_H + 8)

    def _on_chunk(self, chunk: str, _full: str):
        if self._typing_widget is not None:
            self._messages_layout.removeWidget(self._typing_widget)
            self._typing_widget.setParent(None)
            self._typing_widget.deleteLater()
            self._typing_widget = None
            self._live_widget = _MessageBubble("ai", chunk, self._now(),
                                               renderer=self._md)
            self._append_widget(self._live_widget)
            self._live_text = chunk
            self._live_widget.set_text(chunk, streaming=True)
        else:
            self._live_text += chunk
            # Throttle: schedule a delayed render instead of rendering every chunk
            self._render_timer.start()  # restarts the 80ms countdown

    def _flush_stream_render(self):
        """Render accumulated streaming text (called by throttle timer)."""
        if self._live_widget is not None:
            self._live_widget.set_text(self._live_text, streaming=True)

    def _on_done(self, full: str):
        self.messages.append({"role": "ai", "content": full, "time": datetime.now().isoformat()})
        self._streaming = False
        self._send_btn.setEnabled(True)
        # Cancel throttle timer and do final full render
        self._render_timer.stop()
        if self._live_widget is not None:
            self._live_widget.set_text(full, streaming=False)
            self._live_widget = None
        self._live_text = ""
        # Auto-save after each response
        self._save_conversation()
        # Update tab title if this is the first user message response
        self._update_tab_bar()

    def _on_err(self, err: str):
        self._streaming = False
        self._send_btn.setEnabled(True)
        self._render_timer.stop()
        if self._typing_widget is not None:
            self._messages_layout.removeWidget(self._typing_widget)
            self._typing_widget.setParent(None)
            self._typing_widget.deleteLater()
            self._typing_widget = None
        err_bubble = _MessageBubble("ai", f"❌ {err}", self._now(),
                                    renderer=self._md)
        self._append_widget(err_bubble)

    def _on_state(self, state: str, _preview: str):
        cmap = {"idle": GREEN, "thinking": GOLD, "error": RED}
        lmap = {"idle": "Ready", "thinking": "Thinking…", "error": "Error"}
        self._status.setText(lmap.get(state, "Ready"))
        self._status.setStyleSheet(
            f"color:{cmap.get(state, GREEN)};font-size:10px;"
            f"background:transparent;border:none;"
        )
        self._status_dot.setStyleSheet(
            f"background:{cmap.get(state, GREEN)};border-radius:3px;"
        )

    # ─────────────────────────────────────────────────────────────────
    # History panel handlers
    # ─────────────────────────────────────────────────────────────────

    def _toggle_history(self):
        """Toggle the history panel open/closed."""
        if self._history_panel.isVisible():
            self._history_panel.hide()
        else:
            archive = _cfg.load_archive()
            self._history_panel.update_data(archive)
            self._history_panel.show()

    def _on_history_switch(self, idx: int):
        """Switch to a conversation from the history panel."""
        self._switch_conversation(idx)
        self._history_panel.hide()

    def _on_history_rename(self, idx: int, title: str):
        """Rename a conversation in the archive."""
        archive = _cfg.load_archive()
        if 0 <= idx < len(archive):
            archive[idx]["title"] = title
            _cfg.save_archive(archive)
            self._history_panel.update_data(archive)

    def _on_history_delete(self, idx: int):
        """Permanently delete a conversation from the archive."""
        archive = _cfg.load_archive()
        if 0 <= idx < len(archive):
            archive.pop(idx)
            _cfg.save_archive(archive)
            self._history_panel.update_data(archive)

    def _on_history_restore(self, idx: int):
        """Restore an archived conversation back to the tab bar."""
        archive = _cfg.load_archive()
        if 0 <= idx < len(archive):
            conv = archive.pop(idx)
            _cfg.save_archive(archive)
            self._conversations.append(conv)
            self._active_idx = len(self._conversations) - 1
            # Reload messages for the restored conversation
            self.messages = list(conv.get("messages", []))
            self._render_messages_from_list(self.messages)
            self._update_tab_bar()
            self._save_all_conversations()
            self._history_panel.update_data(_cfg.load_archive())
            self._history_panel.hide()

    def _on_history_closed(self):
        """History panel closed — no-op, just for completeness."""
        pass

    def append_command_result(self, cmd: str, ok: bool, out: str):
        self._append_widget(_CommandResult(cmd, ok))

    def _clear(self):
        self.messages.clear()
        self._streaming = False
        self._send_btn.setEnabled(True)
        self._live_widget = None
        self._live_text = ""
        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            else:
                sub = item.layout() if item else None
                if sub is not None:
                    while sub.count():
                        s = sub.takeAt(0)
                        sw = s.widget() if s else None
                        if sw is not None:
                            sw.setParent(None)
                            sw.deleteLater()
        self._sys("Chat cleared.")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        usable = int(self.width() * 0.88)
        bubble_max = max(220, usable - 18 - 18 - 24 - 10)
        for i in range(self._messages_layout.count() - 1):
            item = self._messages_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, _MessageBubble):
                w._bubble.setMaximumWidth(bubble_max)

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()
            self._input.setFocus()

    # ── Keyboard shortcuts ──
    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_L and (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._clear()
            e.accept()
            return
        if e.key() == Qt.Key.Key_R and (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._regenerate()
            e.accept()
            return
        super().keyPressEvent(e)

    def _regenerate(self):
        """Remove the last AI message and resend the last user message."""
        if self._streaming or not self.messages:
            return
        # Pop assistant messages from history and UI
        while self.messages and self.messages[-1]["role"] == "ai":
            self.messages.pop()
            for i in range(self._messages_layout.count() - 1, -1, -1):
                item = self._messages_layout.itemAt(i)
                w = item.widget() if item else None
                if isinstance(w, _MessageBubble) and w._role == "ai":
                    self._messages_layout.removeWidget(w)
                    w.setParent(None)
                    w.deleteLater()
                    break
        # Re-send using the existing last user message without re-appending
        if self.messages and self.messages[-1]["role"] == "user":
            last_user_text = self.messages[-1]["content"]
            self._streaming = True
            self._send_btn.setEnabled(False)
            self._typing_widget = _TypingBubble()
            self._append_widget(self._typing_widget)
            self.bridge.send(self.messages)

    def closeEvent(self, event):
        """Save conversation on window close."""
        self._save_conversation()
        super().closeEvent(event)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        w, h = float(self.width()), float(self.height())
        r = float(RADIUS_LG)
        # Clear to transparent FIRST — overrides QSS solid background
        p.setPen(Qt.PenStyle.NoPen)
        p.fillRect(QRectF(0, 0, w, h), Qt.GlobalColor.transparent)
        # Draw rounded rect — corners remain transparent (anti-aliased)
        p.setBrush(QColor(BG_DEEP))
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)
        p.end()

    # ── File drag-and-drop ─────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        paths = [u.toLocalFile() for u in urls if u.toLocalFile() and os.path.isfile(u.toLocalFile())]
        if not paths:
            return
        self._on_dropped_files(paths)
        event.acceptProposedAction()

    def _on_dropped_files(self, paths: list):
        """P2-2: 统一处理拖入 / 桌宠吞下的文件列表（已过滤敏感词）。"""
        from ui.drag_drop_util import filter_sensitive_filepaths
        kept, filtered = filter_sensitive_filepaths(paths)
        for fp in filtered:
            self._sys(f"⚠️ 跳过敏感文件: {os.path.basename(fp)}")
        if not kept:
            return
        # 追加到现有文本
        for path in kept:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(8000)
            except Exception:
                content = f"[无法读取文件: {os.path.basename(path)}]"
            name = os.path.basename(path)
            size_kb = os.path.getsize(path) / 1024
            new = f"[附件: {name} ({size_kb:.1f}KB)]\n{content[:2000]}"
            cur = self._input.toPlainText().strip()
            self._input.setPlainText((cur + "\n" + new) if cur else new)
        self._input.setFocus()


