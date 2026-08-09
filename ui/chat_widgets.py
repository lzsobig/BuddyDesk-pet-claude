"""
Chat Widget Components — extracted from chat_window.py.

Contains reusable UI widgets: ChatBaseWindow, ChatInput, _MessageBubble,
_TypingBubble, _CommandResult, and helper functions.
"""
from __future__ import annotations
import os
import re

from PySide6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve, Signal, QRectF
from PySide6.QtGui import (
    QColor, QPainter, QPixmap, QBrush, QPolygon, QPainterPath,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QToolButton, QSizePolicy, QPushButton, QPlainTextEdit, QScrollArea,
    QApplication,
)

from theme import (
    BG_DEEP, BG_SUBTLE, BG_CARD, WHITE, BORDER, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_META, TEXT_ON_ACCENT,
    ACCENT, ACCENT_BRIGHT, ACCENT_SOFT, ACCENT_GLOW,
    GREEN, GREEN_SOFT, RED, RED_SOFT, GOLD, GOLD_SOFT, FONT_FAMILY, FONT_MONO,
    RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_PILL,
)
from ui.markdown_renderer import MarkdownRenderer

_TAG_RE = re.compile(r"""\[(APP|SHELL|CLAUDE|CMD):([^\]
]+)\]?""")

def _html_escape(text: str) -> str:
    """Escape HTML special characters for safe display in QLabel."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

def _strip_command_tags(text: str) -> str:
    """Remove [APP:...], [SHELL:...], [CMD:...], [CLAUDE:...] tags for display."""
    return _TAG_RE.sub("", text).strip()

# Avatar sprite path (chubby orange cat, 24x24)
from config import ASSETS_DIR as _ASSETS, FONT_SCALE_LEVELS
import config as _cfg
_AVATAR_PATH = os.path.join(_ASSETS, "cat_frames_v2", "frame_00.png")

class ChatBaseWindow(QWidget):
    FADE_MS = 150

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos: QPoint | None = None
        self._fade: QPropertyAnimation | None = None
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

    def show(self):
        if self._fade and self._fade.state() == QPropertyAnimation.State.Running:
            self._fade.stop()
        self.setWindowOpacity(0)
        super().show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self._apply_rounded_mask()
        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(self.FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.setStartValue(0)
        self._fade.setEndValue(1)
        self._fade.start()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        w, h = float(self.width()), float(self.height())
        # CRITICAL: fill entire widget transparent FIRST — overrides QSS solid background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.fillRect(QRectF(0, 0, w, h), Qt.GlobalColor.transparent)
        # Draw rounded rect background — corners stay transparent
        p.setBrush(QColor(BG_DEEP))
        p.drawRoundedRect(QRectF(0, 0, w, h), RADIUS_LG, RADIUS_LG)
        p.end()

    def _apply_rounded_mask(self):
        from PySide6.QtGui import QPainterPath, QRegion, QTransform
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.0, 0.0, float(w), float(h)), RADIUS_LG, RADIUS_LG)
        self.setMask(QRegion(path.toFillPolygon(QTransform()).toPolygon()))

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
    """Painted triangle send icon — no font dependency (unicode renders blank
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


_AVATAR_CACHE: dict[int, QPixmap | None] = {}


def _load_cat_avatar(size: int = 24) -> QPixmap | None:
    """Try to load the orange cat sprite for AI avatar. Cached after first call."""
    if size in _AVATAR_CACHE:
        return _AVATAR_CACHE[size]
    if not os.path.exists(_AVATAR_PATH):
        _AVATAR_CACHE[size] = None
        return None
    pm = QPixmap(_AVATAR_PATH)
    if pm.isNull():
        _AVATAR_CACHE[size] = None
        return None
    result = pm.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    _AVATAR_CACHE[size] = result
    return result


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
        # P1-3: AI bubble 流式期间不挂选项卡（流完后由 _finalize_options 处理）
        self._text = text
        # Strip command tags before display
        display_text = _strip_command_tags(text) if self._role == "ai" else text
        if self._role == "ai":
            if streaming:
                self._clear_option_buttons()
                self._clear_task_cards()
                html = self._renderer.render_for_streaming(display_text)
                self._bubble.setText(html)
            else:
                # P3-4: 检测是否含 tasks 块 → 抽取后渲染
                extracted = self._renderer.extract_tasks_block(display_text)
                if extracted:
                    remaining, tasks = extracted
                    html = self._renderer.render(remaining) if remaining else ""
                    self._bubble.setText(html)
                    self._build_task_cards(tasks)
                    self._clear_option_buttons()
                else:
                    html = self._renderer.render(display_text)
                    self._bubble.setText(html)
                    # P1-3: 流完后检测是否是"可点击选项"模式
                    opts = self._renderer.extract_option_list(display_text)
                    if opts:
                        self._build_option_buttons(opts)
                    else:
                        self._clear_option_buttons()
        else:
            self._clear_option_buttons()
            self._clear_task_cards()
            self._bubble.setText(_html_escape(text).replace("\n", "<br>"))

    def _clear_task_cards(self):
        """P3-4: 清除任务卡。"""
        for w in getattr(self, "_task_cards", []):
            w.setParent(None)
            w.deleteLater()
        self._task_cards = []

    def _build_task_cards(self, tasks: list[dict]):
        """P3-4: 渲染 N 个任务卡，每张 3 按钮：📌 Pin / 🤖 让 AI 做 / ✗ 跳过。"""
        from theme import ACCENT_SOFT, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_MUTED, GREEN
        self._clear_task_cards()
        parent_widget = self._bubble.parentWidget()
        if parent_widget is None:
            return
        parent_layout = parent_widget.layout()
        if parent_layout is None:
            return
        bubble_idx = parent_layout.indexOf(self._bubble)
        for i, task in enumerate(tasks):
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ background:{BG_SUBTLE};border:1px solid {BORDER_SUBTLE};"
                f"border-radius:6px;padding:8px 10px;margin-top:4px; }}"
            )
            v = QVBoxLayout(card)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(4)
            # 标题
            from html import escape
            title_lbl = QLabel(f"📋 {escape(task.get('title', '(无标题)'))}")
            title_lbl.setWordWrap(True)
            title_lbl.setStyleSheet(
                f"color:{TEXT_PRIMARY};font-size:12px;font-weight:600;background:transparent;border:none;"
            )
            v.addWidget(title_lbl)
            # meta: mode + difficulty
            meta = f"mode: {task.get('mode', 'claude_code')} · 难度 {task.get('difficulty', 1)}/5"
            meta_lbl = QLabel(meta)
            meta_lbl.setStyleSheet(
                f"color:{TEXT_MUTED};font-size:10px;background:transparent;border:none;"
            )
            v.addWidget(meta_lbl)
            # 按钮行
            h = QHBoxLayout()
            h.setSpacing(4)
            btn_pin = self._make_task_btn("📌 Pin", "primary")
            btn_ai = self._make_task_btn("🤖 让 AI 做", "ai")
            btn_skip = self._make_task_btn("✗ 跳过", "skip")
            btn_pin.clicked.connect(lambda _=False, t=task: self._on_task_pin(t))
            btn_ai.clicked.connect(lambda _=False, t=task: self._on_task_dispatch(t))
            btn_skip.clicked.connect(lambda _=False, t=task: self._on_task_skip(t, card))
            h.addWidget(btn_pin)
            h.addWidget(btn_ai)
            h.addWidget(btn_skip)
            h.addStretch()
            v.addLayout(h)
            parent_layout.insertWidget(bubble_idx + 1 + i, card)
            self._task_cards.append(card)

    def _make_task_btn(self, text: str, kind: str):
        from theme import ACCENT, BORDER_SUBTLE, TEXT_PRIMARY
        if kind == "primary":
            color = ACCENT
        elif kind == "ai":
            color = "#5B8DEF"
        else:
            color = TEXT_MUTED
        btn = QPushButton(text)
        btn.setFixedHeight(22)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background:transparent;color:{color};"
            f" border:1px solid {BORDER_SUBTLE};border-radius:4px;"
            f" font-size:10px;padding:0 6px; }}"
            f"QPushButton:hover {{ background:{color};color:white; }}"
        )
        return btn

    def _on_task_pin(self, task: dict):
        """P3-4: Pin 任务到桌面。

        Pin 能力属于 ChatWindow（通过其 `_main_app` 暴露的 pin_manager）。
        沿父链找到宿主窗口再调用，而不是在本气泡上调用不存在的方法。
        """
        w = self._find_chat_window()
        if w is None:
            return
        main_app = w._find_main_app()
        if main_app and main_app.pin_manager:
            text = f"📋 任务: {task.get('title', '')}\nmode: {task.get('mode', 'claude_code')}\n难度: {task.get('difficulty', 1)}/5"
            main_app.pin_manager.pin(text, getattr(w, "_active_idx", 0))
            w._sys(f"📌 任务已 Pin")

    def _on_task_dispatch(self, task: dict):
        """P3-4: 把任务作为新消息发出去（派给当前 backend）。"""
        msg = f"帮我做这个任务：{task.get('title', '')}（mode: {task.get('mode', 'claude_code')}）"
        # 找到 ChatWindow 注入到 input 然后 send
        w = self.parentWidget()
        depth = 0
        while w is not None and depth < 6:
            if hasattr(w, "_input") and hasattr(w, "_send"):
                w._input.setPlainText(msg)
                w._send()
                return
            w = w.parentWidget()
            depth += 1

    def _on_task_skip(self, task: dict, card_widget):
        """P3-4: 跳过任务（淡出移除）。"""
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        anim = QPropertyAnimation(card_widget, b"windowOpacity")
        anim.setDuration(200)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(lambda: (card_widget.setParent(None), card_widget.deleteLater()))
        anim.start()

    def _clear_option_buttons(self):
        """P1-3: 清除之前渲染的选项卡按钮。"""
        for btn in getattr(self, "_opt_buttons", []):
            btn.setParent(None)
            btn.deleteLater()
        self._opt_buttons = []

    def _build_option_buttons(self, items: list[str]):
        """P1-3: 在 _bubble 下方插入 N 个可点击按钮，点击填入 chat input。"""
        from theme import ACCENT_SOFT, BORDER_SUBTLE, TEXT_PRIMARY
        self._clear_option_buttons()
        # 找到 _bubble 的父 layout（content QVBoxLayout）—— 我们在 __init__ 里
        # 把 _bubble 加到了 `content`（QFrame 内层 layout）。
        # 这里我们用 _bubble.parent() 找到 content frame，再取它的 layout。
        parent_widget = self._bubble.parentWidget()
        if parent_widget is None:
            return
        parent_layout = parent_widget.layout()
        if parent_layout is None:
            return
        for i, item in enumerate(items):
            btn = QToolButton()
            btn.setText(f"  {i+1}.  {item}  ")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QToolButton {{"
                f"  background:{BG_SUBTLE};color:{TEXT_PRIMARY};"
                f"  border:1px solid {BORDER_SUBTLE};border-radius:6px;"
                f"  padding:6px 10px;text-align:left;font-size:12px;"
                f"}}"
                f"QToolButton:hover {{ background:{ACCENT_SOFT};border-color:{ACCENT}; }}"
            )
            # 找最近的 ChatWindow 注入填文本
            def _on_click(checked=False, text=item):
                self._emit_option_clicked(text)
            btn.clicked.connect(_on_click)
            # 插在 _bubble 后面（bubble 是 content_layout 的第 0 项，时间戳是最后）
            parent_layout.insertWidget(parent_layout.indexOf(self._bubble) + 1 + i, btn)
            self._opt_buttons.append(btn)

    def _emit_option_clicked(self, text: str):
        """P1-3: 沿 parent chain 找到 ChatWindow，调用 _on_option_clicked。"""
        w = self.parentWidget()
        depth = 0
        while w is not None and depth < 6:
            if hasattr(w, "_on_option_clicked"):
                w._on_option_clicked(text)
                return
            w = w.parentWidget()
            depth += 1

    def _refresh_md(self, renderer: MarkdownRenderer) -> None:
        """P1-2: 用新 renderer 重新渲染自身文本（不传 streaming）。"""
        if self._role != "ai":
            return
        self._renderer = renderer
        # 重新拿 _text 字段再渲染
        if hasattr(self, "_text"):
            self._bubble.setText(self._renderer.render(self._text))

    def _find_chat_window(self):
        """Walk up the parent chain to the owning ChatWindow.

        Duck-typed on attributes the host exposes so this module never needs
        to import ChatWindow (avoiding a circular import).
        """
        w = self.parentWidget()
        depth = 0
        while w is not None and depth < 8:
            if hasattr(w, "_find_main_app") and hasattr(w, "_sys"):
                return w
            w = w.parentWidget()
            depth += 1
        return None

    def _copy_text(self):
        QApplication.clipboard().setText(self._text)

    def _regen(self):
        # Bubble up to the owning ChatWindow via duck-typed lookup
        w = self._find_chat_window()
        if w is not None and hasattr(w, "_regenerate"):
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

