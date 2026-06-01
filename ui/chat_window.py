"""
Chat Window — light warm theme matching the user's HTML mockup.

Each message is rendered as a standalone QWidget bubble (not a QTextEdit) so
the background colour is fully under our control — no QSS leakage from
viewport / palette / default-style-sheet that we kept hitting with QTextEdit.

AI bubbles use MarkdownRenderer (headings / lists / code blocks) for
streaming-friendly rendering. User bubbles stay as escaped plain text.
"""
from __future__ import annotations
import os
import re
from datetime import datetime

from PySide6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve, Signal, QRectF
from PySide6.QtGui import (
    QColor, QPainter, QPixmap, QBrush, QPolygon, QPainterPath,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QPlainTextEdit, QScrollArea, QSizePolicy, QApplication,
)

from bridge import AIBridge
from theme import (
    BG_DEEP, BG_SUBTLE, BG_CARD, WHITE, BORDER, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_META, TEXT_ON_ACCENT,
    ACCENT, ACCENT_BRIGHT, ACCENT_SOFT, ACCENT_GLOW,
    GREEN, GREEN_SOFT, RED, RED_SOFT, GOLD, GOLD_SOFT, FONT_FAMILY, FONT_MONO,
    RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_PILL,
)
from ui.markdown_renderer import MarkdownRenderer

_TAG_RE = re.compile(r"\[(APP|SHELL|CLAUDE|CMD):([^\]\n]+)\]?")

# Avatar sprite path (chubby orange cat, 24×24)
_AVATAR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "cat_frames_v2", "frame_00.png",
)


# ─────────────────────────────────────────────────────────────────────────────
# Base frameless window with fade-in
# ─────────────────────────────────────────────────────────────────────────────

class ChatBaseWindow(QWidget):
    FADE_MS = 150

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos: QPoint | None = None
        self._fade: QPropertyAnimation | None = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )

    def show(self):
        if self._fade and self._fade.state() == QPropertyAnimation.State.Running:
            self._fade.stop()
        self.setWindowOpacity(0)
        super().show()
        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(self.FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.setStartValue(0)
        self._fade.setEndValue(1)
        self._fade.start()

    def hide(self):
        if not self.isVisible():
            return
        if self._fade and self._fade.state() == QPropertyAnimation.State.Running:
            self._fade.stop()
        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(self.FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.setStartValue(1)
        self._fade.setEndValue(0)
        self._fade.finished.connect(super().hide)
        self._fade.start()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _e):
        self._drag_pos = None


# ─────────────────────────────────────────────────────────────────────────────
# Auto-growing multi-line input
# ─────────────────────────────────────────────────────────────────────────────

class ChatInput(QPlainTextEdit):
    MAX_LINES = 4
    LINE_H = 22
    send_signal = Signal()

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self._busy = False
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background: transparent;
                color: {TEXT_PRIMARY};
                border: none;
                padding: 0;
                font-size: 13px;
                font-family: {FONT_FAMILY};
                selection-background-color: {ACCENT_SOFT};
            }}
        """)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedHeight(self.LINE_H + 8)
        self.textChanged.connect(self._auto_h)

    def _auto_h(self):
        if self._busy:
            return
        self._busy = True
        lines = max(1, self.document().blockCount())
        h = min(lines, self.MAX_LINES) * self.LINE_H + 8
        self.setFixedHeight(h)
        self._busy = False

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Return and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.send_signal.emit()
            e.accept()
        else:
            super().keyPressEvent(e)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_triangle_icon(size: int = 34) -> QPixmap:
    """Painted triangle send icon — no font dependency (▶ unicode renders blank
    in some Windows fonts). Used in chat input pill."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(WHITE)))
    p.drawPolygon(QPolygon([QPoint(12, 9), QPoint(12, 25), QPoint(24, 17)]))
    p.end()
    return px


def _load_cat_avatar(size: int = 24) -> QPixmap | None:
    """Try to load the orange cat sprite for AI avatar. Returns None if missing."""
    if not os.path.exists(_AVATAR_PATH):
        return None
    pm = QPixmap(_AVATAR_PATH)
    if pm.isNull():
        return None
    return pm.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Message bubble widgets
# ─────────────────────────────────────────────────────────────────────────────

