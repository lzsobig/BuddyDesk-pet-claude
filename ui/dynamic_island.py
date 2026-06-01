"""
Dynamic Island — light warm theme, 5 states (idle / thinking / result / notify / error).

Faithful to the HTML reference (hermes-pet-win-ui-4-island-2.html):
  - idle:    7px green pulsing dot + 15px cat emoji + 12px text "小橘待命中"
  - thinking: 28px spinning ring + 12px "正在思考" + 10.5px sub "AI 正在处理你的请求…" + bouncing 5px dots
  - result:  28px green check pill + 2-line label + "已完成" pill
  - notify:  28px gold bell pill + 2-line label + "提醒" pill
  - error:   28px red ✕ pill + "出错了" + error info (≤24 chars truncated)

Transitions (per user spec — must be 200ms, NOT the 450ms in the HTML):
  - Old widget group fades out 1 → 0 over 100ms (QGraphicsOpacityEffect)
  - New widget group fades in  0 → 1 over 100ms (overlapping with the fade-out)
  - Width / height / border-radius interpolate 200ms with QEasingCurve.OutCubic
  - All animations are real, not hide()/show()

Edge antialiasing fix:
  - Previous version called `setMask(QRegion(path.toFillPolygon(QTransform()).toPolygon()))`
    which rasterises the rounded rect to a pixel grid and produced visible jaggies
    on the pill's edge.
  - We now drop the mask entirely. The window is `WA_TranslucentBackground`; the
    paintEvent draws the white capsule with a fully antialiased QPainterPath so
    every edge is GPU-AA. Outside the rounded corners the window is fully
    transparent (alpha 0) — there is no visible artifact.
"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import (
    Qt, QTimer, QRectF, QPropertyAnimation, QEasingCurve, QPoint, QPointF, Property,
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFont, QLinearGradient, QPainterPath, QTransform,
    QRadialGradient, QBrush,
)
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout, QGraphicsOpacityEffect

from theme import (
    BG_DEEP, WHITE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, ACCENT_SOFT, GREEN, GREEN_SOFT, GOLD, GOLD_SOFT,
    RED, RED_SOFT, RADIUS_PILL,
)

# ── Per-state dimensions (from HTML) ───────────────────────────────────────
IDLE_W = 200
IDLE_H = 38
IDLE_RADIUS = 20          # HTML uses 20, not 19; matches the h/2 pill rule

THINK_W = 340
THINK_H = 52
THINK_RADIUS = 26

RESULT_W = 320
RESULT_H = 52
RESULT_RADIUS = 26

NOTIFY_W = 280
NOTIFY_H = 52
NOTIFY_RADIUS = 26

ERROR_W = 340
ERROR_H = 52
ERROR_RADIUS = 26

# ── Timing (per user requirement: 200ms) ──────────────────────────────────
FADE_MS = 100            # cross-fade per group
SIZE_MS = 200            # width / height / radius interpolation
FADE_WINDOW_MS = 200     # whole show/hide of the window

HOVER_W = IDLE_W - 40    # 160 — water-drop shrink
HOVER_H = 56             # expand down

# ── Idle label phrases for hover ──────────────────────────────────────────
COMPANION_PHRASES = [
    "陪着你呢~", "早呀~", "辛苦啦", "摸鱼时间到~",
    "加油！", "休息一下吧~", "今天也要开心哦",
    "有什么需要帮忙的？", "在呢在呢~", "喵~", "想你了~",
]


# ─────────────────────────────────────────────────────────────────────────────
# Custom-painted animation widgets (self-contained, no layout dependencies)
# ─────────────────────────────────────────────────────────────────────────────

class BreathingDot(QWidget):
    """A 7px pulsing green dot — used in the idle state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(7, 7)
        self._opacity = 0.5
        self._scale = 1.0
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def _tick(self):
        self._phase += (2 * math.pi * 33) / 3000
        if self._phase > 2 * math.pi:
            self._phase -= 2 * math.pi
        # Same curve as HTML @keyframes idlePulse: opacity 0.5→1, scale 0.85→1.1
        sine = (1 + math.sin(self._phase)) / 2
        self._opacity = 0.5 + 0.5 * sine
        self._scale = 0.85 + 0.25 * sine
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx, cy = self.width() / 2, self.height() / 2
        # Outer glow halo
        glow = QColor(ACCENT)
        glow.setAlphaF(self._opacity * 0.30)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QRectF(cx - 5, cy - 5, 10, 10))
        # Core dot
        core = QColor(ACCENT)
        core.setAlphaF(self._opacity)
        r = (7 * self._scale) / 2
        p.setBrush(core)
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        p.end()


