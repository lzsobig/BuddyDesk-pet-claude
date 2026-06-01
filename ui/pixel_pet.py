"""
Pixel Pet — PySide6 widget using real Pixel Art sprite PNGs from
C:\\Users\\李振\\Desktop\\chubby-orange-cat-codex-pet\\frames\\.

Features:
- 7 main states: idle / walk / happy / sleep / love / thinking / error
- All sprites are real PNGs loaded via QPixmap — no PIL drawing
- 10 FPS animation for walk/happy (4 frames each)
- 静止时完全静止 (idle/sleep/thinking/error use SINGLE static frame,
  no per-tick setPixmap, no breath bob — eliminates flicker)
- 拖拽采用 spring easing
- Speech bubble (dark glass)
- Floating ZZZ on sleep, hearts on love

Public API kept stable:
- set_state(state)
- say(text, duration)
- show() / hide() with fade
- mouseDoubleClickEvent -> on_double_click
"""
import math
import os
import random

from PySide6.QtWidgets import QWidget, QLabel
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QPixmap, QPainter, QColor, QTransform, QPainterPath, QRegion

from theme import TEXT_MUTED, ACCENT


# Path to the user-provided chubby-orange-cat asset pack.
# Falls back to the local assets/ if the original isn't reachable
# (e.g. a teammate runs the app from a different machine).
ASSET_DIR_CANDIDATES = [
    r"C:\Users\李振\Desktop\chubby-orange-cat-codex-pet\frames",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets", "cat_frames_v2",
    ),
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets", "pet_frames",
    ),
]


def _resolve_asset_dir() -> str | None:
    for d in ASSET_DIR_CANDIDATES:
        if os.path.isdir(d):
            return d
    return None


# Display sizing — source PNGs are 256x256.
DISPLAY_SIZE = 128  # scaled down to fit a small desktop widget


# ── State → frame mapping (spritesheet is 8 cols × 9 rows = 72 frames) ────────
# 静态状态只用一个 frame：永远不会 setPixmap 重绘 → 彻底消除闪烁。
# 动画状态 (walk / happy) 用 4 帧循环，10 FPS。
STATE_FRAMES: dict[str, list[str]] = {
    "idle":     ["frame_00.png"],          # 静态单帧 — 绝不掉帧、绝不闪烁
    "walk":     ["frame_08.png", "frame_09.png", "frame_10.png", "frame_11.png"],
    "happy":    ["frame_24.png", "frame_25.png", "frame_26.png", "frame_27.png"],
    "sleep":    ["frame_48.png"],          # 静态 + 浮动 ZZZ
    "love":     ["frame_24.png", "frame_25.png"],  # 复用 happy 挥手
    "thinking": ["frame_64.png"],          # 静态 review 姿势
    "error":    ["frame_40.png"],          # 静态 fail 表情
}


