from __future__ import annotations

import ctypes
import json
import math
import sys
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QCursor, QPalette, QPainter
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QSizePolicy


def installed_profile():
    if sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\CTF\TIP") as root:
            for index in range(winreg.QueryInfoKey(root)[0]):
                clsid = winreg.EnumKey(root, index)
                try:
                    with winreg.OpenKey(root, clsid + r"\LanguageProfile\0x00000804") as profiles:
                        for number in range(winreg.QueryInfoKey(profiles)[0]):
                            profile = winreg.EnumKey(profiles, number)
                            with winreg.OpenKey(profiles, profile) as key:
                                description = winreg.QueryValueEx(key, "Description")[0]
                                if "豆包" in str(description):
                                    return clsid, profile
                except OSError:
                    continue
    except OSError:
        return None
    return None


class _Guid(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16),
                ("data3", ctypes.c_uint16), ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def of(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value.strip("{}")).bytes_le)


class _Profile(ctypes.Structure):
    _fields_ = [("kind", ctypes.c_uint32), ("language", ctypes.c_uint16), ("clsid", _Guid),
                ("profile", _Guid), ("category", _Guid), ("substitute", ctypes.c_void_p),
                ("capabilities", ctypes.c_uint32), ("layout", ctypes.c_void_p), ("flags", ctypes.c_uint32)]


class _InputProfile:
    def __init__(self, identity):
        self.pointer = ctypes.c_void_p()
        self.previous = _Profile()
        self.have_previous = False
        self.initialized = ctypes.windll.ole32.CoInitializeEx(None, 2) in (0, 1)
        clsid = _Guid.of("33C53A50-F456-4884-B049-85FD643ECFED")
        interface = _Guid.of("71c6e74c-0f28-11d8-a82a-00065b84435c")
        result = ctypes.windll.ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(interface), ctypes.byref(self.pointer))
        if result != 0:
            self.close()
            raise OSError("无法连接 Windows 输入法服务")
        self.table = ctypes.cast(self.pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        get_active = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(_Guid), ctypes.POINTER(_Profile))(self.table[10])
        category = _Guid.of("34745C63-B2F0-4784-8B67-5E12C8701A31")
        self.have_previous = get_active(self.pointer, ctypes.byref(category), ctypes.byref(self.previous)) == 0
        self.activate = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint16,
            ctypes.POINTER(_Guid), ctypes.POINTER(_Guid), ctypes.c_void_p, ctypes.c_uint32)(self.table[3])
        result = self.activate(self.pointer, 1, 0x0804, ctypes.byref(_Guid.of(identity[0])), ctypes.byref(_Guid.of(identity[1])), None, 0x10000000)
        if result != 0:
            self.close()
            raise OSError("无法切换豆包输入法，请在此输入框中切换后重试")

    def close(self):
        if self.pointer:
            if self.have_previous and hasattr(self, "activate"):
                p = self.previous
                self.activate(self.pointer, p.kind, p.language, ctypes.byref(p.clsid), ctypes.byref(p.profile), p.layout, 0x10000000)
            table = ctypes.cast(self.pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])(self.pointer)
            self.pointer = ctypes.c_void_p()
        if self.initialized:
            ctypes.windll.ole32.CoUninitialize()
            self.initialized = False


class _Receiver(QPlainTextEdit):
    preview = Signal(str)
    submit = Signal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.submit.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def inputMethodEvent(self, event):
        super().inputMethodEvent(event)
        body = self.toPlainText()
        cursor = self.textCursor().position()
        self.preview.emit(body[:cursor] + event.preeditString() + body[cursor:])


