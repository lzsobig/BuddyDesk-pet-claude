"""
Markdown Renderer for ChatWindow.

Renders markdown text to HTML with streaming support for incomplete content.
Supports: code blocks (with language tags), inline code, bold, italic, lists, headers, blockquotes.

Colors pull from theme.py so light/dark variants stay in sync.

P1-2: 字号缩放 —— 通过 font_scale 控制所有 font-size: Npx 的输出。
仅影响 Markdown 渲染的字号（标题/正文/代码块/列表），输入栏/灵动岛/桌宠不受影响。

P1-3: 编号列表自动检测 → 渲染为 <div class="opt-card" data-idx="N">可点击选项</div>。
启发式：连续 ≤7 条 + 每条 < 30 字 + 没有"第一步""接下来"等叙述词 → 视为选项。
chat_window 看到 class="opt-card" 时转为 QToolButton。
"""
import re

import config
from theme import (
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, BORDER,
    ACCENT, ACCENT_SOFT, BG_SUBTLE, BG_CARD, FONT_MONO,
)


_PX_PATTERN = re.compile(r'font-size:\s*(\d+(?:\.\d+)?)px')

# P1-3: 叙述性关键词（出现这些词就不当选项）
_NARRATIVE_HINTS = re.compile(r'(第[一二三四五六七八九十]|首先|其次|然后|接下来|最后|步骤|阶段)')


def _scale_px(html: str, scale: float) -> str:
    """对 HTML 字符串里所有 font-size: Npx 做等比缩放。"""
    if scale == 1.0:
        return html
    def repl(m: re.Match) -> str:
        v = float(m.group(1)) * scale
        return f'font-size:{v:.1f}px'
    return _PX_PATTERN.sub(repl, html)


def _detect_option_list(text: str) -> list[str] | None:
    """P1-3: 检测一段连续有序列表是否应被渲染为可点击选项。

    返回清洗后的选项文本列表（去 "1. " 前缀），不通过返回 None。
    """
    lines = text.strip().split('\n')
    items: list[str] = []
    for line in lines:
        m = re.match(r'^\s*\d+\.\s+(.+)$', line)
        if not m:
            # 列表中断
            if items:
                break
            continue
        content = m.group(1).strip()
        items.append(content)
    if not items:
        return None
    if len(items) > 7:
        return None
    for it in items:
        if len(it) > 30:
            return None
    full = '\n'.join(items)
    if _NARRATIVE_HINTS.search(full):
        return None
    return items


def _render_option_cards(items: list[str], scale: float) -> str:
    """P1-3: 把选项列表渲染为可点击卡片（class=opt-card, data-idx）。"""
    parts: list[str] = []
    parts.append('<div class="opt-card-list" style="margin:6px 0;display:flex;flex-direction:column;gap:4px;">')
    for i, it in enumerate(items):
        # 用 base64 防特殊字符破 HTML（实际 _inline 会先 escape，但这里直接放文本最安全）
        from html import escape
        text = escape(it)
        parts.append(
            f'<div class="opt-card" data-idx="{i}" '
            f'style="display:block;padding:8px 12px;background:{BG_SUBTLE};'
            f'border:1px solid {BORDER};border-radius:6px;cursor:pointer;'
            f'color:{TEXT_PRIMARY};font-size:12px;">'
            f'<span style="color:{ACCENT};font-weight:600;margin-right:6px;">{i+1}.</span>{text}</div>'
        )
    parts.append('</div>')
    return _scale_px('\n'.join(parts), scale)


