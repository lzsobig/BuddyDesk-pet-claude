"""
Confirm Dialog — modal prompt for dangerous command execution.

When CommandEngine detects a dangerous command, it sets _pending_confirmation.
This dialog shows the command and lets the user confirm or cancel.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)
from PySide6.QtGui import QPainter, QColor, QPen, QPolygon
from PySide6.QtCore import QPoint

from theme import (
    BG_DEEP, BG_CARD, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    RED, RED_SOFT, GREEN, GREEN_SOFT, ACCENT, ACCENT_SOFT, WHITE,
    FONT_FAMILY, FONT_MONO, RADIUS_SM, RADIUS_MD, RADIUS_LG,
)


class ConfirmDialog(QDialog):
    """Frameless modal dialog that asks the user to confirm a dangerous command."""

    def __init__(self, command: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("命令确认")
        self.setModal(True)
        self.setFixedSize(380, 220)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None
        self._command = command
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_LG}px;
            }}
        """)
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(24, 20, 24, 18)
        card_l.setSpacing(12)

        # Warning icon + title row
        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setStyleSheet(
            f"background:{RED_SOFT};border-radius:18px;"
        )
        # Draw a warning triangle icon
        px = __import__('PySide6.QtGui', fromlist=['QPixmap']).QPixmap(36, 36)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(RED), 2))
        p.setBrush(QColor(RED_SOFT))
        p.drawPolygon([
            QPoint(18, 4), QPoint(32, 30), QPoint(4, 30)
        ])
        p.setPen(QPen(QColor(RED)))
        p.drawText(16, 17, "!")
        p.end()
        icon_lbl.setPixmap(px)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("危险命令")
        title.setStyleSheet(
            f"color:{RED};font-size:15px;font-weight:700;"
            f"background:transparent;border:none;"
        )
        subtitle = QLabel("以下命令可能对系统造成影响")
        subtitle.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:11px;"
            f"background:transparent;border:none;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_row.addWidget(icon_lbl)
        title_row.addLayout(title_col)
        title_row.addStretch()
        card_l.addLayout(title_row)

        # Command display
        cmd_lbl = QLabel(self._command)
        cmd_lbl.setWordWrap(True)
        cmd_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cmd_lbl.setMaximumHeight(48)
        cmd_lbl.setStyleSheet(
            f"background:{BG_DEEP};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};border-radius:{RADIUS_SM}px;"
            f"padding:8px 12px;font-family:{FONT_MONO};font-size:12px;"
        )
        card_l.addWidget(cmd_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_DEEP}; color: {TEXT_PRIMARY};
                border: 1.5px solid {BORDER}; border-radius: {RADIUS_SM}px;
                font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {RED_SOFT}; border-color: {RED}; color: {RED}; }}
        """)
        cancel_btn.clicked.connect(self.reject)

        confirm_btn = QPushButton("确认执行")
        confirm_btn.setFixedHeight(36)
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background: {RED}; color: {WHITE};
                border: none; border-radius: {RADIUS_SM}px;
                font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #c06a62; }}
        """)
        confirm_btn.clicked.connect(self.accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(confirm_btn)
        card_l.addLayout(btn_row)

        root.addWidget(card)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawRoundedRect(0, 0, self.width(), self.height(), RADIUS_LG, RADIUS_LG)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _e):
        self._drag_pos = None
