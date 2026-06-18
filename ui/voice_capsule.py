"""
VoiceCapsule — 闪电说同款悬浮语音胶囊。

参考闪电说（Tauri 2 + Rust + WebView2）的视觉：
- 黑色圆角胶囊，无边框、置顶、跳过任务栏、透明背景
- 左侧文字"语音输入"，右侧 6 根实时波形条
- 三种状态：idle（隐藏）/ recording（采集中，波形随 RMS 动）/ processing（波形脉冲）

数据来源：voice_input.VoiceInputController 通过 push_level(level: float) 喂电平 (0~1)，
本胶囊保留滚动窗口 + EMA 平滑画 6 根条。
"""
from __future__ import annotations

import math
from collections import deque
from typing import Optional

from PySide6.QtCore import (
    Qt,
    QTimer,
    QRectF,
    QPropertyAnimation,
    QEasingCurve,
    Property,
)
from PySide6.QtGui import QPainter, QColor, QPainterPath, QFont, QFontMetrics, QPen
from PySide6.QtWidgets import QWidget


# ── 视觉常量 ──────────────────────────────────────────────────────
WIDTH = 168
HEIGHT = 44
RADIUS = HEIGHT / 2
BG_COLOR = QColor(20, 22, 24, 235)        # 几乎纯黑半透明
BORDER_COLOR = QColor(255, 255, 255, 28)  # 微微的高光边
TEXT_COLOR = QColor(245, 245, 245)
DIVIDER_COLOR = QColor(255, 255, 255, 60)
BAR_COLOR_IDLE = QColor(255, 255, 255, 140)
BAR_COLOR_REC = QColor(255, 255, 255, 235)
BAR_COUNT = 6
BAR_WIDTH = 2.4
BAR_GAP = 3.0
BAR_MIN_H = 4.0
BAR_MAX_H = 22.0

LEVEL_WINDOW = 6   # 滚动窗口：每根条对应一个最近的电平
LEVEL_EMA = 0.55   # 平滑系数，越大越跟手


