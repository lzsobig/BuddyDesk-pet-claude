"""
Custom-painted icon widgets.

We paint icons with QPainter instead of using emoji / unicode characters
because the underlying font may not have the glyph (e.g. ✕ or ─ on offscreen
renderers, or non-Apple emoji fonts on Windows). SVG-style painting on
widgets is the only way to get crisp, predictable icons everywhere.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QSize, QPointF, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient
from PySide6.QtWidgets import QWidget, QPushButton


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


class VoiceButton(QPushButton):
    """Font-independent microphone control for the chat input row.

    Emoji glyphs are not reliable in a frozen Windows Qt package: the glyph
    can be missing or substituted as an empty square. Painting the tiny icon
    keeps the control crisp and also gives recording a clear stop state.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recording = False
        self._hover = False
        self.setFixedSize(QSize(34, 34))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_recording(self, recording: bool):
        self._recording = bool(recording)
        self.update()

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
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        if self._recording:
            bg_top, bg_bottom = QColor("#fff7f5"), QColor("#fbe8e5")
            fg, border = QColor("#c8756d"), QColor("#e4aaa3")
        elif self._hover:
            bg_top, bg_bottom = QColor("#f5fcf8"), QColor("#e3f4ec")
            fg, border = QColor("#4aaf88"), QColor("#93d1b8")
        else:
            bg_top, bg_bottom = QColor("#ffffff"), QColor("#edf5f1")
            fg, border = QColor("#5cb89a"), QColor("#c9e2d7")
        bg = QLinearGradient(0, 0, 0, self.height())
        bg.setColorAt(0.0, bg_top)
        bg.setColorAt(1.0, bg_bottom)
        p.setPen(QPen(border, 1))
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(rect, 10, 10)

        # Small inner highlight: keeps the control luminous against the input
        # tray and prevents the glyph from reading as a heavy black stamp.
        p.setPen(QPen(QColor(255, 255, 255, 180), 1))
        p.drawLine(QPointF(10, 2), QPointF(self.width() - 10, 2))

        pen = QPen(fg, 1.9)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = self.width() / 2, self.height() / 2
        if self._recording:
            p.setBrush(fg)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(cx - 5, cy - 5, 10, 10), 2, 2)
        else:
            p.setBrush(fg)
            p.setPen(QPen(fg, 1.2))
            p.drawRoundedRect(QRectF(cx - 3.5, cy - 8, 7, 12), 3.5, 3.5)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(pen)
            p.drawArc(QRectF(cx - 8, cy - 5, 16, 15), 200 * 16, 140 * 16)
            p.drawLine(QPointF(cx, cy + 10), QPointF(cx, cy + 12))
            p.drawLine(QPointF(cx - 4, cy + 13), QPointF(cx + 4, cy + 13))
        p.end()


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