class _MessageBubble(QFrame):
    """A single message row: avatar + bubble + cmd tag + time + hover actions.

    AI bubbles render their text through MarkdownRenderer so headings / lists /
    code blocks look correct; user bubbles stay as escaped plain text.
    """

    def __init__(self, role: str, text: str, time_str: str, cmd: str | None = None,
                 renderer: MarkdownRenderer | None = None):
        super().__init__()
        self.setStyleSheet("background:transparent;border:none;")
        self._role = role
        self._text = text
        self._renderer = renderer or MarkdownRenderer()
        self._hover_actions: list[QPushButton] = []

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        if role == "user":
            outer.setAlignment(Qt.AlignmentFlag.AlignRight)
            outer.addStretch()

        # Avatar (24x24) — orange cat sprite for AI, person glyph for user
        avatar = QLabel()
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFixedSize(24, 24)
        if role == "ai":
            cat_pm = _load_cat_avatar(24)
            if cat_pm is not None:
                avatar.setPixmap(cat_pm)
                avatar.setStyleSheet(
                    f"border-radius:12px;border:1px solid {BORDER};"
                    f"background:{ACCENT_SOFT};"
                )
            else:
                avatar.setText("🐱")
                avatar.setStyleSheet(
                    f"background:{ACCENT_SOFT};border:1px solid {BORDER};"
                    f"border-radius:12px;font-size:12px;color:{TEXT_PRIMARY};"
                )
        else:
            avatar.setText("👤")
            avatar.setStyleSheet(
                f"background:{GOLD_SOFT};border:1px solid rgba(184,166,106,0.15);"
                f"border-radius:12px;font-size:12px;color:{TEXT_PRIMARY};"
            )
        if role == "user":
            outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)

        # Content column (bubble + cmd + time + hover actions)
        content = QVBoxLayout()
        content.setSpacing(2)
        if role == "user":
            content.setAlignment(Qt.AlignmentFlag.AlignRight)

        # Bubble
        self._bubble = QLabel()
        self._bubble.setWordWrap(True)
        self._bubble.setTextFormat(Qt.TextFormat.RichText)
        self._bubble.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self._bubble.setOpenExternalLinks(True)
        if role == "ai":
            self._bubble.setStyleSheet(
                f"background:{BG_CARD};color:{TEXT_PRIMARY};"
                f"border:1px solid {BORDER};"
                f"border-top-left-radius:{RADIUS_MD}px;"
                f"border-top-right-radius:{RADIUS_MD}px;"
                f"border-bottom-right-radius:{RADIUS_MD}px;"
                f"border-bottom-left-radius:6px;"
                f"padding:10px 14px;font-size:13px;line-height:1.6;"
            )
        else:
            self._bubble.setStyleSheet(
                f"background:{ACCENT};color:{WHITE};"
                f"border-top-left-radius:{RADIUS_MD}px;"
                f"border-top-right-radius:{RADIUS_MD}px;"
                f"border-bottom-right-radius:6px;"
                f"border-bottom-left-radius:{RADIUS_MD}px;"
                f"padding:10px 14px;font-size:13px;line-height:1.6;"
            )
        self._bubble.setMaximumWidth(420)
        self._bubble.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.set_text(text)  # sets initial HTML
        content.addWidget(self._bubble)

        # Cmd tag (under bubble)
        if cmd:
            cmd_lbl = QLabel(f"⚡ {_html_escape(cmd)}")
            cmd_lbl.setStyleSheet(
                f"background:{GREEN_SOFT};color:{GREEN};"
                f"border-radius:4px;padding:2px 8px;"
                f"font-family:{FONT_MONO};font-size:11px;font-weight:600;"
            )
            if role == "user":
                content.addWidget(cmd_lbl, 0, Qt.AlignmentFlag.AlignRight)
            else:
                content.addWidget(cmd_lbl, 0, Qt.AlignmentFlag.AlignLeft)

        # Time + hover actions row
        time_row = QHBoxLayout()
        time_row.setSpacing(4)
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet(
            f"color:{TEXT_META};font-size:10px;"
            f"font-family:{FONT_MONO};background:transparent;border:none;"
        )
        time_row.addWidget(time_lbl)

        if role == "ai":
            for label, callback in [("复制", self._copy_text), ("重新生成", self._regen)]:
                btn = QPushButton(label)
                btn.setFixedHeight(18)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background:transparent;color:{TEXT_MUTED};
                        border:none;font-size:9px;padding:0 4px;
                    }}
                    QPushButton:hover {{ color:{ACCENT}; }}
                """)
                btn.clicked.connect(callback)
                time_row.addWidget(btn)
                self._hover_actions.append(btn)
            for btn in self._hover_actions:
                btn.hide()

        time_row.addStretch()
        content.addLayout(time_row)

        outer.addLayout(content, 0)
        if role == "ai":
            outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
            outer.addStretch()

        self.setMaximumWidth(500)

    def set_text(self, text: str, streaming: bool = False):
        """Update bubble text. AI bubbles use MarkdownRenderer."""
        if self._role == "ai":
            if streaming:
                html = self._renderer.render_for_streaming(text)
            else:
                html = self._renderer.render(text)
            self._bubble.setText(html)
        else:
            self._bubble.setText(_html_escape(text).replace("\n", "<br>"))
        self._text = text

    def _copy_text(self):
        QApplication.clipboard().setText(self._text)

    def _regen(self):
        # Bubble up to parent ChatWindow
        w = self.parent()
        while w and not isinstance(w, ChatWindow):
            w = w.parent()
        if w:
            w._regenerate()

    def enterEvent(self, _e):
        for btn in self._hover_actions:
            btn.show()

    def leaveEvent(self, _e):
        for btn in self._hover_actions:
            btn.hide()


class _TypingBubble(QFrame):
    """3-dot typing indicator used while waiting for the AI."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background:transparent;border:none;")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        avatar = QLabel("🐱")
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFixedSize(24, 24)
        avatar.setStyleSheet(
            f"background:{ACCENT_SOFT};border:1px solid {BORDER};"
            f"border-radius:12px;font-size:12px;"
        )
        outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)

        bubble = QLabel()
        bubble.setStyleSheet(
            f"background:{BG_CARD};color:{TEXT_MUTED};"
            f"border:1px solid {BORDER};"
            f"border-top-left-radius:{RADIUS_MD}px;"
            f"border-top-right-radius:{RADIUS_MD}px;"
            f"border-bottom-right-radius:{RADIUS_MD}px;"
            f"border-bottom-left-radius:6px;"
            f"padding:12px 16px;"
        )
        bubble.setTextFormat(Qt.TextFormat.RichText)
        bubble.setText(
            '<span style="display:inline-block;width:6px;height:6px;'
            f'background:{TEXT_MUTED};border-radius:3px;margin-right:5px;"></span>'
            '<span style="display:inline-block;width:6px;height:6px;'
            f'background:{TEXT_MUTED};border-radius:3px;margin-right:5px;"></span>'
            '<span style="display:inline-block;width:6px;height:6px;'
            f'background:{TEXT_MUTED};border-radius:3px;"></span>'
        )
        outer.addWidget(bubble)
        outer.addStretch()


