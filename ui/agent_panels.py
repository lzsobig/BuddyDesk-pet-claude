from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, Signal, QDateTime, QDate, QTime, QTimer, QSize, QPoint
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QLineEdit, QListWidget, QListWidgetItem, QInputDialog,
    QFrame, QScrollArea, QWidget, QAbstractItemView)


def display_time(value):
    return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M") if value else ""


def parse_time(value):
    if not value.strip():
        return None
    result = datetime.fromisoformat(value.strip())
    return result.astimezone().isoformat()


class TimeWheel(QListWidget):
    rangeRequested = Signal(int)

    def __init__(self, labels, index=0, parent=None):
        super().__init__(parent)
        self.setObjectName("timeWheel")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedHeight(140)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._angle_remainder = 0
        self._pixel_remainder = 0
        self._labels_revision = 0
        self.set_labels(labels, index)
        self.currentRowChanged.connect(self._center)

    def set_labels(self, labels, index):
        self._labels_revision += 1
        blocked = self.blockSignals(True)
        self.clear()
        self._value_count = len(labels)
        for position, label in enumerate(["", "", *labels, "", ""]):
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(20, 28))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if position < 2 or position >= len(labels) + 2:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.addItem(item)
        self.setCurrentRow(index + 2)
        self.blockSignals(blocked)
        self._center(self.currentRow())

    def index(self):
        return self.currentRow() - 2

    def set_index(self, index):
        if index < 0 or index >= self._value_count:
            revision = self._labels_revision
            self.rangeRequested.emit(index - self.index())
            if revision != self._labels_revision:
                return
        self.setCurrentRow(min(max(0, index), self._value_count - 1) + 2)

    def _center(self, row):
        if 2 <= row < self._value_count + 2:
            self.scrollToItem(self.item(row), QAbstractItemView.ScrollHint.PositionAtCenter)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self._center(self.currentRow()))

    def wheelEvent(self, event):
        if event.angleDelta().y():
            self._angle_remainder += event.angleDelta().y()
            steps = int(self._angle_remainder / 120)
            self._angle_remainder -= steps * 120
        else:
            self._pixel_remainder += event.pixelDelta().y()
            steps = int(self._pixel_remainder / 28)
            self._pixel_remainder -= steps * 28
        if steps:
            self.set_index(self.index() - steps)
        event.accept()

    def keyPressEvent(self, event):
        steps = {Qt.Key.Key_Up: -1, Qt.Key.Key_Down: 1,
                 Qt.Key.Key_PageUp: -5, Qt.Key.Key_PageDown: 5}
        if event.key() in steps:
            self.set_index(self.index() + steps[event.key()])
            event.accept()
            return
        super().keyPressEvent(event)


