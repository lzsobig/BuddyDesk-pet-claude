"""
BuddyDesk — Main Entry Point (PySide6)

Windows 桌面 AI 伴侣 — 灵动岛 + 像素宠物 + AI 聊天 + 命令执行
"""
import sys
import os
import io
import logging
import threading
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── Qt bootstrap (must run before any PySide6 import) ──────────────────────
# Pin the Qt platform plugin path to the PySide6 install so that stray Qt
# DLLs on PATH (e.g. from WeChat/QQ installers) can never shadow the correct
# plugin, which otherwise surfaces as:
#   "This application failed to start because no Qt platform plugin
#    could be initialized ... Available platform plugins are: windows."
def _bootstrap_qt():
    try:
        import importlib.util
        spec = importlib.util.find_spec("PySide6")
        if spec is not None and spec.submodule_search_locations:
            base = list(spec.submodule_search_locations)[0]
            plugins = os.path.join(base, "plugins")
            if os.path.isdir(plugins):
                os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugins
        # Never inherit a stale QPA platform from the environment.
        os.environ.pop("QT_QPA_PLATFORM", None)
    except Exception:
        pass


_bootstrap_qt()

# Let Qt handle DPI awareness natively — avoids the
# "SetProcessDpiAwarenessContext() failed: 拒绝访问" warning that occurs
# when both our shcore call and Qt's internal init compete for the same setting.
# Qt 6 defaults to DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 which is what we want.
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, QTimer, QObject, Signal, QLockFile
from PySide6.QtGui import QIcon, QFont

from config import load_user_config
from bridge import AIBridge
from engine.command_engine import CommandEngine
from ui.launcher import LauncherDialog
from ui.chat_window import ChatWindow
from ui.dynamic_island import DynamicIsland
from ui.pixel_pet import PixelPet
from ui.tray import SystemTray
from ui.confirm_dialog import ConfirmDialog
from ui.settings_panel import SettingsPanel
from ui.pin_card import PinManager
import audio
import config as cfg


class _VoiceBridge(QObject):
    """Thread-safe bridge for voice recognition results.
    Background ASR thread emits signal → main thread slot receives it."""
    recognized = Signal(str)
    state_changed = Signal(str)


class _CommandBridge(QObject):
    """Marshal confirmed command results from worker threads to the UI."""
    finished = Signal(str, bool, str)


