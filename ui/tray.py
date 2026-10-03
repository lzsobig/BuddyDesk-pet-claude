"""BuddyDesk system tray and application actions."""
from pathlib import Path

from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt

from theme import GREEN, AMBER, RED, BG_CARD, TEXT_PRIMARY, ACCENT
import config


# ── Pre-rendered icon cache ──────────────────────────────────────────────────
_ICON_CACHE: dict[str, QIcon] = {}


def _create_tray_icon(state: str = "idle") -> QIcon:
    if state in _ICON_CACHE:
        return _ICON_CACHE[state]

    source = Path(config.ASSETS_DIR) / "brand" / "logo.png"
    logo = QPixmap(str(source))
    if logo.isNull():
        icon = QIcon(str(Path(config.ASSETS_DIR) / "buddydesk.ico"))
        _ICON_CACHE[state] = icon
        return icon

    pixmap = logo.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    if state != "idle":
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor({"thinking": AMBER, "error": RED}.get(state, GREEN))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f7f5ef"))
        painter.drawEllipse(23, 1, 8, 8)
        painter.setBrush(color)
        painter.drawEllipse(24, 2, 6, 6)
        painter.end()

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
            "Windows 桌面 AI 伴侣\n灵动岛 · 小橘桌宠 · 任务与提醒\n\nAlt+F 和小橘说话；Ctrl+Shift+H 打开聊天",
            _create_tray_icon("idle"),
            5000,
        )

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_chat()
