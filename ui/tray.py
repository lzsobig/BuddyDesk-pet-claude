"""
System Tray — QSystemTrayIcon with context menu and status indicator.

Icon is a rounder cat-face with whiskers rendered via QPainter.
Menu includes Show/Hide Chat toggle, About, and Quit.
"""
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QFont, QAction
from PySide6.QtCore import Qt, QPointF

from theme import GREEN, AMBER, RED, BG_CARD, TEXT_PRIMARY, TEXT_MUTED, ACCENT, BG_DEEP
import config


# ── Pre-rendered icon cache ──────────────────────────────────────────────────
_ICON_CACHE: dict[str, QIcon] = {}


def _create_tray_icon(state: str = "idle") -> QIcon:
    """Generate a polished cat-face tray icon with whiskers (cached)."""
    if state in _ICON_CACHE:
        return _ICON_CACHE[state]

    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    color_map = {"idle": GREEN, "thinking": AMBER, "error": RED}
    color = QColor(color_map.get(state, GREEN))

    # Cat head — rounder shape
    p.setBrush(QBrush(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(5, 10, 22, 18, 8, 8)

    # Ears — slightly more pointed
    p.drawPolygon([
        QPointF(5, 10), QPointF(8, 2), QPointF(13, 10),
    ])
    p.drawPolygon([
        QPointF(19, 10), QPointF(24, 2), QPointF(27, 10),
    ])

    # Inner ear tint (lighter)
    ear_inner = QColor(color)
    ear_inner.setAlpha(90)
    p.setBrush(QBrush(ear_inner.lighter(160)))
    p.drawPolygon([
        QPointF(6, 10), QPointF(8, 4), QPointF(12, 10),
    ])
    p.drawPolygon([
        QPointF(20, 10), QPointF(24, 4), QPointF(26, 10),
    ])

    # Eyes
    p.setBrush(QBrush(QColor(BG_DEEP)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(10, 15, 4, 4)
    p.drawEllipse(18, 15, 4, 4)

    # Eye highlights
    p.setBrush(QBrush(QColor(255, 255, 255, 200)))
    p.drawEllipse(11, 15, 2, 2)
    p.drawEllipse(19, 15, 2, 2)

    # Nose
    p.setBrush(QBrush(QColor("#ff6b9d")))
    nose_pts = [
        QPointF(15, 20), QPointF(17, 20), QPointF(16, 21.5),
    ]
    p.drawPolygon(nose_pts)

    # Whiskers
    whisker_pen = QPen(QColor("#8B7355"))
    whisker_pen.setWidth(1)
    p.setPen(whisker_pen)
    # Left whiskers
    p.drawLine(QPointF(5, 18), QPointF(1, 17))
    p.drawLine(QPointF(5, 19.5), QPointF(0, 19.5))
    p.drawLine(QPointF(5, 21), QPointF(1, 22))
    # Right whiskers
    p.drawLine(QPointF(27, 18), QPointF(31, 17))
    p.drawLine(QPointF(27, 19.5), QPointF(32, 19.5))
    p.drawLine(QPointF(27, 21), QPointF(31, 22))

    p.end()
    icon = QIcon(pixmap)
    _ICON_CACHE[state] = icon
    return icon


class SystemTray(QSystemTrayIcon):
    """System tray icon with status updates and context menu."""

    def __init__(self, on_toggle_chat=None, on_quit=None, on_settings=None, parent=None):
        super().__init__(parent)
        self.on_toggle_chat = on_toggle_chat
        self.on_quit = on_quit
        self.on_settings = on_settings
        self._chat_visible = False

        self.setIcon(_create_tray_icon("idle"))
        self.setToolTip("BuddyDesk — Ready")

        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {BG_CARD};
                color: {TEXT_PRIMARY};
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
                padding: 6px 0;
                font-size: 13px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: 6px;
                margin: 2px 6px;
            }}
            QMenu::item:selected {{
                background-color: {ACCENT};
                color: #2a2a28;
            }}
        """)

        # Plain text — emoji stripped for a clean, consistent menu style.
        self._chat_action = menu.addAction("显示聊天窗口")
        self._chat_action.triggered.connect(self._toggle_chat)

        self._settings_action = menu.addAction("设置")
        self._settings_action.triggered.connect(self._open_settings)

        menu.addSeparator()

        about_action = menu.addAction("关于 BuddyDesk")
        about_action.triggered.connect(self._show_about)

        menu.addSeparator()

        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self._quit)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def update_state(self, state: str, text: str = ""):
        """Update tray icon color and tooltip text."""
        self.setIcon(_create_tray_icon(state))
        if text:
            self.setToolTip(f"BuddyDesk — {text}")

    def set_chat_visible(self, visible: bool):
        """Update menu text to reflect chat window visibility."""
        self._chat_visible = visible
        if visible:
            self._chat_action.setText("隐藏聊天窗口")
        else:
            self._chat_action.setText("显示聊天窗口")

    def _toggle_chat(self):
        if self.on_toggle_chat:
            self.on_toggle_chat()

    def _open_settings(self):
        if self.on_settings:
            self.on_settings()

    def _quit(self):
        if self.on_quit:
            self.on_quit()

    def _show_about(self):
        """Show a brief about message via tray notification."""
        self.showMessage(
            f"BuddyDesk v{config.APP_VERSION}",
            "Windows 桌面 AI 伴侣\n灵动岛 · 像素橘猫 · 自然语言命令执行\n\n快捷键: Ctrl+Shift+H 呼出/隐藏聊天",
            _create_tray_icon("idle"),
            5000,
        )

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_chat()
