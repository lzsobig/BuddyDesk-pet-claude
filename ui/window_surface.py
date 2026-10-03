import math
from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen


@lru_cache(maxsize=48)
def _surface_path(width, height, inset, radius):
    path = QPainterPath()
    left, top = inset, inset
    right, bottom = width - inset, height - inset
    radius = min(radius, (right - left) / 2, (bottom - top) / 2)
    if radius <= 0:
        return path
    centers = ((right - radius, top + radius, -90),
               (right - radius, bottom - radius, 0),
               (left + radius, bottom - radius, 90),
               (left + radius, top + radius, 180))
    for corner, (cx, cy, angle) in enumerate(centers):
        for step in range(33):
            radians = math.radians(angle + step * 90 / 32)
            cosine, sine = math.cos(radians), math.sin(radians)
            x = cx + radius * math.copysign(abs(cosine) ** (2 / 2.6), cosine)
            y = cy + radius * math.copysign(abs(sine) ** (2 / 2.6), sine)
            if corner == 0 and step == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
    path.closeSubpath()
    return path


def paint_window_surface(widget, dark=False):
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.fillRect(widget.rect(), Qt.GlobalColor.transparent)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.setPen(Qt.PenStyle.NoPen)
    for spread in range(9, 0, -1):
        painter.setBrush(QColor(0, 0, 0, 4 + (9 - spread) // 2) if dark else QColor(41, 54, 72, 2 + (9 - spread) // 3))
        painter.drawPath(_surface_path(widget.width(), widget.height(), 10 - spread, 27 + spread))
    surface = _surface_path(widget.width(), widget.height(), 10, 27)
    gradient = QLinearGradient(0, 10, widget.width() * 0.7, widget.height())
    gradient.setColorAt(0, QColor('#1b1c20' if dark else '#ffffff'))
    gradient.setColorAt(0.45, QColor('#101114' if dark else '#f8f9fb'))
    gradient.setColorAt(1, QColor('#08090b' if dark else '#f1f3f7'))
    painter.fillPath(surface, gradient)
    painter.setPen(QPen(QColor(255, 255, 255, 24) if dark else QColor(158, 170, 188, 105), 1.0))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(surface)
    painter.setPen(QPen(QColor(255, 255, 255, 10 if dark else 220), 1.0))
    painter.drawPath(_surface_path(widget.width(), widget.height(), 11, 26))
    painter.end()
