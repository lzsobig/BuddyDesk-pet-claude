from __future__ import annotations

import ctypes
import json
import logging
import math
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtGui import QIcon, QWindow

import config as cfg
from ui.settings_panel import SettingsPanel
from winisland_bridge import _process_alive, _write_atomic


logger = logging.getLogger(__name__)
PAGES = ("connection", "preferences", "voice", "pet")
DIRECTORY = Path.home() / ".buddydesk" / "winisland"


def _read_json(name):
    path = DIRECTORY / name
    if path.stat().st_size > 4096:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) and data.get("protocol_version") == 1 else None


def _fresh_process(data):
    pid = data.get("pid")
    stamp = data.get("updated_at_ms")
    age = int(time.time() * 1000) - stamp if type(stamp) is int else 10000
    return type(pid) is int and pid > 0 and -1000 <= age <= 3000 and _process_alive(pid)


def native_input_healthy():
    try:
        data = _read_json("input-surface.json")
        return bool(data and _fresh_process(data))
    except (OSError, UnicodeError, ValueError, TypeError):
        return False


def _valid_window(hwnd, pid):
    if sys.platform != "win32":
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = (ctypes.c_void_p,)
    user32.IsWindow.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = (ctypes.c_void_p,)
    user32.IsWindowVisible.restype = ctypes.c_int
    user32.IsIconic.argtypes = (ctypes.c_void_p,)
    user32.IsIconic.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
    user32.GetWindowThreadProcessId.restype = ctypes.c_uint32
    user32.GetWindowTextW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    owner = ctypes.c_uint32()
    title = ctypes.create_unicode_buffer(128)
    handle = ctypes.c_void_p(hwnd)
    return (bool(user32.IsWindow(handle)) and bool(user32.IsWindowVisible(handle))
            and not user32.IsIconic(handle)
            and bool(user32.GetWindowThreadProcessId(handle, ctypes.byref(owner)))
            and owner.value == pid and user32.GetWindowTextW(handle, title, len(title)) > 0
            and title.value == "WinIsland Settings")


def read_settings_surface():
    try:
        data = _read_json("settings-surface.json")
        if not data or type(data.get("active")) is not bool:
            return None
        if not data["active"]:
            return None
        if data.get("page") not in PAGES:
            return None
        hwnd = data.get("hwnd")
        if type(hwnd) is not int or hwnd <= 0 or not _valid_window(hwnd, data["pid"]):
            return None
        if not _fresh_process(data) and not _window_moving(hwnd):
            return None
        for key in ("x", "y", "width", "height", "dpi"):
            value = data.get(key)
            if type(value) not in (int, float) or not math.isfinite(value):
                return None
        if (not 160 <= data["width"] <= 8192 or not 100 <= data["height"] <= 8192
                or not 0.5 <= data["dpi"] <= 8
                or abs(data["x"]) > 100000 or abs(data["y"]) > 100000):
            return None
        if type(data.get("is_light")) is not bool:
            return None
        return data
    except (OSError, UnicodeError, ValueError, TypeError):
        return None


def _window_moving(hwnd):
    from ctypes import wintypes

    class ThreadInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                    *[(name, wintypes.HWND) for name in
                      ("active", "focus", "capture", "menu", "move", "caret")],
                    ("caret_rect", wintypes.RECT)]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetGUIThreadInfo.argtypes = (wintypes.DWORD, ctypes.POINTER(ThreadInfo))
    user32.GetGUIThreadInfo.restype = wintypes.BOOL
    thread = user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), None)
    info = ThreadInfo()
    info.cbSize = ctypes.sizeof(info)
    return bool(thread and user32.GetGUIThreadInfo(thread, ctypes.byref(info))
                and info.flags & 2 and info.move == hwnd)


def _window_geometry(hwnd):
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetClientRect.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.RECT))
    user32.GetClientRect.restype = ctypes.c_int
    user32.ClientToScreen.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.POINT))
    user32.ClientToScreen.restype = ctypes.c_int
    user32.GetDpiForWindow.argtypes = (ctypes.c_void_p,)
    user32.GetDpiForWindow.restype = ctypes.c_uint
    rect = wintypes.RECT()
    origin = wintypes.POINT()
    handle = ctypes.c_void_p(hwnd)
    dpi = user32.GetDpiForWindow(handle) / 96
    if not dpi or not user32.GetClientRect(handle, ctypes.byref(rect)):
        return None
    if not user32.ClientToScreen(handle, ctypes.byref(origin)):
        return None
    geometry = (origin.x + round(184 * dpi), origin.y + round(64 * dpi),
                rect.right - rect.left - round(196 * dpi),
                rect.bottom - rect.top - round(76 * dpi))
    return (geometry, dpi) if geometry[2] >= 160 and geometry[3] >= 100 else None


