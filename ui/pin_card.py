"""
Pin Card — 把任意 AI 回答钉到桌面的独立小卡片（P2-3）。

设计：
- 独立 QWidget，无边框 + 圆角 + 半透明 + 置顶
- 持久化到 ~/.buddydesk/pins.json
- 启动时恢复所有 pin
- 拖动自由摆放；右键菜单"关闭 / 跳回对话"
- 超过 10 个时新 pin 替换最旧的

注：纯显示卡片，不接收 AI 流式更新（pin 的是当时 AI 回答的完整文本）。
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMenu, QSizePolicy,
)

from theme import (
    BG_CARD, BORDER, BORDER_SUBTLE, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, ACCENT, ACCENT_SOFT, RED, RED_SOFT,
    FONT_FAMILY, RADIUS_MD, RADIUS_SM,
)


# 持久化路径
PINS_PATH = os.path.join(os.path.expanduser("~"), ".buddydesk", "pins.json")
MAX_PINS = 10  # 同时存在的最大 pin 数


def _load_pins() -> list[dict]:
    if not os.path.isfile(PINS_PATH):
        return []
    try:
        with open(PINS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("Failed to load pins from %s: %s", PINS_PATH, exc)
        return []


def _save_pins(pins: list[dict]) -> None:
    os.makedirs(os.path.dirname(PINS_PATH), exist_ok=True)
    try:
        with open(PINS_PATH, "w", encoding="utf-8") as f:
            json.dump(pins, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.debug("Failed to save pins to %s: %s", PINS_PATH, exc)


class PinCard(QWidget):
    """单个 Pin 桌面卡片。"""

    closed = Signal(str)  # pin_id
    jump_requested = Signal(str, int)  # pin_id, conversation_idx (hint)

    def __init__(self, pin_id: str, content: str, conversation_idx: int = 0,
                 x: int = 100, y: int = 100, parent=None):
        super().__init__(parent)
        self.pin_id = pin_id
        self._conversation_idx = conversation_idx
        self._drag_pos: Optional[QPoint] = None

        # 内容预览（截断 200 字符 + markdown 简单清洗）
        preview = self._clean_markdown(content)
        if len(preview) > 200:
            preview = preview[:200] + "…"

        self.setWindowTitle(f"Pin {pin_id[:8]}")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(240, 140)
        self.move(x, y)

        # 主体
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QWidget()
        card.setStyleSheet(
            f"QWidget {{ background:{BG_CARD};border:1px solid {BORDER_SUBTLE};"
            f"border-radius:{RADIUS_MD}px; }}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        title_lbl = QLabel("📌 BuddyDesk")
        title_lbl.setStyleSheet(
            f"color:{ACCENT};font-size:11px;font-weight:700;background:transparent;border:none;"
        )
        header.addWidget(title_lbl)
        header.addStretch()

        time_lbl = QLabel(datetime.now().strftime("%H:%M"))
        time_lbl.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:10px;background:transparent;border:none;"
        )
        header.addWidget(time_lbl)

        close_btn = QLabel("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:12px;background:transparent;border:none;"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.mousePressEvent = lambda _e: self._on_close()
        header.addWidget(close_btn)
        card_layout.addLayout(header)

        # 分隔线
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{BORDER_SUBTLE};border:none;")
        card_layout.addWidget(line)

        # 内容
        content_lbl = QLabel(preview)
        content_lbl.setWordWrap(True)
        content_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:12px;line-height:1.5;background:transparent;border:none;"
        )
        content_lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        card_layout.addWidget(content_lbl, 1)

        root.addWidget(card)

    @staticmethod
    def _clean_markdown(text: str) -> str:
        """简单清洗 markdown（去掉 code fence、链接、强调标记），保留纯文本预览。"""
        import re
        text = re.sub(r"```[\s\S]*?```", "[代码块]", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        return text.strip()

    def _on_close(self):
        self.closed.emit(self.pin_id)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        if self._drag_pos:
            self._drag_pos = None
            # 持久化新位置
            self._persist_position()

    def _persist_position(self):
        pins = _load_pins()
        for p in pins:
            if p.get("id") == self.pin_id:
                p["x"] = self.x()
                p["y"] = self.y()
                break
        _save_pins(pins)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_jump = menu.addAction("跳回对话")
        act_close = menu.addAction("关闭")
        act_close.setShortcut("Ctrl+W")
        chosen = menu.exec(event.globalPos())
        if chosen is act_jump:
            self.jump_requested.emit(self.pin_id, self._conversation_idx)
        elif chosen is act_close:
            self._on_close()


class PinManager:
    """Pin 卡片管理器：负责创建 / 销毁 / 持久化所有 PinCard。"""

    def __init__(self):
        self._cards: dict[str, PinCard] = {}
        self._on_jump_cb = None

    def pin(self, content: str, conversation_idx: int = 0,
            position: Optional[QPoint] = None) -> str:
        """创建并显示一个新 pin。返回 pin_id。"""
        # 超过 MAX_PINS 时删最旧的
        if len(self._cards) >= MAX_PINS:
            oldest_id = next(iter(self._cards))
            self._remove(oldest_id)

        pin_id = str(uuid.uuid4())[:8]
        x, y = 100, 100
        if position:
            x, y = position.x(), position.y()
        # 找当前已存在的 pin 位置，cascade
        offset = 30 * (len(self._cards) % 6)
        x = (x + offset) % 1200
        y = (y + offset) % 800

        card = PinCard(pin_id, content, conversation_idx, x, y)
        card.closed.connect(self._remove)
        card.jump_requested.connect(self._on_jump)
        self._cards[pin_id] = card
        card.show()

        # 持久化
        pins = _load_pins()
        pins.append({
            "id": pin_id,
            "content": content,
            "conversation_idx": conversation_idx,
            "x": x,
            "y": y,
            "created_at": datetime.now().isoformat(),
        })
        _save_pins(pins)
        return pin_id

    def _remove(self, pin_id: str):
        card = self._cards.pop(pin_id, None)
        if card:
            card.close()
            card.deleteLater()
        pins = [p for p in _load_pins() if p.get("id") != pin_id]
        _save_pins(pins)

    def _on_jump(self, pin_id: str, conversation_idx: int):
        """跳回对话：调用 main.py 注册的回调。"""
        if self._on_jump_cb:
            self._on_jump_cb(pin_id, conversation_idx)

    def restore_all(self, on_jump=None):
        """启动时恢复所有 pin。"""
        if on_jump:
            self._on_jump_cb = on_jump
        for p in _load_pins():
            pin_id = p["id"]
            if pin_id in self._cards:
                continue
            card = PinCard(
                pin_id,
                p.get("content", ""),
                p.get("conversation_idx", 0),
                p.get("x", 100),
                p.get("y", 100),
            )
            card.closed.connect(self._remove)
            card.jump_requested.connect(self._on_jump)
            self._cards[pin_id] = card
            card.show()

    def get_card(self, pin_id: str) -> Optional[PinCard]:
        return self._cards.get(pin_id)