class VoiceCapsule(QWidget):
    """悬浮胶囊。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._state = "idle"
        self._levels: deque[float] = deque([0.0] * LEVEL_WINDOW, maxlen=LEVEL_WINDOW)
        self._smoothed: list[float] = [0.0] * BAR_COUNT
        self._phase = 0.0
        self._anchor_top = True  # 默认贴顶部居中

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(WIDTH, HEIGHT)

        self._font = QFont("Inter, Noto Sans SC, Segoe UI, sans-serif")
        self._font.setPixelSize(13)
        self._font.setWeight(QFont.Weight.DemiBold)

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)

        self._fade: Optional[QPropertyAnimation] = None

    # ── 对外 API ────────────────────────────────────────────────────

    def show_recording(self) -> None:
        """开始录音：定位、淡入、启动 60fps 重绘。"""
        self._state = "recording"
        self._levels = deque([0.0] * LEVEL_WINDOW, maxlen=LEVEL_WINDOW)
        self._smoothed = [0.0] * BAR_COUNT
        self._reposition()
        self._tick.start(16)
        self._fade_in()

    def show_processing(self) -> None:
        """识别中：保持显示，波形改为脉冲。"""
        self._state = "processing"
        self._tick.start(33)
        if not self.isVisible():
            self._reposition()
            self._fade_in()

    def hide_capsule(self) -> None:
        """淡出并停止重绘。"""
        if not self.isVisible():
            return
        self._state = "idle"
        self._tick.stop()
        self._fade_out()

    def push_level(self, level: float) -> None:
        """喂一帧麦克风电平 (0~1)。线程安全（Qt 信号已切回主线程后再调用）。"""
        lv = max(0.0, min(1.0, float(level)))
        self._levels.append(lv)

    # ── 内部：定位与动画 ──────────────────────────────────────────

    def _reposition(self) -> None:
        scr = self.screen()
        if not scr:
            return
        g = scr.availableGeometry()
        x = g.x() + (g.width() - self.width()) // 2
        if self._anchor_top:
            # 留出顶部灵动岛的位置，胶囊放下面一点
            y = g.y() + 28 + 52 + 12
        else:
            y = g.y() + g.height() - self.height() - 80
        self.move(x, y)

    def _fade_in(self) -> None:
        if self._fade and self._fade.state() == QPropertyAnimation.State.Running:
            self._fade.stop()
        self.setWindowOpacity(0.0)
        self.show()
        a = QPropertyAnimation(self, b"windowOpacity")
        a.setDuration(160)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.start()
        self._fade = a

    def _fade_out(self) -> None:
        if self._fade and self._fade.state() == QPropertyAnimation.State.Running:
            self._fade.stop()
        a = QPropertyAnimation(self, b"windowOpacity")
        a.setDuration(180)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.setStartValue(self.windowOpacity())
        a.setEndValue(0.0)
        a.finished.connect(super().hide)
        a.start()
        self._fade = a

    # ── 内部：帧驱动 ────────────────────────────────────────────────

    def _on_tick(self) -> None:
        self._phase += 0.16
        # 把滚动窗口里的电平当作 6 根条的目标高度，做一遍 EMA 平滑
        targets = list(self._levels)
        # 不够 6 个就补 0
        while len(targets) < BAR_COUNT:
            targets.insert(0, 0.0)
        for i in range(BAR_COUNT):
            if self._state == "processing":
                # 脉冲：左右扫的波，幅度随时间衰减
                t = math.sin(self._phase * 2.5 - i * 0.6)
                tgt = 0.35 + 0.35 * max(0.0, t)
            else:
                tgt = targets[i]
            self._smoothed[i] = (
                self._smoothed[i] * (1 - LEVEL_EMA) + tgt * LEVEL_EMA
            )
        self.update()

    # ── 绘制 ─────────────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = float(self.width()), float(self.height())

        # 圆角胶囊背景
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), RADIUS, RADIUS)
        p.setClipPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BG_COLOR)
        p.drawRoundedRect(QRectF(0, 0, w, h), RADIUS, RADIUS)

        # 文本"语音输入"
        p.setFont(self._font)
        p.setPen(TEXT_COLOR)
        fm = QFontMetrics(self._font)
        label = "语音输入"
        text_w = fm.horizontalAdvance(label)
        text_x = 18.0
        text_y = h / 2 + fm.ascent() / 2 - 2
        p.drawText(int(text_x), int(text_y), label)

        # 中间细分隔线
        div_x = text_x + text_w + 12
        p.setPen(QPen(DIVIDER_COLOR, 1))
        p.drawLine(int(div_x), int(h * 0.28), int(div_x), int(h * 0.72))

        # 右侧 6 根波形条
        bars_total = BAR_COUNT * BAR_WIDTH + (BAR_COUNT - 1) * BAR_GAP
        # 让波形组在 [div_x+10, w-16] 内居中
        bar_area_left = div_x + 10
        bar_area_right = w - 18
        bar_area_w = bar_area_right - bar_area_left
        start_x = bar_area_left + max(0.0, (bar_area_w - bars_total) / 2)
        center_y = h / 2

        color = BAR_COLOR_REC if self._state == "recording" else BAR_COLOR_IDLE
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        for i in range(BAR_COUNT):
            lv = self._smoothed[i]
            bar_h = BAR_MIN_H + (BAR_MAX_H - BAR_MIN_H) * lv
            x = start_x + i * (BAR_WIDTH + BAR_GAP)
            y = center_y - bar_h / 2
            p.drawRoundedRect(
                QRectF(x, y, BAR_WIDTH, bar_h),
                BAR_WIDTH / 2,
                BAR_WIDTH / 2,
            )

        # 边框（取消裁剪后画，避免锯齿）
        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(BORDER_COLOR, 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), RADIUS, RADIUS)
        p.end()
