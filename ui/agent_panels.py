from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QLineEdit, QListWidget, QListWidgetItem, QInputDialog,
    QFrame, QScrollArea, QWidget)


def display_time(value):
    return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M") if value else ""


def parse_time(value):
    if not value.strip():
        return None
    result = datetime.fromisoformat(value.strip())
    return result.astimezone().isoformat()


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
            QDialog#draftDialog QWidget { font-family: 'Microsoft YaHei UI'; }
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
        hint = QLabel("修改后，加入灵动岛" if drafts and not editing else
                      "修改后保存" if editing else "还没有可加入的事项")
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
        due = QLineEdit(display_time(draft.get("due_at")))
        due.setPlaceholderText("截止：今日 18:00 / 明天 09:00 / 年-月-日 时:分")
        due.setAccessibleName("截止时间")
        reminders = QLineEdit("; ".join(display_time(t) for t in draft.get("reminder_times", [])))
        reminders.setPlaceholderText("提醒：可填多个时间，用分号隔开")
        reminders.setAccessibleName("提醒时间")
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
        due.textEdited.connect(lambda: self._clear_error(error, due))
        reminders.textEdited.connect(lambda: self._clear_error(error, reminders))
        row = {"original": draft, "card": card, "title": title_input,
               "due": due, "reminders": reminders, "time_panel": time_panel,
               "error": error, "summary": summary, "accept": accept, "accepted": False}
        if accept is not None:
            accept.clicked.connect(lambda: self._accept_question(row))
            for field in (title_input, due, reminders):
                field.textChanged.connect(lambda _text, item=row: self._reset_question_acceptance(item))
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

    @staticmethod
    def _parse_input_time(value):
        value = value.strip()
        if not value:
            return None
        now = datetime.now().astimezone()
        day = None
        for prefix, offset in (("今天", 0), ("今日", 0), ("明天", 1)):
            if value.startswith(prefix):
                day = (now + timedelta(days=offset)).date()
                value = value[len(prefix):].strip()
                break
        try:
            if day is not None:
                parsed = datetime.strptime(value, "%H:%M").replace(year=day.year, month=day.month, day=day.day)
            elif len(value) == 5 and value[2] == ":":
                parsed = datetime.strptime(value, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
            else:
                parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError("时间格式请填 今日 18:00、明天 09:00 或 2026-10-02 18:00") from error
        return parsed.astimezone().isoformat()

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
            due_changed = row["due"].text().strip() != display_time(original.get("due_at"))
            reminders_changed = row["reminders"].text().strip() != "; ".join(
                display_time(t) for t in original.get("reminder_times", []))
            try:
                due = self._parse_input_time(row["due"].text()) if due_changed else original.get("due_at")
            except ValueError as error:
                self._show_error(row, row["due"], str(error))
                return
            due_changed = due_changed and (not due or not original.get("due_at") or
                datetime.fromisoformat(due) != datetime.fromisoformat(original["due_at"]))
            if due and (not self.editing or due_changed) and datetime.fromisoformat(due) < now:
                self._show_error(row, row["due"], "截止时间已过去，请改成未来时间")
                return
            try:
                reminders = ([self._parse_input_time(value) for value in
                    row["reminders"].text().replace("；", ";").split(";") if value.strip()]
                    if reminders_changed else original.get("reminder_times", []))
            except ValueError as error:
                self._show_error(row, row["reminders"], str(error))
                return
            reminders_changed = reminders_changed and (
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
    completed = Signal(str)
    detail = Signal(str)
    add_requested = Signal()

    def __init__(self, tasks, parent=None):
        super().__init__(parent)
        self.setWindowTitle("今日事项")
        self.resize(410, 420)
        layout = QVBoxLayout(self)
        self.items = QListWidget()
        for task in tasks:
            text = task["title"]
            if task.get("due_at"):
                text += "\n" + display_time(task["due_at"])
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, task["id"])
            self.items.addItem(item)
        self.items.itemDoubleClicked.connect(lambda item: self.detail.emit(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.items)
        controls = QHBoxLayout()
        for name, callback in (("完成", lambda: self._selected(self.completed)), ("查看 / 编辑", lambda: self._selected(self.detail)), ("语音添加", self.add_requested.emit)):
            button = QPushButton(name)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)

    def _selected(self, signal):
        item = self.items.currentItem()
        if item:
            signal.emit(item.data(Qt.ItemDataRole.UserRole))


class TaskDetail(QDialog):
    completed = Signal()
    later = Signal(int)
    edit = Signal()

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
        for text, callback in (("完成", self.completed.emit), ("稍后提醒", self.choose_later), ("编辑", self.edit.emit)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)

    def choose_later(self):
        minutes, ok = QInputDialog.getInt(self, "稍后提醒", "多少分钟后", 10, 1, 10080)
        if ok:
            self.later.emit(minutes)
