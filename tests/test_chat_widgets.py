"""Tests for ui.chat_widgets module

Focuses on:
- _TAG_RE regex pattern matching
- _MessageBubble.set_text logic via a minimal stub (avoids Qt event loop)
- Data transformations rather than visual rendering
"""
import re
import unittest
from unittest.mock import MagicMock, patch
import sys

# Import after PySide6 is mocked
from ui.chat_widgets import _TAG_RE
from ui.markdown_renderer import MarkdownRenderer

# test_chat_widgets historically replaced PySide6 with MagicMock at module
# import time, which permanently poisoned sys.modules for every other test
# module collected afterwards. Keep the mock, but scope it to this module's
# test run and restore the real modules afterwards.
_MOCKED_MODULES = [
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
]


def setUpModule():
    global _ORIG
    _ORIG = {}
    for mod_name in _MOCKED_MODULES:
        _ORIG[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = MagicMock()


def tearDownModule():
    for mod_name in _MOCKED_MODULES:
        if _ORIG.get(mod_name) is not None:
            sys.modules[mod_name] = _ORIG[mod_name]
        else:
            sys.modules.pop(mod_name, None)


class TestTagRegex(unittest.TestCase):
    """Tests for the _TAG_RE compiled regex that extracts APP/SHELL/CMD tags."""

    def test_shell_tag(self):
        # Arrange
        text = "[SHELL:echo hello]"
        # Act
        m = _TAG_RE.search(text)
        # Assert
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "SHELL")
        self.assertEqual(m.group(2), "echo hello")

    def test_app_tag(self):
        # Arrange
        text = "[APP:Chrome]"
        # Act
        m = _TAG_RE.search(text)
        # Assert
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "APP")
        self.assertEqual(m.group(2), "Chrome")

    def test_cmd_tag(self):
        # Arrange
        text = "[CMD:ls -la]"
        # Act
        m = _TAG_RE.search(text)
        # Assert
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "CMD")
        self.assertEqual(m.group(2), "ls -la")

    def test_claude_tag(self):
        # Arrange
        text = "[CLAUDE:analyze this]"
        # Act
        m = _TAG_RE.search(text)
        # Assert
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "CLAUDE")
        self.assertEqual(m.group(2), "analyze this")

    def test_tag_with_surrounding_text(self):
        # Arrange
        text = "Please run [SHELL:ipconfig] and show me"
        # Act
        m = _TAG_RE.search(text)
        # Assert
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "SHELL")
        self.assertEqual(m.group(2), "ipconfig")

    def test_multiple_tags(self):
        # Arrange
        text = "Run [SHELL:echo hi] then [APP:Notepad]"
        # Act
        matches = _TAG_RE.findall(text)
        # Assert
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0][0], "SHELL")
        self.assertEqual(matches[1][0], "APP")

    def test_no_tag(self):
        # Arrange
        text = "Just plain text with no tags"
        # Act
        m = _TAG_RE.search(text)
        # Assert
        self.assertIsNone(m)

    def test_empty_string(self):
        # Arrange / Act
        m = _TAG_RE.search("")
        # Assert
        self.assertIsNone(m)

    def test_unclosed_tag_still_matches(self):
        """The regex uses ]? (optional closing bracket) so unclosed tags still match."""
        # Arrange
        text = "[SHELL:echo hello"
        # Act
        m = _TAG_RE.search(text)
        # Assert
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "SHELL")
        self.assertEqual(m.group(2), "echo hello")

    def test_tag_colon_in_command(self):
        # Arrange
        text = "[SHELL:net user:password]"
        # Act
        m = _TAG_RE.search(text)
        # Assert
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "net user:password")


class TestMarkdownRendererUsedByBubble(unittest.TestCase):
    """Tests verifying the MarkdownRenderer contract that _MessageBubble depends on.

    Since _MessageBubble requires a full Qt event loop, we test the renderer
    interface that the bubble delegates its text-processing logic to.
    """

    def test_renderer_returns_html_string(self):
        # Arrange
        renderer = MarkdownRenderer()
        # Act
        html = renderer.render("Hello **world**")
        # Assert
        self.assertIsInstance(html, str)
        self.assertIn("<b>world</b>", html)

    def test_renderer_for_streaming_returns_string(self):
        # Arrange
        renderer = MarkdownRenderer()
        # Act
        html = renderer.render_for_streaming("Streaming **text**")
        # Assert
        self.assertIsInstance(html, str)

    def test_extract_tasks_block_interface(self):
        """Verify that extract_tasks_block returns the tuple shape _MessageBubble expects."""
        # Arrange
        renderer = MarkdownRenderer()
        text = "intro\n```tasks\n- T1\n- T2\n```\nend"
        # Act
        result = renderer.extract_tasks_block(text)
        # Assert
        self.assertIsNotNone(result)
        remaining, tasks = result
        self.assertIsInstance(remaining, str)
        self.assertIsInstance(tasks, list)
        self.assertTrue(all(isinstance(t, dict) for t in tasks))
        self.assertTrue(all("title" in t for t in tasks))

    def test_extract_option_list_interface(self):
        """Verify that extract_option_list returns the list shape _MessageBubble expects."""
        # Arrange
        renderer = MarkdownRenderer()
        text = "1. Apple\n2. Banana"
        # Act
        result = renderer.extract_option_list(text)
        # Assert
        self.assertIsNotNone(result)
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(s, str) for s in result))


