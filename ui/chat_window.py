"""
Chat Window — the main ChatWindow class.

Imports reusable widget components from chat_widgets.py.
"""
from __future__ import annotations
import os
import re
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QEvent
from PySide6.QtGui import QShortcut, QKeySequence, QColor, QPainter, QPalette
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QFrame, QWidget,
    QPushButton, QScrollArea, QApplication, QSizePolicy, QMenu, QListWidget, QListWidgetItem, QSizeGrip,
    QFileDialog, QLayout,
)

from bridge import AIBridge
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
    ChatBaseWindow, ChatInput, SidebarButton, _MessageBubble, _TypingBubble,
    _CommandResult, _make_triangle_icon, _load_cat_avatar,
)


def _normalize_role(role: str) -> str:
    """Normalize persisted message roles to the display roles used by the UI.

    New replies are persisted with ``role == "ai"``, but legacy data (and some
    earlier versions) stored ``"assistant"``. Both must render as AI bubbles.
    """
    if role == "user":
        return "user"
    return "ai"


class ChatWindow(ChatBaseWindow):
    """A frameless chat panel with a scrollable message list and conversation tabs."""

    settings_requested = Signal()  # emitted when gear icon is clicked

    def __init__(self, bridge: AIBridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._streaming = False
        self._typing_widget: _TypingBubble | None = None
        self._tool_busy_widget: _TypingBubble | None = None
        self._live_widget: _MessageBubble | None = None
        self._live_text: str = ""
        self._error_card = None
        self._tool_operations = {}
        self._tool_cards = {}
        self._sidebar_width = 0
        # Streaming render throttle: batch chunks, render at most every 80ms
        self._render_timer = QTimer()
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(80)
        self._render_timer.timeout.connect(self._flush_stream_render)
        # P1-2: 字号缩放（从 user_config 读 idx 还原 scale）
        try:
            self._font_scale_idx = min(len(FONT_SCALE_LEVELS) - 1, max(0, int(bridge.user_config.get("font_scale_idx", 1))))
        except (TypeError, ValueError):
            self._font_scale_idx = 1
        self._md = MarkdownRenderer(font_scale=FONT_SCALE_LEVELS[self._font_scale_idx])

        # ── Multi-conversation state ──
        self._conversations: list[dict] = []  # [{id, title, messages, created_at, updated_at}, ...]
        self._active_idx: int = 0  # index into _conversations

        self.setMinimumSize(420, 420)
        self.resize(480, 600)
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
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        # ── Main body: history panel (hidden) + content ──
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._session_panel = QFrame()
        self._session_panel.setFixedWidth(190)
        self._session_panel.setObjectName("sessionPanel")
        self._session_panel.setStyleSheet(f"QFrame#sessionPanel {{background:{BG_SUBTLE};border:none;}}")
        navigation = QVBoxLayout(self._session_panel)
        navigation.setContentsMargins(10, 14, 10, 14)
        heading = QLabel("会话")
        heading.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;padding:4px;background:transparent;")
        navigation.addWidget(heading)
        self._session_list = QListWidget()
        self._session_list.setWordWrap(True)
        self._session_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._session_list.setStyleSheet(f"QListWidget {{background:transparent;border:none;outline:none;color:{TEXT_SECONDARY};font-size:12px;}}"
            f"QListWidget::item {{padding:10px 8px;border-radius:6px;}}"
            f"QListWidget::item:selected {{background:{BG_CARD};color:{TEXT_PRIMARY};}}"
            f"QListWidget::item:hover {{background:{BG_CARD};}}")
        self._session_list.itemClicked.connect(self._select_session)
        self._session_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._session_list.customContextMenuRequested.connect(self._session_menu)
        navigation.addWidget(self._session_list)
        self._session_panel.hide()
        body.addWidget(self._session_panel)

        # Right side: tab bar + messages + input
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        # Scrollable message area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            "QScrollArea { background:transparent;border:none; }"
        )
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._last_scroll_maximum = 0
        self._scroll.verticalScrollBar().rangeChanged.connect(self._scroll_range_changed)

        self._message_container = QWidget()
        self._message_container.setStyleSheet("background:transparent;border:none;")
        self._scroll.viewport().setAutoFillBackground(False)
        self._messages_layout = QVBoxLayout(self._message_container)
        self._messages_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self._messages_layout.setContentsMargins(24, 22, 24, 20)
        self._messages_layout.setSpacing(20)
        self._messages_layout.addStretch(1)

        self._scroll.setWidget(self._message_container)
        content.addWidget(self._scroll, 1)

        content.addWidget(self._build_input())
        body.addLayout(content, 1)

        root.addLayout(body, 1)
        self._resize_grip = QSizeGrip(self)
        self._resize_grip.setFixedSize(14, 14)
        self._resize_grip.setStyleSheet("background:transparent;")
        self._resize_grip.setToolTip("拖动调整窗口大小")

    def _build_header(self) -> QFrame:
        hdr = QFrame()
        hdr.setObjectName("chatHeader")
        hdr.setFixedHeight(58)
        hdr.setStyleSheet(
            f"QFrame#chatHeader {{ background:transparent;border:none;"
            f"border-bottom:1px solid {BORDER_SUBTLE}; }}"
        )
        layout = QHBoxLayout(hdr)
        layout.setContentsMargins(22, 10, 16, 10)
        layout.setSpacing(10)
        self._sidebar_button = SidebarButton()
        self._sidebar_button.clicked.connect(self._toggle_history)
        layout.addWidget(self._sidebar_button)
        avatar = QLabel()
        self._pet_avatar = avatar
        avatar.setFixedSize(28, 28)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setPixmap(_load_cat_avatar(28, pet_id=self.bridge.user_config.get("pet_id", "orange"), ratio=self.devicePixelRatioF()) or _make_triangle_icon(28))
        layout.addWidget(avatar)
        self._pet_title = QLabel(str(self.bridge.user_config.get("pet_name", "小橘")))
        self._pet_title.setTextFormat(Qt.TextFormat.PlainText)
        self._pet_title.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:14px;font-weight:600;")
        layout.addWidget(self._pet_title)
        self._conversation_title = QLabel("新对话")
        self._conversation_title.setTextFormat(Qt.TextFormat.PlainText)
        self._conversation_title.setMinimumWidth(0)
        self._conversation_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._conversation_title.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        layout.addWidget(self._conversation_title, 1)
        new_chat = QPushButton("＋")
        new_chat.setFixedSize(28, 28)
        new_chat.setAccessibleName("新建对话")
        new_chat.setToolTip("新建对话")
        new_chat.setStyleSheet(f"QPushButton {{background:transparent;border:none;padding:0;color:{TEXT_MUTED};font-size:19px;}}"
                              f"QPushButton:hover {{background:{BG_CARD};border-radius:7px;}}")
        new_chat.clicked.connect(self._add_conversation)
        layout.addWidget(new_chat)

        self._status = QLabel()
        self._status.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        self._status.hide()
        layout.addWidget(self._status)
        more = QPushButton("···")
        more.setFixedSize(30, 30)
        more.setToolTip("对话、历史和设置")
        more.setAccessibleName("对话、历史和设置")
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more.setStyleSheet(
            f"QPushButton {{ background:transparent;color:{TEXT_MUTED};"
            f"border:none;padding:0;font-size:18px; }}"
            f"QPushButton:hover {{ background:{BG_CARD};border-radius:8px; }}"
        )
        menu = QMenu(more)
        menu.addAction("新建对话", self._add_conversation)
        menu.addAction("归档当前会话", lambda: self._close_conversation(self._active_idx))
        menu.addSeparator()
        menu.addAction("重新生成回答    Ctrl+R", self._regenerate)
        menu.addAction("清空当前对话    Ctrl+L", self._clear)
        menu.addSeparator()
        menu.addAction("语音设置", lambda: self._open_settings_page(2))
        menu.addAction("访问权限", lambda: self._open_settings_page(1))
        menu.addAction("设置", self.settings_requested.emit)
        more.clicked.connect(lambda: menu.exec(more.mapToGlobal(more.rect().bottomLeft())))
        layout.addWidget(more)

        from ui.icon_widgets import WindowControlButton
        minimize = WindowControlButton("min", color=TEXT_MUTED, hover_bg=BG_CARD, hover_fg=TEXT_PRIMARY)
        minimize.setToolTip("最小化")
        minimize.mousePressEvent = lambda e: self.showMinimized() if e.button() == Qt.MouseButton.LeftButton else None
        layout.addWidget(minimize)
        close = WindowControlButton("close", color=TEXT_MUTED, hover_bg=RED_SOFT, hover_fg=RED)
        close.setToolTip("关闭")
        close.mousePressEvent = lambda e: self.close() if e.button() == Qt.MouseButton.LeftButton else None
        layout.addWidget(close)
        return hdr

    def _build_input(self) -> QFrame:
        wrap = QFrame()
        wrap.setObjectName("composerWrap")
        wrap.setStyleSheet("QFrame#composerWrap {background:transparent;border:none;}")
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(22, 12, 22, 20)
        self._integration_notice = QLabel()
        self._integration_notice.setTextFormat(Qt.TextFormat.PlainText)
        self._integration_notice.setWordWrap(True)
        self._integration_notice.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;background:transparent;")
        self._integration_notice.hide()
        layout.addWidget(self._integration_notice)
        pill = QFrame()
        pill.setObjectName("composer")
        pill.setStyleSheet(
            f"QFrame#composer {{ background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:14px; }}"
        )
        composer = QHBoxLayout(pill)
        composer.setContentsMargins(9, 9, 9, 9)
        composer.setSpacing(4)
        from ui.icon_widgets import VoiceButton, IslandActionButton
        self._attach_btn = IslandActionButton("attach")
        self._attach_btn.setToolTip("添加文件或文件夹")
        self._attach_btn.setAccessibleName("添加附件")
        attachment_menu = QMenu(self._attach_btn)
        attachment_menu.addAction("选择文件…    Ctrl+O", self._choose_files)
        attachment_menu.addAction("选择文件夹…    Ctrl+Shift+O", self._choose_folder)
        attachment_menu.addSeparator()
        attachment_menu.addAction("截取屏幕…    Ctrl+Shift+J", self._on_capture_screen)
        self._attach_btn.clicked.connect(
            lambda: attachment_menu.exec(self._attach_btn.mapToGlobal(self._attach_btn.rect().topLeft()))
        )
        composer.addWidget(self._attach_btn, 0, Qt.AlignmentFlag.AlignBottom)
        self._input = ChatInput("发送消息…")
        self._input.setAccessibleName("消息输入框")
        self._input.send_signal.connect(self._send)
        composer.addWidget(self._input, 1)
        composer.addSpacing(8)
        self._voice_btn = VoiceButton()
        self._voice_btn.setToolTip("语音输入（Ctrl+Shift+V）")
        self._voice_btn.setAccessibleName("语音输入")
        self._voice_btn.clicked.connect(self._on_voice_button)
        composer.addWidget(self._voice_btn, 0, Qt.AlignmentFlag.AlignBottom)
        self._send_btn = IslandActionButton("send")
        self._send_btn.setAccessibleName("发送消息")
        self._send_btn.setToolTip("发送消息（Enter）")
        self._input.textChanged.connect(self._update_send_button)
        self._update_send_button()
        self._send_btn.clicked.connect(self._send_or_stop)
        composer.addWidget(self._send_btn, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addWidget(pill)
        self._access_mode_btn = QPushButton()
        self._access_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._access_mode_btn.setToolTip("打开访问权限设置")
        self._access_mode_btn.setStyleSheet(
            f"QPushButton {{background:transparent;color:{TEXT_MUTED};border:none;"
            f"padding:4px 2px 0;font-size:10px;}}"
            f"QPushButton:hover {{color:{ACCENT};}}"
        )
        self._access_mode_btn.clicked.connect(lambda: self._open_settings_page(1))
        layout.addWidget(self._access_mode_btn, 0, Qt.AlignmentFlag.AlignRight)
        self.refresh_access_mode()
        return wrap

    def _open_settings_page(self, page: int):
        main_app = self._find_main_app()
        if main_app is not None:
            main_app._open_settings(page)
        else:
            self.settings_requested.emit()

    def refresh_access_mode(self):
        mode = self.bridge.user_config.get("agent_access_mode", "confirm")
        label = "完全访问" if mode == "full" else "逐次确认"
        self._access_mode_btn.setText(f"访问权限：{label} ›")
        self._access_mode_btn.setAccessibleName(f"访问权限：{label}，打开设置")

    def _choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        if paths:
            self._on_dropped_files(paths)

    def _choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if path:
            self._on_dropped_files([path])

    # ── wire ──
    def _wire(self):
        self.bridge.chunk_received.connect(self._on_chunk)
        self.bridge.stream_done.connect(self._on_done)
        self.bridge.stream_error.connect(self._on_err)
        self.bridge.state_changed.connect(self._on_state)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._choose_files)
        QShortcut(QKeySequence("Ctrl+Shift+O"), self, activated=self._choose_folder)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._add_conversation)
        # P1-2: 字号缩放快捷键
        QShortcut(QKeySequence("Ctrl+="), self, activated=self._font_scale_up)
        QShortcut(QKeySequence("Ctrl++"), self, activated=self._font_scale_up)
        QShortcut(QKeySequence("Ctrl+-"), self, activated=self._font_scale_down)
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self._font_scale_reset)

        # P2-1: 截图快门
        QShortcut(QKeySequence("Ctrl+Shift+J"), self, activated=self._on_capture_screen)

        # P2-3: Pin 最新 AI 回答到桌面
        QShortcut(QKeySequence("Ctrl+Shift+P"), self, activated=self._on_pin_last)

    def _on_voice_button(self):
        """Toggle push-to-talk from the visible microphone control."""
        main_app = self._find_main_app()
        if main_app and main_app.agent:
            main_app.agent.start_chat_voice()
            return
        voice = getattr(main_app, "voice_input", None) if main_app else None
        if voice is None or not voice.is_available():
            self._sys(getattr(voice, "last_error", "") or "请在设置 → 语音中配置识别方式")
            self.settings_requested.emit()
            return
        if voice._recording:
            main_app._do_voice_stop()
            self._voice_btn.set_recording(False)
            self._voice_btn.setToolTip("语音输入（Ctrl+Shift+V）")
            return
        if getattr(voice, "_processing", False) is True:
            self._voice_btn.setToolTip("正在识别，请稍候")
            return
        main_app._on_voice_press()
        if voice._recording:
            self._voice_btn.set_recording(True)
            self._voice_btn.setToolTip("停止录音")

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
            if _normalize_role(m.get("role", "")) == "ai" and m.get("content") and m.get("kind") != "tool_result":
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
            if isinstance(w, _MessageBubble) and w._role == "ai":
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
        if isinstance(w, _MessageBubble):
            width = max(180, self._scroll.viewport().width() - 48)
            w.setMaximumWidth(width)
            w._bubble.setMaximumWidth(width if w._role == "ai" else int(width * 0.88))
        busy = getattr(self, "_tool_busy_widget", None)
        idx = self._messages_layout.indexOf(busy) if busy is not None and w is not busy else -1
        if idx < 0:
            idx = self._messages_layout.count() - 1
        if idx < 0:
            self._messages_layout.addWidget(w)
        else:
            self._messages_layout.insertWidget(idx, w)
        bar = self._scroll.verticalScrollBar()
        if bar.value() >= self._last_scroll_maximum - 24:
            QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def _scroll_range_changed(self, minimum, maximum):
        bar = self._scroll.verticalScrollBar()
        follow = bar.value() >= self._last_scroll_maximum - 24
        self._last_scroll_maximum = maximum
        if follow:
            bar.setValue(maximum)

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
        if getattr(self, "_welcome_card", None) is not None:
            return
        card = QFrame()
        card.setStyleSheet("background:transparent;border:none;")
        area = QVBoxLayout(card)
        area.setContentsMargins(4, 56, 4, 20)
        title = QLabel("有什么想一起做的？")
        title.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:20px;font-weight:600;")
        hint = QLabel("问个问题，或从一个想法开始。")
        hint.setStyleSheet(f"color:{TEXT_MUTED};font-size:12px;padding-top:6px;")
        area.addWidget(title)
        area.addWidget(hint)
        self._welcome_card = card
        self._append_widget(card)

    def _update_tab_bar(self) -> None:
        if 0 <= self._active_idx < len(self._conversations):
            title = self._conversations[self._active_idx].get("title", "新对话")
            self._conversation_title.setText(title)
            self._conversation_title.setToolTip(title)
        self._session_list.clear()
        for index, conversation in enumerate(self._conversations):
            item = QListWidgetItem(conversation.get("title", "新对话"))
            item.setToolTip(item.text())
            item.setData(Qt.ItemDataRole.UserRole, ("active", index))
            self._session_list.addItem(item)
            if index == self._active_idx:
                self._session_list.setCurrentItem(item)
        archived = _cfg.load_archive()
        if archived:
            heading = QListWidgetItem("已归档")
            heading.setFlags(Qt.ItemFlag.NoItemFlags)
            self._session_list.addItem(heading)
            for index, conversation in enumerate(archived):
                item = QListWidgetItem(conversation.get("title", "历史对话"))
                item.setData(Qt.ItemDataRole.UserRole, ("archive", index))
                item.setToolTip(item.text())
                self._session_list.addItem(item)

    def _select_session(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, index = data
        if kind == "archive":
            self._on_history_restore(index)
        else:
            self._switch_conversation(index)
        self._close_sidebar()

    def _session_menu(self, position):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        item = self._session_list.itemAt(position)
        if item is None or not item.data(Qt.ItemDataRole.UserRole):
            return
        kind, index = item.data(Qt.ItemDataRole.UserRole)
        title = item.text()
        menu = QMenu(self)
        rename = menu.addAction("重命名")
        remove = menu.addAction("归档" if kind == "active" else "删除")
        choice = menu.exec(self._session_list.mapToGlobal(position))
        if choice == rename:
            value, accepted = QInputDialog.getText(self, "重命名会话", "名称", text=title)
            if accepted and value.strip():
                callback = self._rename_conversation if kind == "active" else self._on_history_rename
                callback(index, value.strip())
        elif choice == remove:
            if kind == "active":
                self._close_conversation(index)
            elif QMessageBox.question(self, "删除历史", "删除这条已归档会话？") == QMessageBox.StandardButton.Yes:
                self._on_history_delete(index)

    def _switch_conversation(self, idx: int) -> None:
        self.bridge.temporary_context = ""
        """Save current conversation, then load the conversation at *idx*."""
        if idx == self._active_idx:
            return
        if idx < 0 or idx >= len(self._conversations):
            return

        self._stop_generation()
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
        self._stop_generation()
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
        if 0 <= idx < len(self._conversations) and any(origin is self._conversations[idx] for origin, _ in self._tool_operations.values()):
            self.set_integration_warning("这段会话还有本机操作，完成后再归档。")
            return
        if len(self._conversations) <= 1:
            self._add_conversation()
        if idx < 0 or idx >= len(self._conversations):
            return

        self._stop_generation()
        self._save_conversation()
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
            for conversation in convs:
                for message in conversation.get("messages", []):
                    if message.get("kind") == "tool_result" and message.get("tool_status") in ("queued", "running"):
                        message.update(tool_status="interrupted", success=None, content="上次会话已结束，未能确认这项操作的执行结果。")
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
        self._remove_typing()
        self.set_tool_busy(False)
        self._streaming = False
        self._set_generating(False)
        self._live_widget = None
        self._live_text = ""
        self._typing_widget = None
        self._error_card = None
        self._welcome_card = None
        self._tool_cards = {}

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
        if not messages:
            self._sys_welcome()
        for msg in messages:
            if msg.get("kind") == "tool_result":
                card = _CommandResult(msg.get("command", ""), msg.get("success"), msg.get("content", ""), title=msg.get("title", "本机操作"), state=msg.get("tool_status"))
                self._tool_cards[msg.get("operation_id", "")] = card
                self._append_widget(card)
                continue
            role = _normalize_role(msg.get("role", "user"))
            content = msg.get("content", "")
            time_str = msg.get("time", "")
            if role == "user":
                self._append_widget(_MessageBubble("user", content, time_str, renderer=self._md))
            else:
                self._append_widget(_MessageBubble("ai", content, time_str, renderer=self._md))
        self._on_state("executing" if self._tool_operations else "idle")

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

    def set_integration_warning(self, message):
        self._integration_notice.setText(message)
        self._integration_notice.setVisible(bool(message))

    def _set_generating(self, active):
        self._streaming = active
        self._send_btn.set_busy(active)
        self._send_btn.setToolTip("停止生成，保留已收到的内容" if active else "发送消息（Enter）")
        self._update_send_button()

    def _update_send_button(self):
        self._send_btn.setEnabled(self._streaming or bool(self._input.toPlainText().strip()))

    def _send_or_stop(self):
        if self._streaming:
            self._stop_generation()
        else:
            self._send()

    def _remove_typing(self):
        if self._typing_widget is not None:
            self._messages_layout.removeWidget(self._typing_widget)
            self._typing_widget.setParent(None)
            self._typing_widget.deleteLater()
            self._typing_widget = None

    def set_tool_busy(self, busy: bool, label: str = ""):
        if busy:
            if self._tool_busy_widget is None:
                self._tool_busy_widget = _TypingBubble("正在使用工具")
                self._append_widget(self._tool_busy_widget)
            if label:
                self._tool_busy_widget.set_progress(label, trusted=True)
        elif self._tool_busy_widget is not None:
            self._messages_layout.removeWidget(self._tool_busy_widget)
            self._tool_busy_widget.setParent(None)
            self._tool_busy_widget.deleteLater()
            self._tool_busy_widget = None

    def _dismiss_error(self):
        if self._error_card is not None:
            self._messages_layout.removeWidget(self._error_card)
            self._error_card.setParent(None)
            self._error_card.deleteLater()
            self._error_card = None

    def _stop_generation(self):
        if not self._streaming:
            return
        self._set_generating(False)
        self.bridge.cancel()
        self._render_timer.stop()
        self._remove_typing()
        if self._live_text and self._live_widget is not None:
            self._live_widget.set_text(self._live_text, streaming=False)
            self.messages.append({"role": "ai", "content": self._live_text,
                                  "time": datetime.now().isoformat()})
        self._live_widget = None
        self._live_text = ""
        self.bridge.state_changed.emit("idle", "已停止")
        self._save_conversation()
        self._update_tab_bar()

    def _retry_response(self):
        if not self._streaming and self.messages and self.messages[-1].get("error_partial"):
            self.messages.pop()
        if self._streaming or not self.messages or self.messages[-1].get("role") != "user":
            return
        self._dismiss_error()
        if self._live_widget is not None:
            self._messages_layout.removeWidget(self._live_widget)
            self._live_widget.setParent(None)
            self._live_widget.deleteLater()
        self._live_widget = None
        self._live_text = ""
        self._set_generating(True)
        self._typing_widget = _TypingBubble()
        self._append_widget(self._typing_widget)
        self.bridge.send(self._message_payload())

    def _send(self):
        text = self._input.toPlainText().strip()
        if not text or self._streaming:
            return
        if self._error_card is not None and self._live_widget is not None:
            self._messages_layout.removeWidget(self._live_widget)
            self._live_widget.setParent(None)
            self._live_widget.deleteLater()
            self._live_widget = None
        self._dismiss_error()
        self._input.clear()
        welcome = getattr(self, "_welcome_card", None)
        if welcome is not None:
            self._messages_layout.removeWidget(welcome)
            welcome.deleteLater()
            self._welcome_card = None
        # 显示用户消息气泡
        self._append_widget(_MessageBubble("user", text, self._now(), renderer=self._md))
        self.messages.append({"role": "user", "content": text, "time": datetime.now().isoformat()})
        self._live_text = ""
        self._live_widget = None
        self._streaming = True
        self._set_generating(True)
        self._typing_widget = _TypingBubble()
        self._append_widget(self._typing_widget)
        self.bridge.send(self._message_payload())

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
        if not self._streaming:
            return
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
            if not self._render_timer.isActive():
                self._render_timer.start()

    def _flush_stream_render(self):
        """Render accumulated streaming text (called by throttle timer)."""
        if self._live_widget is not None:
            self._live_widget.set_text(self._live_text, streaming=True)

    def _on_done(self, full: str):
        if not self._streaming:
            return
        if not full.strip():
            self._on_err("服务没有返回内容，请重试。")
            return
        self._render_timer.stop()
        self._remove_typing()
        if self._live_widget is not None:
            self._live_widget.set_text(full, streaming=False)
        else:
            self._append_widget(_MessageBubble("ai", full, self._now(), renderer=self._md))
        self.messages.append({"role": "ai", "content": full, "time": datetime.now().isoformat()})
        self._live_widget = None
        self._live_text = ""
        self._set_generating(False)
        self._on_state("idle")
        self._save_conversation()
        self._update_tab_bar()

    def _on_err(self, err: str):
        if not self._streaming:
            return
        self._render_timer.stop()
        if self._live_text and self._live_widget is not None:
            self._live_widget.set_text(self._live_text, streaming=False)
            self.messages.append({"role": "ai", "content": self._live_text,
                                  "time": datetime.now().isoformat(), "error_partial": True})
        self._remove_typing()
        self._set_generating(False)
        self._dismiss_error()
        card = QFrame()
        card.setObjectName("responseError")
        card.setStyleSheet(f"QFrame#responseError {{background:{RED_SOFT};border:none;border-radius:10px;}}")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 10)
        title = QLabel("这次没有完成")
        title.setStyleSheet(f"color:{RED};font-size:12px;font-weight:600;background:transparent;")
        layout.addWidget(title)
        detail = QLabel(str(err)[:500])
        detail.setTextFormat(Qt.TextFormat.PlainText)
        detail.setWordWrap(True)
        detail.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;background:transparent;")
        layout.addWidget(detail)
        retry = QPushButton("重试")
        retry.setFixedSize(54, 28)
        retry.setStyleSheet(f"QPushButton {{background:{BG_CARD};border:none;padding:0;color:{TEXT_PRIMARY};border-radius:6px;}}")
        retry.clicked.connect(self._retry_response)
        layout.addWidget(retry, 0, Qt.AlignmentFlag.AlignLeft)
        self._error_card = card
        self._append_widget(card)
        self._on_state("error")
        self._save_conversation()

    def _on_state(self, state: str, _preview: str = ""):
        agent = getattr(self._find_main_app(), "agent", None)
        tools_running = bool(getattr(agent, "_tools_running", 0))
        files_running = bool(getattr(agent, "_file_busy", False))
        if files_running:
            self.set_tool_busy(True, "正在读取文件或文件夹")
            if state == "idle":
                state = "understanding"
        elif state == "executing" or tools_running:
            label = _preview if state == "executing" and _preview in {
                "正在读取文件", "正在读取文件夹", "正在处理", "正在使用工具"} else ""
            self.set_tool_busy(not bool(self._tool_operations), label)
            if self._tool_operations and not any(origin is self._conversations[self._active_idx] for origin, _ in self._tool_operations.values()):
                state = "background_tool"
        else:
            self.set_tool_busy(False)
        self._avatar_thinking = state in ("thinking", "understanding", "transcribing", "executing")
        self._refresh_pet_avatar()
        if state == "thinking" and self._typing_widget is not None:
            self._typing_widget.set_progress(_preview)
        labels = {"thinking": "思考中…", "error": "需要留意", "listening": "正在听",
                  "transcribing": "正在转写", "understanding": "正在整理", "executing": "正在处理",
                  "asking_confirmation": "等待确认", "reminding": "到提醒时间了", "success": "已完成", "background_tool": "后台操作"}
        self._status.setText(labels.get(state, ""))
        self._status.setVisible(state in labels)
        self._status.setStyleSheet(
            f"color:{RED if state == 'error' else TEXT_MUTED};font-size:11px;"
            f"background:transparent;border:none;"
        )

    def _refresh_pet_avatar(self):
        avatar = _load_cat_avatar(28, thinking=getattr(self, "_avatar_thinking", False),
                                  pet_id=self.bridge.user_config.get("pet_id", "orange"),
                                  ratio=self.devicePixelRatioF())
        if avatar is not None:
            self._pet_avatar.setPixmap(avatar)

    def event(self, event):
        result = super().event(event)
        if event.type() == QEvent.Type.DevicePixelRatioChange and hasattr(self, "_pet_avatar"):
            self._refresh_pet_avatar()
        return result

    # ─────────────────────────────────────────────────────────────────
    # History panel handlers
    # ─────────────────────────────────────────────────────────────────

    def _toggle_history(self):
        if self._session_panel.isVisible():
            self._close_sidebar()
        else:
            self._update_tab_bar()
            width = min(self.width() + 190, self.screen().availableGeometry().width())
            self._sidebar_width = width - self.width()
            self.resize(width, self.height())
            self._session_panel.show()
            self._sidebar_button.setChecked(True)

    def _close_sidebar(self):
        self._session_panel.hide()
        self._sidebar_button.setChecked(False)
        if self._sidebar_width:
            self.resize(max(420, self.width() - self._sidebar_width), self.height())
            self._sidebar_width = 0

    def _on_history_switch(self, idx: int):
        """Switch to a conversation from the history panel."""
        self._switch_conversation(idx)
        self._close_sidebar()

    def _on_history_rename(self, idx: int, title: str):
        """Rename a conversation in the archive."""
        archive = _cfg.load_archive()
        if 0 <= idx < len(archive):
            archive[idx]["title"] = title
            _cfg.save_archive(archive)
            self._update_tab_bar()

    def _on_history_delete(self, idx: int):
        """Permanently delete a conversation from the archive."""
        archive = _cfg.load_archive()
        if 0 <= idx < len(archive):
            archive.pop(idx)
            _cfg.save_archive(archive)
            self._update_tab_bar()

    def _on_history_restore(self, idx: int):
        """Restore an archived conversation back to the tab bar."""
        self._stop_generation()
        self._save_conversation()
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
            self._update_tab_bar()
            self._close_sidebar()

    def _on_history_closed(self):
        """History panel closed — no-op, just for completeness."""
        pass

    def append_command_result(self, cmd: str, ok: bool, out: str):
        from uuid import uuid4
        identity = uuid4().hex
        self.begin_tool(identity, "本机操作", cmd)
        self.finish_tool(identity, cmd, ok, out)

    def begin_tool(self, identity, title, command, origin=None):
        from engine.command_engine import _redact_command
        origin = origin or self._conversations[self._active_idx]
        if title == "打开应用":
            title += " · " + _redact_command(self.bridge._redact_keys(command))[:60]
        message = {"role": "ai", "kind": "tool_result", "operation_id": identity,
                   "title": title, "command": _redact_command(command), "content": "",
                   "success": None, "tool_status": "queued", "time": datetime.now().isoformat()}
        origin["messages"].append(message)
        self._tool_operations[identity] = (origin, message)
        if origin is self._conversations[self._active_idx]:
            card = _CommandResult(message["command"], None, title=title)
            self._tool_cards[identity] = card
            self.set_tool_busy(False)
            self._append_widget(card)
        self._save_tool_history()

    def _save_tool_history(self):
        try:
            self._save_all_conversations()
        except OSError:
            self.set_integration_warning("聊天记录暂时未能写入磁盘，工具状态仍会正常更新。")

    def mark_tool_started(self, identity):
        operation = self._tool_operations.get(identity)
        if operation is None:
            return
        operation[1]["tool_status"] = "running"
        card = self._tool_cards.get(identity)
        if card:
            card.update_result(None, "", state="running")

    def finish_tool(self, identity, command, ok, output):
        operation = self._tool_operations.pop(identity, None)
        if operation is None:
            return
        from engine.command_engine import _redact_command
        origin, message = operation
        safe_output = _redact_command(self.bridge._redact_keys(str(output)))
        if len(safe_output) > 64000:
            safe_output = safe_output[:64000] + "\n[输出较长，已保留前 64000 个字符]"
        message.update(content=safe_output, success=bool(ok), tool_status="success" if ok else "error")
        if ok and message["title"] == "本机操作" and safe_output.startswith(("已打开", "已启动")):
            message["title"] = safe_output.splitlines()[0][:100]
        card = self._tool_cards.get(identity)
        if card:
            card._title.setText(message["title"])
            card.update_result(ok, safe_output)
        origin["updated_at"] = datetime.now().isoformat()
        self._save_tool_history()

    def _clear(self):
        if any(origin is self._conversations[self._active_idx] for origin, _ in self._tool_operations.values()):
            self.set_integration_warning("本机操作还在执行，结束后再清空这段会话。")
            return
        self._stop_generation()
        self.set_tool_busy(False)
        self._dismiss_error()
        self.messages.clear()
        self._streaming = False
        self._set_generating(False)
        self._live_widget = None
        self._live_text = ""
        self._welcome_card = None
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
        self._sys_welcome()
        self._save_conversation()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_rounded_mask()
        if hasattr(self, "_resize_grip"):
            self._resize_grip.move(self.width() - 30, self.height() - 30)
        if not hasattr(self, "_messages_layout"):
            return
        width = max(180, self._scroll.viewport().width() - 48)
        for index in range(self._messages_layout.count() - 1):
            widget = self._messages_layout.itemAt(index).widget()
            if isinstance(widget, _MessageBubble):
                widget.setMaximumWidth(width)
                widget._bubble.setMaximumWidth(width if widget._role == "ai" else int(width * 0.88))

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

    def _regenerate(self, source=None):
        """Remove the last AI message and resend the last user message."""
        if self._streaming or not self.messages:
            return
        last_user = max((index for index, message in enumerate(self.messages) if message.get("role") == "user"), default=-1)
        if any(message.get("kind") == "tool_result" for message in self.messages[last_user + 1:]):
            self.set_integration_warning("这条回复已执行过本机操作。如需再次执行，请发送新消息。")
            return
        if source is not None and not isinstance(source, bool):
            latest = next((self._messages_layout.itemAt(index).widget() for index in range(self._messages_layout.count() - 1, -1, -1)
                          if isinstance(self._messages_layout.itemAt(index).widget(), _MessageBubble) and self._messages_layout.itemAt(index).widget()._role == "ai"), None)
            if latest is not source:
                self.set_integration_warning("只能重新生成当前会话的最后一条回答。")
                return
        if self._error_card is not None:
            self._retry_response()
            return
        self._dismiss_error()
        # Pop assistant messages from history and UI
        while self.messages and _normalize_role(self.messages[-1].get("role", "")) == "ai":
            self.messages.pop()
            for i in range(self._messages_layout.count() - 1, -1, -1):
                item = self._messages_layout.itemAt(i)
                w = item.widget() if item else None
                if isinstance(w, _MessageBubble) and w._role == "ai":
                    self._messages_layout.removeWidget(w)
                    w.setParent(None)
                    w.deleteLater()
                    break
        self._live_widget = None
        self._live_text = ""
        # Re-send using the existing last user message without re-appending
        if self.messages and self.messages[-1]["role"] == "user":
            last_user_text = self.messages[-1]["content"]
            self._streaming = True
            self._set_generating(True)
            self._typing_widget = _TypingBubble()
            self._append_widget(self._typing_widget)
            self.bridge.send(self._message_payload())

    def _message_payload(self):
        from bridge import local_read_request
        if self.messages and self.messages[-1].get("role") == "user":
            latest = self.messages[-1]
            content = latest.get("content", "")
            if self.bridge.temporary_context:
                latest["attachment_context_id"] = self.bridge.remember_attachment(self.bridge.temporary_context)
                self.bridge.temporary_context = ""
                latest["external_context"] = True
            if isinstance(content, str) and (local_read_request(content) or "```" in content or "~~~" in content):
                latest["external_context"] = True
        return [dict(message) for message in self.messages if message.get("kind") != "tool_result"]

    def closeEvent(self, event):
        """Save conversation on window close."""
        self._save_conversation()
        main_app = getattr(self, "_main_app", None)
        if main_app:
            event.ignore()
            self.hide()
            if main_app.tray:
                main_app.tray.set_chat_visible(False)
            return
        super().closeEvent(event)

    def paintEvent(self, event):
        from ui.window_surface import paint_window_surface
        paint_window_surface(self)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        paths = [path for url in urls if (path := url.toLocalFile())
                 and (os.path.isfile(path) or os.path.isdir(path))]
        if not paths:
            return
        self._on_dropped_files(paths)
        event.acceptProposedAction()

    def _on_dropped_files(self, paths: list):
        """P2-2: 统一处理拖入 / 桌宠吞下的文件列表（已过滤敏感词）。"""
        main_app = getattr(self, "_main_app", None)
        if main_app and main_app.agent:
            main_app.agent.files_dropped(paths)
            return
        from ui.drag_drop_util import filter_sensitive_filepaths
        kept, filtered = filter_sensitive_filepaths(paths)
        for fp in filtered:
            self._sys(f"⚠️ 跳过敏感文件: {os.path.basename(fp)}")
        if not kept:
            return
        # 追加到现有文本
        for path in kept:
            if os.path.isdir(path):
                new = f"[文件夹: {os.path.basename(path)}] {path}"
                cur = self._input.toPlainText().strip()
                self._input.setPlainText((cur + "\n" + new) if cur else new)
                continue
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
