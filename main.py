"""
BuddyDesk — Main Entry Point (PySide6)

Windows 桌面 AI 伴侣 — 灵动岛 + 像素宠物 + AI 聊天 + 命令执行
"""
import sys
import os
import io

# Enable per-monitor DPI awareness on Windows for crisp rendering
if sys.platform == "win32":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor V2
    except Exception:
        try:
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from config import load_user_config
from bridge import AIBridge
from engine.command_engine import CommandEngine
from ui.launcher import LauncherDialog
from ui.chat_window import ChatWindow
from ui.dynamic_island import DynamicIsland
from ui.pixel_pet import PixelPet
from ui.tray import SystemTray
from theme import get_stylesheet


class BuddyDeskApp:
    """BuddyDesk 主应用 (PySide6)"""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(True)  # close chat → quit app
        self.app.setStyleSheet(get_stylesheet())

        self.bridge = None
        self.command_engine = None
        self.chat = None
        self.island = None
        self.pet = None
        self.tray = None
        self._keyboard_registered = False

    def run(self):
        """Run the application."""
        # Step 1: Show launcher
        launcher = LauncherDialog()
        # Center on the primary screen so the user always finds it.
        scr = self.app.primaryScreen().availableGeometry()
        launcher.move(
            scr.x() + (scr.width() - launcher.width()) // 2,
            scr.y() + (scr.height() - launcher.height()) // 2,
        )
        if launcher.exec() != LauncherDialog.DialogCode.Accepted:
            return

        user_config = launcher.result_config

        # Step 2: Create bridge (AI + EventEngine)
        self.bridge = AIBridge(user_config)
        self.command_engine = CommandEngine(self.bridge.event_engine)

        # Step 3: Initialize UI components
        if user_config.get("chat_enabled", True):
            self.chat = ChatWindow(self.bridge)
            # Wire command engine to chat — connects BEFORE chat's own _on_done
            # so commands are processed first, then the send button re-enables.
            self.bridge.stream_done.connect(self._process_commands)

        if user_config.get("island_enabled", True):
            self.island = DynamicIsland(on_click=self._toggle_chat)
            self.island.show()

        if user_config.get("pet_enabled", True):
            self.pet = PixelPet(on_double_click=self._toggle_chat)
            self.pet.pet_name = user_config.get("pet_name", "小橘")
            self.pet.name_label.setText(self.pet.pet_name)
            self.pet.show()
            self.pet.say(f"Hi! 我是{self.pet.pet_name}~", 5000)

        # Step 4: System tray
        self.tray = SystemTray(
            on_toggle_chat=self._toggle_chat,
            on_quit=self._quit,
        )
        self.tray.show()

        # Step 5: Global hotkeys
        self._setup_hotkeys()

        # Step 6: Connect state changes to island, tray, and pet
        self.bridge.state_changed.connect(self._on_state_change)

        # Show chat by default
        if self.chat:
            scr = self.app.primaryScreen().availableGeometry()
            self.chat.move(
                scr.x() + (scr.width() - self.chat.width()) // 2,
                scr.y() + (scr.height() - self.chat.height()) // 2,
            )
            self.chat.show()
            if self.tray:
                self.tray.set_chat_visible(True)

        print(f"\n{'='*55}")
        print(f"  BuddyDesk")
        print(f"  Backend: {self.bridge.backend.get_name()}")
        print(f"  Hotkey: Ctrl+F")
        print(f"{'='*55}\n")

        self.app.exec()

    def _toggle_chat(self):
        if self.chat:
            self.chat.toggle_visibility()
            if self.tray:
                self.tray.set_chat_visible(self.chat.isVisible())
            if self.chat.isVisible() and self.pet:
                self.pet.set_state("happy")
                self.pet.say("来聊天啦~", 2000)

    def _on_state_change(self, state, preview=""):
        if self.island:
            self.island.set_state(state, preview)
        if self.tray:
            self.tray.update_state(state, preview)
        if self.pet:
            if state == "thinking":
                self.pet.set_state("think")
                self.pet.say("思考中...", 3000)
            elif state == "idle" and preview:
                self.pet.set_state("happy")
                self.pet.say("搞定!", 2000)
            elif state == "error":
                self.pet.set_state("sad")
                self.pet.say("出错了...", 3000)

    def _process_commands(self, full_text):
        """Parse AI response for command tags and execute them."""
        if not self.command_engine:
            return

        results = self.command_engine.parse_and_execute(full_text)
        for result in results:
            if self.chat:
                self.chat.append_command_result(
                    result.command,
                    result.success,
                    result.output if result.success else result.error,
                )

    def _setup_hotkeys(self):
        """Poll GetAsyncKeyState for Ctrl+F — works without admin, no third-party lib."""
        if sys.platform != "win32":
            return
        try:
            from ctypes import windll
            self._user32 = windll.user32
            self._hotkey_pressed = False
            def _poll():
                ctrl = self._user32.GetAsyncKeyState(0x11) & 0x8000  # VK_CONTROL
                f = self._user32.GetAsyncKeyState(0x46) & 0x8000    # VK_F
                if ctrl and f and not self._hotkey_pressed:
                    self._hotkey_pressed = True
                    self._toggle_chat()
                elif not (ctrl and f):
                    self._hotkey_pressed = False
            from PySide6.QtCore import QTimer
            self._hotkey_timer = QTimer()
            self._hotkey_timer.timeout.connect(_poll)
            self._hotkey_timer.start(30)
            self._keyboard_registered = True
        except Exception as e:
            print(f"Hotkey setup failed: {e}")

    def _quit(self):
        """Clean up hotkey, tray, and app, then exit."""
        if hasattr(self, "_hotkey_timer"):
            self._hotkey_timer.stop()
        self._keyboard_registered = False
        """Clean up keyboard hooks, tray, and app, then exit."""
        if hasattr(self, '_hotkey_listener') and self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._keyboard_registered = False

        if self.tray:
            try:
                self.tray.hide()
            except Exception:
                pass

        if self.bridge:
            try:
                self.bridge.cancel()
            except Exception:
                pass

        self.app.quit()


def main():
    app = BuddyDeskApp()
    app.run()


if __name__ == "__main__":
    main()