class NativeSettingsDock(QObject):
    def __init__(self, main_app):
        super().__init__(main_app.app)
        self.main_app = main_app
        self.panel = None
        self._host_window = None
        self._host_hwnd = None
        self._geometry = None
        self._page = None
        self._is_light = None
        self.suspended = False
        self._request_id = None
        self._request_page = None
        self._docked_request_id = None
        self._closing_panels = {}
        self._surface = None
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.poll)
        self._timer.start()
        self._position_timer = QTimer(self)
        self._position_timer.setInterval(16)
        self._position_timer.timeout.connect(self._sync_position)
        main_app.app.aboutToQuit.connect(self.close)

    def request(self, page):
        if not native_input_healthy():
            return None
        try:
            request_id = uuid4().hex
            _write_atomic(DIRECTORY, "native-settings-request.json", {
                "protocol_version": 1,
                "id": request_id,
                "issued_at_ms": int(time.time() * 1000),
                "page": PAGES[page],
            })
            self._request_id = request_id
            self._request_page = PAGES[page]
            self.poll()
            return request_id
        except (OSError, IndexError) as error:
            logger.warning("Native settings request failed: %s", type(error).__name__)
            return None

    def needs_fallback(self, request_id):
        return request_id == self._request_id and request_id != self._docked_request_id

    def poll(self):
        if self.suspended:
            self._position_timer.stop()
            if self.panel is not None:
                self.panel.hide()
            return
        surface = read_settings_surface()
        if surface is None:
            self._position_timer.stop()
            self._surface = None
            if self.panel is not None:
                self.panel.hide()
            self._geometry = None
            return
        if self.panel is None:
            self.panel = SettingsPanel(self.main_app._user_config, dock_mode=True)
            icon = Path(cfg.ASSETS_DIR) / "buddydesk.ico"
            if icon.is_file():
                self.panel.setWindowIcon(QIcon(str(icon)))
            self.panel.saved.connect(self.main_app._on_settings_saved)
        hwnd = surface["hwnd"]
        if hwnd != self._host_hwnd:
            self._host_window = QWindow.fromWinId(hwnd)
            if self._host_window is None:
                self.panel.hide()
                return
            self.panel.winId()
            self.panel.windowHandle().setTransientParent(self._host_window)
            self._host_hwnd = hwnd
            self._geometry = None
        page = PAGES.index(surface["page"])
        if page != self._page:
            self.panel._select_settings_page(page)
            self._page = page
        if surface["is_light"] != self._is_light:
            self.panel.set_native_light(surface["is_light"])
            self._is_light = surface["is_light"]
        self._surface = surface
        self._sync_position()
        self._position_timer.start()
        if self.panel.isVisible() and surface["page"] == self._request_page:
            self._docked_request_id = self._request_id

    def _sync_position(self):
        if self.panel is None or self._surface is None or self.suspended:
            return
        if not _valid_window(self._surface["hwnd"], self._surface["pid"]):
            self.panel.hide()
            self._geometry = None
            return
        live = _window_geometry(self._surface["hwnd"])
        if live is None:
            self.panel.hide()
            self._geometry = None
            return
        geometry, dpi = live
        geometry_key = (*geometry, dpi)
        if geometry_key != self._geometry or not self.panel.isVisible():
            self.panel.resize(round(geometry[2] / dpi), round(geometry[3] / dpi))
            if not self.panel.isVisible():
                self.panel.show()
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.SetWindowPos.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint)
            user32.SetWindowPos.restype = ctypes.c_int
            if user32.SetWindowPos(ctypes.c_void_p(int(self.panel.winId())), None,
                                   *geometry, 0x0010 | 0x0004 | 0x0200):
                self._geometry = geometry_key
            else:
                self.panel.hide()

    def is_docked(self):
        return self.panel is not None and self.panel.isVisible() and read_settings_surface() is not None

    def discard_panel(self):
        panel = self.panel
        if panel is None:
            return
        self.panel = None
        self._position_timer.stop()
        self._surface = None
        self._closing_panels[panel] = self._host_window
        self._host_window = None
        self._host_hwnd = None
        self._geometry = None
        self._page = None
        self._is_light = None
        panel.finished.connect(lambda _result, old_panel=panel: self._finish_panel(old_panel))
        panel.hide()
        panel.reject()

    def _finish_panel(self, panel):
        self._closing_panels.pop(panel, None)
        panel.deleteLater()

    def close(self):
        self._timer.stop()
        self._position_timer.stop()
        self.discard_panel()
