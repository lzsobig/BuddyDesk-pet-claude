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
from html import escape
from urllib.parse import urlsplit

import mistune

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
    lines = text.rstrip().splitlines()
    items = []
    position = len(lines)
    while position:
        match = re.match(r'^\s*(\d+)\.\s+(.+)$', lines[position - 1])
        if not match:
            break
        items.insert(0, (int(match.group(1)), match.group(2).strip()))
        position -= 1
    if not 2 <= len(items) <= 7 or [number for number, _ in items] != list(range(1, len(items) + 1)):
        return None
    prefix = '\n'.join(lines[:position])
    if not re.search(r'选择|选项|可选|你想|你希望', prefix[-200:]):
        return None
    fence = None
    for line in lines[:position]:
        match = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
    values = [value for _, value in items]
    if fence or any(len(value) > 30 for value in values) or _NARRATIVE_HINTS.search('\n'.join(values)):
        return None
    return values


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


class _QtMarkdownHTML(mistune.HTMLRenderer):
    def __init__(self, owner):
        super().__init__(escape=True)
        self.owner = owner

    def paragraph(self, text):
        return f'<p style="font-family:Microsoft YaHei UI;font-size:14px;margin-top:6px;margin-bottom:12px;line-height:145%;">{text}</p>'

    def list(self, text, ordered, **attrs):
        tag = "ol" if ordered else "ul"
        start = f' start="{int(attrs["start"])}"' if ordered and "start" in attrs else ""
        return f'<{tag}{start} style="font-family:Microsoft YaHei UI;font-size:14px;margin-top:6px;margin-bottom:10px;">{text}</{tag}>'

    def heading(self, text, level, **attrs):
        size = {1: 19, 2: 17, 3: 15}.get(level, 14)
        return f'<h{level} style="font-size:{size}px;color:{TEXT_PRIMARY};margin:12px 0 6px;">{text}</h{level}>'

    def block_code(self, code, info=None):
        return self.owner._render_code_block((info or "code").split()[0], code.rstrip('\n'))

    def codespan(self, text):
        return f'<code style="font-family:{FONT_MONO};font-size:12px;color:{ACCENT};background-color:{BG_SUBTLE};">{escape(text)}</code>'

    def link(self, text, url, title=None):
        try:
            allowed = urlsplit(url).scheme.lower() in ("http", "https", "mailto") and not any(ord(c) < 32 for c in url)
        except ValueError:
            allowed = False
        if not allowed:
            return text
        return f'<a href="{escape(url, quote=True)}" style="color:{ACCENT};">{text}</a>'

    def image(self, text, url, title=None):
        return f'<span style="color:{TEXT_MUTED};">[图片：{text}]</span>'

    def table(self, text):
        return f'<table width="100%" border="1" cellspacing="0" cellpadding="7" style="border-color:{BORDER};font-family:Microsoft YaHei UI;font-size:13px;">{text}</table>'

    def table_head(self, text):
        return f'<tr bgcolor="{BG_SUBTLE}">{text}</tr>'

    def table_body(self, text):
        return text

    def table_row(self, text):
        return f'<tr>{text}</tr>'

    def table_cell(self, text, align=None, head=False):
        tag = "th" if head else "td"
        return f'<{tag} align="{align or "left"}" style="color:{TEXT_PRIMARY};font-weight:{"600" if head else "400"};">{text}</{tag}>'

    def task_list_item(self, text, checked=False, **attrs):
        return f'<li>{"✓" if checked else "○"} {text}</li>'


class MarkdownRenderer:
    """Converts markdown text to HTML for QTextEdit display."""

    def __init__(self, font_scale: float = 1.0):
        self.font_scale = font_scale
        self._parser = mistune.create_markdown(renderer=_QtMarkdownHTML(self), plugins=["table", "strikethrough", "task_lists", "url"])

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
        if not text:
            return ""
        return _scale_px(self._parser(text), self.font_scale)

    def _render_code_block(self, lang: str, code: str) -> str:
        return (f'<table width="100%" cellspacing="0" cellpadding="10" bgcolor="{BG_SUBTLE}"><tr><td>'
                f'<p style="margin:0;color:{TEXT_MUTED};font-size:10px;">{escape(lang)}</p>'
                f'<pre style="margin:8px 0 2px;color:{TEXT_PRIMARY};font-family:{FONT_MONO};font-size:12px;">'
                f'{escape(code)}</pre></td></tr></table>')

    def _render_paragraph(self, text: str) -> str:
        """Render a paragraph with inline formatting."""
        return f'<p style="margin-top:6px;margin-bottom:12px;line-height:145%;">{self._inline(text)}</p>'

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
        return self.render(text)
