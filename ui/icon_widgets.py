"""
Custom-painted icon widgets.

We paint icons with QPainter instead of using emoji / unicode characters
because the underlying font may not have the glyph (e.g. ✕ or ─ on offscreen
renderers, or non-Apple emoji fonts on Windows). SVG-style painting on
widgets is the only way to get crisp, predictable icons everywhere.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QSize, QPointF, QRectF, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient
from PySide6.QtWidgets import QWidget, QPushButton
from theme import BG_SUBTLE, BG_CARD, TEXT_SECONDARY, TEXT_MUTED, ACCENT, RED


class WindowControlButton(QWidget):
    """A circular button with a custom-painted icon.

    Pass `kind="min"` for the horizontal line (minimize) or
    `kind="close"` for the X. The icon is drawn in the active accent
    color so it always shows up, regardless of font availability.
    """

    SIZE = 28

    def __init__(self, kind: str, color: str, hover_bg: str, hover_fg: str, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._color = color
        self._hover_bg = hover_bg
        self._hover_fg = hover_fg
        self.setFixedSize(QSize(self.SIZE, self.SIZE))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Round hover background
        if self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(self._hover_bg)))
            p.drawEllipse(0, 0, self.width(), self.height())

        # Icon
        pen = QPen(QColor(self._hover_fg if self._hover else self._color), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        cx = self.width() / 2
        cy = self.height() / 2
        if self._kind == "min":
            p.drawLine(QPointF(cx - 7, cy), QPointF(cx + 7, cy))
        else:  # close
            d = 6.5
            p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
            p.drawLine(QPointF(cx - d, cy + d), QPointF(cx + d, cy - d))
        p.end()


class IslandActionButton(QPushButton):
    def __init__(self, kind="send", parent=None):
        super().__init__(parent)
        self._kind = kind
        self._recording = False
        self._busy = False
        self._hover_amount = 0.0
        self.setFixedSize(40, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QPushButton {background:transparent;border:none;padding:0;}")
        self._motion = QVariantAnimation(self)
        self._motion.setDuration(140)
        self._motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._motion.valueChanged.connect(self._animate_hover)

    def _animate_hover(self, value):
        self._hover_amount = float(value)
        self.update()

    def _hover_to(self, amount):
        self._motion.stop()
        self._motion.setStartValue(self._hover_amount)
        self._motion.setEndValue(amount)
        self._motion.start()

    def enterEvent(self, event):
        self._hover_to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_to(0.0)
        super().leaveEvent(event)

    def set_recording(self, recording):
        self._recording = bool(recording)
        self.setAccessibleName("停止录音" if recording else "语音输入")
        self.update()

    def set_busy(self, busy):
        self._busy = bool(busy)
        self.setAccessibleName("停止生成" if busy else "发送消息")
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(20, 20)
        scale = 0.92 if self.isDown() else 1.0 + self._hover_amount * 0.025
        p.scale(scale, scale)
        if self._kind == "attach":
            p.setPen(Qt.PenStyle.NoPen)
            color = QColor(BG_SUBTLE)
            color.setAlphaF(self._hover_amount)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(-15, -15, 30, 30), 8, 8)
            p.setPen(QPen(QColor(ACCENT if self._hover_amount > .5 else TEXT_MUTED), 1.7,
                         Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(-5, 0), QPointF(5, 0))
            p.drawLine(QPointF(0, -5), QPointF(0, 5))
            if self.hasFocus():
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(ACCENT), 1.0))
                p.drawRoundedRect(QRectF(-17, -17, 34, 34), 8, 8)
            p.end()
            return
        circle = QRectF(-17, -17, 34, 34)
        primary = self._kind == "send" and self.isEnabled()
        active = self._busy or self._recording
        gradient = QLinearGradient(0, -17, 0, 17)
        if primary:
            gradient.setColorAt(0, QColor('#3b414b' if self._hover_amount > .5 else '#303640'))
            gradient.setColorAt(1, QColor('#151a22'))
            border = QColor(255, 255, 255, 45)
            ink = QColor('#ffffff')
        else:
            gradient.setColorAt(0, QColor(255, 255, 255, int(210 + self._hover_amount * 45)))
            gradient.setColorAt(1, QColor('#e9edf3'))
            border = QColor('#d9dfe7')
            ink = QColor(RED if self._recording else TEXT_SECONDARY)
            if not self.isEnabled():
                ink.setAlpha(105)
        p.setBrush(QBrush(gradient))
        p.setPen(QPen(border, .8))
        p.drawEllipse(circle)
        p.setPen(QPen(ink, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ink)
            p.drawRoundedRect(QRectF(-5, -5, 10, 10), 2.5, 2.5)
        elif self._kind == "send":
            p.drawLine(QPointF(0, 6), QPointF(0, -6))
            p.drawLine(QPointF(-4.5, -1.5), QPointF(0, -6))
            p.drawLine(QPointF(0, -6), QPointF(4.5, -1.5))
        else:
            p.drawRoundedRect(QRectF(-3, -8, 6, 11), 3, 3)
            p.drawArc(QRectF(-6, -5, 12, 12), 180 * 16, 180 * 16)
            p.drawLine(QPointF(0, 7), QPointF(0, 10))
            p.drawLine(QPointF(-3, 10), QPointF(3, 10))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(TEXT_SECONDARY), 1))
            p.drawEllipse(QRectF(-19, -19, 38, 38))
        p.end()


class VoiceButton(IslandActionButton):
    def __init__(self, parent=None):
        super().__init__("voice", parent)

class CheckIcon(QWidget):
    """A 28x28 round soft-green pill with a hand-drawn green checkmark.

    The checkmark animates in via a stroke-dashoffset trick, identical to
    the HTML design: a 0.4s scale-in pop + 0.4s stroke draw.
    """

    def __init__(self, bg: str, fg: str, border: str, parent=None):
        super().__init__(parent)
        self._bg = bg
        self._fg = fg
        self._border = border
        self.setFixedSize(QSize(28, 28))
        self._progress = 0.0  # 0..1
        self._scale = 0.5
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self):
        # 25 frames at 16ms = 0.4s pop
        self._scale = min(1.0, self._scale + 0.06)
        if self._scale >= 1.0:
            # 25 frames at 16ms = 0.4s draw
            self._progress = min(1.0, self._progress + 0.06)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Pop-in scale
        p.translate(self.width() / 2, self.height() / 2)
        p.scale(self._scale, self._scale)
        p.translate(-self.width() / 2, -self.height() / 2)

        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(self._border), 1.5))
        p.setBrush(QBrush(QColor(self._bg)))
        p.drawEllipse(rect)

        # Check path
        p.setPen(QPen(QColor(self._fg), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Two-segment polyline approximating the SVG path
        # Start (8, 14.5) → (12, 18.5) → (20, 9.5)
        a = QPointF(8, 14.5)
        b = QPointF(12, 18.5)
        c = QPointF(20, 9.5)
        if self._progress < 0.5:
            t = self._progress / 0.5
            cur = QPointF(
                a.x() + (b.x() - a.x()) * t,
                a.y() + (b.y() - a.y()) * t,
            )
            p.drawLine(a, cur)
        else:
            t = (self._progress - 0.5) / 0.5
            p.drawLine(a, b)
            cur = QPointF(
                b.x() + (c.x() - b.x()) * t,
                b.y() + (c.y() - b.y()) * t,
            )
            p.drawLine(b, cur)
        p.end()


class BellIcon(QWidget):
    """A 28x28 gold pill with a stylized bell that swings once on first show."""

    def __init__(self, bg: str, fg: str, border: str, parent=None):
        super().__init__(parent)
        self._bg = bg
        self._fg = fg
        self._border = border
        self.setFixedSize(QSize(28, 28))
        self._angle = 0.0
        self._phase = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def _tick(self):
        if self._phase >= 30:
            return
        # Bell swing: 0 → 14 → -10 → 6 → 0 (over 30 frames at 33ms ≈ 1s)
        keyframes = [0, 14, -10, 6, 0]
        idx = min(self._phase // 8, len(keyframes) - 1)
        if idx >= len(keyframes) - 1:
            self._angle = keyframes[-1]
            self._phase = 30
        else:
            t = (self._phase % 8) / 8.0
            a, b = keyframes[idx], keyframes[idx + 1]
            self._angle = a + (b - a) * t
        self._phase += 1
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(self._border), 1.5))
        p.setBrush(QBrush(QColor(self._bg)))
        p.drawEllipse(rect)

        # Bell — rotate around top center so it swings like hanging
        p.translate(self.width() / 2, 7)
        p.rotate(self._angle)
        p.translate(-self.width() / 2, -7)
        pen = QPen(QColor(self._fg), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Simple bell outline
        p.drawPolyline([
            QPointF(10.5, 7.5),
            QPointF(10.5, 14.0),
            QPointF(17.5, 14.0),
            QPointF(17.5, 7.5),
        ])
        # Top dome
        for i in range(20):
            t = math.pi * i / 20
            x = 14 + 3.5 * math.cos(t + math.pi)
            y = 11 + 3.5 * math.sin(t + math.pi)
            p.drawPoint(QPointF(x, y))
        # Clapper
        p.drawLine(QPointF(13.0, 16.5), QPointF(15.0, 16.5))
        p.end()

