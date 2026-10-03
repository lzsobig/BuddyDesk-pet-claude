"""Desktop pet with timed sprite clips and pointer interactions."""
import math
import os
import random
import time

from PySide6.QtWidgets import QApplication, QWidget, QLabel
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, Signal, QEvent
from PySide6.QtGui import QPixmap, QPainter, QColor, QTransform, QPainterPath, QRegion

from theme import TEXT_MUTED, ACCENT


# Path to the user-provided chubby-orange-cat asset pack.
# Falls back to the local assets/ if the original isn't reachable
# (e.g. a teammate runs the app from a different machine).
from config import ASSETS_DIR as _ASSETS
ASSET_DIR_CANDIDATES = [
    os.path.join(_ASSETS, "cat_frames_v2"),
    os.path.join(_ASSETS, "pet_frames"),
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
    "sad":      ["frame_40.png", "frame_41.png"],  # 垂头丧气（fail 帧）
    "think":    ["frame_32.png", "frame_33.png", "frame_34.png", "frame_35.png"],  # 蹦跳思考（jump 帧）
}


class PixelPet(QWidget):
    """Desktop pet using the chubby-orange-cat sprite pack."""

    FADE_DURATION = 180          # ms
    ANIM_FPS = 30
    ANIM_INTERVAL = 1000 // ANIM_FPS
    STATE_COOLDOWN_MIN = 8000    # 8s
    STATE_COOLDOWN_MAX = 15000   # 15s
    WALK_DURATION_FRAMES = 50    # ~5s at 10 FPS
    DRAG_SPRING_MS = 200

    # P2-2: 拖文件时"吞下"动画时长
    EAT_ANIM_MS = 600

    # ZZZ / heart colors
    ZZZ_COLOR = "#7B8CDE"
    HEART_FILL = "#FF6B8A"

    def __init__(self, on_double_click=None, parent=None, settings=None):
        super().__init__(parent)
        self._settings = dict(settings or {})
        self.on_double_click = on_double_click
        self.pet_name = str(self._settings.get("pet_name", "小橘"))
        self.state = "idle"
        self.frame_idx = 0
        self.direction = 1
        self._walk_timer = 0
        self._dragging = False
        self._activity_state = "idle"
        self._interaction_until = 0.0
        self._activity_until = 0.0
        self._last_interaction = time.monotonic()
        self._hover_point = None
        self._stroke_distance = 0
        self._frame_elapsed = 0.0
        self._last_tick = time.monotonic()
        self._frame_durations = {}
        self._fade_anim = None
        self._position_anim = None
        self._zzz_phase = 0.0
        self._heart_phase = 0.0
        self._last_drawn_frame_idx = -1   # 防闪烁：仅在帧索引变化时 setPixmap
        # P2-2: 拖文件"吞下"动画状态
        self._eat_anim: QPropertyAnimation | None = None

        self._asset_dir = _resolve_asset_dir()
        self._frames: dict[str, list[QPixmap]] = {}
        self._load_sprites()
        self._setup_ui()
        self._start_animation()
        # 立刻绘制第一帧,避免显示空白
        self._draw_current_frame(force=True)

        # P2-2: 接受文件拖入
        self.setAcceptDrops(True)

    # P2-2: 文件拖入 → 吞下动画 → 转发给 chat_window
    file_dropped = Signal(list)  # list[str] 绝对路径
    # P3-5: 桌宠嗅到桌面图标后请求 AI 短评
    sniff_requested = Signal(str)  # icon name
    position_changed = Signal(int, int, str)
    settings_requested = Signal()
    hide_requested = Signal()

    def contextMenuEvent(self, event):
        """P3-5: 右键菜单：嗅桌面图标。"""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        try:
            import desktop_icon_reader
            icons = desktop_icon_reader.get_desktop_shortcuts()
        except Exception:
            icons = []
        menu = QMenu(self)
        menu.addAction("宠物设置", self.settings_requested.emit)
        menu.addAction("回到右下角", lambda: self.reset_position(save=True))
        menu.addAction("隐藏桌面宠物", self.hide_requested.emit)
        menu.addSeparator()
        if icons:
            sniff_menu = menu.addMenu("👃 嗅桌面图标")
            for icon in icons[:20]:  # 最多 20 个
                act = QAction(icon["name"], self)
                act.triggered.connect(lambda _=False, n=icon["name"]: self.sniff_requested.emit(n))
                sniff_menu.addAction(act)
            if len(icons) > 20:
                sniff_menu.addSeparator()
                more = QAction(f"…还有 {len(icons) - 20} 个", self)
                more.setEnabled(False)
                sniff_menu.addAction(more)
            menu.addSeparator()
        # 已有"切到..."状态选项
        for st in ("idle", "happy", "thinking", "love", "sleep"):
            act = QAction(f"切到 {st}", self)
            act.triggered.connect(lambda _=False, s=st: self._set_state_safely(s))
            menu.addAction(act)
        menu.exec(event.globalPos())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.toLocalFile() and os.path.exists(u.toLocalFile())]
        if not paths:
            return
        event.acceptProposedAction()
        # 吞下动画 + emit
        self._play_eat_anim()
        # 过滤敏感词
        from ui.drag_drop_util import filter_sensitive_filepaths
        kept, filtered = filter_sensitive_filepaths(paths)
        for fp in filtered:
            self.say(f"跳过敏感文件\n{os.path.basename(fp)}", 2000)
        if kept:
            self.say("收到啦，选一下怎么处理", 1800)
            self.file_dropped.emit(kept)

    def _play_eat_anim(self):
        """P2-2: 吞下动画 —— 0.6s 缩放 0.7→1.15→1.0 + 切到 happy 状态。"""
        if self._eat_anim and self._eat_anim.state() == QPropertyAnimation.State.Running:
            self._eat_anim.stop()
        # 暂切到 happy 状态
        prev_state = self.state
        self._set_state_safely("happy")
        # 缩放动画
        from PySide6.QtCore import QRect
        original_geo = self.geometry()
        shrunk = QRect(
            original_geo.x() + int(original_geo.width() * 0.15),
            original_geo.y() + int(original_geo.height() * 0.15),
            int(original_geo.width() * 0.7),
            int(original_geo.height() * 0.7),
        )
        grown = QRect(
            original_geo.x() - int(original_geo.width() * 0.075),
            original_geo.y() - int(original_geo.height() * 0.075),
            int(original_geo.width() * 1.15),
            int(original_geo.height() * 1.15),
        )
        self._eat_anim = QPropertyAnimation(self, b"geometry")
        self._eat_anim.setDuration(self.EAT_ANIM_MS)
        self._eat_anim.setKeyValueAt(0.0, original_geo)
        self._eat_anim.setKeyValueAt(0.4, grown)
        self._eat_anim.setKeyValueAt(1.0, original_geo)
        self._eat_anim.finished.connect(lambda: self._set_state_safely(prev_state))
        self._eat_anim.start()

    # ── Sprite loading ──────────────────────────────────────────
    def _load_pixmap(self, filename: str) -> QPixmap | None:
        if not self._asset_dir and not os.path.isabs(filename):
            return None
        path = filename if os.path.isabs(filename) else os.path.join(self._asset_dir, filename)
        if not os.path.exists(path):
            return None
        pm = QPixmap(path)
        if pm.isNull():
            return None
        ratio = self.devicePixelRatioF()
        result = pm.scaled(
            round(DISPLAY_SIZE * ratio), round(DISPLAY_SIZE * ratio),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        result.setDevicePixelRatio(ratio)
        return result

    def _load_sprites(self):
        from pet_library import resolve_pet, load_animation
        pet = resolve_pet(str(self._settings.get("pet_id", "orange")))
        clips = load_animation(pet["id"])
        self._frame_durations.clear()
        for state, files in STATE_FRAMES.items():
            custom = pet["thinking" if state in ("thinking", "think") else "idle"]
            if pet["id"] != "pixel-cat" and os.path.isfile(custom):
                files = [custom]
            pixs: list[QPixmap] = []
            for f in files:
                pm = self._load_pixmap(f)
                if pm is not None:
                    pixs.append(pm)
            if not pixs:
                pixs = self._frames.get("idle", [])[:]
            self._frames[state] = pixs
        for state in ("petting", "drag"):
            self._frames[state] = self._frames.get("love" if state == "petting" else "thinking", [])
        for state, clip in clips.items():
            pixmaps = [self._load_pixmap(path) for path in clip["frames"]]
            if pixmaps and all(pixmap is not None for pixmap in pixmaps):
                self._frames[state] = pixmaps
                self._frame_durations[state] = clip["durations"]
        if clips:
            for state in self._frames:
                if state not in clips:
                    source = "petting" if state in ("happy", "love") and "petting" in clips else "idle"
                    if state == "drag" and "thinking" in clips:
                        source = "thinking"
                    self._frames[state] = self._frames[source]
                    self._frame_durations[state] = self._frame_durations.get(source, [100] * len(self._frames[source]))
        for alias, source in (("think", "thinking"), ("sad", "error"), ("love", "petting")):
            self._frames[alias] = self._frames[source]
            if source in self._frame_durations:
                self._frame_durations[alias] = self._frame_durations[source]
        for state, source in (("listening", "idle"), ("reminding", "petting")):
            self._frames[state] = self._frames[source]
            self._frame_durations[state] = self._frame_durations.get(source, [140] * len(self._frames[source]))

    # ── UI setup ─────────────────────────────────────────────────
    def _setup_ui(self):
        w = DISPLAY_SIZE + 32
        h = DISPLAY_SIZE + 36
        self.setFixedSize(w, h)
        self.setWindowTitle(f"桌面宠物 · {self.pet_name}")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowOpacity(1)
        self.setObjectName("desktopPet")
        self.setStyleSheet("QWidget#desktopPet { background:transparent; }")
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        # Position at bottom-right
        self.restore_position()

        # Sprite label — centered horizontally
        self.sprite_label = QLabel(self)
        self.sprite_label.setStyleSheet("background:transparent;")
        self.sprite_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sprite_label.setGeometry(16, 0, DISPLAY_SIZE, DISPLAY_SIZE)
        self.sprite_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )

        # Name label
        self.name_label = QLabel(self.pet_name, self)
        self.name_label.setTextFormat(Qt.TextFormat.PlainText)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet(
            "QLabel {color:#4f5967;font-size:10px;background:rgba(255,255,255,225);"
            "border-radius:8px;padding:1px 6px;}"
        )
        self.name_label.setGeometry(12, DISPLAY_SIZE + 2, DISPLAY_SIZE + 8, 20)
        self.name_label.hide()
        self.name_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )

        # Speech bubble
        self.bubble = QLabel("", self)
        self.bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bubble.setWordWrap(True)
        self.bubble.setMaximumWidth(w - 8)
        self.bubble.setTextFormat(Qt.TextFormat.PlainText)
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
        self._last_tick = time.monotonic()
        if hasattr(self, "_anim_timer"):
            self._anim_timer.start(self.ANIM_INTERVAL)
            self._reschedule_state_change()
        if self._fade_anim and self._fade_anim.state() == QPropertyAnimation.State.Running:
            self._fade_anim.stop()
        self.setWindowOpacity(0)
        super().show()
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(self.FADE_DURATION)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.setStartValue(0)
        self._fade_anim.setEndValue(1)
        animation = self._fade_anim
        QTimer.singleShot(0, lambda: animation.start() if self._fade_anim is animation else None)

    def hide(self):
        self._dragging = False
        self._interaction_until = 0.0
        if self.state in ("drag", "petting"):
            self._set_state_safely(self._activity_state)
        if hasattr(self, "_drag_pos"):
            del self._drag_pos
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if hasattr(self, "_anim_timer"):
            self._anim_timer.stop()
            self._state_timer.stop()
        if not self.isVisible():
            return
        if self._fade_anim and self._fade_anim.state() == QPropertyAnimation.State.Running:
            self._fade_anim.stop()
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(self.FADE_DURATION)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.setStartValue(self.windowOpacity())
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

    # P3-1: 桌宠获取灵动岛几何（main.py 注入）
    island_provider = None  # callable returning (x, y, w, h) or None

    # P3-2: 跨岛传送冷却（防止两边反复闪）
    _TELEPORT_COOLDOWN_FRAMES = 90  # ~3 秒 @ 30 FPS walk
    _teleport_cd = 0

    def _on_tick(self):
        if not self.isVisible():
            return
        now = time.monotonic()
        elapsed = min(100.0, (now - self._last_tick) * 1000)
        self._last_tick = now
        if self._activity_until and now >= self._activity_until:
            self._activity_until = 0.0
            self._activity_state = "idle"
            if not self._dragging and not self._interaction_until:
                self._set_state_safely("idle")
        if self._interaction_until and now >= self._interaction_until and not self._dragging:
            self._interaction_until = 0.0
            self._set_state_safely(self._activity_state)
        self._frame_elapsed += elapsed
        frames = self._frames.get(self.state, [])
        durations = self._frame_durations.get(self.state, [100] * len(frames))
        while durations and self._frame_elapsed >= durations[self.frame_idx % len(durations)]:
            self._frame_elapsed -= durations[self.frame_idx % len(durations)]
            self.frame_idx = (self.frame_idx + 1) % len(frames)
        # Walk: 物理位移 + 翻面 + 避让灵动岛
        if self.state == "walk" and not self._dragging:
            if self._teleport_cd > 0:
                self._teleport_cd -= 1
            step = max(1, round(elapsed * 0.03))
            x = self.x() + self.direction * step
            s = self.screen()
            area = s.availableGeometry() if s else None
            screen_left = area.left() if area else 0
            screen_w = area.right() + 1 if area else 1920
            # P3-1: 撞到屏幕边反向
            if x <= screen_left or x >= screen_w - self.width():
                self.direction *= -1
                x = self.x() + self.direction * step
            # P3-1 + P3-2: 撞到灵动岛避让带
            teleported = False
            if PixelPet.island_provider and self._teleport_cd == 0:
                try:
                    ig = PixelPet.island_provider()
                    if ig:
                        ix, iy, iw, ih = ig
                        # 避让带：岛左右各扩 30px
                        avoid_left = ix - 30
                        avoid_right = ix + iw + 30
                        if avoid_left <= x + self.width() and x <= avoid_right:
                            # P3-2: 尝试跨岛传送（如果屏幕另一侧有空间）
                            target_x = self._teleport_to_other_side(ix, iw, screen_w)
                            if target_x is not None:
                                self._teleport_to(target_x)
                                teleported = True
                                self._teleport_cd = self._TELEPORT_COOLDOWN_FRAMES
                            else:
                                # 没空间 → 普通反向
                                self.direction *= -1
                                x = self.x() + self.direction * 3
                except Exception:
                    pass
            if not teleported:
                self.move(x, self.y())
            self._walk_timer += elapsed / 100
            if self._walk_timer > self.WALK_DURATION_FRAMES:
                self._set_state_safely("idle")
                return

        self._draw_current_frame()
        self._update_zzz()
        self._update_hearts()

    def _teleport_to_other_side(self, ix: int, iw: int, screen_w: int) -> int | None:
        """P3-2: 计算岛另一侧的 x 坐标。如果没空间返回 None。"""
        pet_w = self.width()
        # 左侧空隙
        left_space = ix - 30  # 岛左 30px 内不允许
        if left_space > pet_w:
            # 有空间 → 出现在岛左侧
            return max(0, left_space - pet_w - 10)
        # 右侧空隙
        right_space_start = ix + iw + 30
        if screen_w - right_space_start > pet_w:
            return right_space_start + 10
        return None

    def _teleport_to(self, target_x: int) -> None:
        """P3-2: 0.6s 传送动画：fade out → 瞬移 → fade in。"""
        if self._fade_anim and self._fade_anim.state() == QPropertyAnimation.State.Running:
            return
        # fade out
        a_out = QPropertyAnimation(self, b"windowOpacity")
        a_out.setDuration(180)
        a_out.setStartValue(1.0)
        a_out.setEndValue(0.0)

        from PySide6.QtCore import QPoint as _QP
        def _on_fade_out():
            self.move(target_x, self.y())
            # fade in
            a_in = QPropertyAnimation(self, b"windowOpacity")
            a_in.setDuration(180)
            a_in.setStartValue(0.0)
            a_in.setEndValue(1.0)
            a_in.start()
            self._fade_anim = a_in

        a_out.finished.connect(_on_fade_out)
        a_out.start()
        self._fade_anim = a_out

    def _draw_current_frame(self, force: bool = False):
        """Set sprite pixmap. Skips the call when the frame index didn't change
        AND the state uses a single frame — that's the anti-flicker rule.
        """
        frames = self._frames.get(self.state, self._frames.get("idle", []))
        if not frames:
            return
        idx = self.frame_idx % len(frames)

        # 单帧状态 + 帧没变 → 跳过 setPixmap(防闪烁)
        drawn_key = (self.state, idx, self.direction if self.state == "walk" else 1)
        if not force and drawn_key == self._last_drawn_frame_idx:
            return
        self._last_drawn_frame_idx = drawn_key

        frame = frames[idx]
        # 行走向左时镜像 — cache mirrored frames to avoid per-tick transformation
        pix = frame
        if self.state == "walk" and self.direction == -1:
            cache_key = ("walk_mirror", idx)
            if not hasattr(self, '_mirror_cache'):
                self._mirror_cache = {}
            if cache_key not in self._mirror_cache:
                self._mirror_cache[cache_key] = frame.transformed(
                    QTransform().scale(-1, 1),
                    Qt.TransformationMode.SmoothTransformation,
                )
            pix = self._mirror_cache[cache_key]
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
        # Use rgba color for fade instead of setWindowOpacity (no-op on child widgets)
        alpha = int(max(0, min(255, (1.0 - rise / 28.0) * 255)))
        r, g, b = 180, 180, 220  # ZZZ_COLOR rgb approximation
        self._zzz_label.setStyleSheet(
            f"color: rgba({r},{g},{b},{alpha}); font-size: {size}px; font-weight: bold; "
            f"background: transparent;"
        )
        self._zzz_label.adjustSize()
        self._zzz_label.move(16 + x, y)

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
        # Use rgba color for opacity instead of setWindowOpacity (no-op on child widgets)
        alpha = int((0.4 + 0.6 * t) * 255)
        self._heart_label.setStyleSheet(
            f"color: rgba(255,100,120,{alpha}); font-size: {size}px; font-weight: bold; "
            f"background: transparent;"
        )
        self._heart_label.adjustSize()
        self._heart_label.move(x, y)

    def _set_state_safely(self, new_state: str):
        if new_state not in self._frames:
            return
        self.state = new_state
        # 切换状态时重置 frame_idx,触发首次重绘
        self.frame_idx = 0
        self._frame_elapsed = 0.0
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
        self._refresh_caption()
        self._reschedule_state_change()

    def _random_state_change(self):
        if not self.isVisible() or self._dragging or self._interaction_until or self._activity_state != "idle":
            return
        quiet = time.monotonic() - self._last_interaction
        states = ["idle", "idle", "idle"]
        if quiet > 60:
            states.append("sleep")
        if self._settings.get("pet_roam", False) and not self.underMouse():
            states.append("walk")
        self._set_state_safely(random.choice(states))

    # ── Public API ───────────────────────────────────────────────
    def say(self, text: str, duration: int = 3000):
        self.bubble.setText(text)
        self.bubble.adjustSize()
        bx = (self.width() - self.bubble.width()) // 2
        self.bubble.move(bx, max(0, self.height() - self.bubble.height() - 2))
        self.bubble.raise_()
        self.bubble.show()
        self._bubble_timer.start(duration)

    def _hide_bubble(self):
        if self.bubble.isVisible():
            self.bubble.hide()

    def set_state(self, state: str):
        state = {"think": "thinking", "sad": "error"}.get(state, state)
        if state not in self._frames:
            return
        self._activity_state = state
        self._activity_until = time.monotonic() + 3.0 if state in ("happy", "error") else 0.0
        if not self._dragging:
            self._interaction_until = 0.0
            self._set_state_safely(state)

    def _refresh_caption(self):
        captions = {"thinking": "正在琢磨…", "think": "正在琢磨…", "petting": "好舒服", "drag": "轻轻放下我", "error": "遇到一点问题", "listening": "我在听", "reminding": "轻轻提醒你"}
        self.name_label.setText(captions.get(self.state, self.pet_name))
        self.name_label.setVisible(self.underMouse() or self.state in captions)

    def _pet(self):
        self._last_interaction = time.monotonic()
        if self._activity_state in ("thinking", "listening", "reminding", "error") or self._dragging:
            return
        self._interaction_until = self._last_interaction + 2.4
        if self.state != "petting":
            self._set_state_safely("petting")

    def enterEvent(self, event):
        self._hover_point = None
        self._stroke_distance = 0
        self._last_interaction = time.monotonic()
        if self.state == "sleep" or self.state == "walk":
            if self._activity_state in ("sleep", "walk"):
                self._activity_state = "idle"
            self._set_state_safely(self._activity_state)
        self._refresh_caption()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_point = None
        self._stroke_distance = 0
        self._refresh_caption()
        super().leaveEvent(event)

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
            self._last_interaction = time.monotonic()
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_pos = event.globalPosition().toPoint()
            self._dragging = False
            if self._position_anim and self._position_anim.state() == QPropertyAnimation.State.Running:
                self._position_anim.stop()

    def mouseMoveEvent(self, event):
        if hasattr(self, "_drag_pos") and event.buttons() & Qt.MouseButton.LeftButton:
            if not self._dragging and (event.globalPosition().toPoint() - self._press_pos).manhattanLength() < QApplication.startDragDistance():
                return
            if not self._dragging:
                self._dragging = True
                self._interaction_until = 0.0
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self._set_state_safely("drag")
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        elif event.buttons() == Qt.MouseButton.NoButton:
            point = event.position().toPoint()
            if self._hover_point is not None and self.sprite_label.geometry().contains(point):
                self._stroke_distance += (point - self._hover_point).manhattanLength()
                if self._stroke_distance >= 24:
                    self._stroke_distance = 0
                    self._pet()
            self._hover_point = point

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if hasattr(self, "_press_pos") and self._dragging:
            screen = self.screen().availableGeometry()
            cur = self.pos()
            x = max(screen.x(), min(cur.x(), screen.x() + screen.width() - self.width()))
            y = max(screen.y(), min(cur.y(), screen.y() + screen.height() - self.height()))
            if (x, y) != (cur.x(), cur.y()):
                self._animate_position_to(QPoint(x, y))
            self._dragging = False
            position = {"x": x, "y": y, "screen": self.screen().name()}
            self._settings["pet_position"] = position
            self.position_changed.emit(x, y, position["screen"])
            self._set_state_safely(self._activity_state)
        else:
            self._pet()
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if hasattr(self, "_drag_pos"):
            del self._drag_pos

    def reset_position(self, save=False):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.right() - self.width() - 19, geo.bottom() - self.height() - 19)
        self._settings["pet_position"] = None
        if save:
            self.position_changed.emit(self.x(), self.y(), screen.name())

    def restore_position(self):
        position = self._settings.get("pet_position")
        if isinstance(position, dict) and type(position.get("x")) is int and type(position.get("y")) is int:
            screen = next((screen for screen in QApplication.screens()
                           if screen.name() == position.get("screen")), None)
            if screen:
                area = screen.availableGeometry()
                x = max(area.left(), min(position["x"], area.right() - self.width() + 1))
                y = max(area.top(), min(position["y"], area.bottom() - self.height() + 1))
                self.move(x, y)
                return
        self.reset_position()

    def apply_settings(self, settings):
        previous_position = self._settings.get("pet_position")
        self._settings = dict(settings)
        self.pet_name = str(settings.get("pet_name", "小橘"))
        self.setWindowTitle(f"桌面宠物 · {self.pet_name}")
        self.name_label.setText(self.pet_name)
        self._frames.clear()
        self._mirror_cache = {}
        self._load_sprites()
        self._last_drawn_frame_idx = -1
        self._draw_current_frame(force=True)
        if not settings.get("pet_roam", False):
            if self._activity_state == "walk":
                self._activity_state = "idle"
            if self.state == "walk":
                self._set_state_safely(self._activity_state)
        if previous_position != settings.get("pet_position") or settings.get("pet_position") is None:
            self.restore_position()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.on_double_click:
            self.on_double_click()

    def event(self, event):
        result = super().event(event)
        if event.type() == QEvent.Type.DevicePixelRatioChange and hasattr(self, "sprite_label"):
            self._frames.clear()
            self._mirror_cache = {}
            self._load_sprites()
            self._last_drawn_frame_idx = -1
            self._draw_current_frame(force=True)
        return result