class MarkdownRenderer:
    """Converts markdown text to HTML for QTextEdit display."""

    def __init__(self, font_scale: float = 1.0):
        self.font_scale = font_scale  # P1-2: 由 chat_window 注入

    def set_font_scale(self, scale: float) -> None:
        """P1-2: 实时更新字号缩放比例，已渲染的消息下次更新会生效。"""
        self.font_scale = scale

    def extract_option_list(self, text: str) -> list[str] | None:
        """P1-3: 若 text 末尾一段是"可点击选项"模式，返回清洗后的选项列表。
        否则返回 None（让 bubble 走普通 HTML 渲染）。
        """
        return _detect_option_list(text)

    def extract_tasks_block(self, text: str) -> tuple[str, list[dict]] | None:
        """P3-4: 若 text 含 ```tasks YAML 块，提取为 (剩余文本, 任务列表)。
        返回 None 表示无 tasks 块。
        任务列表元素: {title, mode, difficulty}

        支持两种 YAML 风格：
        A. 列表式：
            - title: 任务A
              mode: claude_code
              difficulty: 2
            - title: 任务B
        B. 列表值式（更简单）：
            - 任务A
            - 任务B
        """
        m = re.search(r"```tasks\s*\n([\s\S]*?)\n```", text)
        if not m:
            return None
        yaml_text = m.group(1)
        tasks: list[dict] = []
        current: dict = {}
        for line in yaml_text.split('\n'):
            stripped = line.lstrip()
            if not stripped or stripped.startswith('#'):
                continue
            if stripped.startswith('- '):
                # 新任务
                if current.get("title"):
                    tasks.append(current)
                rest = stripped[2:].strip()
                # 判断是 "- title: 任务A" 还是 "- 任务A"
                kv = re.match(r'(\w+):\s*(.+)', rest)
                if kv:
                    # A 风格
                    current = {
                        kv.group(1): kv.group(2).strip(),
                        "mode": "claude_code",
                        "difficulty": 1,
                    }
                    # 兼容其他字段
                    if kv.group(1) != "title":
                        current["title"] = rest
                else:
                    # B 风格
                    current = {
                        "title": rest,
                        "mode": "claude_code",
                        "difficulty": 1,
                    }
            else:
                # 字段：key: value（接续上一个任务）
                km = re.match(r'(\w+):\s*(.+)', stripped)
                if km and current:
                    key = km.group(1).strip()
                    val = km.group(2).strip()
                    if key in ("title", "mode", "difficulty"):
                        if key == "difficulty":
                            try:
                                val = int(val)
                            except ValueError:
                                val = 1
                        current[key] = val
        if current.get("title"):
            tasks.append(current)
        # 剩余文本去掉 tasks 块
        remaining = text[:m.start()] + text[m.end():]
        return remaining.rstrip(), tasks

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
                ul_text = re.sub(r'^[-*]\s+', '', line)
                result.append(f'<li style="margin:2px 0 2px 14px;color:{TEXT_PRIMARY};list-style-type:disc;">{self._inline(ul_text)}</li>')
            # Ordered list — 普通 li（可点击选项卡由 _MessageBubble 特殊处理）
            elif re.match(r'^\d+\.\s+', line):
                flush_buffer()
                ol_text = re.sub(r'^\d+\.\s+', '', line)
                result.append(f'<li style="margin:2px 0 2px 14px;list-style-type:decimal;color:{TEXT_PRIMARY};">{self._inline(ol_text)}</li>')
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
        # P1-2: 末尾对所有 font-size: Npx 做缩放
        return _scale_px('\n'.join(result), self.font_scale)

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
        """Apply inline formatting (no markdown in system messages).

        Processing order: escape → inline code (protect from further regex) → bold → italic → strikethrough.
        Inline code is extracted first so that asterisks inside code spans are never
        misinterpreted as bold/italic markers.
        """
        result = self._escape_html(text)

        # Extract inline code spans first — replace with placeholders to protect content
        code_spans: list[str] = []
        def _stash_code(m):
            code_spans.append(
                f'<code style="background:{BG_SUBTLE};padding:1px 5px;border-radius:4px;'
                f'font-family:{FONT_MONO};font-size:12px;color:{ACCENT};">{m.group(1)}</code>'
            )
            return f'\x00CODE{len(code_spans) - 1}\x00'

        result = re.sub(r'`([^`]+)`', _stash_code, result)

        # Bold
        result = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', result)
        result = re.sub(r'__(.+?)__', r'<b>\1</b>', result)
        # Italic — require word boundaries to avoid matching `2*3*4`
        result = re.sub(r'(?<=[\s(])\*(.+?)\*(?=[\s).,;:!?])', r'<i>\1</i>', result)
        result = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'<i>\1</i>', result)
        # Strikethrough
        result = re.sub(r'~~(.+?)~~', r'<s>\1</s>', result)

        # Restore code spans
        for i, html in enumerate(code_spans):
            result = result.replace(f'\x00CODE{i}\x00', html)

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
                return self.render(before) + self._render_code_block('', code) + f'<span style="color:{ACCENT};font-weight:bold;">&#9612;</span>'

        return self.render(text)