class InputCard(QDialog):
    finish_requested = Signal()
    cancel_requested = Signal()
    keyboard_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("和小橘说话 · BuddyDesk")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.docked = False
        self.setObjectName("doubaoInputCard")
        self.setStyleSheet("QDialog#doubaoInputCard {background:transparent;}"
                          "QWidget {font-family:'Microsoft YaHei UI';background:transparent;}"
                          "QPlainTextEdit#islandVoiceEditor {background:transparent;border:none;padding:0;color:#f0f0f3;font-size:13px;selection-background-color:#414851;}"
                          "QLabel {background:transparent;color:#aeb3ba;font-size:10px;}"
                          "QPushButton#voiceFinish {background:transparent;color:#e2e5e9;border:none;padding:0;border-radius:6px;font-size:11px;}"
                          "QPushButton#voiceFinish:hover {background:rgba(255,255,255,18);color:#ffffff;}"
                          "QPushButton#voiceFinish:pressed {background:rgba(255,255,255,28);}"
                          "QPushButton#voiceFinish:disabled {color:#7c828b;}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 12, 18, 12)
        layout.setSpacing(2)
        header = QHBoxLayout()
        header.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(4, 4)
        dot.setStyleSheet("background:#a1c6a7;border-radius:2px;")
        header.addWidget(dot)
        self.status = QLabel("小橘在听")
        self.status.setWordWrap(False)
        self.status.setFixedHeight(18)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        header.addWidget(self.status, 1)
        from ui.icon_widgets import WindowControlButton
        self.cancel_button = WindowControlButton("close", "#8c8d95", "#292a2e", "#f0f0f3", self)
        self.cancel_button.setFixedSize(18, 18)
        self.cancel_button.setAccessibleName("取消语音输入")
        self.cancel_button.mousePressEvent = lambda event: self.cancel_requested.emit() if event.button() == Qt.MouseButton.LeftButton else None
        header.addWidget(self.cancel_button)
        layout.addLayout(header)
        self.editor = _Receiver()
        self.editor.submit.connect(self.finish_requested.emit)
        self.editor.setObjectName("islandVoiceEditor")
        self.editor.setAccessibleName("豆包语音接收区")
        self.editor.setPlaceholderText("说点什么，或直接输入…")
        self.editor.setFixedHeight(40)
        self.editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        palette = self.editor.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#a4aab2"))
        self.editor.setPalette(palette)
        layout.addWidget(self.editor)
        buttons = QHBoxLayout()
        self.hint = QLabel("右 Alt 说话 · Ctrl+Enter 发送")
        buttons.addWidget(self.hint, 1)
        self.keyboard_button = QPushButton("输入")
        self.keyboard_button.setFixedSize(34, 26)
        self.keyboard_button.setStyleSheet("color:#aaa19b;background:transparent;border:none;padding:0;font-size:10px;")
        self.keyboard_button.clicked.connect(self.keyboard_requested.emit)
        self.keyboard_button.hide()
        buttons.addWidget(self.keyboard_button)
        self.finish_button = QPushButton("发送")
        self.finish_button.setObjectName("voiceFinish")
        self.finish_button.setAccessibleName("发送给小橘")
        self.finish_button.setToolTip("发送 · Ctrl+Enter")
        self.finish_button.setFixedSize(40, 24)
        self.finish_button.clicked.connect(self.finish_requested.emit)
        buttons.addWidget(self.finish_button)
        layout.addLayout(buttons)

    def paintEvent(self, event):
        if self.docked:
            painter = QPainter(self)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
            painter.end()
            return
        from ui.window_surface import paint_window_surface
        paint_window_surface(self, dark=True)

    def set_docked(self, docked):
        if self.docked != docked:
            self.docked = docked
            self.update()

    def reject(self):
        self.cancel_requested.emit()


class DoubaoInput(QObject):
    partial = Signal(str)
    final = Signal(str)
    failed = Signal(str)
    state_changed = Signal(str)
    cancelled = Signal()
    direct_finished = Signal()
    keyboard_requested = Signal()
    setup_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False
        self.finishing = False
        self._retry_mode = False
        self.direct_mode = False
        self._needs_setup = False
        self.input_session = ""
        self._dock_enabled = bool(getattr(getattr(parent, "main", None), "winisland", None))
        self._dock_deadline = 0.0
        self._last_surface_rect = None
        self.card = InputCard()
        self._fade = QPropertyAnimation(self.card, b"windowOpacity", self)
        self._fade.setDuration(140)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._dock_timer = QTimer(self)
        self._dock_timer.setInterval(50)
        self._dock_timer.timeout.connect(self._sync_surface)
        self.card.editor.preview.connect(self.partial.emit)
        self.card.editor.textChanged.connect(self._changed)
        self.card.finish_requested.connect(self.finish)
        self.card.cancel_requested.connect(self._request_cancel)
        self.card.keyboard_requested.connect(lambda: self.setup_requested.emit() if self._needs_setup else self.keyboard_requested.emit())
        self._profile = None
        self._previous_window = None
        self._generation = 0
        self._last_change = 0.0
        self._finish_started = 0.0
        self._commit_timer = QTimer(self)
        self._commit_timer.setInterval(150)
        self._commit_timer.timeout.connect(self._check_commit)

    def start(self):
        identity = installed_profile()
        if not identity:
            self.failed.emit("没有检测到豆包输入法，请安装后再使用")
            return False
        u = ctypes.windll.user32
        u.GetForegroundWindow.restype = ctypes.c_void_p
        self._previous_window = u.GetForegroundWindow()
        self._generation += 1
        self.active, self.finishing = True, False
        self._retry_mode = False
        self.direct_mode, self._needs_setup = False, False
        self.card.editor.setReadOnly(False)
        self.card.keyboard_button.hide()
        self.card.editor.clear()
        self.card.finish_button.setEnabled(True)
        self.card.finish_button.setText("发送")
        self.card.finish_button.setToolTip("发送 · Ctrl+Enter")
        self.card.hint.setText("右 Alt 说话 · Ctrl+Enter 发送")
        self.card.status.setText("小橘在听")
        self.card.status.setToolTip("")
        self._show_card()
        generation = self._generation
        QTimer.singleShot(300, lambda: self._trigger(identity, generation, time.monotonic()))
        self.state_changed.emit("listening")
        return True

    def _show_card(self, activate=True):
        self.input_session = uuid.uuid4().hex if self._dock_enabled else ""
        self._last_surface_rect = None
        self._dock_deadline = time.monotonic() + 1.5
        self._fade.stop()
        self.card.set_docked(False)
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.card.resize(min(360, area.width() - 32), 112)
        self.card.move(area.center().x() - self.card.width() // 2, area.top() + 12)
        surface = self._read_surface() if self._dock_enabled else None
        self.card.setWindowOpacity(0.0 if self._dock_enabled else 1.0)
        self.card.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not activate)
        self.card.show()
        if surface:
            self._place_surface(surface)
        if self._dock_enabled:
            self._dock_timer.start()
        if activate:
            self.card.raise_()
            self.card.activateWindow()
            self.card.editor.setFocus()

    def show_direct(self, cloud=False):
        ctypes.windll.user32.GetForegroundWindow.restype = ctypes.c_void_p
        self._previous_window = ctypes.windll.user32.GetForegroundWindow()
        self._generation += 1
        self.active, self.finishing, self.direct_mode, self._retry_mode = True, False, True, False
        self._needs_setup = False
        self.card.editor.clear()
        self.card.editor.setReadOnly(True)
        self.card.status.setText("正在听 · 云端识别" if cloud else "正在听 · 本地识别")
        self.card.status.setToolTip("")
        self.card.hint.setText("Alt+F 结束 · Esc 取消")
        self.card.keyboard_button.setText("输入")
        self.card.keyboard_button.show()
        self.card.finish_button.setText("结束")
        self.card.finish_button.setToolTip("结束录音并发送 · Alt+F")
        self.card.finish_button.setEnabled(True)
        self._show_card(activate=False)

    def update_direct(self, text):
        if self.active and self.direct_mode:
            blocked = self.card.editor.blockSignals(True)
            self.card.editor.setPlainText(text)
            cursor = self.card.editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.card.editor.setTextCursor(cursor)
            self.card.editor.blockSignals(blocked)

    def direct_transcribing(self):
        if self.active and self.direct_mode:
            self.finishing = True
            self.card.status.setText("正在识别…")
            self.card.finish_button.setEnabled(False)

    def use_keyboard(self, message="直接输入", needs_setup=False):
        self.direct_mode, self.finishing, self._retry_mode = False, False, True
        self._needs_setup = needs_setup
        self.card.editor.setReadOnly(False)
        self.card.status.setText(message)
        self.card.hint.setText("Ctrl+Enter 发送 · Esc 取消")
        self.card.keyboard_button.setText("设置")
        self.card.keyboard_button.setVisible(needs_setup)
        self.card.finish_button.setText("发送")
        self.card.finish_button.setEnabled(True)
        self.card.finish_button.setToolTip("发送 · Ctrl+Enter")
        self.card.activateWindow()
        self.card.editor.setFocus()

    def close_direct(self):
        if self.active and self.direct_mode:
            self._close()

    def _read_surface(self):
        path = Path.home() / ".buddydesk" / "winisland" / "input-surface.json"
        try:
            if path.stat().st_size > 4096:
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("protocol_version") != 1:
                return None
            stamp, pid = data.get("updated_at_ms"), data.get("pid")
            if type(stamp) is not int or type(pid) is not int or pid <= 0 or not -1000 <= time.time() * 1000 - stamp <= 3000:
                return None
            for key in ("x", "y", "width", "height", "dpi"):
                if type(data.get(key)) not in (int, float) or not math.isfinite(data[key]):
                    return None
            if not (160 <= data["width"] <= 4096 and 64 <= data["height"] <= 1024 and 0.5 <= data["dpi"] <= 8):
                return None
            if abs(data["x"]) > 100000 or abs(data["y"]) > 100000:
                return None
            from winisland_bridge import _process_alive
            return data if _process_alive(pid) else None
        except (OSError, ValueError, TypeError, UnicodeError):
            return None

    def _place_surface(self, surface):
        geometry = tuple(round(surface[key]) for key in ("x", "y", "width", "height"))
        key = (*geometry, surface["dpi"])
        if key == self._last_surface_rect:
            return True
        self.card.resize(round(surface["width"] / surface["dpi"]), round(surface["height"] / surface["dpi"]))
        if sys.platform == "win32":
            set_position = ctypes.windll.user32.SetWindowPos
            set_position.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_uint)
            if not set_position(int(self.card.winId()), -1, *geometry, 0x0010 | 0x0200):
                return False
        else:
            self.card.move(geometry[0], geometry[1])
        self._last_surface_rect = key
        return True

    def _reveal_controls(self):
        if self.card.windowOpacity() >= 1.0 or self._fade.state() == QPropertyAnimation.State.Running:
            return
        parent = self.parent()
        if getattr(getattr(parent, "main", None), "_user_config", {}).get("agent_reduced_motion", False):
            self.card.setWindowOpacity(1.0)
            return
        self._fade.setStartValue(self.card.windowOpacity())
        self._fade.setEndValue(1.0)
        self._fade.start()

    def _sync_surface(self):
        if not self.active:
            self._dock_timer.stop()
            return
        surface = self._read_surface()
        matches = surface and surface.get("active") is True and surface.get("input_session") == self.input_session
        if matches and surface.get("ready") is True:
            self.card.set_docked(bool(self._place_surface(surface)))
            self._reveal_controls()
        elif self.card.docked:
            self.card.set_docked(False)
            self._reveal_controls()
        elif time.monotonic() >= self._dock_deadline:
            self.card.set_docked(False)
            self._reveal_controls()

    def reopen_for_retry(self, text, message):
        if self.active:
            self._close()
        ctypes.windll.user32.GetForegroundWindow.restype = ctypes.c_void_p
        self._previous_window = ctypes.windll.user32.GetForegroundWindow()
        self._generation += 1
        self.active, self.finishing, self._retry_mode = True, False, True
        self.direct_mode, self._needs_setup = False, False
        self.card.editor.setReadOnly(False)
        self.card.keyboard_button.hide()
        self.card.editor.setPlainText(text)
        self.card.status.setText("没能回应，内容已保留")
        self.card.status.setToolTip(message)
        self.card.hint.setText("可修改内容 · Ctrl+Enter 重试")
        self.card.finish_button.setText("发送")
        self.card.finish_button.setToolTip("重试 · Ctrl+Enter")
        self.card.finish_button.setEnabled(True)
        self._show_card()

    def _owns_focus(self):
        ctypes.windll.user32.GetForegroundWindow.restype = ctypes.c_void_p
        return ctypes.windll.user32.GetForegroundWindow() == int(self.card.winId())

    def _trigger(self, identity, generation, started):
        if generation != self._generation or not self.active:
            return
        if ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000:
            if time.monotonic() - started < 2:
                QTimer.singleShot(50, lambda: self._trigger(identity, generation, started))
            return
        if not self._owns_focus():
            self.card.status.setText("点击输入区，按住右 Alt 说话")
            return
        try:
            self._profile = _InputProfile(identity)
        except (OSError, ValueError) as error:
            self.card.status.setText(str(error))

    def _changed(self):
        self._last_change = time.monotonic()
        if self.active:
            self.partial.emit(self.card.editor.toPlainText())

    def finish(self):
        if not self.active or self.finishing:
            return
        if self.direct_mode:
            self.direct_transcribing()
            self.direct_finished.emit()
            return
        if self._retry_mode:
            QApplication.inputMethod().commit()
            text = self.card.editor.toPlainText().strip()
            if not text:
                self.card.status.setText("先说说你想聊什么")
                self.card.editor.setFocus()
                return
            self._close()
            self.final.emit(text)
            return
        self.finishing = True
        self.card.finish_button.setEnabled(False)
        self.card.status.setText("正在接收文字…")
        self.card.editor.setFocus()
        generation = self._generation
        QTimer.singleShot(100, lambda: self._request_commit(generation))
        self.state_changed.emit("transcribing")

    def _request_commit(self, generation):
        if generation != self._generation or not self.active:
            return
        if ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000:
            QTimer.singleShot(60, lambda: self._request_commit(generation))
            return
        if not self._owns_focus():
            self.finishing = False
            self.card.finish_button.setEnabled(True)
            self.card.status.setText("请回到输入区核对文字，再点“发送”")
            self.state_changed.emit("listening")
            return
        QApplication.inputMethod().commit()
        self._finish_started = time.monotonic()
        self._last_change = self._finish_started
        self._commit_timer.start()

    def _check_commit(self):
        now = time.monotonic()
        text = self.card.editor.toPlainText().strip()
        if text and now - self._last_change >= 1.2 and now - self._finish_started >= 1.8:
            self._close()
            self.final.emit(text)
        elif now - self._finish_started >= 12:
            self._commit_timer.stop()
            self.finishing = False
            self.card.finish_button.setEnabled(True)
            self.card.status.setText("还没有收到文字，可继续输入或重新唤起豆包语音")
            self.state_changed.emit("listening")

    def cancel(self):
        if not self.active:
            return
        if self._profile and self._owns_focus():
            u = ctypes.windll.user32
            u.keybd_event(0x1B, 0, 0, 0)
            u.keybd_event(0x1B, 0, 2, 0)
        self._close()
        self.state_changed.emit("idle")

    def _request_cancel(self):
        self.cancel()
        self.cancelled.emit()

    def _close(self):
        restore_focus = self._owns_focus()
        self.active, self.finishing = False, False
        self.direct_mode = False
        self._retry_mode = False
        self.input_session = ""
        self._dock_timer.stop()
        self._fade.stop()
        self._generation += 1
        self._commit_timer.stop()
        self.card.hide()
        if self._profile:
            self._profile.close()
            self._profile = None
        if self._previous_window and restore_focus:
            ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(self._previous_window))
