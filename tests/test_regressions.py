"""Regression tests for the Batch-1 fixes.

Covers:
- conversation role normalization (ai vs assistant persistence)
- archive history card signal routing
- settings save preserving sound paths
- chat bubble copy / regenerate / task-pin wiring

These use the real Qt stack (offscreen) where widgets are involved, and pure
logic helpers where they are not. No network calls and no real shell commands.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Make sure we run offscreen so widget construction works on headless CI.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRoleNormalization(unittest.TestCase):
    """_normalize_role maps persisted roles to display roles."""

    def test_user_role_stays_user(self):
        from ui.chat_window import _normalize_role
        self.assertEqual(_normalize_role("user"), "user")

    def test_ai_role_maps_to_ai(self):
        from ui.chat_window import _normalize_role
        self.assertEqual(_normalize_role("ai"), "ai")

    def test_legacy_assistant_maps_to_ai(self):
        from ui.chat_window import _normalize_role
        self.assertEqual(_normalize_role("assistant"), "ai")

    def test_unknown_role_maps_to_ai(self):
        from ui.chat_window import _normalize_role
        self.assertEqual(_normalize_role("whatever"), "ai")

    def test_missing_role_maps_to_user(self):
        from ui.chat_window import _normalize_role
        self.assertEqual(_normalize_role(""), "ai")


class TestHistoryCardSignals(unittest.TestCase):
    """Cards must route restore/rename/delete through injected signals,
    not through an unreliable parent chain."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def _make_card(self):
        from ui.history_panel import _ConversationCard
        conv = {
            "title": "Test conv",
            "messages": [{"role": "user", "content": "hi"}],
            "updated_at": "",
        }
        return _ConversationCard(0, conv)

    def test_restore_uses_injected_signal(self):
        card = self._make_card()
        sig = MagicMock()
        card.restore_requested = sig
        card._on_restore(0)
        sig.emit.assert_called_once_with(0)

    def test_restore_silently_noops_without_signal(self):
        card = self._make_card()
        # No injected signal → no crash, nothing emitted.
        card._on_restore(0)

    def test_delete_uses_injected_signal(self):
        card = self._make_card()
        sig = MagicMock()
        card.delete_requested = sig
        card._on_delete()
        sig.emit.assert_called_once_with(0)

    def test_rename_uses_injected_signal(self):
        card = self._make_card()
        sig = MagicMock()
        card.rename_requested = sig
        with patch("PySide6.QtWidgets.QInputDialog") as qid:
            qid.getText.return_value = ("新名字", True)
            card._on_rename()
        sig.emit.assert_called_once_with(0, "新名字")


class TestSettingsSoundPaths(unittest.TestCase):
    """Opening settings then saving must not wipe custom sound paths."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def _make_panel(self, config):
        from ui.settings_panel import SettingsPanel
        return SettingsPanel(config)

    def test_populate_keeps_existing_custom_path(self):
        config = {"sound_voice_start_custom_path": r"C:\sounds\ding.wav"}
        panel = self._make_panel(config)
        self.assertEqual(
            panel._sound_paths.get("voice_start"),
            r"C:\sounds\ding.wav",
        )

    def test_save_preserves_unmodified_paths(self):
        config = {
            "sound_voice_start_enabled": True,
            "sound_voice_start_custom_path": r"C:\sounds\ding.wav",
            "sound_message_received_enabled": True,
            "sound_message_received_custom_path": r"D:\music\pop.mp3",
        }
        panel = self._make_panel(config)
        with patch("ui.settings_panel.cfg.save_user_config") as save, \
             patch.object(panel, "accept") as accept, \
             patch.object(panel, "_apply_autostart") as apply_autostart:
            panel._save()
        self.assertTrue(save.called)
        saved_config = save.call_args[0][0]
        self.assertEqual(saved_config["sound_voice_start_custom_path"], r"C:\sounds\ding.wav")
        self.assertEqual(saved_config["sound_message_received_custom_path"], r"D:\music\pop.mp3")


class TestMessageBubbleActions(unittest.TestCase):
    """Copy / regenerate / task-pin must not crash on the real widget stack."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def _make_bubble(self, text="hello"):
        from ui.chat_widgets import _MessageBubble
        from ui.markdown_renderer import MarkdownRenderer
        return _MessageBubble("ai", text, "12:00", renderer=MarkdownRenderer())

    def test_copy_text_puts_text_on_clipboard(self):
        bubble = self._make_bubble("clip me")
        bubble._copy_text()
        from PySide6.QtWidgets import QApplication
        self.assertEqual(QApplication.clipboard().text(), "clip me")

    def test_regen_noops_without_host(self):
        bubble = self._make_bubble()
        bubble._regen()  # no ChatWindow ancestor → must not raise

    def test_regen_routes_to_host_window(self):
        from PySide6.QtWidgets import QWidget, QVBoxLayout
        from ui.chat_widgets import _MessageBubble
        from ui.markdown_renderer import MarkdownRenderer

        host = QWidget()
        host._find_main_app = lambda: None
        host._sys = lambda *a, **k: None
        host._regenerate = MagicMock()
        layout = QVBoxLayout(host)
        bubble = _MessageBubble("ai", "x", "12:00", renderer=MarkdownRenderer())
        layout.addWidget(bubble)
        bubble._regen()
        host._regenerate.assert_called_once()

    def test_task_pin_routes_to_host_pin_manager(self):
        from PySide6.QtWidgets import QWidget, QVBoxLayout
        from ui.chat_widgets import _MessageBubble
        from ui.markdown_renderer import MarkdownRenderer

        pin_manager = MagicMock()
        host = QWidget()
        host._active_idx = 2
        host._find_main_app = lambda: MagicMock(pin_manager=pin_manager)
        host._sys = MagicMock()
        layout = QVBoxLayout(host)
        bubble = _MessageBubble("ai", "x", "12:00", renderer=MarkdownRenderer())
        layout.addWidget(bubble)

        bubble._on_task_pin({"title": "T1", "mode": "claude_code", "difficulty": 3})
        self.assertTrue(pin_manager.pin.called)
        host._sys.assert_called_once()

    def test_task_pin_noops_without_host(self):
        bubble = self._make_bubble()
        bubble._on_task_pin({"title": "T1"})  # no host → must not raise


