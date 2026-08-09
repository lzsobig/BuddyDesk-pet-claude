"""Focused Qt regressions for the voice surface and window layering."""
import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDynamicIslandVoice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_voice_state_transitions_and_dimensions(self):
        from ui.dynamic_island import DIMS, DynamicIsland
        island = DynamicIsland()
        island.set_voice_recording()
        self.assertEqual(island._state, "voice_recording")
        self.app.processEvents()
        from PySide6.QtTest import QTest
        QTest.qWait(450)
        self.assertEqual((island.width(), island.height()), DIMS["voice_recording"])
        island.set_voice_level(0.75)
        self.assertAlmostEqual(island._voice_levels[-1], 0.75)
        island.set_voice_processing()
        self.assertEqual(island._state, "voice_processing")
        island.clear_voice_state()
        self.assertEqual(island._state, "idle")
        island.deleteLater()

    def test_voice_island_lifecycle_does_not_raise(self):
        from PySide6.QtWidgets import QApplication
        from ui.dynamic_island import DynamicIsland
        island = DynamicIsland()
        island.set_voice_recording()
        QApplication.processEvents()
        island.set_voice_processing()
        QApplication.processEvents()
        island.clear_voice_state()
        QApplication.processEvents()
        island.deleteLater()

    def test_voice_resize_keeps_island_centered(self):
        from ui.dynamic_island import DynamicIsland
        island = DynamicIsland()
        island.move(400, 120)
        island.show()
        from PySide6.QtTest import QTest
        QTest.qWait(100)
        self.app.processEvents()
        idle_center = island.x() + island.width() / 2
        island.set_voice_recording()
        QTest.qWait(450)
        self.app.processEvents()
        voice_center = island.x() + island.width() / 2
        self.assertAlmostEqual(idle_center, voice_center, delta=4.0)
        island.deleteLater()


class TestVoiceControllerGuards(unittest.TestCase):
    def test_processing_rejects_second_recording(self):
        from voice_input import VoiceInputController
        controller = VoiceInputController.__new__(VoiceInputController)
        controller._available = True
        controller._recording = False
        controller._processing = True
        self.assertFalse(controller.begin_recording())

    def test_missing_model_marks_voice_unavailable(self):
        from unittest.mock import patch
        from voice_input import VoiceInputController
        with patch("sensevoice_asr.is_model_available", return_value=False):
            controller = VoiceInputController()
        self.assertFalse(controller.is_available())


class TestChatWindowLayering(unittest.TestCase):
    def test_chat_base_window_is_not_always_on_top(self):
        from PySide6.QtCore import Qt
        from ui.chat_widgets import ChatBaseWindow
        window = ChatBaseWindow()
        self.assertFalse(bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
        window.deleteLater()


class TestVoiceButtonRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_button_uses_main_voice_state_machine(self):
        from PySide6.QtWidgets import QWidget, QVBoxLayout
        from ui.chat_window import ChatWindow

        window = QWidget()
        window._main_app = MagicMock()
        window._main_app.voice_input = MagicMock(is_available=lambda: True, _recording=False)
        window._main_app._on_voice_press = MagicMock()
        window._find_main_app = lambda: window._main_app
        layout = QVBoxLayout(window)
        # The routing helper only needs the host contract; use ChatWindow method
        # directly to avoid constructing a full network bridge.
        ChatWindow._on_voice_button(window)
        window._main_app._on_voice_press.assert_called_once()

    def test_voice_button_ignores_processing_controller(self):
        from PySide6.QtWidgets import QWidget, QVBoxLayout
        from ui.chat_window import ChatWindow
        from ui.icon_widgets import VoiceButton
        window = QWidget()
        window._main_app = MagicMock()
        window._main_app.voice_input = MagicMock(
            is_available=lambda: True, _recording=False, _processing=True
        )
        window._main_app._on_voice_press = MagicMock()
        window._find_main_app = lambda: window._main_app
        window._voice_btn = VoiceButton(window)
        QVBoxLayout(window)
        ChatWindow._on_voice_button(window)
        window._main_app._on_voice_press.assert_not_called()
        window.deleteLater()

    def test_voice_button_has_painted_icon_state(self):
        from ui.icon_widgets import VoiceButton
        button = VoiceButton()
        self.assertEqual((button.width(), button.height()), (34, 34))
        self.assertFalse(button._recording)
        button.set_recording(True)
        self.assertTrue(button._recording)
        button.deleteLater()


if __name__ == "__main__":
    unittest.main()