class BuddyDeskApp:
    """BuddyDesk 主应用 (PySide6)"""

    def __init__(self):
        # 复用已存在的 QApplication（如有），避免双实例错误
        self.app = QApplication.instance() or QApplication(sys.argv)
        self._winisland_mode = "--winisland" in sys.argv
        self._show_chat_on_start = "--show-chat" in sys.argv
        self._background_mode = "--background" in sys.argv or not self._show_chat_on_start
        self.app.setQuitOnLastWindowClosed(False)
        self._instance_lock = None

        # Set app icon (taskbar + Alt-Tab)
        _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "assets", "buddydesk.ico")
        if os.path.exists(_icon_path):
            self.app.setWindowIcon(QIcon(_icon_path))

        from theme import get_stylesheet
        ui_font = QFont("Microsoft YaHei UI")
        ui_font.setPixelSize(14)
        self.app.setFont(ui_font)
        self.app.setStyleSheet(get_stylesheet())

        self.bridge = None
        self.command_engine = None
        self.chat = None
        self.island = None
        self.pet = None
        self.tray = None
        self.winisland = None
        self._settings_dialog = None
        self.pin_manager = None  # P2-3
        self.voice_input = None  # P3-6
        self.agent = None
        self._keyboard_registered = False
        self._user_config: dict = {}
        self._clipboard_last: str = ""
        self._command_bridge = _CommandBridge()
        self._command_bridge.finished.connect(self._on_command_finished)

    def run(self):
        """Run the application."""
        from winisland_bridge import request_existing_chat, _write_atomic
        from pathlib import Path
        from uuid import uuid4
        import time
        if request_existing_chat(open_chat=self._show_chat_on_start):
            return
        os.makedirs(cfg.CONFIG_DIR, exist_ok=True)
        self._instance_lock = QLockFile(os.path.join(cfg.CONFIG_DIR, "agent-instance.lock"))
        self._instance_lock.setStaleLockTime(0)
        if not self._instance_lock.tryLock(0):
            if self._show_chat_on_start:
                _write_atomic(Path(cfg.CONFIG_DIR) / "winisland", "commands.json", {
                    "protocol_version": 1, "id": uuid4().hex,
                    "issued_at_ms": int(time.time() * 1000), "action": "open_chat"})
            return
        self.app.aboutToQuit.connect(self._instance_lock.unlock)
        saved = load_user_config()
        needs_setup = getattr(sys, "frozen", False) and not self._has_saved_backend(saved)
        if self._background_mode or self._has_saved_backend(saved):
            self._user_config = saved
        else:
            launcher = LauncherDialog()
            scr = self.app.primaryScreen().availableGeometry()
            launcher.move(
                scr.x() + (scr.width() - launcher.width()) // 2,
                scr.y() + (scr.height() - launcher.height()) // 2,
            )
            if launcher.exec() != LauncherDialog.DialogCode.Accepted:
                return
            self._user_config = launcher.result_config

        # Step 2: Create bridge (AI + EventEngine)
        self.bridge = AIBridge(self._user_config)
        self.command_engine = CommandEngine(
            self.bridge.event_engine,
            user_config=self._user_config,
        )
        # Step 3: Initialize UI components
        if self._show_chat_on_start or self._user_config.get("chat_enabled", True):
            self._ensure_chat()

        if not self._winisland_mode and self._user_config.get("island_enabled", True):
            self.island = DynamicIsland(on_click=self._toggle_chat)
            self.island.show()

        self._apply_pet_settings(self._user_config)

        # Step 4: System tray
        self.tray = SystemTray(
            on_toggle_chat=self._toggle_chat,
            on_quit=self._quit,
            on_settings=self._open_settings,
        )
        self.tray.show()

        # Step 5: Global hotkeys
        self._setup_hotkeys()

        # P3-6: Voice input controller + 闪电说同款悬浮胶囊
        self._voice_bridge = _VoiceBridge()
        self._voice_bridge.recognized.connect(self._on_voice_recognized_main)
        self._voice_bridge.state_changed.connect(self._on_voice_state_main)
        try:
            from voice_input import VoiceInputController
            self.voice_input = VoiceInputController(settings=self._user_config)
            self.voice_input.set_callbacks(
                on_recognized=self._emit_voice_recognized,
                on_state=self._emit_voice_state,
            )
            if self.island:
                self.voice_input.level_emitted.connect(self.island.set_voice_level)
            if not self.voice_input.is_available():
                detail = "依赖未安装"
                try:
                    import sensevoice_asr
                    if not sensevoice_asr.is_model_available():
                        detail = "SenseVoice 模型未找到"
                except ImportError:
                    pass
                print(f"[voice] 语音功能不可用：{detail}")
        except Exception as e:
            print(f"[voice] init failed: {e}")

        # Step 6: Connect state changes to island, tray, pet, and sound
        self.bridge.state_changed.connect(self._on_state_change)
        from winisland_bridge import WinIslandBridge
        self.winisland = WinIslandBridge(self)
        from agent_controller import AgentController
        self.agent = AgentController(self)
        if getattr(sys, "frozen", False) and "--island-running" not in sys.argv:
            native = Path(sys.executable).parent / "_internal" / "bin" / "WinIsland.exe"
            if native.is_file():
                import subprocess
                try:
                    subprocess.Popen([str(native), "--companion"], cwd=str(native.parent),
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                except OSError as error:
                    logger.exception("Bundled WinIsland could not start")
                    QMessageBox.warning(None, "灵动岛启动失败", "请完整解压发布包后重试。\n" + str(error))
        if needs_setup:
            QTimer.singleShot(600, self._open_settings)

        # Step 7: Clipboard monitoring (optional)
        self._clipboard_monitor = self._user_config.get("clipboard_monitor", False)
        if self._clipboard_monitor:
            self._start_clipboard_monitor()

        # Step 8: Auto-update check (async, non-blocking)
        # 已禁用：仓库占位 + 本机 SSL 层连 GitHub 会段错误
        # QTimer.singleShot(3000, self._check_update)

        # P1-4: Crash check on startup
        QTimer.singleShot(5000, self._check_crashes)

        if self.chat and self._show_chat_on_start:
            scr = self.app.primaryScreen().availableGeometry()
            self.chat.move(
                scr.x() + (scr.width() - self.chat.width()) // 2,
                scr.y() + (scr.height() - self.chat.height()) // 2,
            )
            self.chat.show()
            if self.tray:
                self.tray.set_chat_visible(True)

        print(f"\n{'='*55}")
        print(f"  BuddyDesk v{cfg.APP_VERSION}")
        print(f"  Backend: {self.bridge.backend.get_name()}")
        print(f"  Hotkey: Ctrl+Shift+H")
        print(f"{'='*55}\n")

        self.app.exec()

    def _has_saved_backend(self, saved):
        if not os.path.isfile(cfg.CONFIG_PATH):
            return False
        if saved.get("backend") == cfg.BACKEND_OPENAI:
            try:
                endpoint = urlparse(str(saved.get("openai_api_base", "")))
            except ValueError:
                return False
            if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
                return False
            local = endpoint.hostname in {"localhost", "127.0.0.1", "::1"}
            return bool(saved.get("openai_model")) and (local or bool(saved.get("openai_api_key")))
        if saved.get("backend") == cfg.BACKEND_CLAUDE:
            from ai.backend import _find_claude_cli
            cli = str(saved.get("claude_cli_path", cfg.CLAUDE_CLI_PATH))
            endpoint = saved.get("anthropic_api_base") or os.environ.get("ANTHROPIC_BASE_URL")
            token = saved.get("anthropic_api_key") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            return bool(_find_claude_cli(cli)) or bool(endpoint and token)
        return False

    # ── Settings ────────────────────────────────────────────────────
    def _open_settings(self, page=0):
        """Open the settings panel dialog."""
        if not self.bridge:
            return
        if self._settings_dialog is not None:
            self._settings_dialog._select_settings_page(page)
            self._settings_dialog.showNormal()
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        dlg = SettingsPanel(self._user_config, parent=self.chat if self.chat and self.chat.isVisible() else None)
        self._settings_dialog = dlg
        dlg._select_settings_page(page)
        dlg.saved.connect(self._on_settings_saved)
        def finished(_result):
            if self._settings_dialog is dlg:
                self._settings_dialog = None
            dlg.deleteLater()
        dlg.finished.connect(finished)
        dlg.setModal(False)
        dlg.showNormal()
        dlg.raise_()
        dlg.activateWindow()

    def _on_settings_saved(self, new_config: dict):
        """Apply new config from settings panel."""
        backend_keys = ("backend", "openai_api_key", "openai_api_base", "openai_model",
                        "anthropic_api_key", "anthropic_api_base", "claude_cli_path",
                        "claude_model", "working_dir")
        backend_changed = any(self._user_config.get(key) != new_config.get(key) for key in backend_keys)
        if backend_changed and self.chat:
            self.chat._stop_generation()
        self._user_config = new_config
        if self.voice_input:
            self.voice_input.update_settings(new_config)
        if self.agent:
            self.agent.update_settings(new_config)
        if backend_changed:
            self.bridge.update_config(new_config)
        else:
            self.bridge.user_config = new_config
        if self.chat:
            self.chat._pet_title.setText(str(new_config.get("pet_name", "小橘")))

        self._apply_pet_settings(new_config)
        if self.chat:
            self.chat._on_state("thinking" if self.chat._streaming else "idle")
            self.chat.refresh_access_mode()
        if self.winisland:
            self.winisland.refresh_pet()

        # Update clipboard monitoring
        self._clipboard_monitor = new_config.get("clipboard_monitor", False)
        if self._clipboard_monitor:
            self._start_clipboard_monitor()

        # Rebuild command engine with new config
        self.command_engine = CommandEngine(
            self.bridge.event_engine,
            user_config=self._user_config,
        )
        if self.agent:
            from agent_tools import create_registry
            self.agent.tools = create_registry(self.agent.store, self.agent.context, self.command_engine)

    def apply_external_pet_settings(self, new_config: dict, key: str):
        self._user_config = new_config
        if self.bridge:
            self.bridge.user_config = new_config
        if self._settings_dialog:
            self._settings_dialog.apply_external_pet_settings(new_config, key)
        if self.chat:
            self.chat._pet_title.setText(str(new_config.get("pet_name", "小橘")))
            self.chat._refresh_pet_avatar()
        self._apply_pet_settings(new_config)
        if self.winisland:
            self.winisland.refresh_pet()

    def _apply_pet_settings(self, settings):
        enabled = bool(settings.get("pet_enabled", True))
        if enabled and self.pet is None:
            self.pet = PixelPet(on_double_click=self._show_chat, settings=settings)
            self.pet.file_dropped.connect(self._on_pet_file_dropped)
            self.pet.sniff_requested.connect(self._on_pet_sniff)
            self.pet.position_changed.connect(self._save_pet_position)
            self.pet.settings_requested.connect(lambda: self._open_settings(3))
            self.pet.hide_requested.connect(self._hide_desktop_pet)
            if self.island:
                self.pet.island_provider = lambda: self.island.get_geometry()
        if self.pet:
            self.pet.apply_settings(settings)
            if self.chat and self.chat._streaming:
                self.pet.set_state("think")
            if enabled and not self.pet.isVisible():
                self.pet.show()
            elif not enabled:
                self.pet.hide()

    def _save_pet_position(self, x, y, screen):
        self._user_config["pet_position"] = {"x": x, "y": y, "screen": screen}
        cfg.save_user_config(self._user_config)
        if self._settings_dialog:
            self._settings_dialog.apply_external_pet_settings(self._user_config, "pet_position")
        if self.winisland:
            self.winisland.refresh_pet()

    def _hide_desktop_pet(self):
        self._user_config["pet_enabled"] = False
        self._apply_pet_settings(self._user_config)
        cfg.save_user_config(self._user_config)
        if self._settings_dialog:
            self._settings_dialog.apply_external_pet_settings(self._user_config, "pet_enabled")
        if self.winisland:
            self.winisland.refresh_pet()

    # ── Command confirmation ────────────────────────────────────────
    def _on_confirm_command(self, command: str):
        """Show confirm dialog, then execute the approved operation off the UI thread."""
        audio.play("file_dropped", config_dict=self._user_config)

        dlg = ConfirmDialog(command, parent=self.chat)
        if dlg.exec() == ConfirmDialog.DialogCode.Accepted:
            worker = threading.Thread(
                target=self._execute_confirmed_command,
                args=(command,),
                daemon=True,
            )
            worker.start()
        else:
            self.command_engine.cancel_pending()
            if self.chat:
                self.chat.append_command_result(command, False, "用户取消执行")

    def _execute_confirmed_command(self, fallback_command: str):
        """Consume one pending command and publish its result to the UI thread."""
        try:
            result = self.command_engine.confirm_pending()
            command = result.command or fallback_command
            output = result.output if result.success else result.error
            self._command_bridge.finished.emit(command, result.success, output)
        except Exception as exc:
            self._command_bridge.finished.emit(
                fallback_command, False, f"执行失败: {exc}"
            )

    def _on_command_finished(self, command: str, success: bool, output: str):
        if self.chat:
            self.chat.append_command_result(command, success, output)
        if self.agent:
            self.agent.tool_finished(success)

    # ── State changes ───────────────────────────────────────────────
    def _ensure_chat(self):
        if self.chat is not None:
            return
        self.chat = ChatWindow(self.bridge)
        self.chat._main_app = self
        self.bridge.stream_done.connect(self._process_commands)
        self.bridge.command_needs_confirm.connect(self._on_confirm_command)
        self.chat.settings_requested.connect(self._open_settings)
        self.pin_manager = PinManager()
        self.pin_manager.restore_all(on_jump=self._on_pin_jump)
        if self.agent:
            self.bridge.state_changed.disconnect(self.chat._on_state)
            self.chat._on_state(self.agent.state.state, self.agent.state.label)

    def _toggle_chat(self):
        self._ensure_chat()
        if self.chat:
            self.chat.toggle_visibility()
            if self.tray:
                self.tray.set_chat_visible(self.chat.isVisible())
            if self.chat.isVisible() and self.pet and not self.agent:
                self.pet.set_state("happy")
                self.pet.say("来聊天啦~", 2000)

    def _show_chat(self):
        self._ensure_chat()
        if self.chat:
            self.chat.showNormal()
            self.chat.show()
            self.chat.raise_()
            self.chat.activateWindow()
            self.chat._input.setFocus()
            if self.tray:
                self.tray.set_chat_visible(True)

    # ── P2-2 pet ate files ─────────────────────────────────────────
    def _on_pet_file_dropped(self, paths: list):
        """桌宠吞下文件后转发给 chat window。"""
        if not paths:
            return
        if self.agent:
            self.agent.files_dropped(paths)
            return
        if self.chat and hasattr(self.chat, "_on_dropped_files"):
            self.chat._on_dropped_files(paths)
        audio.play("file_dropped", config_dict=self._user_config)

    # ── P3-5 pet sniff ─────────────────────────────────────────────
    def _on_pet_sniff(self, icon_name: str):
        """桌宠嗅桌面图标：发 AI 求短评。"""
        try:
            import desktop_icon_reader
            prompt = desktop_icon_reader.sniff_icon(icon_name)
        except Exception:
            prompt = f"用 ≤10 个中文字评价这个图标名：'{icon_name}'"
        if self.pet:
            self.pet.say(f"嗅一嗅...\n{icon_name}", 1500)
        if self.chat and hasattr(self.chat, "_send_text"):
            self.chat._send_text(prompt)

    # ── P2-3 pin last answer ───────────────────────────────────────
    def _on_pin_last_answer(self):
        """⌘⇧P Pin 最新 AI 回答到桌面。"""
        if not self.chat or not hasattr(self.chat, "pin_last_ai_answer"):
            return
        self.chat.pin_last_ai_answer()

    # ── P2-3 pin jump ──────────────────────────────────────────────
    def _on_pin_jump(self, pin_id: str, conversation_idx: int):
        """从 pin 卡片"跳回对话"——切到对应 idx 并打开 chat。"""
        if self.chat and hasattr(self.chat, "switch_to_conversation"):
            self.chat.switch_to_conversation(conversation_idx)
        if self.chat and not self.chat.isVisible():
            self._toggle_chat()

    def _on_state_change(self, state, preview=""):
        if self.agent:
            self.agent.chat_state(state, preview)
            return
        if self.winisland:
            self.winisland.update_state(state, preview)
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
                audio.play("message_received", config_dict=self._user_config)
            elif state == "error":
                self.pet.set_state("sad")
                self.pet.say("出错了...", 3000)
                audio.play("error", config_dict=self._user_config)
            elif state == "result":
                self.pet.set_state("happy")
                audio.play("message_received", config_dict=self._user_config)
            elif state == "idle":
                self.pet.set_state("idle")

    def _process_commands(self, full_text):
        """Parse AI response for command tags and execute them."""
        if self.agent:
            self.agent.process_commands(full_text)
            return
        if not self.command_engine:
            return

        results = self.command_engine.parse_and_execute(full_text)
        for result in results:
            if result.requires_confirmation:
                self._on_confirm_command(result.command)
                continue
            if self.chat:
                self.chat.append_command_result(
                    result.command,
                    result.success,
                    result.output if result.success else result.error,
                )

    # ── Clipboard monitoring ────────────────────────────────────────
    def _start_clipboard_monitor(self):
        """Start polling clipboard for changes."""
        if hasattr(self, "_clipboard_timer") and self._clipboard_timer:
            return
        self._clipboard_timer = QTimer()
        self._clipboard_timer.timeout.connect(self._poll_clipboard)
        self._clipboard_timer.start(2000)

    def _poll_clipboard(self):
        if not self._clipboard_monitor:
            return
        clip = QApplication.clipboard()
        text = clip.text()
        if text and text != self._clipboard_last and len(text.strip()) > 2:
            # Skip sensitive-looking content (passwords, tokens, keys)
            import re
            if re.search(r'(password|passwd|secret|token|api[_-]?key|bearer)\s*[:=]', text, re.I):
                return
            if re.search(r'^[A-Za-z0-9+/=_-]{32,}$', text.strip()):
                return
            self._clipboard_last = text
            if self.island:
                self.island.set_state("notify", "检测到新内容")
            if self.chat and self.chat.isVisible():
                self.chat._input.setPlainText(f"帮我处理: {text[:100]}")

    # ── Crash reporter (P1-4) ─────────────────────────────────────
    def _check_crashes(self):
        """启动后 5s 检查本地崩溃日志。"""
        try:
            import ui.crash_reporter as cr
            unread = cr.get_unread_crashes()
            if not unread:
                return
            n = len(unread)
            if self.island:
                self.island.set_state(
                    "notify",
                    f"发现 {n} 个崩溃日志 → 打开设置查看",
                )
            if self.chat:
                self.chat._sys(
                    f"检测到 **{n} 份未查看的异常日志**。\n"
                    f"可在「设置 → 偏好 → 高级设置 → 诊断」查看。"
                )
        except (OSError, ValueError) as exc:
            logger.debug("Failed to check crash logs: %s", exc)

    # ── Hotkeys ─────────────────────────────────────────────────────
    def _setup_hotkeys(self):
        """Poll GetAsyncKeyState for Ctrl+Shift+H — works without admin, no third-party lib."""
        if sys.platform != "win32":
            return
        try:
            from ctypes import windll
            self._user32 = windll.user32
            self._hotkey_pressed = False
            self._hotkey_voice_pressed = False  # P3-6
            def _poll():
                ctrl = self._user32.GetAsyncKeyState(0x11) & 0x8000   # VK_CONTROL
                shift = self._user32.GetAsyncKeyState(0x10) & 0x8000  # VK_SHIFT
                h = self._user32.GetAsyncKeyState(0x48) & 0x8000      # VK_H
                v = self._user32.GetAsyncKeyState(0x56) & 0x8000      # VK_V
                # Ctrl+Shift+H toggle chat
                if ctrl and shift and h and not self._hotkey_pressed:
                    self._hotkey_pressed = True
                    self._toggle_chat()
                elif not (ctrl and shift and h):
                    self._hotkey_pressed = False
                # P3-6: Ctrl+Shift+V push-to-talk / toggle
                if ctrl and shift and v:
                    if not self._hotkey_voice_pressed:
                        self._hotkey_voice_pressed = True
                        self._on_voice_press()
                else:
                    if self._hotkey_voice_pressed:
                        self._hotkey_voice_pressed = False
                        self._on_voice_release()
            self._hotkey_timer = QTimer()
            self._hotkey_timer.timeout.connect(_poll)
            self._hotkey_timer.start(30)
            self._keyboard_registered = True
        except Exception as e:
            print(f"Hotkey setup failed: {e}")

    # ── P3-6 voice input ───────────────────────────────────────────
    def _on_voice_press(self):
        if self.agent and (self.agent.voice.recording or self.agent.voice.processing):
            return
        logger.debug("_on_voice_press called")
        if not self.voice_input:
            logger.debug("voice_input is None")
            return
        if not self.voice_input.is_available():
            detail = "请安装语音依赖"
            try:
                import sensevoice_asr
                if not sensevoice_asr.is_model_available():
                    detail = "请安装 SenseVoice 模型"
            except ImportError:
                pass
            self._voice_msg(f"⚠️ 语音输入不可用，{detail}")
            if self.island:
                self.island.set_state("error", detail)
            return
        if self.voice_input._recording:
            # 已在录音 → 视为 toggle off（用户单击而非长按）
            logger.debug("already recording → stopping (toggle)")
            self._do_voice_stop()
            return
        if self.voice_input.begin_recording():
            if self.chat and hasattr(self.chat, "_voice_btn"):
                self.chat._voice_btn.set_recording(True)
                self.chat._voice_btn.setToolTip("停止录音")
            logger.debug("recording started")
            audio.play("voice_start", config_dict=self._user_config)
            if self.island:
                self.island.set_voice_recording()
            # 安全超时：最长录音 30 秒自动停止
            QTimer.singleShot(30000, self._voice_auto_stop)
        else:
            logger.debug("begin_recording failed")
            if self.island:
                self.island.set_state("error", "检查麦克风设备")
            self._voice_msg("⚠️ 无法启动录音，请检查麦克风设备")

    def _on_voice_release(self):
        logger.debug("_on_voice_release called, _recording=%s", self.voice_input._recording if self.voice_input else 'N/A')
        if not self.voice_input:
            return
        if not self.voice_input._recording:
            return  # 已通过 toggle 停止，忽略
        self._do_voice_stop()

    def _do_voice_stop(self):
        """统一停止录音 + 显示 processing + 启动 ASR。"""
        if not self.voice_input:
            return
        self.voice_input.end_recording()
        if self.island:
            self.island.set_voice_processing()
        logger.debug("recording stopped → processing")

    def _voice_auto_stop(self):
        """30 秒安全超时：如果录音还在进行就自动停止。"""
        if self.voice_input and self.voice_input._recording:
            logger.debug("auto-stop after 30s timeout")
            self._do_voice_stop()

    # ── Voice signal emitters (called from background ASR thread) ──
    def _emit_voice_recognized(self, text: str):
        """Background thread → emit signal → main thread handles it."""
        logger.debug("_emit_voice_recognized: '%s'", text)
        self._voice_bridge.recognized.emit(text)

    def _emit_voice_state(self, state: str):
        """Background thread → emit signal → main thread handles it."""
        self._voice_bridge.state_changed.emit(state)

    # ── Voice main-thread slots (connected to _VoiceBridge signals) ──
    def _on_voice_recognized_main(self, text: str):
        """识别完成：填入 chat input + 隐藏胶囊 + 灵动岛回执。在主线程执行。"""
        logger.debug("_on_voice_recognized_main text='%s'", text)
        if not text.strip():
            if self.island:
                self.island.clear_voice_state()
            self._voice_msg("⚠️ 语音识别为空，请重试")
            return
        if self.chat and hasattr(self.chat, "_input"):
            cur = self.chat._input.toPlainText().strip()
            new_text = (cur + " " + text).strip() if cur else text
            self.chat._input.setPlainText(new_text)
            self.chat._input.setFocus()
            logger.debug("text set to chat input: '%s'", new_text[:50])
        else:
            logger.error("chat=%s, has _input=%s", self.chat, hasattr(self.chat, '_input') if self.chat else 'N/A')
        if self.island:
            self.island.set_state("result", f"🎙 {text[:30]}")
        QTimer.singleShot(3000, lambda: self.island.set_state("idle", "") if self.island else None)
        self._voice_msg(f"🎙 识别结果：{text}")
        audio.play("message_received", config_dict=self._user_config)

    def _on_voice_state_main(self, state: str):
        """录音/处理/就绪 状态通知。在主线程执行。"""
        logger.debug("state_main: %s", state)
        if state in ("error", "ready"):
            if state == "error" and self.voice_input:
                self._voice_msg(self.voice_input.last_error or "语音识别失败，请检查设置 → 语音")
            if self.chat and hasattr(self.chat, "_voice_btn"):
                self.chat._voice_btn.set_recording(False)
                self.chat._voice_btn.setToolTip("语音输入（Ctrl+Shift+V）")
            if self.island:
                self.island.clear_voice_state()
            if state == "error" and self.island:
                self.island.set_state("error", "语音出错")
                QTimer.singleShot(4000, lambda: self.island.set_state("idle", "") if self.island else None)

    def _voice_msg(self, text: str):
        """语音系统消息：有 chat 窗口时显示在 chat 里，否则灵动岛提示。"""
        if self.chat and hasattr(self.chat, "_sys"):
            self.chat._sys(text)
        else:
            logger.debug("voice fallback: %s", text)

    def _quit(self):
        """Clean up hotkey, tray, and app, then exit."""
        if self.agent:
            self.agent.close()
        if self.winisland:
            self.winisland.close()
        if hasattr(self, "_hotkey_timer"):
            self._hotkey_timer.stop()
        self._keyboard_registered = False

        if hasattr(self, "_clipboard_timer") and self._clipboard_timer:
            self._clipboard_timer.stop()

        if self.island:
            self.island.clear_voice_state()

        if self.tray:
            try:
                self.tray.hide()
            except (RuntimeError, AttributeError) as exc:
                logger.debug("Failed to hide tray: %s", exc)

        if self.bridge:
            try:
                self.bridge.cancel()
            except (RuntimeError, AttributeError) as exc:
                logger.debug("Failed to cancel bridge: %s", exc)

        self.app.quit()


def main():
    app = BuddyDeskApp()
    app.run()


if __name__ == "__main__":
    main()
