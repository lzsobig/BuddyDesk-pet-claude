from __future__ import annotations

import re
import logging
import threading

from PySide6.QtCore import QObject, QTimer, Qt, Signal, QSize
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QFileIconProvider, QApplication
from PySide6.QtCore import QFileInfo

from agent_tools import calculator
from engine.app_index import get_app_index

logger = logging.getLogger(__name__)


class QuickLauncher(QObject):
    indexed = Signal(str)
    launched = Signal(bool, str)

    def __init__(self, agent):
        super().__init__(agent)
        self.agent = agent
        self.main = agent.main
        self.index = get_app_index()
        self.active = False
        self.height = 112
        self._rows = []
        self._query = ""
        self._launching = False
        self._folders = tuple(self.main._user_config.get("launcher_folders", ()))
        self._closed = False
        self._scan_running = False
        self._pending_refresh = False
        self._icons = {}
        self._icon_provider = QFileIconProvider()
        self.ime = agent.ime
        self.ime._launcher = self
        self.card = self.ime.card
        self.results = QListWidget(self.card)
        self.results.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.results.setAccessibleName("应用搜索结果")
        self.results.setIconSize(QSize(23, 23))
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setStyleSheet("QListWidget{border:none;background:transparent;color:#edf0f4;font-size:12px;outline:none;}"
            "QListWidget::item{border:none;border-radius:9px;padding:2px 8px;}"
            "QListWidget::item:selected{background:rgba(255,255,255,22);color:white;}"
            "QListWidget::item:hover{background:rgba(255,255,255,12);}")
        self.results.hide()
        self.card.layout().insertWidget(2, self.results)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(65)
        self._debounce.timeout.connect(self.search)
        self.card.editor.textChanged.connect(lambda: self._debounce.start() if self.active else None)
        self.card.editor.launcher_activate.connect(self.activate)
        self.card.editor.launcher_move.connect(self.move_selection)
        self.results.itemClicked.connect(lambda item: self.activate(item.data(Qt.ItemDataRole.UserRole)))
        self.ime.cancelled.connect(self.close)
        self.indexed.connect(self._indexed)
        self.launched.connect(self._launched)
        agent.state.changed.connect(self._agent_state_changed)
        self.hotkey = self._bind_hotkey(self.main._user_config.get("launcher_hotkey", "Alt+Space"))
        self._menu_action = None
        if self.main.tray:
            self._menu_action = self.main.tray.contextMenu().addAction("搜索应用 · " + self.hotkey.label, self.toggle)
            self.main.tray.contextMenu().addAction("刷新应用索引", self.refresh)
        self.refresh()

    def _bind_hotkey(self, requested):
        from agent_controller import AgentHotkeys
        choices = ("Alt+Space", "Ctrl+Alt+Space", "Ctrl+Shift+Space")
        requested = requested if requested in choices else choices[0]
        for shortcut in dict.fromkeys((requested, *choices)):
            hotkey = AgentHotkeys(self.main.app, self.toggle, identity=0xBADF, shortcut=shortcut)
            if hotkey.registered:
                if shortcut != requested:
                    import config
                    try:
                        current = config.load_user_config()
                        current["launcher_hotkey"] = shortcut
                        config.save_user_config(current)
                    except (OSError, ValueError):
                        logger.warning("Fallback launcher shortcut could not be saved")
                    self.main._user_config["launcher_hotkey"] = shortcut
                    if self.main.tray:
                        QTimer.singleShot(600, lambda label=shortcut: self.main.tray.showMessage("快速搜索快捷键", f"原组合键被占用，已启用 {label}。可在偏好里修改。"))
                return hotkey
            hotkey.close()
        return AgentHotkeys(self.main.app, self.toggle, identity=0xBADF, shortcut=requested)

    def refresh(self):
        if self._closed:
            return
        if self._scan_running or self.index.scanning:
            self._pending_refresh = True
            return
        self._scan_running = True
        folders = self._folders
        def worker():
            try:
                success = self.index.refresh(folders)
                message = "" if success else self.index.last_error
            except Exception:
                logger.exception("Application index update failed")
                message = "索引更新失败，可从托盘重新刷新"
            if not self._closed:
                self.indexed.emit(message)
        threading.Thread(target=worker, daemon=True).start()

    def _indexed(self, error):
        self._scan_running = False
        if self._closed:
            return
        if self.active:
            self.search()
            if error:
                self.card.status.setText(error)
        if self._pending_refresh:
            self._pending_refresh = False
            self.refresh()

    def update_settings(self, settings):
        shortcut = settings.get("launcher_hotkey", "Alt+Space")
        if shortcut != self.hotkey.label:
            self.hotkey.close()
            self.hotkey = self._bind_hotkey(shortcut)
            if not self.hotkey.registered:
                if self.main.tray:
                    self.main.tray.showMessage("快捷键已被占用", "可以从托盘进入搜索应用，并在偏好里修改组合键。")
            if self._menu_action:
                self._menu_action.setText("搜索应用 · " + self.hotkey.label)
        folders = tuple(settings.get("launcher_folders", ()))
        if folders != self._folders:
            self._folders = folders
            self.refresh()

    def toggle(self):
        if self.active:
            self.close()
            return
        if (self._launching or self.ime.active or self.agent.voice.recording or self.agent.voice.processing
                or self.agent.draft_dialog or self.agent.state.state not in ("idle", "success", "error")):
            if self.main.tray:
                self.main.tray.showMessage("先完成当前交互", "结束语音或确认当前内容后，再搜索应用。")
            return
        self.active = True
        self.card.setWindowTitle("搜索应用 · BuddyDesk")
        QApplication.inputMethod().reset()
        self.card.editor._composing = False
        self.card.editor.launcher_mode = True
        self.card.editor.setAccessibleName("搜索应用、拼音或文件夹")
        self.card.editor.setPlaceholderText("搜索应用、拼音或文件夹…")
        self.card.editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.card.finish_button.setFixedWidth(65)
        self.ime.reopen_for_retry("", "")
        self.card.status.setText("搜索应用")
        self.card.hint.setText("↑ ↓ 选择 · Enter 打开 · Ctrl+Enter 交给小橘")
        self.card.finish_button.setText("交给小橘")
        self.card.finish_button.setAccessibleName("将当前输入交给小橘理解")
        self.card.finish_button.setToolTip("明确交给小橘 · Ctrl+Enter")
        self.search()
        self.agent.publish(force=True)
        if not self.hotkey.registered:
            self.card.status.setText("快捷键被占用 · 可在偏好里修改")

    def search(self):
        if not self.active:
            return
        self._debounce.stop()
        query = self.card.editor.toPlainText().strip()[:500]
        selected = self.results.currentItem()
        old_id = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        self._query = query
        self._rows = []
        self.results.clear()
        if query and re.fullmatch(r"[\d\s.+*/()%\-]+", query) and any(char in query for char in "+-*/%"):
            try:
                result = calculator(query)
                text = str(result)
                self._rows.append(("calculator", text))
                item = QListWidgetItem(f"{query} = {text}\nEnter 复制结果")
                item.setData(Qt.ItemDataRole.UserRole, "calculator")
                item.setSizeHint(QSize(0, 40))
                self.results.addItem(item)
            except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
                pass
        if not self._rows:
            for entry in self.index.search(query, limit=4):
                self._rows.append((entry.id, entry))
                label = {"app": "应用", "folder": "文件夹", "website": "网页"}[entry.kind]
                item = QListWidgetItem(f"{entry.name}\n{label} · {entry.source}")
                item.setData(Qt.ItemDataRole.UserRole, entry.id)
                item.setSizeHint(QSize(0, 40))
                item.setToolTip(entry.target + ("\n目标：" + entry.destination if entry.destination != entry.target else ""))
                if entry.target not in self._icons:
                    if len(self._icons) > 128:
                        self._icons.clear()
                    self._icons[entry.target] = self._icon_provider.icon(QFileInfo(entry.target))
                item.setIcon(self._icons[entry.target])
                self.results.addItem(item)
        if self._rows:
            self.results.setCurrentRow(next((number for number, row in enumerate(self._rows) if row[0] == old_id), 0))
        self.results.setVisible(bool(self._rows))
        self.results.setFixedHeight(40 * len(self._rows))
        self.height = 114 + 40 * len(self._rows)
        self.card.status.setText("正在建立索引…" if self.index.scanning else "搜索应用" if self._rows else "没有匹配 · 可交给小橘")
        if not self.card.docked:
            self.card.resize(360, self.height)
        self.agent.publish(force=True)

    def move_selection(self, delta):
        if self.active and self._rows:
            self.results.setCurrentRow((self.results.currentRow() + delta) % len(self._rows))

    def activate(self, identity=None):
        if not self.active or self._launching:
            return
        if self._query != self.card.editor.toPlainText().strip()[:500]:
            self.search()
            if identity is not None:
                return
        number = self.results.currentRow()
        if identity is None and 0 <= number < len(self._rows):
            identity = self._rows[number][0]
        row = next((row for row in self._rows if row[0] == identity), None)
        if row is None:
            return
        if identity == "calculator":
            QApplication.clipboard().setText(row[1])
            self.close()
            return
        self._launching = True
        engine = self.main.command_engine
        self.close()
        def worker():
            try:
                result = engine.open_indexed(identity)
                self.agent.store.audit("launcher_open", None, "success" if result.success else "failed")
                self.launched.emit(result.success, result.output or result.error)
            except Exception as error:
                self.launched.emit(False, "应用未能打开：" + str(error)[:160])
        threading.Thread(target=worker, daemon=True).start()

    def _launched(self, success, message):
        self._launching = False
        if not success and not self._closed and self.main.tray:
            self.main.tray.showMessage("快速搜索", message)

    def _agent_state_changed(self, snapshot):
        if self.active and snapshot["state"] in ("listening", "transcribing", "understanding", "executing", "asking_confirmation", "reminding"):
            self.close()

    def submit_agent(self):
        if not self.active:
            return
        text = self.card.editor.toPlainText().strip()
        if not text:
            self.card.editor.setFocus()
            return
        self.close()
        self.agent.plan(text)

    def close(self):
        if not self.active:
            return
        self.active = False
        QApplication.inputMethod().reset()
        self.card.editor._composing = False
        self._debounce.stop()
        self.ime.cancel()
        self.results.hide()
        self.results.clear()
        self.card.editor.launcher_mode = False
        self.card.editor.setAccessibleName("语音与文字输入区")
        self.card.editor.setPlaceholderText("说点什么，或直接输入…")
        self.card.editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.card.finish_button.setFixedWidth(40)
        self.card.finish_button.setAccessibleName("发送给小橘")
        self.card.setWindowTitle("和小橘说话 · BuddyDesk")
        self.height = 112
        self.agent.publish(force=True)

    def shutdown(self):
        self.close()
        self._closed = True
        self.hotkey.close()