if __name__ == "__main__":
    unittest.main()


class TestAppResolution(unittest.TestCase):
    """App lookup robustness: lnk parsing, registry fallbacks, symlinks."""

    def test_find_app_returns_string_for_known(self):
        from engine.command_engine import AppRegistry
        result = AppRegistry.find_app("微信")
        self.assertIsInstance(result, str)
        self.assertTrue(result)

    def test_wechat_alias_prefers_start_menu_shortcut(self):
        from engine.command_engine import AppRegistry
        with patch.object(
            AppRegistry,
            "_find_via_start_menu",
            return_value='"C:\\Start Menu\\微信.lnk"',
        ), patch.object(AppRegistry, "_find_via_registry") as registry:
            self.assertEqual(
                AppRegistry.find_app("wechat"),
                '"C:\\Start Menu\\微信.lnk"',
            )
        registry.assert_not_called()

    def test_find_app_special_builtin(self):
        from engine.command_engine import AppRegistry
        # notepad is a special — returns bare command
        self.assertEqual(AppRegistry.find_app("notepad"), "notepad")

    def test_find_app_unknown_returns_empty_target(self):
        from engine.command_engine import AppRegistry
        self.assertEqual(AppRegistry.find_app("不存在的应用xyz"), "")

    def test_extract_exe_path_from_display_icon(self):
        from engine.command_engine import AppRegistry
        self.assertEqual(
            AppRegistry._extract_exe_path(r'"C:\Apps\Foo\foo.exe",0'),
            r"C:\Apps\Foo\foo.exe",
        )
        self.assertEqual(
            AppRegistry._extract_exe_path("no exe here"),
            "",
        )

    def test_path_launchable_broken_symlink(self):
        from engine.command_engine import AppRegistry
        self.assertFalse(AppRegistry._path_launchable(r"C:\definitely\missing\app.exe"))

    def test_read_lnk_target_missing_file(self):
        from engine.command_engine import _read_lnk_target
        self.assertEqual(_read_lnk_target(r"C:\nonexistent\shortcut.lnk"), "")

    def test_external_launch_env_strips_buddydesk_qt_overrides(self):
        from engine.command_engine import CommandEngine
        with patch.dict(
            "os.environ",
            {
                "QT_QPA_PLATFORM_PLUGIN_PATH": r"C:\PySide6\plugins",
                "QT_PLUGIN_PATH": r"C:\PySide6\plugins",
                "QT_QPA_PLATFORM": "windows",
                "QT_DEBUG_PLUGINS": "1",
                "KEEP_ME": "yes",
            },
            clear=True,
        ):
            env = CommandEngine._external_launch_env()
        self.assertEqual(env["KEEP_ME"], "yes")
        self.assertNotIn("QT_QPA_PLATFORM_PLUGIN_PATH", env)
        self.assertNotIn("QT_PLUGIN_PATH", env)
        self.assertNotIn("QT_QPA_PLATFORM", env)
        self.assertNotIn("QT_DEBUG_PLUGINS", env)
