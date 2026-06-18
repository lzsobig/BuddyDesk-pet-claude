"""Tests for ui.markdown_renderer module"""
import unittest

from ui.markdown_renderer import (
    MarkdownRenderer,
    _scale_px,
    _detect_option_list,
    _NARRATIVE_HINTS,
)


class TestScalePx(unittest.TestCase):
    """Tests for the _scale_px font-size scaling helper."""

    def test_no_change_at_scale_1(self):
        # Arrange
        html = '<div style="font-size:14px;">Hello</div>'
        # Act
        result = _scale_px(html, 1.0)
        # Assert
        self.assertEqual(result, html)

    def test_scale_up(self):
        # Arrange
        html = '<div style="font-size:14px;">Hello</div>'
        # Act
        result = _scale_px(html, 1.5)
        # Assert
        self.assertIn('font-size:21.0px', result)

    def test_scale_down(self):
        # Arrange
        html = '<div style="font-size:20px;">Hello</div>'
        # Act
        result = _scale_px(html, 0.5)
        # Assert
        self.assertIn('font-size:10.0px', result)

    def test_multiple_font_sizes_scaled(self):
        # Arrange
        html = '<h1 style="font-size:17px;">Title</h1><p style="font-size:13px;">Body</p>'
        # Act
        result = _scale_px(html, 2.0)
        # Assert
        self.assertIn('font-size:34.0px', result)
        self.assertIn('font-size:26.0px', result)

    def test_no_font_size_unchanged(self):
        # Arrange
        html = '<div>Hello</div>'
        # Act
        result = _scale_px(html, 2.0)
        # Assert
        self.assertEqual(result, html)

    def test_fractional_font_size(self):
        # Arrange
        html = 'font-size:11.5px'
        # Act
        result = _scale_px(html, 1.2)
        # Assert
        # 11.5 * 1.2 = 13.8
        self.assertIn('font-size:13.8px', result)


class TestDetectOptionList(unittest.TestCase):
    """Tests for the _detect_option_list heuristic."""

    def test_valid_short_list(self):
        # Arrange
        text = "1. Option A\n2. Option B\n3. Option C"
        # Act
        result = _detect_option_list(text)
        # Assert
        self.assertEqual(result, ["Option A", "Option B", "Option C"])

    def test_returns_none_for_empty(self):
        # Arrange
        text = ""
        # Act
        result = _detect_option_list(text)
        # Assert
        self.assertIsNone(result)

    def test_returns_none_for_no_list(self):
        # Arrange
        text = "Just some plain text"
        # Act
        result = _detect_option_list(text)
        # Assert
        self.assertIsNone(result)

    def test_returns_none_for_over_7_items(self):
        # Arrange
        items = "\n".join(f"{i}. Item {i}" for i in range(1, 9))
        # Act
        result = _detect_option_list(items)
        # Assert
        self.assertIsNone(result)

    def test_returns_none_for_item_over_30_chars(self):
        # Arrange
        text = "1. Short\n2. This is a very long item that exceeds thirty chars\n3. OK"
        # Act
        result = _detect_option_list(text)
        # Assert
        self.assertIsNone(result)

    def test_returns_none_for_narrative_keywords(self):
        # Arrange
        text = "1. 第一步 做这个\n2. 第二步 做那个"
        # Act
        result = _detect_option_list(text)
        # Assert
        self.assertIsNone(result)

    def test_returns_none_for_narrative_keyword_shouci(self):
        # Arrange
        text = "1. 首先安装依赖\n2. 然后启动服务"
        # Act
        result = _detect_option_list(text)
        # Assert
        self.assertIsNone(result)

    def test_exactly_7_items_accepted(self):
        # Arrange
        text = "\n".join(f"{i}. Opt{i}" for i in range(1, 8))
        # Act
        result = _detect_option_list(text)
        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 7)

    def test_strips_number_prefix(self):
        # Arrange
        text = "5. Fifth option"
        # Act
        result = _detect_option_list(text)
        # Assert
        self.assertEqual(result, ["Fifth option"])

    def test_handles_leading_whitespace(self):
        # Arrange
        text = "  1. Option A\n  2. Option B"
        # Act
        result = _detect_option_list(text)
        # Assert
        self.assertEqual(result, ["Option A", "Option B"])

    def test_mixed_list_and_text(self):
        # Arrange
        # First few lines are a list, then a non-list line breaks it.
        # _detect_option_list stops at the first non-list line.
        text = "1. Opt A\n2. Opt B\nSome other text"
        # Act
        result = _detect_option_list(text)
        # Assert
        self.assertEqual(result, ["Opt A", "Opt B"])


