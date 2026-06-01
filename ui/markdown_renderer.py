"""
Markdown Renderer for ChatWindow.

Renders markdown text to HTML with streaming support for incomplete content.
Supports: code blocks (with language tags), inline code, bold, italic, lists, headers, blockquotes.

Colors pull from theme.py so light/dark variants stay in sync.
"""
import re

from theme import (
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, BORDER,
    ACCENT, ACCENT_SOFT, BG_SUBTLE, BG_CARD, FONT_MONO,
)


class MarkdownRenderer:
    """Converts markdown text to HTML for QTextEdit display."""

    def render(self, text: str) -> str:
        """Render markdown text to HTML."""
        if not text:
            return ""

        # Split into lines and process
        lines = text.split('\n')
        result = []
        i = 0
        buffer = []

        def flush_buffer():
            nonlocal buffer
            if buffer:
                result.append(self._render_paragraph('\n'.join(buffer)))
                buffer = []

        while i < len(lines):
            line = lines[i]

            # Fenced code block
            if line.strip().startswith('```'):
                flush_buffer()
                lang = line.strip()[3:].strip() or 'code'
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                result.append(self._render_code_block(lang, '\n'.join(code_lines)))
                i += 1
                continue

            # Headers
            if line.startswith('### '):
                flush_buffer()
                result.append(f'<h3 style="margin:8px 0 4px;font-size:13px;font-weight:600;color:{TEXT_PRIMARY};">{self._inline(line[4:])}</h3>')
            elif line.startswith('## '):
                flush_buffer()
                result.append(f'<h2 style="margin:10px 0 6px;font-size:15px;font-weight:600;color:{TEXT_PRIMARY};">{self._inline(line[3:])}</h2>')
            elif line.startswith('# '):
                flush_buffer()
                result.append(f'<h1 style="margin:12px 0 8px;font-size:17px;font-weight:600;color:{TEXT_PRIMARY};">{self._inline(line[2:])}</h1>')
            # Blockquote
            elif line.startswith('> '):
                flush_buffer()
                result.append(
                    f'<div style="margin:6px 0;padding:6px 12px;background:{ACCENT_SOFT};'
                    f'border-left:3px solid {ACCENT};color:{TEXT_SECONDARY};'
                    f'font-style:italic;border-radius:0 6px 6px 0;">{self._inline(line[2:])}</div>'
                )
            # Unordered list
            elif re.match(r'^[-*]\s+', line):
                flush_buffer()
                result.append(f'<li style="margin:2px 0 2px 14px;color:{TEXT_PRIMARY};list-style-type:disc;">{self._inline(re.sub(r'^[-*]\s+', '', line))}</li>')
            # Ordered list
            elif re.match(r'^\d+\.\s+', line):
                flush_buffer()
                result.append(f'<li style="margin:2px 0 2px 14px;list-style-type:decimal;color:{TEXT_PRIMARY};">{self._inline(re.sub(r'^\d+\.\s+', '', line))}</li>')
            # Horizontal rule
            elif line.strip() in ('---', '***'):
                flush_buffer()
                result.append(f'<hr style="border:none;border-top:1px solid {BORDER};margin:10px 0;">')
            # Empty line
            elif not line.strip():
                flush_buffer()
            else:
                buffer.append(line)
            i += 1

        flush_buffer()
        return '\n'.join(result)

    def _render_code_block(self, lang: str, code: str) -> str:
        """Render a fenced code block."""
        escaped = self._escape_html(code)
        return (
            f'<div style="margin:6px 0;background:{BG_SUBTLE};'
            f'border:1px solid {BORDER};border-radius:8px;overflow:hidden;">'
            f'<div style="padding:4px 12px;background:{BG_CARD};'
            f'color:{TEXT_MUTED};font-size:10px;font-family:{FONT_MONO};border-bottom:1px solid {BORDER};">'
            f'{self._escape_html(lang) or "code"}</div>'
            f'<pre style="margin:0;padding:8px 12px;color:{TEXT_PRIMARY};'
            f'font-family:{FONT_MONO};font-size:12px;'
            f'white-space:pre-wrap;word-break:break-all;background:transparent;">{escaped}</pre>'
            f'</div>'
        )

    def _render_paragraph(self, text: str) -> str:
        """Render a paragraph with inline formatting."""
        return f'<div style="margin:3px 0;line-height:1.6;">{self._inline(text)}</div>'

    def _inline(self, text: str) -> str:
        """Apply inline formatting (no markdown in system messages)."""
        result = self._escape_html(text)
        # Bold
        result = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', result)
        result = re.sub(r'__(.+?)__', r'<b>\1</b>', result)
        # Italic
        result = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', result)
        result = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'<i>\1</i>', result)
        # Inline code
        result = re.sub(
            r'`([^`]+)`',
            f'<code style="background:{BG_SUBTLE};padding:1px 5px;border-radius:4px;'
            f'font-family:{FONT_MONO};font-size:12px;color:{ACCENT};">\\1</code>',
            result,
        )
        # Strikethrough
        result = re.sub(r'~~(.+?)~~', r'<s>\1</s>', result)
        return result

    def _escape_html(self, text: str) -> str:
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))


    def render_for_streaming(self, text: str) -> str:
        """Render text for streaming - handles incomplete markdown gracefully."""
        if not text:
            return ""

        # Count backticks to detect unclosed code blocks
        total_backticks = text.count('`')
        unclosed_code = total_backticks % 2 != 0

        if unclosed_code:
            # Find last ```
            last_triple = text.rfind('```')
            last_single = text.rfind('`')
            if last_single > last_triple:
                # Unclosed inline code - just escape it
                return self.render(text + '`')
            # Otherwise, find unclosed fenced code block
            last_triple = text.rfind('```')
            if last_triple >= 0:
                before = text[:last_triple]
                code = text[last_triple + 3:]
                return self.render(before) + self._render_code_block('', code) + f'<span style="color:{ACCENT};animation:blink 1s infinite;">▌</span>'

        return self.render(text)