class PixelPet(QWidget):
    """Desktop pet using the chubby-orange-cat sprite pack."""

    FADE_DURATION = 180          # ms
    ANIM_FPS = 10
    ANIM_INTERVAL = 1000 // ANIM_FPS
    STATE_COOLDOWN_MIN = 8000    # 8s
    STATE_COOLDOWN_MAX = 15000   # 15s
    WALK_DURATION_FRAMES = 50    # ~5s at 10 FPS
    DRAG_SPRING_MS = 200

    # ZZZ / heart colors
    ZZZ_COLOR = "#7B8CDE"
    HEART_FILL = "#FF6B8A"

    def __init__(self, on_double_click=None, parent=None):
        super().__init__(parent)
        self.on_double_click = on_double_click
        self.pet_name = "小橘"
        self.state = "idle"
        self.frame_idx = 0
        self.direction = 1
        self._walk_timer = 0
        self._dragging = False
        self._fade_anim = None
        self._position_anim = None
        self._zzz_phase = 0.0
        self._heart_phase = 0.0
        self._last_drawn_frame_idx = -1   # 防闪烁：仅在帧索引变化时 setPixmap

        self._asset_dir = _resolve_asset_dir()
        self._frames: dict[str, list[QPixmap]] = {}
        self._load_sprites()
        self._setup_ui()
        self._start_animation()
        # 立刻绘制第一帧,避免显示空白
        self._draw_current_frame(force=True)

    # ── Sprite loading ──────────────────────────────────────────
    def _load_pixmap(self, filename: str) -> QPixmap | None:
        if not self._asset_dir:
            return None
        path = os.path.join(self._asset_dir, filename)
        if not os.path.exists(path):
            return None
        pm = QPixmap(path)
        if pm.isNull():
            return None
        return pm.scaled(
            DISPLAY_SIZE, DISPLAY_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _load_sprites(self):
        for state, files in STATE_FRAMES.items():
            pixs: list[QPixmap] = []
            for f in files:
                pm = self._load_pixmap(f)
                if pm is not None:
                    pixs.append(pm)
            if not pixs:
                pixs = self._frames.get("idle", [])[:]
            self._frames[state] = pixs

    # ── UI setup ─────────────────────────────────────────────────
    def _setup_ui(self):
        w = DISPLAY_SIZE + 32
        h = DISPLAY_SIZE + 36
        self.setFixedSize(w, h)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(1)

        # Position at bottom-right
        screen = self.screen().availableGeometry()
        self.move(
            screen.width() - self.width() - 20,
            screen.height() - self.height() - 40,
        )

        # Sprite label — centered horizontally
        self.sprite_label = QLabel(self)
        self.sprite_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sprite_label.setGeometry(16, 0, DISPLAY_SIZE, DISPLAY_SIZE)
        self.sprite_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )

        # Name label
        self.name_label = QLabel(self.pet_name, self)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; font-weight: bold; "
            f"background: transparent;"
        )
        self.name_label.setGeometry(0, DISPLAY_SIZE, DISPLAY_SIZE + 32, 18)
        self.name_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )

        # Speech bubble
        self.bubble = QLabel("", self)
        self.bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bubble.setWordWrap(True)
        self.bubble.setMaximumWidth(200)
        self.bubble.setStyleSheet("""
            background: rgba(10, 10, 30, 210);
            color: #f0f0ff;
            border: 1px solid rgba(125, 211, 252, 0.25);
            border-radius: 10px;
            padding: 6px 12px;
            font-size: 11px;
            font-weight: 500;
        """)
        self.bubble.hide()
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self._hide_bubble)

        # ZZZ floater (sleep state)
        self._zzz_label = QLabel("z", self)
        self._zzz_label.setStyleSheet(
            f"color: {self.ZZZ_COLOR}; font-size: 16px; font-weight: bold; "
            f"background: transparent;"
        )
        self._zzz_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._zzz_label.hide()

        # Heart floater (love state)
        self._heart_label = QLabel("♥", self)
        self._heart_label.setStyleSheet(
            f"color: {self.HEART_FILL}; font-size: 14px; font-weight: bold; "
            f"background: transparent;"
        )
        self._heart_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._heart_label.hide()

    # ── Fade animations ──────────────────────────────────────────
    def show(self):
        if self._fade_anim and self._fade_anim.state() == QPropertyAnimation.State.Running:
            self._fade_anim.stop()
        self.setWindowOpacity(0)
        super().show()
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(self.FADE_DURATION)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.setStartValue(0)
        self._fade_anim.setEndValue(1)
        self._fade_anim.start()

    def hide(self):
        if not self.isVisible():
            return
        if self._fade_anim and self._fade_anim.state() == QPropertyAnimation.State.Running:
            self._fade_anim.stop()
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(self.FADE_DURATION)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.setStartValue(1)
        self._fade_anim.setEndValue(0)
        self._fade_anim.finished.connect(super().hide)
        self._fade_anim.start()

    # ── Animation loop ───────────────────────────────────────────
    def _start_animation(self):
        # 单一定时器驱动所有状态更新（呼吸、ZZZ、心、行走）。
        # 但只有真正需要变动的状态才会 setPixmap / 移动控件。
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_tick)
        self._anim_timer.start(self.ANIM_INTERVAL)

        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._random_state_change)
        self._reschedule_state_change()

    def _reschedule_state_change(self):
        ms = random.randint(self.STATE_COOLDOWN_MIN, self.STATE_COOLDOWN_MAX)
        self._state_timer.stop()
        self._state_timer.start(ms)

    def _on_tick(self):
        # Walk: 物理位移 + 翻面
        if self.state == "walk":
            x = self.x() + self.direction * 3
            screen_w = self.screen().availableGeometry().width()
            if x <= 0 or x >= screen_w - self.width():
                self.direction *= -1
            self.move(x, self.y())
            self._walk_timer += 1
            if self._walk_timer > self.WALK_DURATION_FRAMES:
                self._set_state_safely("idle")
                return
            self.frame_idx += 1
        # happy / love 也需要推进帧
        elif self.state in ("happy", "love"):
            self.frame_idx += 1

        # 核心：调 _draw_current_frame,内部去重(单帧状态不重绘)
        self._draw_current_frame()

        # 浮动元素
        self._update_zzz()
        self._update_hearts()

    def _draw_current_frame(self, force: bool = False):
        """Set sprite pixmap. Skips the call when the frame index didn't change
        AND the state uses a single frame — that's the anti-flicker rule.
        """
        frames = self._frames.get(self.state, self._frames.get("idle", []))
        if not frames:
            return
        idx = self.frame_idx % len(frames)

        # 单帧状态 + 帧没变 → 跳过 setPixmap(防闪烁)
        if not force and len(frames) == 1 and idx == self._last_drawn_frame_idx:
            return
        self._last_drawn_frame_idx = idx

        frame = frames[idx]
        # 行走向左时镜像
        pix = frame
        if self.state == "walk" and self.direction == -1:
            pix = frame.transformed(
                QTransform().scale(-1, 1),
                Qt.TransformationMode.SmoothTransformation,
            )
        self.sprite_label.setPixmap(pix)

    def _update_zzz(self):
        if self.state != "sleep":
            if self._zzz_label.isVisible():
                self._zzz_label.hide()
            return
        # 慢节奏浮动,3 段循环
        self._zzz_phase = (self._zzz_phase + 0.05) % 3.0
        if not self._zzz_label.isVisible():
            self._zzz_label.show()
        p = self._zzz_phase
        rise = int(p * 8) % 28
        size = 12 + (int(p) % 3) * 4
        char = "z" if int(p) % 3 < 2 else "Z"
        x = DISPLAY_SIZE - 4 + int(p * 2) % 4
        y = 2 + rise
        self._zzz_label.setText(char)
        self._zzz_label.setStyleSheet(
            f"color: {self.ZZZ_COLOR}; font-size: {size}px; font-weight: bold; "
            f"background: transparent;"
        )
        self._zzz_label.adjustSize()
        self._zzz_label.move(16 + x, y)
        op = max(0.0, 1.0 - rise / 28.0)
        self._zzz_label.setWindowOpacity(op)

    def _update_hearts(self):
        if self.state != "love":
            if self._heart_label.isVisible():
                self._heart_label.hide()
            return
        self._heart_phase = (self._heart_phase + 0.10) % (2 * math.pi)
        if not self._heart_label.isVisible():
            self._heart_label.show()
        t = (math.sin(self._heart_phase) + 1) / 2
        size = 12 + int(t * 6)
        x = 16 + DISPLAY_SIZE // 2 + int(t * 18) - 6
        y = 4 - int(t * 8)
        self._heart_label.setText("♥")
        self._heart_label.setStyleSheet(
            f"color: {self.HEART_FILL}; font-size: {size}px; font-weight: bold; "
            f"background: transparent;"
        )
        self._heart_label.adjustSize()
        self._heart_label.move(x, y)
        self._heart_label.setWindowOpacity(0.4 + 0.6 * t)

    def _set_state_safely(self, new_state: str):
        if new_state not in self._frames:
            return
        self.state = new_state
        # 切换状态时重置 frame_idx,触发首次重绘
        self.frame_idx = 0
        self._last_drawn_frame_idx = -1
        self._walk_timer = 0
        if new_state == "walk":
            self.direction = random.choice([-1, 1])
        if new_state != "sleep" and self._zzz_label.isVisible():
            self._zzz_label.hide()
        if new_state != "love" and self._heart_label.isVisible():
            self._heart_label.hide()
        # 立刻绘制一次,保证状态切换瞬间新帧已显示
        self._draw_current_frame(force=True)
        self._reschedule_state_change()

    def _random_state_change(self):
        if self.state == "walk":
            states = ["idle", "idle", "idle", "walk"]
        elif self.state == "sleep":
            states = ["idle", "sleep", "sleep", "idle"]
        elif self.state == "love":
            states = ["idle", "idle", "love", "idle"]
        elif self.state == "happy":
            # 强烈倾向回到 idle: 80% idle → 只有 20% 继续挥手
            states = ["idle", "idle", "idle", "idle", "idle",
                      "happy", "happy", "walk", "love", "sleep"]
        elif self.state == "thinking":
            states = ["idle", "idle", "thinking", "idle", "walk"]
        elif self.state == "error":
            states = ["idle", "idle", "error", "idle"]
        else:
            states = [
                "idle", "idle", "idle", "idle",
                "walk", "sleep", "love", "happy",
            ]
        self._set_state_safely(random.choice(states))

    # ── Public API ───────────────────────────────────────────────
    def say(self, text: str, duration: int = 3000):
        self.bubble.setText(text)
        self.bubble.adjustSize()
        bx = (self.width() - self.bubble.width()) // 2
        self.bubble.move(bx, -self.bubble.height() - 4)
        self.bubble.show()
        self._bubble_timer.start(duration)

    def _hide_bubble(self):
        if self.bubble.isVisible():
            self.bubble.hide()

    def set_state(self, state: str):
        self._set_state_safely(state)

    # ── Drag with spring physics ─────────────────────────────────
    def _animate_position_to(self, target: QPoint):
        if self._position_anim and self._position_anim.state() == QPropertyAnimation.State.Running:
            self._position_anim.stop()
        self._position_anim = QPropertyAnimation(self, b"pos")
        self._position_anim.setDuration(self.DRAG_SPRING_MS)
        self._position_anim.setEasingCurve(QEasingCurve.OutBack)
        self._position_anim.setStartValue(self.pos())
        self._position_anim.setEndValue(target)
        self._position_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_pos = event.globalPosition().toPoint()
            self._dragging = False
            if self._position_anim and self._position_anim.state() == QPropertyAnimation.State.Running:
                self._position_anim.stop()

    def mouseMoveEvent(self, event):
        if hasattr(self, "_drag_pos") and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            self._dragging = True

    def mouseReleaseEvent(self, event):
        if hasattr(self, "_press_pos") and self._dragging:
            screen = self.screen().availableGeometry()
            cur = self.pos()
            x = max(screen.x(), min(cur.x(), screen.x() + screen.width() - self.width()))
            y = max(screen.y(), min(cur.y(), screen.y() + screen.height() - self.height()))
            if (x, y) != (cur.x(), cur.y()):
                self._animate_position_to(QPoint(x, y))
            self._dragging = False

    def mouseDoubleClickEvent(self, event):
        if self.on_double_click:
            self.on_double_click()
