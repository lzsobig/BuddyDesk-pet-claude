"""
VoiceCapsule - floating voice capture status surface.

The capsule stays deliberately self-contained: one transparent QWidget, one
paintEvent, and a small timer. It gives recording and recognition their own
visual language without adding another widget hierarchy to the desktop.
"""
from __future__ import annotations

import math
import time
from collections import deque
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QRectF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPainterPath,
    QFont,
    QFontMetrics,
    QPen,
    QLinearGradient,
)
from PySide6.QtWidgets import QWidget

from theme import (
    ACCENT,
    ACCENT_BRIGHT,
    BG_CARD,
    BORDER,
    GREEN,
    GOLD,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


WIDTH = 286
HEIGHT = 76
RADIUS = 24.0
CONTENT_MARGIN = 7.0
BAR_COUNT = 7
BAR_WIDTH = 3.0
BAR_GAP = 4.0
BAR_MIN_H = 7.0
BAR_MAX_H = 30.0
LEVEL_WINDOW = 12
LEVEL_EMA = 0.42


class VoiceCapsule(QWidget):
    """Animated, always-visible status surface for voice input."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._state = "idle"
        self._levels: deque[float] = deque([0.0] * LEVEL_WINDOW, maxlen=LEVEL_WINDOW)
        self._smoothed = [0.0] * BAR_COUNT
        self._phase = 0.0
        self._started_at = 0.0
        self._anchor_top = True
        self._fade: Optional[QPropertyAnimation] = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(WIDTH, HEIGHT)

        self._font_title = QFont("Inter, Noto Sans SC, Segoe UI, sans-serif")
        self._font_title.setPixelSize(14)
        self._font_title.setWeight(QFont.Weight.DemiBold)
        self._font_sub = QFont("Inter, Noto Sans SC, Segoe UI, sans-serif")
        self._font_sub.setPixelSize(11)
        self._font_sub.setWeight(QFont.Weight.Normal)
        self._font_time = QFont("Cascadia Code, Consolas, monospace")
        self._font_time.setPixelSize(10)

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)

    # Public API -----------------------------------------------------
    def show_recording(self) -> None:
        self._state = "recording"
        self._started_at = time.monotonic()
        self._levels = deque([0.0] * LEVEL_WINDOW, maxlen=LEVEL_WINDOW)
        self._smoothed = [0.0] * BAR_COUNT
        self._reposition()
        self._tick.start(16)
        self._fade_in()

    def show_processing(self) -> None:
        self._state = "processing"
        if not self._started_at:
            self._started_at = time.monotonic()
        self._tick.start(24)
        if not self.isVisible():
            self._reposition()
            self._fade_in()
        else:
            self.update()

    def show_error(self, detail: str = "检查麦克风和模型") -> None:
        self._state = "error"
        self._error_detail = detail
        self._tick.stop()
        self._reposition()
        self._fade_in()
        QTimer.singleShot(2200, self.hide_capsule)

    def hide_capsule(self) -> None:
        if not self.isVisible():
            self._state = "idle"
            return
        self._state = "idle"
        self._tick.stop()
        self._fade_out()

    def push_level(self, level: float) -> None:
        self._levels.append(max(0.0, min(1.0, float(level))))

    # Position and animation ----------------------------------------
    def _reposition(self) -> None:
        screen = self.screen()
        if not screen:
            screen = self.windowHandle().screen() if self.windowHandle() else None
        if not screen:
            return
        geometry = screen.availableGeometry()
        x = geometry.x() + (geometry.width() - self.width()) // 2
        y = geometry.y() + 38 + 18
        if not self._anchor_top:
            y = geometry.y() + geometry.height() - self.height() - 80
        self.move(x, y)

    def _fade_in(self) -> None:
        if self._fade and self._fade.state() == QPropertyAnimation.State.Running:
            self._fade.stop()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(180)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.start()
        self._fade = animation

    def _fade_out(self) -> None:
        if self._fade and self._fade.state() == QPropertyAnimation.State.Running:
            self._fade.stop()
        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(200)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setStartValue(self.windowOpacity())
        animation.setEndValue(0.0)
        animation.finished.connect(self.hide)
        animation.start()
        self._fade = animation

    # Animation ------------------------------------------------------
    def _on_tick(self) -> None:
        self._phase += 0.12
        targets = list(self._levels)
        while len(targets) < BAR_COUNT:
            targets.insert(0, 0.0)
        for index in range(BAR_COUNT):
            if self._state == "processing":
                sweep = (math.sin(self._phase * 2.0 - index * 0.72) + 1.0) / 2.0
                target = 0.24 + sweep * 0.66
            else:
                target = targets[-BAR_COUNT + index]
            self._smoothed[index] += (target - self._smoothed[index]) * LEVEL_EMA
        self.update()

    # Painting -------------------------------------------------------
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        rect = QRectF(CONTENT_MARGIN, CONTENT_MARGIN,
                      self.width() - CONTENT_MARGIN * 2,
                      self.height() - CONTENT_MARGIN * 2)
        radius = RADIUS

        # Layered shadow gives the floating surface separation from light apps.
        painter.setPen(Qt.PenStyle.NoPen)
        for offset, alpha in ((5, 12), (3, 18), (1, 24)):
            painter.setBrush(QColor(31, 36, 34, alpha))
            painter.drawRoundedRect(rect.adjusted(-offset, -offset / 2, offset, offset), radius + offset / 2, radius + offset / 2)

        state_color = self._state_color()
        fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
        fill.setColorAt(0.0, QColor(BG_CARD))
        fill.setColorAt(1.0, QColor("#f3f0e9"))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, radius, radius)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(state_color), 1.2))
        painter.drawRoundedRect(rect, radius, radius)

        self._draw_mic(painter, rect.left() + 18, rect.center().y(), state_color)
        self._draw_text(painter, rect, state_color)
        self._draw_wave(painter, rect, state_color)
        painter.end()

    def _state_color(self) -> QColor:
        if self._state == "processing":
            return QColor(GOLD)
        if self._state == "error":
            return QColor(RED)
        return QColor(ACCENT_BRIGHT if self._state == "recording" else ACCENT)

    def _draw_mic(self, painter: QPainter, x: float, y: float, color: QColor) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 28))
        painter.drawEllipse(QRectF(x - 15, y - 15, 30, 30))
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(x - 3.5, y - 9, 7, 14), 3.5, 3.5)
        painter.setPen(QPen(color, 1.6))
        painter.drawArc(QRectF(x - 8, y - 6, 16, 15), 200 * 16, 140 * 16)
        painter.drawLine(int(x), int(y + 9), int(x), int(y + 12))
        painter.drawLine(int(x - 5), int(y + 13), int(x + 5), int(y + 13))

    def _draw_text(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        title = {
            "recording": "正在聆听",
            "processing": "正在识别",
            "error": "语音不可用",
        }.get(self._state, "语音输入")
        subtitle = {
            "recording": "松开或点击停止",
            "processing": "请稍候，正在整理文字",
            "error": getattr(self, "_error_detail", "请稍后重试"),
        }.get(self._state, "按住 Ctrl+Shift+V")
        text_x = rect.left() + 48
        painter.setFont(self._font_title)
        painter.setPen(QColor(TEXT_PRIMARY))
        painter.drawText(int(text_x), int(rect.top() + 29), title)
        painter.setFont(self._font_sub)
        painter.setPen(QColor(TEXT_SECONDARY if self._state != "error" else RED))
        painter.drawText(int(text_x), int(rect.top() + 49), subtitle)

        if self._state == "recording":
            elapsed = max(0, int(time.monotonic() - self._started_at))
            painter.setFont(self._font_time)
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawText(int(rect.right() - 48), int(rect.top() + 20), f"{elapsed:02d}s")

    def _draw_wave(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        if self._state == "error":
            return
        left = rect.right() - 84
        center_y = rect.center().y() + 1
        for index, level in enumerate(self._smoothed):
            height = BAR_MIN_H + (BAR_MAX_H - BAR_MIN_H) * level
            x = left + index * (BAR_WIDTH + BAR_GAP)
            bar_rect = QRectF(x, center_y - height / 2, BAR_WIDTH, height)
            alpha = 150 + int(90 * min(1.0, level + 0.15))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), alpha))
            painter.drawRoundedRect(bar_rect, BAR_WIDTH / 2, BAR_WIDTH / 2)