class TimePickerDialog(QDialog):
    def __init__(self, title, value=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(360)
        self.setStyleSheet("""
            QWidget { background: transparent; color: #f2eee9;
                font-family: 'Microsoft YaHei UI'; }
            QLabel { background: transparent; border: none; }
            QPushButton { background: transparent; border: none; border-radius: 8px;
                color: #bfb9b4; padding: 8px 12px; }
            QPushButton:hover { background: #343238; color: #f2eee9; }
            QPushButton#primary { background: #efae78; color: #191511; }
            QListWidget#timeWheel { background: #202126; border: none;
                border-radius: 8px; padding: 0; outline: 0; font-size: 13px; }
            QListWidget#timeWheel::item { color: #aaa39d; border: none; padding: 0; }
            QListWidget#timeWheel::item:selected { background: #3b3028; color: #f2c39f;
                border: none; border-radius: 6px; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        heading = QLabel(title)
        heading.setStyleSheet("font-size:16px;font-weight:600;")
        layout.addWidget(heading)
        initial = datetime.fromisoformat(value).astimezone() if value else (
            datetime.now().astimezone() + timedelta(minutes=5)).replace(second=0, microsecond=0)
        self._initial = initial
        today = datetime.now().astimezone().date()
        self._today = today
        self._dates = self._near_dates(initial.date(), 180)
        self.day = TimeWheel(self._date_labels(), self._dates.index(initial.date()))
        self.day.rangeRequested.connect(self._extend_dates)
        self.hour = TimeWheel([f"{hour:02d}" for hour in range(24)], initial.hour)
        self.minute = TimeWheel([f"{minute:02d}" for minute in range(60)], initial.minute)
        wheels = QHBoxLayout()
        wheels.setSpacing(8)
        for label, wheel, stretch in (("日期", self.day, 2), ("时", self.hour, 1), ("分", self.minute, 1)):
            column = QVBoxLayout()
            caption = QLabel(label)
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption.setStyleSheet("color:#aaa19b;font-size:11px;")
            column.addWidget(caption)
            wheel.setAccessibleName("选择" + label)
            column.addWidget(wheel)
            wheels.addLayout(column, stretch)
        layout.addLayout(wheels)
        shortcuts = QHBoxLayout()
        for label, days in (("今天", 0), ("明天", 1)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, offset=days:
                self._select_date(datetime.now().astimezone().date() + timedelta(days=offset)))
            shortcuts.addWidget(button)
        shortcuts.addStretch()
        layout.addLayout(shortcuts)
        self.feedback = QLabel("")
        self.feedback.setStyleSheet("color:#e58f81;font-size:12px;")
        self.feedback.hide()
        layout.addWidget(self.feedback)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        confirm = QPushButton("选好了")
        confirm.setObjectName("primary")
        confirm.setDefault(True)
        confirm.clicked.connect(self.confirm)
        actions.addWidget(confirm)
        layout.addLayout(actions)

    def _date_labels(self):
        labels = []
        for day in self._dates:
            label = day.strftime("%m/%d" if day.year == self._today.year else "%Y/%m/%d")
            if day == self._today:
                label = "今天 " + label
            elif day == self._today + timedelta(days=1):
                label = "明天 " + label
            labels.append(label)
        return labels

    @staticmethod
    def _near_dates(day, after):
        dates = []
        for offset in range(-30, after + 1):
            try:
                dates.append(day + timedelta(days=offset))
            except OverflowError:
                continue
        return dates

    def _select_date(self, day):
        if day not in self._dates:
            self._dates = self._near_dates(day, 90)
            self.day.set_labels(self._date_labels(), self._dates.index(day))
        else:
            self.day.set_index(self._dates.index(day))

    def _extend_dates(self, offset):
        try:
            self._select_date(self._dates[self.day.index()] + timedelta(days=offset))
        except OverflowError:
            return

    def paintEvent(self, event):
        from ui.window_surface import paint_window_surface
        paint_window_surface(self, dark=True)

    def value(self):
        date = self._dates[self.day.index()]
        if (date == self._initial.date() and self.hour.index() == self._initial.hour
                and self.minute.index() == self._initial.minute):
            return self._initial.isoformat()
        selected = QDateTime(QDate(date.year, date.month, date.day), QTime(self.hour.index(), self.minute.index()))
        if not selected.isValid() or selected.time().hour() != self.hour.index():
            raise ValueError("这个时刻不可用，请滚动选择相邻时间")
        return datetime.fromtimestamp(selected.toSecsSinceEpoch()).astimezone().isoformat()

    def confirm(self):
        try:
            if datetime.fromisoformat(self.value()) <= datetime.now().astimezone():
                raise ValueError("这个时间已经过去了，请选一个未来时间")
        except ValueError as error:
            self.feedback.setText(str(error))
            self.feedback.show()
            return
        self.accept()


class TimeField(QWidget):
    valueChanged = Signal()

    def __init__(self, label, values, multiple=False, parent=None):
        super().__init__(parent)
        self.setObjectName("timeField")
        self.setAccessibleName(label)
        self.label, self.multiple = label, multiple
        self._values = list(values)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(5)
        self._refresh()

    def values(self):
        return list(self._values)

    def _refresh(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            item.widget().hide()
            item.widget().deleteLater()
        for index, value in enumerate(self._values):
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            button = QPushButton(self.label + " · " + display_time(value))
            button.setObjectName("timeValue")
            button.setAutoDefault(True)
            button.clicked.connect(lambda checked=False, position=index: self.choose(position))
            row.addWidget(button, 1)
            if index == 0:
                self.setFocusProxy(button)
            remove = QPushButton("×")
            remove.setFixedWidth(28)
            remove.setAutoDefault(True)
            remove.setToolTip("移除" + self.label)
            remove.clicked.connect(lambda checked=False, position=index: self.remove(position))
            row.addWidget(remove)
            self._layout.addWidget(container)
        if self.multiple or not self._values:
            add = QPushButton(("添加" if self.multiple else "选择") + self.label)
            add.setObjectName("timeValue")
            add.setAutoDefault(True)
            add.clicked.connect(lambda: self.choose())
            self._layout.addWidget(add)
            if not self._values:
                self.setFocusProxy(add)

    def choose(self, index=None):
        value = self._values[index] if index is not None else None
        dialog = TimePickerDialog(self.label, value, self)
        dialog.adjustSize()
        anchor_widget = self._layout.itemAt(index if index is not None else self._layout.count() - 1).widget()
        anchor = anchor_widget.mapToGlobal(QPoint(0, anchor_widget.height()))
        available = self.screen().availableGeometry()
        x = min(max(available.left(), anchor.x()), available.right() - dialog.width() + 1)
        y = anchor.y() + 4
        if y + dialog.height() > available.bottom():
            y = anchor_widget.mapToGlobal(QPoint(0, 0)).y() - dialog.height() - 4
        dialog.move(x, max(available.top(), y))
        selected = dialog.value() if dialog.exec() == QDialog.DialogCode.Accepted else None
        dialog.deleteLater()
        if selected is not None:
            before = list(self._values)
            if index is not None:
                if datetime.fromisoformat(selected) != datetime.fromisoformat(value):
                    self._values[index] = selected
            elif self.multiple:
                if all(datetime.fromisoformat(selected) != datetime.fromisoformat(existing)
                       for existing in self._values):
                    self._values.append(selected)
            else:
                self._values = [selected]
            if self._values != before:
                self._refresh()
                self.valueChanged.emit()

    def remove(self, index):
        self._values.pop(index)
        self._refresh()
        self.valueChanged.emit()


class DraftDialog(QDialog):
    confirmed = Signal(list)
    revise = Signal(str)
    supplement = Signal()

    def __init__(self, drafts, transcript, parent=None, editing=False):
        super().__init__(parent)
        self.editing = editing
        self.setWindowTitle("编辑事项" if editing else "加入灵动岛")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("draftDialog")
        self.resize(500, min(620, max(300, 190 + 68 * len(drafts)),
                             self.screen().availableGeometry().height() - 32))
        self._base_height = self.height()
        self.drafts = list(drafts)
        self.rows = []
        self._drag_origin = None
        self.setStyleSheet("""
            QDialog#draftDialog { color: #f2eee9; background: transparent; }
            QWidget { font-family: 'Microsoft YaHei UI'; color: #f2eee9; background: transparent; }
            QLabel { color: #f2eee9; background: transparent; }
            QFrame#draftCard { background: transparent; border: none;
                border-bottom: 1px solid #292a2e; }
            QLineEdit, QPlainTextEdit { color: #f2eee9; background: #25262a;
                border: 1px solid #434047; border-radius: 8px; padding: 7px 9px;
                selection-background-color: #a56b44; }
            QLineEdit#draftTitle { background: transparent; border: 1px solid transparent;
                border-radius: 6px; padding: 2px 5px; font-size: 14px; }
            QLineEdit#draftTitle:focus { background: #222126; border-color: #59493c; }
            QLineEdit:focus, QPlainTextEdit:focus { border-color: #a77957; }
            QLineEdit[error="true"] { border-color: #d57167; }
            QPushButton { color: #bfb9b4; background: transparent; border: none;
                border-radius: 8px; padding: 7px 9px; text-align: left; }
            QPushButton:hover { color: #f2eee9; background: #343238; }
            QPushButton#primary { color: #191511; background: #efae78; font-weight: 600;
                padding: 10px 16px; text-align: center; }
            QPushButton#primary:hover { background: #ffc397; }
            QPushButton#primary:disabled { color: #746c66; background: #4b4038; }
            QPushButton#delete { color: #8f8986; font-size: 17px; padding: 0; text-align: center; }
            QPushButton#timeToggle { color: #a59b94; font-size: 11px; padding: 0 5px;
                text-align: left; }
            QPushButton#timeToggle:hover { color: #efae78; background: transparent; }
            QPushButton#timeValue { background: #25262a; border: 1px solid #434047;
                padding: 8px 10px; color: #d6d0ca; }
            QPushButton#timeValue:hover { border-color: #a77957; color: #f2eee9; }
            QWidget#timeField[error="true"] QPushButton#timeValue { border-color: #d57167; }
            QPushButton#acceptQuestion { color: #c6a17e; font-size: 11px;
                padding: 2px 5px; }
            QPushButton#acceptQuestion:disabled { color: #9cae9d; background: transparent; }
            QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 7px; margin: 0; }
            QScrollBar::handle:vertical { background: #514640; border-radius: 3px; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        title = QLabel("编辑事项" if editing else "整理好了")
        title.setStyleSheet("font-size:19px;font-weight:600;")
        heading.addWidget(title)
        heading.addStretch()
        close_button = QPushButton("×")
        close_button.setFixedSize(26, 26)
        close_button.clicked.connect(self.reject)
        heading.addWidget(close_button)
        layout.addLayout(heading)
        hint = QLabel("修改后，按 Enter 或点击“加入灵动岛”" if drafts and not editing else
                      "修改后，按 Enter 保存" if editing else "还没有可加入的事项")
        hint.setStyleSheet("color:#aaa19b;font-size:12px;")
        layout.addWidget(hint)

        scroll = QScrollArea()
        self.scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self.items_layout = QVBoxLayout(container)
        self.items_layout.setContentsMargins(1, 1, 8, 1)
        self.items_layout.setSpacing(3)
        for draft in self.drafts:
            self._add_row(draft)
        self.items_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        if not editing:
            transcript_button = QPushButton("原话 / 重新整理  ·  展开")
            transcript_button.setStyleSheet("color:#b29c8c;font-size:12px;")
            layout.addWidget(transcript_button)
        self.transcript_panel = QWidget()
        transcript_layout = QVBoxLayout(self.transcript_panel)
        transcript_layout.setContentsMargins(0, 0, 0, 0)
        self.transcript = QPlainTextEdit(transcript)
        self.transcript.setPlaceholderText("在这里修改原话，再重新整理")
        self.transcript.setMaximumHeight(76)
        transcript_layout.addWidget(self.transcript)
        reparse_button = QPushButton("重新整理")
        reparse_button.clicked.connect(self.reparse)
        transcript_layout.addWidget(reparse_button)
        self.transcript_panel.hide()
        if not editing:
            transcript_button.clicked.connect(lambda: self.transcript_panel.setVisible(not self.transcript_panel.isVisible()))
            layout.addWidget(self.transcript_panel)

        self.feedback = QLabel("")
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback.setWordWrap(True)
        self.feedback.setStyleSheet("color:#e58f81;font-size:12px;")
        self.feedback.hide()
        layout.addWidget(self.feedback)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        if not editing:
            voice = QPushButton("语音补充")
            voice.clicked.connect(self.supplement.emit)
            controls.addWidget(voice)
        controls.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        controls.addWidget(cancel)
        self.primary = QPushButton("保存修改" if editing else "加入灵动岛")
        self.primary.setObjectName("primary")
        self.primary.setEnabled(bool(self.rows))
        self.primary.clicked.connect(self.confirm)
        controls.addWidget(self.primary)
        layout.addLayout(controls)
        self.primary.setDefault(True)

    def paintEvent(self, event):
        from ui.window_surface import paint_window_surface
        paint_window_surface(self, dark=True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 55:
            self._drag_origin = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def _add_row(self, draft):
        card = QFrame()
        card.setObjectName("draftCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(4, 5, 4, 5)
        card_layout.setSpacing(1)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        title_input = QLineEdit(draft.get("title") or "")
        title_input.setObjectName("draftTitle")
        title_input.setFixedHeight(31)
        title_input.setMaxLength(240)
        title_input.setPlaceholderText("这件事要做什么？")
        top.addWidget(title_input, 1)
        if not self.editing:
            delete = QPushButton("×")
            delete.setObjectName("delete")
            delete.setFixedSize(28, 28)
            delete.setToolTip("移除这件事")
            delete.clicked.connect(lambda: self._remove_row(card))
            top.addWidget(delete)
        card_layout.addLayout(top)
        summary = QPushButton(self._time_summary(draft))
        summary.setObjectName("timeToggle")
        summary.setFixedHeight(20)
        card_layout.addWidget(summary)
        time_panel = QWidget()
        time_layout = QVBoxLayout(time_panel)
        time_layout.setContentsMargins(0, 4, 0, 0)
        time_layout.setSpacing(5)
        due = TimeField("截止时间", [draft["due_at"]] if draft.get("due_at") else [])
        reminders = TimeField("提醒时间", draft.get("reminder_times", []), multiple=True)
        time_layout.addWidget(due)
        time_layout.addWidget(reminders)
        time_panel.hide()
        summary.clicked.connect(lambda: self._toggle_time_panel(time_panel))
        card_layout.addWidget(time_panel)
        accept = None
        if draft.get("questions") and not self.editing:
            question = QLabel("待确认：" + "；".join(draft["questions"]))
            question.setTextFormat(Qt.TextFormat.PlainText)
            question.setWordWrap(True)
            question.setStyleSheet("color:#c9a47f;font-size:11px;padding:2px 5px;")
            card_layout.addWidget(question)
            accept = QPushButton("按当前内容加入")
            accept.setObjectName("acceptQuestion")
            card_layout.addWidget(accept)
        error = QLabel("")
        error.setTextFormat(Qt.TextFormat.PlainText)
        error.setWordWrap(True)
        error.setStyleSheet("color:#e58f81;font-size:12px;")
        error.hide()
        card_layout.addWidget(error)
        title_input.textEdited.connect(lambda: self._clear_error(error, title_input))
        due.valueChanged.connect(lambda: self._clear_error(error, due))
        reminders.valueChanged.connect(lambda: self._clear_error(error, reminders))
        row = {"original": draft, "card": card, "title": title_input,
               "due": due, "reminders": reminders, "time_panel": time_panel,
               "error": error, "summary": summary, "accept": accept, "accepted": False}
        if accept is not None:
            accept.clicked.connect(lambda: self._accept_question(row))
            title_input.textChanged.connect(lambda _text, item=row: self._reset_question_acceptance(item))
            for field in (due, reminders):
                field.valueChanged.connect(lambda item=row: self._reset_question_acceptance(item))
        for field in (due, reminders):
            field.valueChanged.connect(lambda item=row: self._refresh_time_summary(item))
        self.items_layout.addWidget(card)
        self.rows.append(row)

    @staticmethod
    def _reset_question_acceptance(row):
        if row["accepted"]:
            row["accepted"] = False
            row["accept"].setText("按当前内容加入")
            row["accept"].setEnabled(True)

    @staticmethod
    def _accept_question(row):
        row["accepted"] = True
        row["accept"].setText("已按当前内容确认")
        row["accept"].setEnabled(False)
        row["error"].hide()

    def _refresh_time_summary(self, row):
        due = row["due"].values()
        row["summary"].setText(self._time_summary({
            "due_at": due[0] if due else None, "reminder_times": row["reminders"].values()}))

    @staticmethod
    def _questions_resolved(questions, due_changed, due, reminders_changed, reminders):
        for question in questions:
            needs_due = "截止" in question
            needs_reminder = "提醒" in question
            if not needs_due and not needs_reminder:
                return False
            if needs_due and not (due_changed and due):
                return False
            if needs_reminder and not (reminders_changed and reminders):
                return False
        return True

    @staticmethod
    def _time_summary(draft):
        parts = []
        if draft.get("due_at"):
            parts.append("截止 " + display_time(draft["due_at"]))
        if draft.get("reminder_times"):
            parts.append(f"{len(draft['reminder_times'])} 个提醒")
        return "  ·  ".join(parts) + "  ›" if parts else "时间  ›"

    @staticmethod
    def _clear_error(label, field):
        label.hide()
        field.setProperty("error", False)
        field.style().unpolish(field)
        field.style().polish(field)

    def _show_error(self, row, field, message):
        row["error"].setText(message)
        row["error"].show()
        field.setProperty("error", True)
        field.style().unpolish(field)
        field.style().polish(field)
        if field is not row["title"] and not row["time_panel"].isVisible():
            self._toggle_time_panel(row["time_panel"])
        field.setFocus()
        self.scroll.ensureWidgetVisible(field, 0, 12)

    def show_error(self, message):
        self.feedback.setText(str(message))
        self.feedback.show()

    def _remove_row(self, card):
        self.rows = [row for row in self.rows if row["card"] is not card]
        self.items_layout.removeWidget(card)
        card.deleteLater()
        self.primary.setEnabled(bool(self.rows))

    def _toggle_time_panel(self, panel):
        panel.setVisible(not panel.isVisible())
        expanded = sum(row["time_panel"].isVisible() for row in self.rows)
        limit = min(620, self.screen().availableGeometry().height() - 32)
        self.resize(self.width(), min(limit, self._base_height + 40 * expanded))
        if panel.isVisible():
            self.scroll.ensureWidgetVisible(panel, 0, 12)

    def reparse(self):
        self.revise.emit(self.transcript.toPlainText())

    def confirm(self):
        from agent_tasks import validate_draft

        self.feedback.hide()
        result = []
        now = datetime.now().astimezone()
        removed_ids = ({draft.get("id") or draft.get("draft_id") for draft in self.drafts}
            - {row["original"].get("id") or row["original"].get("draft_id") for row in self.rows}) - {None}
        for row in self.rows:
            original = row["original"]
            title = row["title"].text().strip()
            if not title:
                self._show_error(row, row["title"], "请填写这件事的名称")
                return
            due_values = row["due"].values()
            due = due_values[0] if due_values else None
            original_due = original.get("due_at")
            due_changed = (datetime.fromisoformat(due) != datetime.fromisoformat(original_due)
                           if due and original_due else due != original_due)
            if due and (not self.editing or due_changed) and datetime.fromisoformat(due) < now:
                self._show_error(row, row["due"], "截止时间已过去，请改成未来时间")
                return
            reminders = row["reminders"].values()
            reminders_changed = (
                [datetime.fromisoformat(value) for value in reminders] !=
                [datetime.fromisoformat(value) for value in original.get("reminder_times", [])])
            if (not self.editing or reminders_changed) and any(
                datetime.fromisoformat(value) <= now for value in reminders):
                self._show_error(row, row["reminders"], "提醒时间已过去，请改成未来时间")
                return
            if (not self.editing and original.get("questions") and not row["accepted"] and
                    not self._questions_resolved(original["questions"], due_changed, due,
                                                 reminders_changed, reminders)):
                row["error"].setText("请修正对应时间，或点“按当前内容加入”确认现状")
                row["error"].show()
                row["accept"].setFocus()
                self.scroll.ensureWidgetVisible(row["card"], 0, 12)
                return
            if self.editing:
                changes = {}
                if title != original.get("title"):
                    changes["title"] = title
                if due_changed and due != original.get("due_at"):
                    changes["due_at"] = due
                if reminders_changed and reminders != original.get("reminder_times", []):
                    changes["reminder_times"] = reminders
                    changes["reminder_repeat_rules"] = ["none"] * len(reminders)
                    changes["repeat_rule"] = "none"
                result.append(changes)
            else:
                draft = deepcopy(original)
                draft.update(title=title, due_at=due, reminder_times=reminders, questions=[])
                if removed_ids:
                    draft["dependencies"] = [identifier for identifier in
                        draft.get("dependencies", []) if identifier not in removed_ids]
                if reminders_changed:
                    draft.pop("_reminder_rules", None)
                    draft.pop("reminder_repeat_rules", None)
                    draft.pop("repeat_rule", None)
                try:
                    result.append(validate_draft(draft))
                except (ValueError, TypeError) as error:
                    self._show_error(row, row["title"], str(error))
                    return
        if result:
            self.confirmed.emit(result)


class ReminderCard(QDialog):
    completed = Signal(str)
    snoozed = Signal(str, int)
    dismissed = Signal(str)
    opened = Signal(str)

    def __init__(self, reminder, parent=None):
        super().__init__(parent)
        self.reminder = reminder
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("轻轻提醒")
        self.setFixedWidth(340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        label = QLabel("到时间了")
        label.setStyleSheet("color:#788292;font-size:12px;")
        layout.addWidget(label)
        title = QLabel(reminder.get("title", "今日事项"))
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setStyleSheet("font-size:17px;color:#222933;padding:8px 0;")
        layout.addWidget(title)
        controls = QHBoxLayout()
        done = QPushButton("完成")
        done.clicked.connect(lambda: self.completed.emit(reminder["task_id"]))
        later = QPushButton("稍后提醒")
        later.clicked.connect(self.snooze)
        opened = QPushButton("打开事项")
        opened.clicked.connect(lambda: self.opened.emit(reminder["task_id"]))
        for button in (done, later, opened):
            controls.addWidget(button)
        layout.addLayout(controls)
        ignore = QPushButton("忽略这次提醒")
        ignore.clicked.connect(lambda: self.dismissed.emit(reminder["id"]))
        layout.addWidget(ignore)
        self.adjustSize()
        area = self.screen().availableGeometry()
        self.move(area.right() - self.width() - 24, area.bottom() - self.height() - 24)

    def snooze(self):
        choice, ok = QInputDialog.getItem(self, "稍后提醒", "过多久再提醒", ["10 分钟", "30 分钟", "1 小时", "自定义"], 0, False)
        if not ok:
            return
        minutes = {"10 分钟": 10, "30 分钟": 30, "1 小时": 60}.get(choice)
        if minutes is None:
            minutes, ok = QInputDialog.getInt(self, "稍后提醒", "分钟", 10, 1, 10080)
        if ok:
            self.snoozed.emit(self.reminder["id"], minutes)

    def closeEvent(self, event):
        event.ignore()
        self.hide()


class TasksDialog(QDialog):
    completed = Signal(str, bool)
    detail = Signal(str)
    add_requested = Signal()

    def __init__(self, tasks, parent=None):
        super().__init__(parent)
        self.setWindowTitle("今日事项")
        self.resize(410, 420)
        layout = QVBoxLayout(self)
        self.items = QListWidget()
        self._completed = {task["id"]: task["status"] == "done" for task in tasks}
        for task in tasks:
            text = task["title"]
            if task.get("due_at"):
                text += "\n" + display_time(task["due_at"])
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, task["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if task["status"] == "done" else Qt.CheckState.Unchecked)
            self.items.addItem(item)
        self.items.itemChanged.connect(self._completion_requested)
        self.items.itemDoubleClicked.connect(lambda item: self.detail.emit(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.items)
        controls = QHBoxLayout()
        for name, callback in (("完成 / 取消", self._toggle_selected), ("查看 / 编辑", lambda: self._selected(self.detail)), ("语音添加", self.add_requested.emit)):
            button = QPushButton(name)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)

    def _toggle_selected(self):
        item = self.items.currentItem()
        if item:
            item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)

    def _completion_requested(self, item):
        identity = item.data(Qt.ItemDataRole.UserRole)
        requested = item.checkState() == Qt.CheckState.Checked
        blocked = self.items.blockSignals(True)
        item.setCheckState(Qt.CheckState.Checked if self._completed[identity] else Qt.CheckState.Unchecked)
        self.items.blockSignals(blocked)
        self.completed.emit(identity, requested)

    def update_task(self, task):
        self._completed[task["id"]] = task["status"] == "done"
        blocked = self.items.blockSignals(True)
        for index in range(self.items.count()):
            item = self.items.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == task["id"]:
                item.setCheckState(Qt.CheckState.Checked if self._completed[task["id"]] else Qt.CheckState.Unchecked)
                break
        self.items.blockSignals(blocked)

    def _selected(self, signal):
        item = self.items.currentItem()
        if item:
            signal.emit(item.data(Qt.ItemDataRole.UserRole))


class TaskDetail(QDialog):
    completed = Signal()
    later = Signal(int)
    edit = Signal()
    deleted = Signal()

    def __init__(self, task):
        super().__init__()
        self.setWindowTitle("事项")
        self.setFixedWidth(380)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        title = QLabel(task["title"])
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setStyleSheet("font-size:18px;font-weight:500;")
        layout.addWidget(title)
        lines = []
        if task.get("due_at"):
            lines.append(display_time(task["due_at"]) + " 前完成")
        if task.get("estimated_minutes"):
            lines.append(f"预计 {task['estimated_minutes']} 分钟")
        if task.get("reminder_times"):
            lines.append("提醒：" + "、".join(display_time(t) for t in task["reminder_times"][:3]))
        if lines:
            detail = QLabel("\n".join(lines))
            detail.setWordWrap(True)
            detail.setStyleSheet("color:#667181;font-size:12px;padding:8px 0;")
            layout.addWidget(detail)
        controls = QHBoxLayout()
        self.complete_button = QPushButton()
        self.complete_button.clicked.connect(self.completed.emit)
        controls.addWidget(self.complete_button)
        self.later_button = QPushButton("稍后提醒")
        self.later_button.clicked.connect(self.choose_later)
        controls.addWidget(self.later_button)
        for text, callback in (("编辑", self.edit.emit),):
            button = QPushButton(text)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)
        delete = QPushButton("删除事项")
        delete.setStyleSheet("color:#8b6660;background:transparent;border:none;padding:4px 0;")
        delete.clicked.connect(self.deleted.emit)
        layout.addWidget(delete, 0, Qt.AlignmentFlag.AlignRight)
        self.set_completed(task["status"] == "done")

    def set_completed(self, completed):
        self.complete_button.setText("取消完成" if completed else "完成")
        self.later_button.setEnabled(not completed)

    def choose_later(self):
        minutes, ok = QInputDialog.getInt(self, "稍后提醒", "多少分钟后", 10, 1, 10080)
        if ok:
            self.later.emit(minutes)