class TestNarrativeHintsRegex(unittest.TestCase):
    """Tests that the narrative hints regex matches expected patterns."""

    def test_matches_step_keywords(self):
        # Arrange
        text = "第一步开始"
        # Act / Assert
        self.assertIsNotNone(_NARRATIVE_HINTS.search(text))

    def test_does_not_match_plain_text(self):
        # Arrange
        text = "Option A"
        # Act / Assert
        self.assertIsNone(_NARRATIVE_HINTS.search(text))


class TestMarkdownRendererInit(unittest.TestCase):
    """Tests for MarkdownRenderer initialization and basic configuration."""

    def test_default_font_scale(self):
        # Arrange / Act
        r = MarkdownRenderer()
        # Assert
        self.assertEqual(r.font_scale, 1.0)

    def test_custom_font_scale(self):
        # Arrange / Act
        r = MarkdownRenderer(font_scale=1.5)
        # Assert
        self.assertEqual(r.font_scale, 1.5)

    def test_set_font_scale(self):
        # Arrange
        r = MarkdownRenderer(font_scale=1.0)
        # Act
        r.set_font_scale(2.0)
        # Assert
        self.assertEqual(r.font_scale, 2.0)


class TestExtractTasksBlock(unittest.TestCase):
    """Tests for MarkdownRenderer.extract_tasks_block."""

    def setUp(self):
        self.renderer = MarkdownRenderer()

    def test_no_tasks_block_returns_none(self):
        # Arrange
        text = "Just some regular markdown text."
        # Act
        result = self.renderer.extract_tasks_block(text)
        # Assert
        self.assertIsNone(result)

    def test_empty_text_returns_none(self):
        # Arrange / Act
        result = self.renderer.extract_tasks_block("")
        # Assert
        self.assertIsNone(result)

    def test_tasks_block_b_style_simple_list(self):
        # Arrange
        text = (
            "Here are your tasks:\n"
            "```tasks\n"
            "- Task Alpha\n"
            "- Task Beta\n"
            "```\n"
            "Good luck!"
        )
        # Act
        remaining, tasks = self.renderer.extract_tasks_block(text)
        # Assert
        self.assertEqual(remaining, "Here are your tasks:\n\nGood luck!")
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["title"], "Task Alpha")
        self.assertEqual(tasks[1]["title"], "Task Beta")
        self.assertEqual(tasks[0]["mode"], "claude_code")
        self.assertEqual(tasks[0]["difficulty"], 1)

    def test_tasks_block_a_style_key_value(self):
        # Arrange
        text = (
            "```tasks\n"
            "- title: Build login page\n"
            "  mode: openai_api\n"
            "  difficulty: 3\n"
            "```"
        )
        # Act
        remaining, tasks = self.renderer.extract_tasks_block(text)
        # Assert
        self.assertEqual(remaining, "")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], "Build login page")
        self.assertEqual(tasks[0]["mode"], "openai_api")
        self.assertEqual(tasks[0]["difficulty"], 3)

    def test_tasks_block_mixed_styles(self):
        # Arrange
        text = (
            "```tasks\n"
            "- title: First task\n"
            "  mode: claude_code\n"
            "- Simple second task\n"
            "```"
        )
        # Act
        remaining, tasks = self.renderer.extract_tasks_block(text)
        # Assert
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["title"], "First task")
        self.assertEqual(tasks[0]["mode"], "claude_code")
        self.assertEqual(tasks[1]["title"], "Simple second task")
        self.assertEqual(tasks[1]["mode"], "claude_code")

    def test_tasks_block_with_comment_lines(self):
        # Arrange
        text = (
            "```tasks\n"
            "# This is a comment\n"
            "- Task One\n"
            "# Another comment\n"
            "- Task Two\n"
            "```"
        )
        # Act
        remaining, tasks = self.renderer.extract_tasks_block(text)
        # Assert
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["title"], "Task One")
        self.assertEqual(tasks[1]["title"], "Task Two")

    def test_tasks_block_difficulty_non_numeric_fallback(self):
        # Arrange
        text = (
            "```tasks\n"
            "- title: Weird task\n"
            "  difficulty: not_a_number\n"
            "```"
        )
        # Act
        _, tasks = self.renderer.extract_tasks_block(text)
        # Assert
        self.assertEqual(tasks[0]["difficulty"], 1)  # fallback

    def test_tasks_block_empty_yaml(self):
        # Arrange
        text = "```tasks\n```"
        # Act
        result = self.renderer.extract_tasks_block(text)
        # Assert
        self.assertIsNone(result)

    def test_tasks_block_preserves_surrounding_text(self):
        # Arrange
        text = "Before\n```tasks\n- T1\n```\nAfter"
        # Act
        remaining, _ = self.renderer.extract_tasks_block(text)
        # Assert
        self.assertEqual(remaining, "Before\n\nAfter")


