"""
History Panel — slide-out conversation history sidebar.

Shows all past conversations with title, date, and message preview.
Supports: click to switch, search/filter, right-click rename/delete.
"""
from __future__ import annotations
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QWidget, QSizePolicy, QMenu,
)
from PySide6.QtGui import QFont, QColor

from theme import (
    BG_DEEP, BG_CARD, BG_SUBTLE, WHITE, BORDER, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_META,
    ACCENT, ACCENT_SOFT, ACCENT_BRIGHT,
    GREEN, RED, RED_SOFT, FONT_FAMILY,
    RADIUS_SM, RADIUS_MD, RADIUS_LG,
)


class _ConversationCard(QFrame):
    """A single conversation entry in the history list."""

    clicked = Signal(int)       # conversation index
    preview_requested = Signal(int)  # conversation index (right-click preview)

    def __init__(self, idx: int, conv: dict, is_active: bool = False, parent=None):
        super().__init__(parent)
        self._idx = idx
        self._conv = conv
        self._is_active = is_active
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()
        self._build_ui()

    def _apply_style(self):
        border = f"1px solid {ACCENT}" if self._is_active else f"1px solid {BORDER_SUBTLE}"
        self.setObjectName("conversationCard")
        self.setStyleSheet(f"""
            #conversationCard {{
                background: transparent;
                border: {border};
                border-radius: {RADIUS_MD}px;
                padding: 0;
            }}
            #conversationCard:hover {{
                background: {BG_SUBTLE};
                border: 1px solid {BORDER};
            }}
        """)
        self.setFixedHeight(84)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(4)

        # Row 1: title + date
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        title_text = self._conv.get("title", "新对话")
        if len(title_text) > 20:
            title_text = title_text[:19] + "…"
        title = QLabel(title_text)
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:13px;font-weight:600;"
            f"background:transparent;border:none;"
        )
        row1.addWidget(title)
        row1.addStretch()

        # Date — relative or absolute
        updated = self._conv.get("updated_at", "")
        date_str = self._format_date(updated)
        date_label = QLabel(date_str)
        date_label.setStyleSheet(
            f"color:{TEXT_META};font-size:10px;background:transparent;border:none;"
        )
        row1.addWidget(date_label)
        layout.addLayout(row1)

        # Row 2: message preview
        msgs = self._conv.get("messages", [])
        preview = self._extract_preview(msgs)
        preview_label = QLabel(preview)
        preview_label.setWordWrap(False)
        preview_label.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:11px;background:transparent;border:none;"
        )
        layout.addWidget(preview_label)

        # Row 3: message count + restore button
        row3 = QHBoxLayout()
        row3.setSpacing(6)
        msg_count = len(msgs)
        count_text = f"{msg_count} 条消息" if msg_count else "空对话"
        count_label = QLabel(count_text)
        count_label.setStyleSheet(
            f"color:{TEXT_META};font-size:9px;background:transparent;border:none;"
        )
        row3.addWidget(count_label)
        row3.addStretch()

        restore_btn = QPushButton("恢复")
        restore_btn.setFixedSize(40, 20)
        restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        restore_btn.setStyleSheet(f"""
            QPushButton {{
                background:{ACCENT_SOFT};color:{ACCENT};
                border:1px solid {ACCENT};border-radius:4px;
                font-size:10px;font-weight:600;
            }}
            QPushButton:hover {{ background:{ACCENT};color:#fff; }}
        """)
        restore_btn.clicked.connect(lambda _=False, i=self._idx: self._on_restore(i))
        row3.addWidget(restore_btn)
        layout.addLayout(row3)

    def _on_restore(self, idx: int):
        if hasattr(self.parent(), 'restore_requested'):
            self.parent().restore_requested.emit(idx)

    def _extract_preview(self, msgs: list[dict]) -> str:
        """Get a one-line preview from the last message."""
        if not msgs:
            return "还没有消息…"
        last = msgs[-1]
        content = last.get("content", "")
        # Strip markdown formatting for clean preview
        content = content.replace("\n", " ").strip()
        if len(content) > 50:
            content = content[:49] + "…"
        role_prefix = "你: " if last.get("role") == "user" else "AI: "
        return role_prefix + content

    def _format_date(self, iso_str: str) -> str:
        """Format ISO timestamp into a human-friendly relative string."""
        if not iso_str:
            return ""
        try:
            dt = datetime.fromisoformat(iso_str)
        except (ValueError, TypeError):
            return ""
        now = datetime.now()
        delta = now - dt
        if delta.days == 0:
            return dt.strftime("%H:%M")
        elif delta.days == 1:
            return "昨天"
        elif delta.days < 7:
            return f"{delta.days} 天前"
        else:
            return dt.strftime("%m/%d")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._idx)
        elif e.button() == Qt.MouseButton.RightButton:
            self.preview_requested.emit(self._idx)
            self._show_context_menu(e.globalPosition().toPoint())
        super().mousePressEvent(e)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {BG_CARD}; color: {TEXT_PRIMARY};
                border: 1px solid {BORDER}; border-radius: 8px;
                padding: 4px 0; font-size: 12px;
            }}
            QMenu::item {{ padding: 6px 20px; border-radius: 4px; margin: 2px 4px; }}
            QMenu::item:selected {{ background: {ACCENT}; color: #2a2a28; }}
        """)
        rename_action = menu.addAction("重命名")
        delete_action = menu.addAction("删除")
        if len(self._conv.get("messages", [])) == 0:
            delete_action.setEnabled(False)

        action = menu.exec(pos)
        if action == rename_action:
            self._on_rename()
        elif action == delete_action:
            self._on_delete()

    def _on_rename(self):
        from PySide6.QtWidgets import QInputDialog
        new_title, ok = QInputDialog.getText(
            self, "重命名对话", "新名称:",
            text=self._conv.get("title", ""),
        )
        if ok and new_title.strip():
            # Signal will be handled by parent panel
            if hasattr(self.parent(), 'rename_requested'):
                self.parent().rename_requested.emit(self._idx, new_title.strip())

    def _on_delete(self):
        if hasattr(self.parent(), 'delete_requested'):
            self.parent().delete_requested.emit(self._idx)


class HistoryPanel(QFrame):
    """Slide-in panel showing archived conversation history."""

    rename_requested = Signal(int, str)      # (archive_index, new_title)
    delete_requested = Signal(int)           # permanently delete from archive
    restore_requested = Signal(int)          # restore archive → active tabs
    new_requested = Signal()                 # create new conversation
    closed = Signal()                        # panel closed

    def __init__(self, parent=None):
        super().__init__(parent)
        self._conversations: list[dict] = []
        self._active_idx: int = 0
        self.setFixedWidth(280)
        self.setStyleSheet(f"""
            HistoryPanel {{
                background: {BG_CARD};
                border-right: 1px solid {BORDER};
            }}
        """)
        self._build_ui()
        self.hide()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header row ──
        header = QFrame()
        header.setFixedHeight(48)
        header.setStyleSheet(
            f"QFrame {{ background:{WHITE}; border-bottom:1px solid {BORDER}; }}"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 0, 10, 0)
        hl.setSpacing(8)

        back_btn = QPushButton("←")
        back_btn.setFixedSize(28, 28)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_PRIMARY};
                font-size: 16px; font-weight: bold; border: none;
            }}
            QPushButton:hover {{ background: {BG_SUBTLE}; border-radius: 6px; }}
        """)
        back_btn.clicked.connect(self._close)
        hl.addWidget(back_btn)

        title = QLabel("归档对话")
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:14px;font-weight:600;"
            f"background:transparent;border:none;"
        )
        hl.addWidget(title)
        hl.addStretch()

        new_btn = QPushButton("+")
        new_btn.setFixedSize(28, 28)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setToolTip("新建对话")
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT}; color: #fff;
                font-size: 16px; font-weight: bold; border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{ background: {ACCENT_BRIGHT}; }}
        """)
        new_btn.clicked.connect(self.new_requested.emit)
        hl.addWidget(new_btn)

        layout.addWidget(header)

        # ── Search bar ──
        search_frame = QFrame()
        search_frame.setFixedHeight(44)
        search_frame.setStyleSheet(f"QFrame {{ background:{BG_CARD}; border:none; }}")
        sl = QHBoxLayout(search_frame)
        sl.setContentsMargins(12, 6, 12, 6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索对话…")
        self._search.setFixedHeight(30)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_SUBTLE}; color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_SUBTLE}; border-radius: {RADIUS_SM}px;
                padding: 0 10px; font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {ACCENT}; background: {WHITE};
            }}
        """)
        self._search.textChanged.connect(self._filter)
        sl.addWidget(self._search)

        layout.addWidget(search_frame)

        # ── Scrollable conversation list ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background:{BG_CARD}; border:none; }}"
        )
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._list_container = QWidget()
        self._list_container.setStyleSheet(f"background:{BG_CARD}; border:none;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch(1)

        self._scroll.setWidget(self._list_container)
        layout.addWidget(self._scroll, 1)

        # ── Footer with count ──
        footer = QFrame()
        footer.setFixedHeight(32)
        footer.setStyleSheet(
            f"QFrame {{ background:{BG_SUBTLE}; border-top:1px solid {BORDER_SUBTLE}; }}"
        )
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(14, 0, 14, 0)
        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            f"color:{TEXT_META};font-size:10px;background:transparent;border:none;"
        )
        fl.addWidget(self._count_label)
        fl.addStretch()
        layout.addWidget(footer)

    def update_data(self, conversations: list[dict]):
        """Refresh the panel with archived conversation data."""
        self._conversations = conversations
        self._active_idx = -1
        self._rebuild_list()

    def _rebuild_list(self, filter_text: str = ""):
        """Rebuild the conversation card list, optionally filtered."""
        # Clear existing cards
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget() if item else None
            if w:
                w.setParent(None)
                w.deleteLater()

        # Empty state
        if not self._conversations and not filter_text:
            empty = QLabel("没有归档的对话\n关闭标签页后会自动归档到这里")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"color:{TEXT_MUTED};font-size:12px;"
                f"background:transparent;border:none;padding:30px 0;"
            )
            self._list_layout.insertWidget(0, empty)
            self._count_label.setText("0 个归档")
            return

        # Build cards (newest first)
        indices = list(range(len(self._conversations)))
        indices.reverse()
        visible = 0

        for idx in indices:
            conv = self._conversations[idx]
            if filter_text:
                title = conv.get("title", "").lower()
                msgs_text = " ".join(
                    m.get("content", "") for m in conv.get("messages", [])
                ).lower()
                if filter_text.lower() not in title and filter_text.lower() not in msgs_text:
                    continue

            card = _ConversationCard(idx, conv)
            card.clicked.connect(self._on_card_clicked)
            card.rename_requested = self.rename_requested
            card.delete_requested = self.delete_requested
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)
            visible += 1

        total = len(self._conversations)
        if filter_text:
            self._count_label.setText(f"{visible}/{total} 个归档")
        else:
            self._count_label.setText(f"{total} 个归档")

    def _filter(self, text: str):
        self._rebuild_list(filter_text=text)

    def _on_card_clicked(self, idx: int):
        self.restore_requested.emit(idx)

    def _close(self):
        self.hide()
        self.closed.emit()

    def toggle(self):
        if self.isVisible():
            self._close()
        else:
            self.show()
            self._search.clear()
            self._search.setFocus()