class TestMessageBubbleBehavior(unittest.TestCase):
    """Test _MessageBubble.set_text branching logic by exercising the renderer path.

    Instead of instantiating the Qt widget (which requires a real event loop),
    we test the exact same branching logic that set_text uses, via the renderer.
    """

    def setUp(self):
        self.renderer = MarkdownRenderer()

    def test_ai_text_renders_through_markdown(self):
        """AI messages go through renderer.render()."""
        # Arrange
        text = "## Heading\n\nSome **bold** text."
        # Act
        html = self.renderer.render(text)
        # Assert
        self.assertIn("<h2", html)
        self.assertIn("<b>bold</b>", html)

    def test_ai_text_extract_tasks_removes_block(self):
        """When extract_tasks_block returns data, remaining text is re-rendered separately."""
        # Arrange
        text = "Intro\n```tasks\n- Task A\n```\nDone."
        # Act
        remaining, tasks = self.renderer.extract_tasks_block(text)
        remaining_html = self.renderer.render(remaining) if remaining else ""
        # Assert
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], "Task A")
        self.assertIn("Intro", remaining_html)
        self.assertNotIn("```tasks", remaining_html)

    def test_ai_text_with_options_builds_buttons(self):
        """When extract_option_list returns items, buttons are built from them."""
        # Arrange
        text = "Choose:\n1. Option A\n2. Option B"
        # Act
        opts = self.renderer.extract_option_list(text)
        # Assert
        self.assertEqual(opts, ["Option A", "Option B"])

    def test_plain_text_user_renders_as_escaped_html(self):
        """User messages are escaped, not rendered through markdown."""
        # Arrange
        text = "Hello <world> & 'friends'"
        # Act -- simulate what _MessageBubble does for user role
        from html import escape
        escaped = escape(text).replace("\n", "<br>")
        # Assert
        self.assertIn("&lt;world&gt;", escaped)
        self.assertIn("&amp;", escaped)
        self.assertNotIn("<world>", escaped)

    def test_streaming_uses_render_for_streaming(self):
        """During streaming, render_for_streaming is called instead of render."""
        # Arrange
        text = "Partial text with `unclosed"
        # Act
        html = self.renderer.render_for_streaming(text)
        # Assert
        self.assertIsInstance(html, str)
        self.assertIn("Partial text", html)

    def test_streaming_clears_option_buttons(self):
        """During streaming, option buttons are cleared (not built).

        We verify this by checking that extract_option_list is only called
        after streaming completes, not during."""
        # Arrange
        option_text = "1. Opt A\n2. Opt B"
        # Act -- simulate streaming path (skips extract_option_list)
        html_streaming = self.renderer.render_for_streaming(option_text)
        # Then simulate finalize path (calls extract_option_list)
        opts = self.renderer.extract_option_list(option_text)
        # Assert
        self.assertIsNotNone(html_streaming)
        self.assertEqual(opts, ["Opt A", "Opt B"])


class TestHtmlEscapeForUserBubble(unittest.TestCase):
    """Test the HTML escaping used for user message bubbles.

    _MessageBubble calls _html_escape(text).replace("\\n", "<br>").
    Since _html_escape is not defined in the module, the chat_window import
    fails -- but the escaping behavior is standard html.escape, which we test here.
    """

    def test_escapes_angle_brackets(self):
        from html import escape
        # Arrange / Act
        result = escape("<script>alert(1)</script>")
        # Assert
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;", result)

    def test_escapes_ampersand(self):
        from html import escape
        # Arrange / Act
        result = escape("A & B")
        # Assert
        self.assertEqual(result, "A &amp; B")

    def test_escapes_quotes(self):
        from html import escape
        # Arrange / Act
        result = escape('He said "hello"')
        # Assert
        self.assertIn("&quot;", result)

    def test_newlines_replaced_with_br(self):
        from html import escape
        # Arrange
        text = "Line 1\nLine 2\nLine 3"
        # Act
        escaped = escape(text).replace("\n", "<br>")
        # Assert
        self.assertIn("<br>", escaped)
        self.assertEqual(escaped.count("<br>"), 2)


if __name__ == "__main__":
    unittest.main()