class TestMarkdownRendererRender(unittest.TestCase):
    """Tests for MarkdownRenderer.render output."""

    def setUp(self):
        self.renderer = MarkdownRenderer()

    def test_empty_text(self):
        # Arrange / Act
        result = self.renderer.render("")
        # Assert
        self.assertEqual(result, "")

    def test_plain_text(self):
        # Arrange
        text = "Hello world"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("Hello world", result)
        self.assertIn("<div", result)  # paragraph wrapper

    def test_code_block(self):
        # Arrange
        text = "```python\nprint('hi')\n```"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<pre", result)
        self.assertIn("python", result)
        self.assertIn("print", result)

    def test_code_block_no_language(self):
        # Arrange
        text = "```\nsome code\n```"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<pre", result)

    def test_header_h1(self):
        # Arrange
        text = "# Title"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<h1", result)
        self.assertIn("Title", result)

    def test_header_h2(self):
        # Arrange
        text = "## Subtitle"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<h2", result)
        self.assertIn("Subtitle", result)

    def test_header_h3(self):
        # Arrange
        text = "### Section"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<h3", result)
        self.assertIn("Section", result)

    def test_blockquote(self):
        # Arrange
        text = "> Quote me"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("Quote me", result)

    def test_unordered_list(self):
        # Arrange
        text = "- Item one\n- Item two"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<li", result)
        self.assertIn("Item one", result)
        self.assertIn("Item two", result)

    def test_ordered_list(self):
        # Arrange
        text = "1. First\n2. Second"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<li", result)
        self.assertIn("First", result)

    def test_horizontal_rule(self):
        # Arrange
        text = "---"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<hr", result)

    def test_horizontal_rule_stars(self):
        # Arrange
        text = "***"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<hr", result)

    def test_inline_bold(self):
        # Arrange
        text = "This is **bold** text"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<b>bold</b>", result)

    def test_inline_italic(self):
        # Arrange
        text = "This is _italic_ text"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<i>italic</i>", result)

    def test_inline_code(self):
        # Arrange
        text = "Use `print()` function"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<code", result)
        self.assertIn("print()", result)

    def test_strikethrough(self):
        # Arrange
        text = "This is ~~deleted~~ text"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<s>deleted</s>", result)

    def test_html_escaping(self):
        # Arrange
        text = "Use <script>alert('xss')</script>"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_bold_inside_code_not_expanded(self):
        # Arrange
        text = "Use `**not bold**` here"
        # Act
        result = self.renderer.render(text)
        # Assert
        # The ** inside code spans should NOT become <b> tags
        self.assertNotIn("<b>", result)
        self.assertIn("**not bold**", result)

    def test_font_scale_applied(self):
        # Arrange
        renderer = MarkdownRenderer(font_scale=1.5)
        # Act
        result = renderer.render("# Title")
        # Assert
        # h1 has font-size:17px -> scaled to 25.5px
        self.assertIn("font-size:25.5px", result)

    def test_mixed_content(self):
        # Arrange
        text = "## Heading\n\nA paragraph with **bold**.\n\n- list item"
        # Act
        result = self.renderer.render(text)
        # Assert
        self.assertIn("<h2", result)
        self.assertIn("Heading", result)
        self.assertIn("<b>bold</b>", result)
        self.assertIn("<li", result)


class TestRenderForStreaming(unittest.TestCase):
    """Tests for MarkdownRenderer.render_for_streaming."""

    def setUp(self):
        self.renderer = MarkdownRenderer()

    def test_empty_text(self):
        # Arrange / Act
        result = self.renderer.render_for_streaming("")
        # Assert
        self.assertEqual(result, "")

    def test_complete_text(self):
        # Arrange
        text = "Hello world"
        # Act
        result = self.renderer.render_for_streaming(text)
        # Assert
        self.assertIn("Hello world", result)

    def test_unclosed_inline_code(self):
        # Arrange
        text = "Use `print() function"
        # Act
        result = self.renderer.render_for_streaming(text)
        # Assert
        # Should still render without crashing
        self.assertIn("print()", result)

    def test_unclosed_fenced_code_block(self):
        # Arrange
        text = "```python\nprint('hi')"
        # Act
        result = self.renderer.render_for_streaming(text)
        # Assert
        self.assertIn("<pre", result)
        self.assertIn("print", result)


class TestExtractOptionList(unittest.TestCase):
    """Tests for MarkdownRenderer.extract_option_list (delegates to _detect_option_list)."""

    def setUp(self):
        self.renderer = MarkdownRenderer()

    def test_valid_options(self):
        # Arrange
        text = "1. Apple\n2. Banana\n3. Cherry"
        # Act
        result = self.renderer.extract_option_list(text)
        # Assert
        self.assertEqual(result, ["Apple", "Banana", "Cherry"])

    def test_no_options(self):
        # Arrange / Act
        result = self.renderer.extract_option_list("No list here")
        # Assert
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
