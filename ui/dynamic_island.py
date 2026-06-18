"""
Dynamic Island — All-Paint architecture.

Every state is drawn in paintEvent. Zero child widgets, zero layouts.
Single QTimer drives all animations. QPainterPath clips for smooth
rounded corners (no jagged edges).
"""
import math, random

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QDateTime
from PySide6.QtCore import QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, Property
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QRadialGradient, QPainterPath, QFont, QFontMetrics,
)
from PySide6.QtWidgets import QWidget

from theme import (
    WHITE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT, GREEN, GREEN_SOFT, GOLD, GOLD_SOFT, RED, RED_SOFT,
)

# ── Config ───────────────────────────────────────────────────────────
DIMS = {
    "idle": (200, 38), "thinking": (340, 52), "result": (320, 52),
    "notify": (280, 52), "error": (300, 52),
}
ANIM_MS = 400
AUTO_MS = 3500
AUTO_ERR_MS = 5000
MIN_THINK_MS = 800
DRAG_TH = 6
COMPANION = [
    "陪着你呢~", "早呀~", "辛苦啦", "摸鱼时间到~",
    "加油！", "休息一下吧~", "今天也要开心哦",
    "有什么需要帮忙的？", "在呢在呢~", "喵~", "想你了~",
]


class DynamicIsland(QWidget):

    def __init__(self, on_click=None, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self._state = "idle"
        self._prev_state = "idle"
        self._drag_pos = self._press_pos = None
        self._dragging = False
        self._ready = False

        self._w = float(DIMS["idle"][0])
        self._h = float(DIMS["idle"][1])

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(*DIMS["idle"])

        # Animation state
        self._phase = 0.0          # master tick counter
        self._thinking_ms = 0
        self._pending = None       # (state, text) deferred
        self._detail = ""          # dynamic sub-text for result/notify/error
        self._idle_label = None    # hover text override for idle
        self._state_start = 0.0    # _phase when current state started

        # Timers — start at slow rate (idle state default)
        self._tick_tmr = QTimer(self, timeout=self._tick); self._tick_tmr.start(200)
        self._auto = QTimer(self, singleShot=True, timeout=self._auto_col)
        self._pending_tmr = QTimer(self, singleShot=True, timeout=self._flush)

        self._build_anims()

        # Fonts
        self._f_label = QFont("Inter, Noto Sans SC, Segoe UI, sans-serif")
        self._f_label.setPixelSize(12); self._f_label.setWeight(QFont.Weight.DemiBold)
        self._f_sub = QFont("Inter, Noto Sans SC, Segoe UI, sans-serif")
        self._f_sub.setPixelSize(10); self._f_sub.setWeight(QFont.Weight.Normal)
        self._f_pill = QFont("Inter, Noto Sans SC, Segoe UI, sans-serif")
        self._f_pill.setPixelSize(10); self._f_pill.setWeight(QFont.Weight.DemiBold)
        self._f_emoji = QFont("Segoe UI Emoji, Apple Color Emoji, sans-serif")
        self._f_emoji.setPixelSize(15)
        self._f_idle = QFont("Inter, Noto Sans SC, Segoe UI, sans-serif")
        self._f_idle.setPixelSize(12); self._f_idle.setWeight(QFont.Weight.Medium)

        QTimer.singleShot(50, self._pos)
        QTimer.singleShot(200, lambda: setattr(self, '_ready', True))

    # ── Tick ─────────────────────────────────────────────────────────

    def _tick(self):
        self._phase += 0.069
        self.update()

    def _set_tick_rate(self, fast: bool = True):
        """Switch tick rate: 16ms (60fps) for active states, 200ms (5fps) for idle."""
        self._tick_tmr.setInterval(16 if fast else 200)

    # ── State machine ────────────────────────────────────────────────

    def set_state(self, state: str, text: str = ""):
        if state not in DIMS:
            state = "idle"
        self._auto.stop()
        self._pending_tmr.stop()
        self._pending = None

        # Enforce minimum thinking display
        if state in ("result", "notify", "error") and self._state == "thinking":
            now = QDateTime.currentMSecsSinceEpoch()
            remaining = MIN_THINK_MS - (now - self._thinking_ms)
            if remaining > 0:
                self._pending = (state, text)
                self._pending_tmr.start(int(remaining))
                return

        self._apply(state, text)

    def _flush(self):
        if self._pending:
            s, t = self._pending
            self._pending = None
            self._apply(s, t)

    def _apply(self, state: str, text: str = ""):
        self._prev_state = self._state
        self._state = state
        self._state_start = self._phase

        # Adjust tick rate: idle uses low fps to save CPU, active states use 60fps
        self._set_tick_rate(fast=(state != "idle"))

        if state == "thinking":
            self._thinking_ms = QDateTime.currentMSecsSinceEpoch()

        if state == "result":
            self._detail = text or "已完成"
        elif state == "notify":
            self._detail = text or "提醒"
        elif state == "error":
            self._detail = (text or "请稍后再试").strip()

        # Animate size
        tw, th = DIMS[state]
        cur_w, cur_h = float(self.width()), float(self.height())
        self._w = cur_w; self._h = cur_h
        if self._cg.state() == QParallelAnimationGroup.State.Running: self._cg.stop()
        if self._eg.state() == QParallelAnimationGroup.State.Running: self._eg.stop()
        gb = tw > cur_w + 5
        ag = self._eg if gb else self._cg
        ww = self._ew if ag is self._eg else self._cw
        hh = self._eh if ag is self._eg else self._ch
        ww.setStartValue(cur_w); ww.setEndValue(float(tw))
        hh.setStartValue(cur_h); hh.setEndValue(float(th))
        ag.start()

        if state in ("result", "notify"):
            self._auto.start(AUTO_MS)
        elif state == "error":
            self._auto.start(AUTO_ERR_MS)

    def _auto_col(self):
        if self._state in ("result", "notify", "error"):
            self.set_state("idle")

    # ── Animations ───────────────────────────────────────────────────

    def _build_anims(self):
        sp = QEasingCurve(QEasingCurve.Type.OutBack); sp.setOvershoot(1.20)
        ec = QEasingCurve(QEasingCurve.Type.OutCubic)
        self._ew = QPropertyAnimation(self, b"aw"); self._ew.setDuration(ANIM_MS); self._ew.setEasingCurve(sp)
        self._eh = QPropertyAnimation(self, b"ah"); self._eh.setDuration(ANIM_MS); self._eh.setEasingCurve(sp)
        self._eg = QParallelAnimationGroup(self); self._eg.addAnimation(self._ew); self._eg.addAnimation(self._eh)
        self._cw = QPropertyAnimation(self, b"aw"); self._cw.setDuration(ANIM_MS); self._cw.setEasingCurve(ec)
        self._ch = QPropertyAnimation(self, b"ah"); self._ch.setDuration(ANIM_MS); self._ch.setEasingCurve(ec)
        self._cg = QParallelAnimationGroup(self); self._cg.addAnimation(self._cw); self._cg.addAnimation(self._ch)

    def _get_aw(self): return self._w
    def _set_aw(self, v):
        self._w = v; ww = int(round(v))
        self.setFixedWidth(ww); self.setMinimumWidth(ww); self.setMaximumWidth(ww)
    aw = Property(float, _get_aw, _set_aw)

    def _get_ah(self): return self._h
    def _set_ah(self, v):
        self._h = v; hh = int(round(v))
        self.setFixedHeight(hh); self.setMinimumHeight(hh); self.setMaximumHeight(hh)
    ah = Property(float, _get_ah, _set_ah)

    def _pos(self):
        s = self.screen()
        if not s: return
        g = s.availableGeometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 28)

    # ── Paint ────────────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        w, h = float(self.width()), float(self.height())
        r = h / 2.0

        # ── Rounded-rect clip path (eliminates jagged edges) ──
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), r, r)
        p.setClipPath(clip)

        # ── Background ──
        p.setPen(Qt.PenStyle.NoPen)
        for i, a in enumerate((28, 18, 10)):
            p.setBrush(QColor(0, 0, 0, a))
            p.drawRoundedRect(QRectF(2, 2 + i * 2, w, h), r, r)
        p.setBrush(QColor(WHITE))
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # Highlight
        sg = QRadialGradient(w / 2, -h * 0.3, h * 1.6)
        sg.setColorAt(0, QColor(255, 255, 255, 200))
        sg.setColorAt(1, Qt.GlobalColor.transparent)
        p.setBrush(sg); p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # State glow
        glow_map = {
            "idle": QColor(92, 184, 154, 30), "thinking": QColor(92, 184, 154, 60),
            "result": QColor(74, 175, 136, 60), "notify": QColor(184, 166, 106, 60),
            "error": QColor(212, 122, 114, 60),
        }
        gc = glow_map.get(self._state)
        if gc:
            gg = QRadialGradient(w / 2, h / 2, w / 2)
            gg.setColorAt(0, gc); gg.setColorAt(1, Qt.GlobalColor.transparent)
            p.setBrush(gg); p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # ── Draw state content ──
        cx, cy = w / 2, h / 2
        if self._state == "idle":
            self._draw_idle(p, w, h, cx, cy)
        elif self._state == "thinking":
            self._draw_thinking(p, w, h, cx, cy)
        elif self._state == "result":
            self._draw_result(p, w, h, cx, cy)
        elif self._state == "notify":
            self._draw_notify(p, w, h, cx, cy)
        elif self._state == "error":
            self._draw_error(p, w, h, cx, cy)

        # Border (drawn AFTER clip so it's always smooth)
        p.setClipping(False)
        bc = QColor(BORDER) if self._state != "error" else QColor(RED)
        p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(bc, 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r, r)
        p.end()

    # ── Idle: dot + emoji + text ─────────────────────────────────────

    def _draw_idle(self, p, w, h, cx, cy):
        o = 0.5 + 0.5 * (1 + math.sin(self._phase)) / 2
        # Glow
        glow = QColor(ACCENT); glow.setAlphaF(o * 0.3)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(glow)
        p.drawEllipse(QPointF(cx - 50, cy), 6, 6)
        # Core dot
        core = QColor(ACCENT); core.setAlphaF(o)
        p.setBrush(core)
        p.drawEllipse(QPointF(cx - 50, cy), 3.5, 3.5)
        # Emoji
        p.setFont(self._f_emoji)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawText(QRectF(cx - 38, cy - 10, 22, 20), Qt.AlignmentFlag.AlignCenter, "🐱")
        # Text
        idle_text = self._idle_label if hasattr(self, '_idle_label') and self._idle_label else "小橘待命中"
        p.setFont(self._f_idle)
        p.setPen(QColor(TEXT_SECONDARY))
        p.drawText(QRectF(cx - 12, cy - 8, 100, 16), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, idle_text)

    # ── Thinking: ring + label + dots ────────────────────────────────

    def _draw_thinking(self, p, w, h, cx, cy):
        x0 = w / 2 - 150  # left padding

        # Spinning ring
        ring_cx, ring_cy = x0 + 14, cy
        ring_r = 12
        # Inner fill
        ig = QColor(ACCENT); ig.setAlphaF(0.10)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(ig)
        p.drawEllipse(QPointF(ring_cx, ring_cy), ring_r - 1, ring_r - 1)
        # Outer ring
        p.setPen(QPen(QColor(BORDER), 2.5)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(ring_cx, ring_cy), ring_r, ring_r)
        # Spinning arc
        arc_pen = QPen(QColor(ACCENT), 2.5); arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(arc_pen)
        angle = int(self._phase * 100) % 360
        p.drawArc(QRectF(ring_cx - ring_r, ring_cy - ring_r, ring_r * 2, ring_r * 2),
                  angle * 16, 120 * 16)

        # Labels
        tx = x0 + 36
        p.setFont(self._f_label); p.setPen(QColor(TEXT_PRIMARY))
        p.drawText(QRectF(tx, cy - 10, 180, 14), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "正在思考")
        p.setFont(self._f_sub); p.setPen(QColor(TEXT_MUTED))
        p.drawText(QRectF(tx, cy + 2, 180, 12), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "AI 正在处理你的请求…")

        # Bouncing dots
        dots_x = w - 50
        for i in range(3):
            s = max(0.0, math.sin(self._phase * 4 - i * 0.9))
            dot_o = 0.3 + 0.7 * s
            dot_y = cy - 3 * s
            c = QColor(ACCENT); c.setAlphaF(dot_o)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(c)
            p.drawEllipse(QPointF(dots_x + i * 9, dot_y), 2.5, 2.5)

    # ── Result: check + label + pill ─────────────────────────────────

    def _draw_result(self, p, w, h, cx, cy):
        x0 = w / 2 - 140
        t = min(1.0, (self._phase - self._state_start) * 3)  # ~0.33s entrance

        # Check circle with pop-in (scale 0→1 with overshoot)
        scale = min(1.0, t * 1.3)  # fast pop
        if t < 0.8:
            overshoot = 1.0 + 0.3 * math.sin(t * math.pi / 0.8)
            scale = min(1.0, t * overshoot * 1.2)
        else:
            scale = 1.0
        chk_cx, chk_cy = x0 + 14, cy
        chk_r = 13 * scale
        if chk_r > 0.5:
            ig = QColor("rgba(74,175,136,0.08)")
            p.setPen(QPen(QColor("rgba(74,175,136,0.2)"), 1.5)); p.setBrush(ig)
            p.drawEllipse(QPointF(chk_cx, chk_cy), chk_r, chk_r)
            # Checkmark stroke (draws in after circle pops)
            if t > 0.3:
                prog = min(1.0, (t - 0.3) / 0.4)
                cp = QPen(QColor(GREEN), 2.5); cp.setCapStyle(Qt.PenCapStyle.RoundCap)
                cp.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.setPen(cp); p.setBrush(Qt.BrushStyle.NoBrush)
                a_pt = QPointF(chk_cx - 5, chk_cy + 0.5)
                b_pt = QPointF(chk_cx - 1, chk_cy + 4.5)
                c_pt = QPointF(chk_cx + 6, chk_cy - 4.5)
                if prog < 0.5:
                    pr = prog / 0.5
                    p.drawLine(a_pt, QPointF(a_pt.x() + (b_pt.x() - a_pt.x()) * pr,
                                              a_pt.y() + (b_pt.y() - a_pt.y()) * pr))
                else:
                    pr = (prog - 0.5) / 0.5
                    p.drawLine(a_pt, b_pt)
                    p.drawLine(b_pt, QPointF(b_pt.x() + (c_pt.x() - b_pt.x()) * pr,
                                              b_pt.y() + (c_pt.y() - b_pt.y()) * pr))

        # Label with fade-in (slight delay)
        tx = x0 + 36
        label_o = max(0.0, min(1.0, (t - 0.15) * 3))
        if label_o > 0:
            p.setFont(self._f_label)
            c = QColor(TEXT_PRIMARY); c.setAlphaF(label_o)
            p.setPen(c)
            p.drawText(QRectF(tx, cy - 10, 160, 14), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "任务完成")
            detail = self._detail if self._detail else "已完成"
            if len(detail) > 18: detail = detail[:17] + "…"
            p.setFont(self._f_sub)
            c2 = QColor(TEXT_MUTED); c2.setAlphaF(label_o)
            p.setPen(c2)
            p.drawText(QRectF(tx, cy + 2, 160, 12), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, detail)

        # Pill slides in from right
        pill_o = max(0.0, min(1.0, (t - 0.25) * 3))
        if pill_o > 0:
            pill_offset = 10 * (1 - pill_o)
            p.setOpacity(pill_o)
            self._draw_pill(p, w - 46 - pill_offset, cy, "已完成", QColor(GREEN_SOFT), QColor(GREEN))
            p.setOpacity(1.0)

    # ── Notify: bell + label + pill ──────────────────────────────────

    def _draw_notify(self, p, w, h, cx, cy):
        x0 = w / 2 - 120

        # Bell circle
        bell_cx, bell_cy = x0 + 14, cy
        bell_r = 13
        ig = QColor(GOLD_SOFT)
        p.setPen(QPen(QColor("rgba(184,166,106,0.15)"), 1.5)); p.setBrush(ig)
        p.drawEllipse(QPointF(bell_cx, bell_cy), bell_r, bell_r)

        # Bell icon (with swing) — phase relative to state transition
        swing = 0
        if self._prev_state == "notify" or self._state == "notify":
            ph = (self._phase - self._state_start) * 8
            swing = 14 * math.sin(ph) * math.exp(-ph * 0.08) if ph < 15 else 0
        p.save()
        p.translate(bell_cx, bell_cy - 6)
        p.rotate(swing)
        bell_pen = QPen(QColor(GOLD), 1.6); bell_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(bell_pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(-3.5, -3.5), QPointF(-3.5, 4))
        p.drawLine(QPointF(-3.5, 4), QPointF(3.5, 4))
        p.drawLine(QPointF(3.5, 4), QPointF(3.5, -3.5))
        p.drawEllipse(QPointF(0, 1), 3.5, 3.5)
        p.restore()

        # Label
        tx = x0 + 36
        p.setFont(self._f_label); p.setPen(QColor(TEXT_PRIMARY))
        p.drawText(QRectF(tx, cy - 10, 160, 14), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "来自小橘的提醒")
        detail = self._detail if self._detail else "提醒"
        if len(detail) > 18: detail = detail[:17] + "…"
        p.setFont(self._f_sub); p.setPen(QColor(TEXT_MUTED))
        p.drawText(QRectF(tx, cy + 2, 160, 12), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, detail)

        # Pill
        self._draw_pill(p, w - 46, cy, "提醒", QColor(GOLD_SOFT), QColor(GOLD))

    # ── Error: exclamation + label + pill ────────────────────────────

    def _draw_error(self, p, w, h, cx, cy):
        x0 = w / 2 - 130

        # Error circle
        err_cx, err_cy = x0 + 14, cy
        err_r = 13
        pulse = 0.5 + 0.5 * math.sin(self._phase * 4)
        ig = QColor(RED); ig.setAlphaF(0.08 + pulse * 0.05)
        p.setPen(QPen(QColor("rgba(212,122,114,0.2)"), 1.5)); p.setBrush(ig)
        p.drawEllipse(QPointF(err_cx, err_cy), err_r, err_r)
        # Exclamation
        ep = QPen(QColor(RED), 2.0); ep.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(ep)
        p.drawLine(QPointF(err_cx, err_cy - 5), QPointF(err_cx, err_cy + 2))
        p.setBrush(QColor(RED)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(err_cx, err_cy + 5.5), 1.2, 1.2)

        # Label
        tx = x0 + 36
        p.setFont(self._f_label); p.setPen(QColor(RED))
        p.drawText(QRectF(tx, cy - 10, 160, 14), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "出错了")
        detail = self._detail if self._detail else ""
        if len(detail) > 18: detail = detail[:17] + "…"
        p.setFont(self._f_sub); p.setPen(QColor(TEXT_MUTED))
        p.drawText(QRectF(tx, cy + 2, 160, 12), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, detail)

        # Pill
        self._draw_pill(p, w - 46, cy, "失败", QColor(RED_SOFT), QColor(RED))

    # ── Pill helper ──────────────────────────────────────────────────

    def _draw_pill(self, p, x, cy, text, bg, fg):
        p.setFont(self._f_pill)
        fm = QFontMetrics(self._f_pill)
        tw = fm.horizontalAdvance(text) + 16
        th = 18.0
        pill_rect = QRectF(x - tw, cy - th / 2, tw, th)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(bg)
        p.drawRoundedRect(pill_rect, th / 2, th / 2)
        p.setPen(fg); p.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, text)

    def get_geometry(self) -> tuple:
        """P3-1: 返回岛当前 (x, y, w, h)，供桌宠避让使用。"""
        return (self.x(), self.y(), self.width(), self.height())

    # ── Fade ─────────────────────────────────────────────────────────

    def show(self):
        self.setWindowOpacity(0); super().show()
        a = QPropertyAnimation(self, b"windowOpacity"); a.setDuration(200)
        a.setEasingCurve(QEasingCurve.OutCubic); a.setStartValue(0); a.setEndValue(1); a.start()
        self._fade = a

    def hide(self):
        if not self.isVisible(): return
        a = QPropertyAnimation(self, b"windowOpacity"); a.setDuration(200)
        a.setEasingCurve(QEasingCurve.OutCubic); a.setStartValue(1); a.setEndValue(0)
        a.finished.connect(super().hide); a.start(); self._fade = a

    # ── Hover ────────────────────────────────────────────────────────

    def enterEvent(self, _e):
        if self._state == "idle" and self._ready:
            self._idle_label = random.choice(COMPANION)
            self._animate_to(240, 52)

    def leaveEvent(self, _e):
        if self._state == "idle" and self._ready:
            self._idle_label = None
            self._animate_to(*DIMS["idle"])

    def _animate_to(self, tw, th):
        cur_w, cur_h = float(self.width()), float(self.height())
        self._w = cur_w; self._h = cur_h
        if self._cg.state() == QParallelAnimationGroup.State.Running: self._cg.stop()
        if self._eg.state() == QParallelAnimationGroup.State.Running: self._eg.stop()
        gb = tw > cur_w + 5
        ag = self._eg if gb else self._cg
        ww = self._ew if ag is self._eg else self._cw
        hh = self._eh if ag is self._eg else self._ch
        ww.setStartValue(cur_w); ww.setEndValue(float(tw))
        hh.setStartValue(cur_h); hh.setEndValue(float(th))
        ag.start()

    # ── Mouse ────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.globalPosition().toPoint()
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._dragging = False

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.MouseButton.LeftButton:
            d = e.globalPosition().toPoint() - self._press_pos
            if not self._dragging and (abs(d.x()) > DRAG_TH or abs(d.y()) > DRAG_TH):
                self._dragging = True
            if self._dragging:
                self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if not self._dragging and self._on_click:
                self._on_click()
            self._drag_pos = None; self._press_pos = None; self._dragging = False