class SpinningRing(QWidget):
    """A 28px ring with inner glow + accent arc — used in thinking state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._timer.start(16)
        self.show()

    def stop(self):
        self._running = False
        self._timer.stop()
        self.hide()

    def _tick(self):
        # HTML uses 0.9s linear; we rotate 6° per 16ms = 360° / 960ms ≈ 0.96s
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Inner glow disc (HTML ::after)
        p.setPen(Qt.PenStyle.NoPen)
        glow = QColor(ACCENT)
        glow.setAlphaF(0.10)
        p.setBrush(glow)
        p.drawEllipse(QRectF(3, 3, 22, 22))
        # Track ring (HTML border)
        track = QPen(QColor(BORDER), 2.5)
        p.setPen(track)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(2, 2, 24, 24))
        # Accent arc (HTML border-top-color)
        arc = QPen(QColor(ACCENT), 2.5)
        arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(arc)
        # 120° arc starting at current angle
        p.drawArc(QRectF(2, 2, 24, 24), self._angle * 16, 120 * 16)
        p.end()


class BouncingDots(QWidget):
    """Three 5px bouncing green dots — used in the thinking state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 14)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._phase = 0
        self._timer.start(50)
        self.show()

    def stop(self):
        self._running = False
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._phase += 0.25
        if self._phase > 6 * math.pi:
            self._phase -= 6 * math.pi
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            # HTML @keyframes thinkBounce: 1.4s, delays 0 / 0.15 / 0.3s
            dot_phase = self._phase - i * 0.9
            sine = max(0.0, math.sin(dot_phase))
            alpha = 0.3 + 0.7 * sine
            offset_y = -3 * sine
            c = QColor(ACCENT)
            c.setAlphaF(alpha)
            p.setBrush(c)
            p.drawEllipse(QRectF(2 + i * 8, 5 + offset_y, 5, 5))
        p.end()


class ErrorIcon(QWidget):
    """28×28 red soft circle with a white ✕ — used in the error state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Soft red background circle with red border
        p.setPen(QPen(QColor(212, 122, 114, 50), 1.5))
        p.setBrush(QBrush(QColor(RED_SOFT)))
        p.drawEllipse(QRectF(0.75, 0.75, self.width() - 1.5, self.height() - 1.5))
        # ✕ in danger red
        pen = QPen(QColor(RED), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        d = 5
        cx, cy = self.width() / 2, self.height() / 2
        p.drawLine(QPoint(cx - d, cy - d), QPoint(cx + d, cy + d))
        p.drawLine(QPoint(cx - d, cy + d), QPoint(cx + d, cy - d))
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# Per-state content group (own opacity, fades independently)
# ─────────────────────────────────────────────────────────────────────────────

class _IslandGroup(QWidget):
    """A container for one state's widgets with its own opacity animation.

    The group fills the parent (DynamicIsland) — we use absolute positioning
    rather than nested layouts so the parent's paintEvent draws the capsule
    body cleanly behind/under all groups, and groups can be cross-faded
    independently.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Start fully transparent
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._opacity_anim: QPropertyAnimation | None = None
        # Inner layout — fixed content per group
        self._inner = QHBoxLayout(self)
        self._inner.setContentsMargins(0, 0, 0, 0)
        self._inner.setSpacing(0)
        self._inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()  # not shown until opacity > 0

    def add(self, w: QWidget):
        self._inner.addWidget(w)

    def addLayout(self, layout, stretch: int = 0):
        self._inner.addLayout(layout, stretch)

    def addStretch(self, stretch: int = 0):
        self._inner.addStretch(stretch)

    def set_opacity_target(self, target: float, duration: int = FADE_MS,
                            on_finish=None):
        if self._opacity_anim and self._opacity_anim.state() == QPropertyAnimation.State.Running:
            self._opacity_anim.stop()
        self._opacity_anim = QPropertyAnimation(self._effect, b"opacity")
        self._opacity_anim.setDuration(duration)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._opacity_anim.setStartValue(self._effect.opacity())
        self._opacity_anim.setEndValue(target)
        if on_finish:
            self._opacity_anim.finished.connect(on_finish)
        # Show when fading in, hide when fully transparent at end
        if target > 0.001:
            self.show()
            self.raise_()
        self._opacity_anim.start()
        if target < 0.001:
            # Hide the group when fully transparent so it doesn't catch stray events
            from PySide6.QtCore import QTimer as _QT
            _QT.singleShot(duration, self.hide)


