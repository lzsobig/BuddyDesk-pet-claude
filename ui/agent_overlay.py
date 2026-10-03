from __future__ import annotations

import math
import sys

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QApplication, QWidget


_STATE_LABELS = {
    "listening": "正在聆听",
    "transcribing": "正在识别",
    "understanding": "正在整理请求",
    "thinking": "正在思考",
    "asking_confirmation": "等待你确认",
    "executing": "正在执行",
    "success": "已完成",
    "error": "遇到问题",
    "reminding": "提醒",
}

_STATE_COLORS = {
    "listening": "#67bfd0",
    "transcribing": "#70b8c8",
    "understanding": "#78b3c5",
    "thinking": "#76a9c4",
    "asking_confirmation": "#c3a16f",
    "executing": "#74b7b2",
    "success": "#72b397",
    "error": "#c77c83",
    "reminding": "#a999c8",
}

_GLOW_COLORS = (
    "#779afa",
    "#6acddc",
    "#7ed4be",
    "#a98bed",
    "#df93bf",
    "#e5b094",
    "#86b2ee",
)


class AgentOverlay(QWidget):
    def __init__(self, screen=None, parent=None):
        super().__init__(parent)
        self._explicit_screen = screen is not None
        self._screen = screen or QApplication.primaryScreen()
        self._state = "idle"
        self._label = ""
        self._transcript = ""
        self._target_level = 0.0
        self._smoothed_level = 0.0
        self._phase = 0.0
        self._reduced_motion = False
        self._color = QColor(_STATE_COLORS["listening"])
        self._glow_mask = None
        self.external_input_active = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle("BuddyDesk Agent Overlay")

        self._status_font = QFont()
        self._status_font.setFamilies(["Microsoft YaHei UI", "Segoe UI"])
        self._status_font.setPixelSize(14)
        self._status_font.setWeight(QFont.Weight.DemiBold)
        self._transcript_font = QFont(self._status_font)
        self._transcript_font.setWeight(QFont.Weight.Normal)
        self._hint_font = QFont(self._transcript_font)
        self._hint_font.setPixelSize(11)

        self._tick = QTimer(self)
        self._tick.setInterval(33)
        self._tick.timeout.connect(self._advance)

    def present(
        self,
        state: str,
        label: str = "",
        transcript: str = "",
        level: float = 0.0,
        reduced_motion: bool = False,
    ) -> None:
        state = str(state or "idle").strip().lower()
        if state == "idle":
            self.dismiss()
            return

        self._state = state
        self._label = str(label or "").strip()
        self._transcript = " ".join(str(transcript or "").split())
        self._target_level = max(0.0, min(1.0, float(level)))
        self._reduced_motion = bool(reduced_motion)
        self._color = QColor(_STATE_COLORS.get(state, _STATE_COLORS["thinking"]))
        if not self.isVisible() and not self._explicit_screen:
            self._screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        self._apply_screen_geometry()

        if self._reduced_motion:
            self._smoothed_level = self._target_level
            self._tick.stop()
        elif not self._tick.isActive():
            self._tick.start()

        if not self.isVisible():
            self.show()
            self.raise_()
        self._apply_native_styles()
        self.update()

    def dismiss(self) -> None:
        self._tick.stop()
        self._state = "idle"
        self._label = ""
        self._transcript = ""
        self._target_level = 0.0
        self._smoothed_level = 0.0
        self.hide()

    def _apply_screen_geometry(self) -> None:
        screen = self._screen or QApplication.primaryScreen()
        if screen is None:
            return
        self._screen = screen
        geometry = screen.geometry()
        self.setGeometry(geometry)

    def _advance(self) -> None:
        if self._reduced_motion or self._state == "idle":
            self._tick.stop()
            return
        self._smoothed_level += (self._target_level - self._smoothed_level) * 0.22
        self._phase += 0.045 if self._state == "listening" else 0.012
        self.update()

    def _apply_native_styles(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            get_window_long = getattr(
                user32,
                "GetWindowLongPtrW",
                user32.GetWindowLongW,
            )
            set_window_long = getattr(
                user32,
                "SetWindowLongPtrW",
                user32.SetWindowLongW,
            )
            get_window_long.argtypes = (ctypes.c_void_p, ctypes.c_int)
            get_window_long.restype = ctypes.c_ssize_t
            set_window_long.argtypes = (
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_ssize_t,
            )
            set_window_long.restype = ctypes.c_ssize_t

            hwnd = ctypes.c_void_p(int(self.winId()))
            exstyle = get_window_long(hwnd, -20)
            exstyle |= 0x00000020 | 0x08000000
            set_window_long(hwnd, -20, exstyle)
            user32.SetWindowPos(
                hwnd,
                None,
                0,
                0,
                0,
                0,
                0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020,
            )
        except (AttributeError, OSError, ValueError):
            pass

    def _draw_edge_glow(self, painter: QPainter) -> None:
        width = float(self.width())
        height = float(self.height())
        if width <= 0 or height <= 0:
            return

        if self._glow_mask is None or self._glow_mask.size() != self.size():
            mask = QImage(self.width(), self.height(), QImage.Format.Format_ARGB32_Premultiplied)
            mask.fill(Qt.GlobalColor.transparent)
            mask_painter = QPainter(mask)
            mask_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            path = QPainterPath()
            path.addRoundedRect(QRectF(1.5, 1.5, width - 3.0, height - 3.0), 58.0, 58.0)
            stroke_scale = min(1.0, max(0.1, min(width, height) / 240.0))
            mask_painter.setBrush(Qt.BrushStyle.NoBrush)
            for stroke_width in range(112, 1, -4):
                mask_painter.setPen(QPen(QColor(255, 255, 255, 5), stroke_width * stroke_scale))
                mask_painter.drawPath(path)
            mask_painter.end()
            self._glow_mask = mask

        brightness = 0.67
        if self._state == "listening":
            brightness += 0.33 * self._smoothed_level
        if not self._reduced_motion:
            brightness += 0.05 * (0.5 + 0.5 * math.sin(self._phase))
        brightness = min(1.0, brightness)

        rotation = -90.0 if self._reduced_motion else -90.0 + math.degrees(self._phase) * 0.2
        colors = [QColor(value) for value in _GLOW_COLORS]
        gradient = QConicalGradient(width / 2.0, height / 2.0, rotation)
        for index, color in enumerate(colors):
            gradient.setColorAt(index / len(colors), color)
        gradient.setColorAt(1.0, colors[0])
        glow = QImage(self.width(), self.height(), QImage.Format.Format_ARGB32_Premultiplied)
        glow_painter = QPainter(glow)
        glow_painter.fillRect(glow.rect(), gradient)
        glow_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        glow_painter.drawImage(0, 0, self._glow_mask)
        glow_painter.end()
        painter.setOpacity(brightness)
        painter.drawImage(0, 0, glow)
        painter.setOpacity(1.0)

    def _transcript_lines(self, text: str, metrics: QFontMetrics, width: float) -> list[str]:
        if not text:
            return []
        remaining = text
        lines: list[str] = []
        for _ in range(2):
            if not remaining:
                break
            end = 0
            last_space = -1
            while end < len(remaining):
                if remaining[end].isspace():
                    last_space = end
                if metrics.horizontalAdvance(remaining[: end + 1]) > width:
                    break
                end += 1
            if end == len(remaining):
                lines.append(remaining.strip())
                remaining = ""
                break
            if end == 0:
                end = 1
            elif last_space > 0:
                end = last_space
            lines.append(remaining[:end].strip())
            remaining = remaining[end:].strip()
        if remaining and lines:
            lines[-1] = metrics.elidedText(
                lines[-1] + " " + remaining,
                Qt.TextElideMode.ElideRight,
                int(width),
            )
        return [line for line in lines if line]

    def paintEvent(self, _event) -> None:
        if self._state == "idle":
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        self._draw_edge_glow(painter)
        self._draw_transcript_panel(painter)
        painter.end()

    def _draw_transcript_panel(self, painter: QPainter) -> None:
        if self.external_input_active or self._state in ("understanding", "thinking", "executing", "success"):
            return
        screen_width = self.width()
        panel_width = min(720.0, max(280.0, screen_width - 56.0))
        panel_width = min(panel_width, max(160.0, screen_width - 40.0))
        margin_bottom = 24.0

        transcript_metrics = QFontMetrics(self._transcript_font)
        text_width = panel_width - 36.0
        lines = self._transcript_lines(self._transcript, transcript_metrics, text_width)
        show_hint = self._state == "listening"
        panel_height = 42.0 + len(lines) * 21.0 + (23.0 if show_hint else 0.0)
        x = (screen_width - panel_width) / 2.0
        available_bottom = self.height()
        if self._screen:
            available_bottom = min(available_bottom, self._screen.availableGeometry().bottom() - self.geometry().top() + 1)
        y = available_bottom - panel_height - margin_bottom
        panel = QRectF(x, y, panel_width, panel_height)

        fill = QColor(17, 27, 37, 225)
        painter.setPen(QPen(QColor(self._color.red(), self._color.green(), self._color.blue(), 76), 1.0))
        painter.setBrush(fill)
        painter.drawRoundedRect(panel, 13.0, 13.0)

        painter.setPen(QPen(self._color, 1.0))
        painter.setBrush(self._color)
        painter.drawEllipse(QRectF(x + 14.0, y + 14.0, 8.0, 8.0))

        status = self._label or _STATE_LABELS.get(self._state, "正在处理")
        status_metrics = QFontMetrics(self._status_font)
        status_width = panel_width - 54.0
        status = status_metrics.elidedText(
            status,
            Qt.TextElideMode.ElideRight,
            int(status_width),
        )
        painter.setFont(self._status_font)
        painter.setPen(QColor("#e8f1f5"))
        painter.drawText(
            QRectF(x + 30.0, y + 7.0, status_width, 22.0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            status,
        )

        if lines:
            painter.setFont(self._transcript_font)
            painter.setPen(QColor("#d0dce2"))
            for index, line in enumerate(lines):
                painter.drawText(QRectF(x + 16.0, y + 34.0 + index * 21.0, text_width, 20.0), line)

        if show_hint:
            painter.setFont(self._hint_font)
            painter.setPen(QColor(185, 201, 209, 205))
            hint = "Alt+F 完成 · Esc 取消"
            hint_metrics = QFontMetrics(self._hint_font)
            hint = hint_metrics.elidedText(
                hint,
                Qt.TextElideMode.ElideRight,
                int(panel_width - 32.0),
            )
            painter.drawText(
                QRectF(x + 16.0, y + panel_height - 19.0, panel_width - 32.0, 14.0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                hint,
            )