class _CommandResult(QFrame):
    """A small pill showing a successfully/failed command result."""

    def __init__(self, cmd: str, ok: bool):
        super().__init__()
        self.setStyleSheet("background:transparent;border:none;")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        outer.addStretch()

        bg = GREEN_SOFT if ok else "rgba(212,122,114,0.08)"
        fg = GREEN if ok else RED
        icon = "✓" if ok else "✗"
        pill = QLabel(f"{icon} {_html_escape(cmd)}")
        pill.setStyleSheet(
            f"background:{bg};color:{fg};"
            f"border-radius:4px;padding:3px 10px;"
            f"font-family:{FONT_MONO};font-size:11px;font-weight:600;"
        )
        outer.addWidget(pill)
        outer.addStretch()


# ─────────────────────────────────────────────────────────────────────────────
# ChatWindow
# ─────────────────────────────────────────────────────────────────────────────

class ChatWindow(ChatBaseWindow):
    """A frameless chat panel with a scrollable message list."""

    def __init__(self, bridge: AIBridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.messages: list[dict] = []
        self._streaming = False
        self._typing_widget: _TypingBubble | None = None
        self._live_widget: _MessageBubble | None = None
        self._live_text: str = ""
        self._md = MarkdownRenderer()

        self.setFixedSize(480, 640)
        self.setWindowTitle("Hermes Pet Chat")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        # NO setMask — paintEvent draws the full rounded rect; setMask creates
        # jagged pixel edges on Windows. WA_TranslucentBackground makes the
        # rounded corners fully transparent at the OS level.

        self._build_ui()
        self._wire()
        self._sys_welcome()

    # ── UI ──────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

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
        root.addWidget(self._scroll, 1)

        root.addWidget(self._build_input())

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
        title = QLabel("Hermes")
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

        self._status = QLabel("就绪")
        self._status.setStyleSheet(
            f"color:{GREEN};font-size:11px;font-weight:600;background:transparent;border:none;"
        )
        hl.addWidget(self._status)

        clr = QPushButton("清空")
        clr.setFixedSize(56, 28)
        clr.setCursor(Qt.CursorShape.PointingHandCursor)
        clr.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_SECONDARY};
                border: none; border-radius: 6px; font-size: 11px; font-weight: 500;
            }}
            QPushButton:hover {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
        """)
        clr.clicked.connect(self._clear)
        hl.addWidget(clr)

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

    # ── message ops ──
    def _append_widget(self, w: QWidget):
        idx = self._messages_layout.count() - 1
        if idx < 0:
            self._messages_layout.addWidget(w)
        else:
            self._messages_layout.insertWidget(idx, w)
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
        self._input.setFixedHeight(self._input.LINE_H + 8)
        bubble = _MessageBubble("user", text, self._now(), renderer=self._md)
        self._append_widget(bubble)
        self.messages.append({"role": "user", "content": text})
        self._streaming = True
        self._send_btn.setEnabled(False)

        self._typing_widget = _TypingBubble()
        self._append_widget(self._typing_widget)

        self.bridge.send(self.messages)

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
            if self._live_widget is not None:
                self._live_widget.set_text(self._live_text, streaming=True)

    def _on_done(self, full: str):
        self.messages.append({"role": "assistant", "content": full})
        self._streaming = False
        self._send_btn.setEnabled(True)
        if self._live_widget is not None:
            self._live_widget.set_text(full, streaming=False)
            self._live_widget = None
        self._live_text = ""
        for m in _TAG_RE.finditer(full):
            kind, payload = m.group(1), m.group(2).strip()
            tag_label = f"[{kind}:{payload}]"
            self._append_widget(_CommandResult(tag_label, ok=True))

    def _on_err(self, err: str):
        self._streaming = False
        self._send_btn.setEnabled(True)
        if self._typing_widget is not None:
            self._messages_layout.removeWidget(self._typing_widget)
            self._typing_widget.setParent(None)
            self._typing_widget.deleteLater()
            self._typing_widget = None
        err_bubble = _MessageBubble("ai", f"❌ {err}", self._now(),
                                    renderer=self._md)
        self._append_widget(err_bubble)

    def eventFilter(self, obj, e):
        # No event filter needed — paintEvent handles the rounded body,
        # and WA_TranslucentBackground ensures corners are invisible.
        return super().eventFilter(obj, e)

    def _on_state(self, state: str, _preview: str):
        cmap = {"idle": GREEN, "thinking": GOLD, "error": RED}
        lmap = {"idle": "就绪", "thinking": "思考中…", "error": "出错"}
        self._status.setText(lmap.get(state, "Ready"))
        self._status.setStyleSheet(
            f"color:{cmap.get(state, GREEN)};font-size:10px;"
            f"background:transparent;border:none;"
        )
        self._status_dot.setStyleSheet(
            f"background:{cmap.get(state, GREEN)};border-radius:3px;"
        )

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
        """Remove the last AI message and resend the conversation."""
        if self._streaming or not self.messages:
            return
        while self.messages and self.messages[-1]["role"] == "assistant":
            self.messages.pop()
            for i in range(self._messages_layout.count() - 1, -1, -1):
                item = self._messages_layout.itemAt(i)
                w = item.widget() if item else None
                if isinstance(w, _MessageBubble) and w._role == "ai":
                    self._messages_layout.removeWidget(w)
                    w.setParent(None)
                    w.deleteLater()
                    break
        if self.messages:
            self._send()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QColor(BORDER))
        p.setBrush(QColor(BG_DEEP))
        p.drawRoundedRect(rect, RADIUS_LG, RADIUS_LG)
        p.end()


def _html_escape(t: str) -> str:
    return (
        t.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