# ─────────────────────────────────────────────────────────────────────────────
# Main island
# ─────────────────────────────────────────────────────────────────────────────

class DynamicIsland(QWidget):
    """A floating capsule at the top of the screen with 5 state variants."""

    # Per-state dimensions
    _DIMS = {
        "idle":     (IDLE_W, IDLE_H, IDLE_RADIUS),
        "thinking": (THINK_W, THINK_H, THINK_RADIUS),
        "result":   (RESULT_W, RESULT_H, RESULT_RADIUS),
        "notify":   (NOTIFY_W, NOTIFY_H, NOTIFY_RADIUS),
        "error":    (ERROR_W, ERROR_H, ERROR_RADIUS),
    }

    def __init__(self, on_click=None, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self._state = "idle"
        self._drag_pos: QPoint | None = None
        self._ready = False
        self._active_group: _IslandGroup | None = None

        # Animated size + corner radius (rounded pill at any size)
        self._width = float(IDLE_W)
        self._height = float(IDLE_H)
        self._radius = float(IDLE_RADIUS)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        # Translucent window — paintEvent does the entire visible body.
        # Crucially: NO setMask. The previous version rasterised the rounded
        # rect into a polygon and produced visible edge jaggies.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFixedSize(IDLE_W, IDLE_H)

        self._build_groups()
        self._build_anims()
        QTimer.singleShot(50, self._position)
        self._show_state("idle", animate=False)

    # ── UI construction ──
    def _build_groups(self):
        """Build the 5 state groups and overlay them on top of the paint surface."""
        self._groups: dict[str, _IslandGroup] = {}

        # ── Idle ──
        g = _IslandGroup(self)
        self._idle_dot = BreathingDot()
        self._idle_emoji = QLabel("🐱")
        self._idle_emoji.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:15px;background:transparent;"
            f"border:none;line-height:1;"
        )
        self._idle_text = QLabel("小橘待命中")
        self._idle_text.setStyleSheet(
            f"color:{TEXT_SECONDARY};font-size:12px;font-weight:500;"
            f"letter-spacing:-0.01em;background:transparent;border:none;"
        )
        # Spacing mirrors HTML gap: 8px between dot-emoji-text
        sp1 = QHBoxLayout(); sp1.setSpacing(0)
        wrap = QWidget()
        wrap.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        wrap_lay = QHBoxLayout(wrap)
        wrap_lay.setContentsMargins(0, 0, 0, 0)
        wrap_lay.setSpacing(8)
        wrap_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        wrap_lay.addWidget(self._idle_dot)
        wrap_lay.addWidget(self._idle_emoji)
        wrap_lay.addWidget(self._idle_text)
        g.add(wrap)
        self._groups["idle"] = g

        # ── Thinking ──
        g = _IslandGroup(self)
        self._think_ring = SpinningRing()
        think_col = QWidget()
        think_col.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        col_lay = QVBoxLayout(think_col)
        col_lay.setContentsMargins(0, 0, 0, 0)
        col_lay.setSpacing(1)
        self._think_label = QLabel("正在思考")
        self._think_label.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:12px;font-weight:600;"
            f"letter-spacing:-0.01em;background:transparent;border:none;"
        )
        self._think_sub = QLabel("AI 正在处理你的请求…")
        self._think_sub.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:10.5px;letter-spacing:0.01em;"
            f"background:transparent;border:none;"
        )
        col_lay.addWidget(self._think_label)
        col_lay.addWidget(self._think_sub)
        self._think_dots = BouncingDots()
        # Wrap content so we can control gap between ring → text → dots
        wrap = QWidget()
        wrap.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        wrap_lay = QHBoxLayout(wrap)
        wrap_lay.setContentsMargins(0, 0, 0, 0)
        wrap_lay.setSpacing(12)
        wrap_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        wrap_lay.addWidget(self._think_ring)
        wrap_lay.addWidget(think_col, 1)
        wrap_lay.addWidget(self._think_dots)
        g.add(wrap)
        self._groups["thinking"] = g

        # ── Result ──
        g = _IslandGroup(self)
        self._result_icon = self._check_icon()
        col = QWidget()
        col.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        col_lay = QVBoxLayout(col)
        col_lay.setContentsMargins(0, 0, 0, 0)
        col_lay.setSpacing(1)
        self._result_label = QLabel("任务完成")
        self._result_label.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:12px;font-weight:600;"
            f"letter-spacing:-0.01em;background:transparent;border:none;"
        )
        self._result_sub = QLabel("已完成")
        self._result_sub.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:10.5px;letter-spacing:0.01em;"
            f"background:transparent;border:none;"
        )
        col_lay.addWidget(self._result_label)
        col_lay.addWidget(self._result_sub)
        self._result_pill = QLabel("已完成")
        self._result_pill.setStyleSheet(
            f"background:{GREEN_SOFT};color:{GREEN};"
            f"border-radius:{RADIUS_PILL}px;"
            f"padding:3px 10px;font-size:10.5px;font-weight:600;"
            f"letter-spacing:0.03em;"
        )
        wrap = QWidget()
        wrap.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        wrap_lay = QHBoxLayout(wrap)
        wrap_lay.setContentsMargins(0, 0, 0, 0)
        wrap_lay.setSpacing(12)
        wrap_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        wrap_lay.addWidget(self._result_icon)
        wrap_lay.addWidget(col, 1)
        wrap_lay.addWidget(self._result_pill)
        g.add(wrap)
        self._groups["result"] = g

        # ── Notify ──
        g = _IslandGroup(self)
        self._notify_icon = self._bell_icon()
        col = QWidget()
        col.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        col_lay = QVBoxLayout(col)
        col_lay.setContentsMargins(0, 0, 0, 0)
        col_lay.setSpacing(1)
        self._notify_label = QLabel("来自小橘的提醒")
        self._notify_label.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:12px;font-weight:600;"
            f"letter-spacing:-0.01em;background:transparent;border:none;"
        )
        self._notify_sub = QLabel("提醒")
        self._notify_sub.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:10.5px;letter-spacing:0.01em;"
            f"background:transparent;border:none;"
        )
        col_lay.addWidget(self._notify_label)
        col_lay.addWidget(self._notify_sub)
        self._notify_pill = QLabel("提醒")
        self._notify_pill.setStyleSheet(
            f"background:{GOLD_SOFT};color:{GOLD};"
            f"border-radius:{RADIUS_PILL}px;"
            f"padding:3px 10px;font-size:10.5px;font-weight:600;"
            f"letter-spacing:0.03em;"
        )
        wrap = QWidget()
        wrap.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        wrap_lay = QHBoxLayout(wrap)
        wrap_lay.setContentsMargins(0, 0, 0, 0)
        wrap_lay.setSpacing(12)
        wrap_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        wrap_lay.addWidget(self._notify_icon)
        wrap_lay.addWidget(col, 1)
        wrap_lay.addWidget(self._notify_pill)
        g.add(wrap)
        self._groups["notify"] = g

        # ── Error (NEW) ──
        g = _IslandGroup(self)
        self._error_icon = ErrorIcon()
        col = QWidget()
        col.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        col_lay = QVBoxLayout(col)
        col_lay.setContentsMargins(0, 0, 0, 0)
        col_lay.setSpacing(1)
        self._error_label = QLabel("出错了")
        self._error_label.setStyleSheet(
            f"color:{RED};font-size:12px;font-weight:600;"
            f"letter-spacing:-0.01em;background:transparent;border:none;"
        )
        self._error_sub = QLabel("")
        self._error_sub.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:10.5px;letter-spacing:0.01em;"
            f"background:transparent;border:none;"
        )
        col_lay.addWidget(self._error_label)
        col_lay.addWidget(self._error_sub)
        self._error_pill = QLabel("失败")
        self._error_pill.setStyleSheet(
            f"background:{RED_SOFT};color:{RED};"
            f"border-radius:{RADIUS_PILL}px;"
            f"padding:3px 10px;font-size:10.5px;font-weight:600;"
            f"letter-spacing:0.03em;"
        )
        wrap = QWidget()
        wrap.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        wrap_lay = QHBoxLayout(wrap)
        wrap_lay.setContentsMargins(0, 0, 0, 0)
        wrap_lay.setSpacing(12)
        wrap_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        wrap_lay.addWidget(self._error_icon)
        wrap_lay.addWidget(col, 1)
        wrap_lay.addWidget(self._error_pill)
        g.add(wrap)
        self._groups["error"] = g

    def _check_icon(self) -> QWidget:
        from ui.icon_widgets import CheckIcon
        return CheckIcon(bg=GREEN_SOFT, fg=GREEN, border="rgba(74,175,136,0.2)")

    def _bell_icon(self) -> QWidget:
        from ui.icon_widgets import BellIcon
        return BellIcon(bg=GOLD_SOFT, fg=GOLD, border="rgba(184,166,106,0.15)")

    def _build_anims(self):
        # Single size animation — used both for state changes and for hover water-drop
        self._size_anim = QPropertyAnimation(self, b"anim_size")
        self._size_anim.setDuration(SIZE_MS)
        self._size_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade: QPropertyAnimation | None = None

    # ── Animated size property (width, height, radius interpolated together) ──
    def _get_anim_size(self):
        return self._width

    def _set_anim_size(self, _v):
        # We don't use this directly — the three sub-anims are driven by the
        # QPropertyAnimation in _animate_size_to. Defined here because Qt
        # requires a real Property to bind a QPropertyAnimation to it.
        pass

    anim_size = Property(float, _get_anim_size, _set_anim_size)

    def _set_size_now(self, w: float, h: float, r: float):
        self._width = w
        self._height = h
        self._radius = r
        self.setFixedSize(int(round(w)), int(round(h)))
        self._reposition_groups()
        self.update()

    def _animate_size_to(self, tw: float, th: float, tr: float, duration: int = SIZE_MS):
        # Stop any in-flight size anim
        if self._size_anim.state() == QPropertyAnimation.State.Running:
            self._size_anim.stop()
        self._size_anim = QPropertyAnimation(self, b"anim_size")
        self._size_anim.setDuration(duration)
        self._size_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        # Drive via valueChanged — we morph w/h/r in lockstep
        steps = max(8, duration // 16)
        start = (self._width, self._height, self._radius)
        end = (tw, th, tr)
        deltas = [(e - s) for s, e in zip(start, end)]
        self._size_anim.setStartValue(0.0)
        self._size_anim.setEndValue(1.0)

        def on_value_changed(t: float):
            t = max(0.0, min(1.0, t))
            self._set_size_now(
                start[0] + deltas[0] * t,
                start[1] + deltas[1] * t,
                start[2] + deltas[2] * t,
            )

        self._size_anim.valueChanged.connect(on_value_changed)
        self._size_anim.start()

    def _reposition_groups(self):
        """Make every group fill the island's current rect (with state padding)."""
        # 0px outer margin; groups paint over the pill, but their content is
        # inset horizontally so the white capsule edge is visible.
        for state, g in self._groups.items():
            g.setGeometry(0, 0, self.width(), self.height())
            # Apply per-state padding so content doesn't kiss the rounded edge
            pad_x = 16 if state == "idle" else 18
            pad_y = 0
            g._inner.setContentsMargins(pad_x, pad_y, pad_x, pad_y)
            # Update spacing inside inner wrap widgets (re-set to 0; the wrap
            # widgets carry the visible gap). Inner layout gap is 0.

    # ── Painting ──
    def paintEvent(self, _e):
        """Layered Apple-style drawing. All edges antialiased by QPainter."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setRenderHint(QPainter.RenderHint.LosslessImageRendering, True)
        w, h = self.width(), self.height()
        r = self._radius

        # 1) Soft outer drop shadow — warm, layered
        # HTML idle: 0 1px 2px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.06)
        # HTML thinking/result/notify/error: 0 2px 4px rgba(0,0,0,0.04),
        #   0 8px 28px rgba(<state>,0.10-0.12)
        state_glow = {
            "idle":     (0,   0,   0,   0),
            "thinking": (92,  184, 154, 30),
            "result":   (74,  175, 136, 30),
            "notify":   (184, 166, 106, 26),
            "error":    (212, 122, 114, 26),
        }.get(self._state, (0, 0, 0, 0))
        # Soft warm shadow
        p.setPen(Qt.PenStyle.NoPen)
        for i, (alpha, dy) in enumerate(((8, 2), (12, 4))):
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawRoundedRect(
                QRectF(1.5, dy, w - 3, h), r, r
            )
        # State-tinted glow shadow (only for non-idle)
        if state_glow[3] > 0:
            p.setBrush(QColor(state_glow[0], state_glow[1], state_glow[2], state_glow[3]))
            p.drawRoundedRect(
                QRectF(2, 6, w - 4, h), r, r
            )

        # 2) White capsule body
        p.setBrush(QColor(WHITE))
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # 3) Top sheen — linear gradient, upper half
        # HTML: linear-gradient(180deg, rgba(255,255,255,0.7) 0%, rgba(255,255,255,0) 100%)
        sheen = QLinearGradient(0, 0, 0, h * 0.5)
        sheen.setColorAt(0.0, QColor(255, 255, 255, int(0.7 * 255)))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(sheen)
        p.setPen(Qt.PenStyle.NoPen)
        # Clip to top half with rounded top corners
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(0, 0, w, h), r, r)
        p.setClipPath(clip_path)
        p.drawRect(QRectF(0, 0, w, h * 0.5))
        p.setClipping(False)

        # 4) Subtle state-tinted inner glow (very low alpha)
        inner_tint = {
            "idle":     QColor(92,  184, 154, 15),
            "thinking": QColor(92,  184, 154, 15),
            "result":   QColor(74,  175, 136, 25),
            "notify":   QColor(184, 166, 106, 25),
            "error":    QColor(212, 122, 114, 25),
        }.get(self._state)
        if inner_tint is not None:
            from PySide6.QtGui import QRadialGradient
            glow = QRadialGradient(w / 2, h / 2, max(w, h) / 2)
            glow.setColorAt(0, inner_tint)
            glow.setColorAt(1, QColor(inner_tint.red(), inner_tint.green(), inner_tint.blue(), 0))
            p.setBrush(glow)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # 5) Inset top highlight — 1px white line at top (HTML inset shadow)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 200), 1))
        p.drawLine(QPointF(r * 0.5, 0.5), QPointF(w - r * 0.5, 0.5))

        # 6) 1px outer border
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r, r)
        p.end()

    # ── State management ──
    def _stop_animations(self, group_name: str):
        g = self._groups.get(group_name)
        if not g:
            return
        if group_name == "thinking":
            self._think_ring.stop()
            self._think_dots.stop()
        # Reset CheckIcon / BellIcon animation by re-creating isn't needed —
        # they animate forever, but their progression is purely cosmetic.

    def _show_state(self, state: str, animate: bool = True):
        """Switch the active group with cross-fade + size animation."""
        if state not in self._groups:
            state = "idle"

        # Update text content FIRST (so when the new group fades in, the
        # labels already have the right strings)
        self._update_text_for_state(state)

        target = self._DIMS[state]
        tw, th, tr = float(target[0]), float(target[1]), float(target[2])
        old_group = self._active_group
        new_group = self._groups[state]

        if not animate or old_group is None:
            # Initial set — show only the target group at full opacity
            if old_group and old_group is not new_group:
                old_group.set_opacity_target(0.0, duration=0)
                old_group.hide()
            new_group.set_opacity_target(1.0, duration=0)
            self._set_size_now(tw, th, tr)
            self._active_group = new_group
            self._state = state
            # Start any state-specific animations
            self._start_state_anim(state)
            return

        if old_group is new_group:
            # Same state — just resize, no cross-fade
            self._animate_size_to(tw, th, tr)
            return

        # Cross-fade
        old_group.set_opacity_target(0.0, duration=FADE_MS)
        new_group.set_opacity_target(1.0, duration=FADE_MS)
        # Size animation runs in parallel (200ms)
        self._animate_size_to(tw, th, tr)
        # Stop old-state-only animations
        self._stop_animations(self._state)
        # Start new-state animations
        self._start_state_anim(state)
        self._active_group = new_group
        self._state = state

    def _start_state_anim(self, state: str):
        if state == "thinking":
            self._think_ring.start()
            self._think_dots.start()

    def _update_text_for_state(self, state: str, text: str = ""):
        if state == "idle":
            self._idle_text.setText("小橘待命中")
        elif state == "thinking":
            self._think_label.setText("正在思考")
            self._think_sub.setText("AI 正在处理你的请求…")
        elif state == "result":
            self._result_label.setText("任务完成")
            self._result_sub.setText(text or "已完成")
            self._result_pill.setText("已完成")
        elif state == "notify":
            self._notify_label.setText("来自小橘的提醒")
            self._notify_sub.setText(text or "提醒")
            self._notify_pill.setText("提醒")
        elif state == "error":
            self._error_label.setText("出错了")
            # Truncate to 24 chars (CSS text-overflow:ellipsis) — keep width
            # predictable. The sub label also has its own ellipsis via
            # QLabel's default, so 24 is a safety cap.
            err = (text or "请稍后再试").strip()
            if len(err) > 24:
                err = err[:23] + "…"
            self._error_sub.setText(err)
            self._error_pill.setText("失败")

    # Public API — main.py calls this
    def set_state(self, state: str, text: str = ""):
        self._show_state(state, animate=True)
        # Re-set the text AFTER _show_state — the previous _update_text_for_state
        # call already populated labels with defaults, but the user may have
        # passed a custom message that we want to apply.
        if state == "result" and text:
            self._result_sub.setText(text[:24] if len(text) > 24 else text)
        elif state == "notify" and text:
            self._notify_sub.setText(text[:24] if len(text) > 24 else text)
        elif state == "error" and text:
            err = text.strip()
            if len(err) > 24:
                err = err[:23] + "…"
            self._error_sub.setText(err)

    def _position(self):
        scr = self.screen()
        if not scr:
            return
        geo = scr.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        self.move(x, geo.y() + 28)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reposition_groups()

    # ── Show / hide window with fade ──
    def show(self):
        if self._fade and self._fade.state() == QPropertyAnimation.State.Running:
            self._fade.stop()
        self.setWindowOpacity(0)
        super().show()
        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(FADE_WINDOW_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.setStartValue(0)
        self._fade.setEndValue(1)
        self._fade.start()
        # Re-position once we're actually on a screen
        QTimer.singleShot(0, self._position)
        # Mark ready for hover (deferred so the initial enterEvent is ignored)
        QTimer.singleShot(200, self._mark_ready)

    def hide(self):
        if not self.isVisible():
            return
        if self._fade and self._fade.state() == QPropertyAnimation.State.Running:
            self._fade.stop()
        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(FADE_WINDOW_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.setStartValue(1)
        self._fade.setEndValue(0)
        self._fade.finished.connect(super().hide)
        self._fade.start()

    def _mark_ready(self):
        self._ready = True

    # ── Hover water-drop effect (idle only) ──
    def enterEvent(self, _e):
        if self._state == "idle" and self._ready:
            self._idle_text.setText(random.choice(COMPANION_PHRASES))
            self._animate_size_to(float(HOVER_W), float(HOVER_H), float(HOVER_H / 2))

    def leaveEvent(self, _e):
        if self._state == "idle" and self._ready:
            self._idle_text.setText("小橘待命中")
            self._animate_size_to(float(IDLE_W), float(IDLE_H), float(IDLE_RADIUS))

    # ── Mouse ──
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click()
        elif e.button() == Qt.MouseButton.RightButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.MouseButton.RightButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _e):
        self._drag_pos = None
