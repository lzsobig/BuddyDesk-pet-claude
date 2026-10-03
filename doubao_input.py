from __future__ import annotations

import ctypes
import sys
import time
import uuid

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPalette
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout


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

    def inputMethodEvent(self, event):
        super().inputMethodEvent(event)
        body = self.toPlainText()
        cursor = self.textCursor().position()
        self.preview.emit(body[:cursor] + event.preeditString() + body[cursor:])


class InputCard(QDialog):
    finish_requested = Signal()
    cancel_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("豆包语音 · BuddyDesk")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("doubaoInputCard")
        self.setStyleSheet("QDialog#doubaoInputCard {background:transparent;}"
                          "QDialog#doubaoInputCard QWidget {font-family:'Microsoft YaHei UI';}"
                          "QPlainTextEdit#islandVoiceEditor {background:transparent;border:none;padding:0;color:#f0f0f3;font-size:15px;selection-background-color:#63472f;}"
                          "QLabel {background:transparent;color:#a8a9b2;font-size:11px;}"
                          "QPushButton#voiceFinish {background:#f2ae6f;color:#171411;border:none;padding:0;border-radius:11px;font-size:12px;font-weight:600;}"
                          "QPushButton#voiceFinish:hover {background:#ffc18b;}"
                          "QPushButton#voiceFinish:pressed {background:#dc9960;}"
                          "QPushButton#voiceFinish:disabled {background:#302923;color:#9d8877;}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 23, 28, 23)
        layout.setSpacing(9)
        header = QHBoxLayout()
        header.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(6, 6)
        dot.setStyleSheet("background:#a1c6a7;border-radius:3px;")
        header.addWidget(dot)
        self.status = QLabel("豆包语音")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        header.addWidget(self.status, 1)
        from ui.icon_widgets import WindowControlButton
        self.cancel_button = WindowControlButton("close", "#8c8d95", "#292a2e", "#f0f0f3", self)
        self.cancel_button.setAccessibleName("取消语音输入")
        self.cancel_button.mousePressEvent = lambda event: self.cancel_requested.emit() if event.button() == Qt.MouseButton.LeftButton else None
        header.addWidget(self.cancel_button)
        layout.addLayout(header)
        self.editor = _Receiver()
        self.editor.setObjectName("islandVoiceEditor")
        self.editor.setAccessibleName("豆包语音接收区")
        self.editor.setPlaceholderText("说说接下来想做的事…")
        self.editor.setFixedHeight(58)
        self.editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        palette = self.editor.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8c8d96"))
        self.editor.setPalette(palette)
        layout.addWidget(self.editor)
        buttons = QHBoxLayout()
        hint = QLabel("按住右 Alt 说话")
        buttons.addWidget(hint, 1)
        self.finish_button = QPushButton("整理  ↗")
        self.finish_button.setObjectName("voiceFinish")
        self.finish_button.setAccessibleName("整理事项")
        self.finish_button.setFixedSize(82, 32)
        self.finish_button.clicked.connect(self.finish_requested.emit)
        buttons.addWidget(self.finish_button)
        layout.addLayout(buttons)

    def paintEvent(self, event):
        from ui.window_surface import paint_window_surface
        paint_window_surface(self, dark=True)

    def reject(self):
        self.cancel_requested.emit()


class DoubaoInput(QObject):
    partial = Signal(str)
    final = Signal(str)
    failed = Signal(str)
    state_changed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False
        self.finishing = False
        self.card = InputCard()
        self.card.editor.preview.connect(self.partial.emit)
        self.card.editor.textChanged.connect(self._changed)
        self.card.finish_requested.connect(self.finish)
        self.card.cancel_requested.connect(self._request_cancel)
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
        self.card.editor.clear()
        self.card.finish_button.setEnabled(True)
        self.card.status.setText("豆包语音")
        self.card.status.setToolTip("")
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.card.resize(min(440, area.width() - 40), 184)
        self.card.move(area.center().x() - self.card.width() // 2, area.bottom() - self.card.height() - 24)
        self.card.show()
        self.card.raise_()
        self.card.activateWindow()
        self.card.editor.setFocus()
        generation = self._generation
        QTimer.singleShot(300, lambda: self._trigger(identity, generation, time.monotonic()))
        self.state_changed.emit("listening")
        return True

    def _owns_focus(self):
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
        self.finishing = True
        self.card.finish_button.setEnabled(False)
        self.card.status.setText("正在接收豆包的最终文字…")
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
            self.card.status.setText("请回到输入区核对文字，再点“整理事项”")
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
        if self._owns_focus():
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
        self._generation += 1
        self._commit_timer.stop()
        self.card.hide()
        if self._profile:
            self._profile.close()
            self._profile = None
        if self._previous_window and restore_focus:
            ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(self._previous_window))