class ChatBubbleFormatter:
    """Formats messages as chat bubbles with proper styling."""

    USER_BG = "rgba(45, 100, 180, 170)"
    USER_BORDER = "rgba(125, 211, 252, 0.25)"
    AI_BG = "rgba(35, 35, 72, 200)"
    AI_BORDER = "rgba(255, 255, 255, 0.08)"
    SYSTEM_COLOR = "#7070a0"

    def __init__(self, renderer: MarkdownRenderer = None):
        self.renderer = renderer or MarkdownRenderer()

    def user_bubble(self, text: str) -> str:
        """Right-aligned user bubble."""
        content = self.renderer.render(text)
        return (
            f'<div style="display:flex;justify-content:flex-end;margin:5px 8px 5px 40px;">'
            f'<div style="max-width:78%;background:{self.USER_BG};border:1px solid {self.USER_BORDER};'
            f'color:#f0f0ff;border-radius:18px 18px 4px 18px;'
            f'padding:9px 14px;font-size:13px;line-height:1.55;">'
            f'{content}</div></div>'
        )

    def ai_bubble(self, text: str, streaming: bool = False) -> str:
        """Left-aligned AI bubble."""
        content = self.renderer.render_for_streaming(text)
        cursor = ""
        if streaming:
            cursor = '<span style="display:inline-block;width:2px;height:13px;background:#7dd3fc;margin-left:2px;vertical-align:middle;animation:blink 0.8s infinite;"></span>'
        return (
            f'<div style="display:flex;justify-content:flex-start;margin:5px 8px 5px 6px;">'
            f'<div style="max-width:82%;background:{self.AI_BG};border:1px solid {self.AI_BORDER};'
            f'color:#f0f0ff;border-radius:18px 18px 18px 4px;'
            f'padding:9px 14px;font-size:13px;line-height:1.55;">'
            f'{content}{cursor}</div></div>'
        )

    def system_message(self, text: str) -> str:
        """Centered muted system message (no markdown)."""
        escaped = self.renderer._escape_html(text).replace('\n', '<br>')
        return (
            f'<div style="text-align:center;color:{self.SYSTEM_COLOR};'
            f'margin:8px 20px;font-size:12px;opacity:0.8;line-height:1.6;">{escaped}</div>'
        )