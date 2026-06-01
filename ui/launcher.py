"""
Launcher — light warm theme matching the user's HTML mockup.

A single QDialog with: mascot, title, backend option cards (radio + brand
SVG icon + name + description + status badge + install hint), pet name
input, launch + quit buttons. The dialog itself is frameless + rounded — we
paint a custom background so the corners follow the 20px radius defined
in the design.
"""
import os
import subprocess

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF, QRect
from PySide6.QtGui import QFont, QPainter, QColor, QBrush, QImage, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QButtonGroup, QComboBox,
    QFrame, QScrollArea, QWidget, QGraphicsDropShadowEffect,
)

import config
from theme import (
    BG_DEEP, BG_SUBTLE, BG_CARD, WHITE, BORDER, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_META,
    ACCENT, ACCENT_BRIGHT, ACCENT_SOFT, ACCENT_GLOW,
    GREEN, GREEN_SOFT, GREEN_GLOW,
    RED, RED_SOFT, GOLD, GOLD_SOFT, FONT_FAMILY, FONT_MONO,
    RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_PILL,
    WARM_CAT_LIGHT, WARM_CAT_MID, WARM_CAT_DEEP, WARM_CAT_TEXT,
    BTN_HEIGHT_PRIMARY, BTN_HEIGHT_SECONDARY, INPUT_HEIGHT,
)

API_PRESETS = {
    "OpenAI": {"base": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "DeepSeek": {"base": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "NVIDIA": {"base": "https://integrate.api.nvidia.com/v1", "model": "meta/llama-3.1-8b-instruct"},
    "Ollama (本地)": {"base": "http://localhost:11434/v1", "model": "llama3"},
    "硅基流动": {"base": "https://api.siliconflow.cn/v1", "model": "Qwen/Qwen2.5-7B-Instruct"},
    "Moonshot": {"base": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "自定义": {"base": "", "model": ""},
}

# Resolve asset directory once so _BackendCard can find the SVGs regardless
# of the current working directory at import time.
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
_CLAUDE_SVG = os.path.join(_ASSETS_DIR, "icons", "claude.svg")
_OPENAI_SVG = os.path.join(_ASSETS_DIR, "icons", "openai.svg")


def _load_svg_pixmap(path: str, size: int = 16) -> QPixmap:
    """Render an SVG file into a QPixmap at the given square size.

    We use QSvgRenderer directly (not QIcon) because PySide6's QIcon wraps
    SVGs in ways that don't render predictably across DPIs on Windows.
    """
    renderer = QSvgRenderer(path)
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(p)
    p.end()
    return QPixmap.fromImage(img)


class _Mascot(QLabel):
    """Floating warm-gradient circle with a cat emoji. Animates gently."""

    def __init__(self):
        super().__init__("🐱")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(80, 80)
        self.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(x1:0,y1:0,x2:0.5,y2:1,
                    stop:0 {WARM_CAT_LIGHT}, stop:0.5 {WARM_CAT_MID}, stop:1 {WARM_CAT_DEEP});
                border: 2px solid {BORDER};
                border-radius: 40px;
                font-size: 38px;
            }}
        """)
        self._float = QPropertyAnimation(self, b"pos")
        self._float.setDuration(4000)
        self._float.setLoopCount(-1)
        self._float.setStartValue(self.pos())
        self._float.setEndValue(self.pos())


class _BackendCard(QFrame):
    """A clickable card representing one AI backend option.

    Layout: [Radio] | [Brand-icon + Name (vertically centered, 4px gap)]
                       [Description]
                       [Status badge + optional install hint]
    """

    def __init__(self, name: str, desc: str, brand_svg: str,
                 radio: QRadioButton, badge: QLabel | None = None,
                 hint: QLabel | None = None):
        super().__init__()
        self.setObjectName(f"card_{name.lower().replace(' ', '_')}")
        # Tone upgrade (Track 2 Task D): +8px height vs the previous 80px.
        self.setFixedHeight(88)
        self._radio = radio
        self._badge = badge
        self._hint = hint

        # Make the whole card clickable as a click target (hand cursor +
        # active feedback) without changing the underlying radio behavior.
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        # ── Radio (20x20 circle; theme.py handles outline→solid ACCENT) ──
        self._radio.setStyleSheet("background:transparent;border:none;")
        # Push the radio a touch above vertical center so it visually lines
        # up with the [icon+name] row instead of with the description.
        radio_wrap = QWidget()
        radio_wrap.setStyleSheet("background:transparent;border:none;")
        radio_lay = QVBoxLayout(radio_wrap)
        radio_lay.setContentsMargins(0, 2, 0, 0)
        radio_lay.setSpacing(0)
        radio_lay.addWidget(self._radio)
        radio_lay.addStretch(1)
        layout.addWidget(radio_wrap)

        # ── Info column ──
        info = QVBoxLayout()
        info.setSpacing(2)
        info.setContentsMargins(0, 0, 0, 0)

        # Title row: brand SVG icon + name, vertically centered, 4px gap.
        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(16, 16)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background:transparent;border:none;")
        # Cache the pixmap so we only hit the disk on first paint.
        if os.path.exists(brand_svg):
            icon_lbl.setPixmap(_load_svg_pixmap(brand_svg, 16))
        title_row.addWidget(icon_lbl)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:15px;font-weight:600;"
            f"background:transparent;border:none;"
        )
        # Match the icon's optical center to the text's x-height by nudging
        # the label up 1px — QLabel baseline ≠ glyph optical center.
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(name_lbl)
        title_row.addStretch(1)
        info.addLayout(title_row)

        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:11px;"
            f"background:transparent;border:none;"
        )
        info.addWidget(desc_lbl)

        if badge is not None:
            info.addWidget(badge)
        if hint is not None:
            info.addWidget(hint)

        layout.addLayout(info, 1)

        self._apply_style(selected=False)
        self._radio.toggled.connect(lambda checked: self._apply_style(checked))

    def _apply_style(self, selected: bool):
        # Selection is signaled by a slightly thicker neutral border (no green
        # accent), keeping the card consistent with the soft, light theme.
        if selected:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {WHITE};
                    border: none;
                    border-radius: 16px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {WHITE};
                    border: 1px solid {BORDER};
                    border-radius: 16px;
                }}
                QFrame:hover {{
                    border: 1.5px solid {TEXT_MUTED};
                    background: {WHITE};
                }}
            """)
        # Re-apply the hover shadow by tweaking the graphics effect each
        # time the selection toggles (cheap; only runs on toggle).
        self._apply_shadow(selected=selected)

    def _apply_shadow(self, selected: bool):
        # Soft drop shadow on hover/selected. Implemented as a
        # QGraphicsDropShadowEffect since QSS box-shadow isn't supported
        # by Qt. Hidden on the unselected state to keep the card visually
        # flat until the user shows intent.
        eff = self.graphicsEffect()
        if not isinstance(eff, QGraphicsDropShadowEffect):
            eff = QGraphicsDropShadowEffect(self)
            self.setGraphicsEffect(eff)
        eff.setBlurRadius(16)
        eff.setOffset(0, 4)
        eff.setColor(QColor(0, 0, 0, int(255 * 0.06)))  # rgba(0,0,0,0.06)
        eff.setEnabled(selected)

    def enterEvent(self, e):
        # Show the hover shadow even when the card isn't selected.
        eff = self.graphicsEffect()
        if isinstance(eff, QGraphicsDropShadowEffect):
            eff.setEnabled(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        # Restore the selected/unselected shadow state on leave.
        self._apply_shadow(selected=self._radio.isChecked())
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._radio.setChecked(True)
        super().mousePressEvent(e)


class _InputField(QFrame):
    """A pill-shaped input with optional icon on the left."""

    def __init__(self, icon: str, placeholder: str, text: str = ""):
        super().__init__()
        self.setObjectName("inputField")
        self.setStyleSheet(f"""
            QFrame#inputField {{
                background: {BG_CARD};
                border: 1.5px solid {BORDER};
                border-radius: {RADIUS_MD}px;
            }}
            QFrame#inputField:focus-within {{
                border: 1.5px solid {ACCENT};
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 4, 0)
        layout.setSpacing(10)

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(20)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            f"font-size:16px;background:transparent;border:none;"
        )
        layout.addWidget(icon_lbl)

        self._input = QLineEdit()
        self._input.setPlaceholderText(placeholder)
        self._input.setText(text)
        self._input.setStyleSheet(
            f"border:none;background:transparent;"
            f"color:{TEXT_PRIMARY};font-size:13px;"
        )
        layout.addWidget(self._input, 1)
        self.setFixedHeight(INPUT_HEIGHT)


class LauncherDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result_config = None
        self._setup_ui()
        self._load_saved()
        QTimer.singleShot(500, self._check_claude)

    def _setup_ui(self):
        self.setWindowTitle(f"{config.APP_NAME} — 启动")
        self.setFixedSize(460, 720)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        # Translucent so the painted rounded background shows through.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Apply the rounded region mask on the next event-loop tick, after
        # the child widgets have been laid out. Doing it here in __init__
        # can clip the content because the layout hasn't computed sizes yet.
        from PySide6.QtCore import QTimer as _QtTimer
        _QtTimer.singleShot(0, self._apply_rounded_mask)

        root = QVBoxLayout(self)

        # Custom title bar — drag area on the left, window controls on the right.
        # Replaces the missing OS chrome since we're FramelessWindowHint.
        title_bar = QFrame()
        title_bar.setFixedHeight(36)
        title_bar.setStyleSheet("background:transparent;border:none;")
        tb_l = QHBoxLayout(title_bar)
        tb_l.setContentsMargins(16, 0, 8, 0)
        tb_l.setSpacing(4)
        tb_l.addStretch()

        from ui.icon_widgets import WindowControlButton
        minimize_btn = WindowControlButton(
            "min", color=ACCENT, hover_bg=BG_SUBTLE, hover_fg=TEXT_SECONDARY,
        )
        minimize_btn.mousePressEvent = lambda e: self.showMinimized() if e.button() == Qt.MouseButton.LeftButton else None
        tb_l.addWidget(minimize_btn)

        close_btn = WindowControlButton(
            "close", color=ACCENT, hover_bg=RED_SOFT, hover_fg=RED,
        )
        close_btn.mousePressEvent = lambda e: self.reject() if e.button() == Qt.MouseButton.LeftButton else None
        tb_l.addWidget(close_btn)
        root.addWidget(title_bar)

        # Content wrapper with the side margins the original design uses
        content = QWidget()
        content.setStyleSheet("background:transparent;border:none;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 4, 32, 0)
        content_layout.setSpacing(0)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        root.addWidget(content)

        # Mascot
        self._mascot = _Mascot()
        mascot_row = QHBoxLayout()
        mascot_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mascot_row.addWidget(self._mascot)
        content_layout.addLayout(mascot_row)
        content_layout.addSpacing(20)

        # Title block
        title = QLabel(config.APP_NAME)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tf = QFont("Segoe UI", 22)
        tf.setWeight(QFont.Weight.Bold)
        tf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -0.5)
        title.setFont(tf)
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY};background:transparent;border:none;"
        )
        content_layout.addWidget(title)

        sub = QLabel()
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setTextFormat(Qt.TextFormat.RichText)
        sub.setText(
            f'<span style="color:{TEXT_MUTED};font-size:12px;letter-spacing:0.08em;">'
            f'桌面 AI 伴侣 <span style="color:{TEXT_META};font-size:3px;vertical-align:middle;">●</span> '
            f'快捷键一按 <span style="color:{TEXT_META};font-size:3px;vertical-align:middle;">●</span> '
            f'AI 即来</span>'
        )
        sub.setStyleSheet("background:transparent;border:none;margin-top:6px;")
        content_layout.addWidget(sub)
        content_layout.addSpacing(28)

        # Scrollable form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        sw = QWidget()
        sw.setStyleSheet("background:transparent;")
        fl = QVBoxLayout(sw)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(20)

        # ── Backend section ──
        backend_label = QLabel("选择 AI 后端")
        backend_label.setStyleSheet(
            f"color:{ACCENT};font-size:11px;font-weight:600;"
            f"background:transparent;border:none;letter-spacing:0.06em;"
        )
        fl.addWidget(backend_label)

        self.backend_group = QButtonGroup(self)

        # Claude badge + install hint (shown only when CLI missing)
        self.claude_badge = QLabel("检测中…")
        self.claude_badge.setStyleSheet(self._badge_style(GOLD_SOFT, GOLD))

        self.claude_hint = QLabel("请先安装 Claude CLI")
        self.claude_hint.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:10px;"
            f"background:transparent;border:none;margin-top:2px;"
        )
        self.claude_hint.setVisible(False)  # hidden until detection runs

        claude_radio = QRadioButton()
        self.claude_card = _BackendCard(
            "Claude Code",
            "推荐 · 零配置 · 直接调用本地 CLI",
            _CLAUDE_SVG,
            claude_radio,
            self.claude_badge,
            self.claude_hint,
        )
        self.backend_group.addButton(claude_radio, 0)
        self.claude_radio = claude_radio
        fl.addWidget(self.claude_card)

        openai_radio = QRadioButton()
        self.openai_card = _BackendCard(
            "OpenAI API",
            "DeepSeek / NVIDIA / Ollama / 硅基流动 等",
            _OPENAI_SVG,
            openai_radio,
        )
        self.backend_group.addButton(openai_radio, 1)
        self.openai_radio = openai_radio
        fl.addWidget(self.openai_card)

        # ── API config (only when OpenAI selected) ──
        self.config_frame = QFrame()
        self.config_frame.setStyleSheet("background:transparent;border:none;")
        cf = QVBoxLayout(self.config_frame)
        cf.setContentsMargins(0, 0, 0, 0)
        cf.setSpacing(10)

        cf.addWidget(self._field_label("API 平台预设"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(API_PRESETS.keys())
        self.preset_combo.currentTextChanged.connect(self._on_preset)
        cf.addWidget(self.preset_combo)

        self.api_key_input = self._labeled_field(cf, "API Key", "sk-...", echo_password=True)

        self.base_url_input = self._labeled_field(cf, "API Base URL", "https://...")

        self.model_input = self._labeled_field(cf, "Model", "gpt-4o-mini")

        fl.addWidget(self.config_frame)

        # ── Pet name (always visible) ──
        pet_label = QLabel("宠物名字")
        pet_label.setStyleSheet(
            f"color:{ACCENT};font-size:11px;font-weight:600;"
            f"background:transparent;border:none;letter-spacing:0.06em;"
        )
        fl.addWidget(pet_label)

        self.pet_field = _InputField("🐾", "给你的宠物起个名字", "小橘")
        fl.addWidget(self.pet_field)
        self.pet_name_input = self.pet_field._input

        fl.addStretch()
        scroll.setWidget(sw)
        content_layout.addWidget(scroll, 1)

        # ── Buttons ──
        btn_group = QVBoxLayout()
        btn_group.setSpacing(8)

        self.launch_btn = QPushButton(f"启动 {config.APP_NAME}")
        self.launch_btn.setFixedHeight(BTN_HEIGHT_PRIMARY)
        self.launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.launch_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: {WHITE};
                border: none;
                border-radius: {RADIUS_MD}px;
                font-size: 15px;
                font-weight: 600;
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{
                background: {ACCENT_BRIGHT};
            }}
            QPushButton:pressed {{
                background: #3a9974;
            }}
        """)
        self.launch_btn.clicked.connect(self._on_launch)
        btn_group.addWidget(self.launch_btn)

        quit_btn = QPushButton("退出")
        quit_btn.setFixedHeight(BTN_HEIGHT_SECONDARY)
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_MUTED};
                border: 1.5px solid {BORDER};
                border-radius: {RADIUS_MD}px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                border-color: {TEXT_META};
                color: {TEXT_SECONDARY};
                background: {BG_CARD};
            }}
        """)
        quit_btn.clicked.connect(self.reject)
        btn_group.addWidget(quit_btn)

        content_layout.addLayout(btn_group)
        content_layout.addSpacing(8)

        # Version
        ver = QLabel(f"Hermes Pet Win v{config.APP_VERSION}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(
            f"color:{TEXT_META};font-size:10px;background:transparent;border:none;"
            f"font-family:{FONT_MONO};letter-spacing:0.06em;"
        )
        content_layout.addWidget(ver)

        # Backend toggle
        self.claude_radio.toggled.connect(self._on_backend)
        self.openai_radio.toggled.connect(self._on_backend)
        self.openai_radio.setChecked(True)

        # Start float animation after layout settles
        QTimer.singleShot(100, self._start_float)

    # ── helpers ──
    def _badge_style(self, bg: str, fg: str) -> str:
        # Plain colored text — no background, no border, no pill. The user
        # explicitly asked the green pill framing to go; status just reads as
        # a tinted label (✓ green / ✗ red) on the card.
        return (
            f"background:transparent;color:{fg};"
            f"font-size:10px;font-weight:600;"
            f"font-family:{FONT_MONO};"
        )

    def _field_label(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(
            f"color:{ACCENT};font-size:11px;font-weight:600;"
            f"background:transparent;border:none;letter-spacing:0.06em;"
        )
        return l

    def _labeled_field(self, parent_layout, label_text: str, placeholder: str,
                       echo_password: bool = False) -> QLineEdit:
        parent_layout.addWidget(self._field_label(label_text))
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setMinimumHeight(INPUT_HEIGHT)
        if echo_password:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        parent_layout.addWidget(edit)
        return edit

    def _start_float(self):
        self._mascot._float.setStartValue(self._mascot.pos())
        end = self._mascot.pos()
        end.setY(end.y() - 6)
        self._mascot._float.setEndValue(end)
        self._mascot._float.start()

    def _check_claude(self):
        # Run the CLI version check. shell=True on Windows so npm-global
        # .cmd shims resolve correctly. 5s timeout so a hung CLI doesn't
        # stall the launcher UI.
        try:
            r = subprocess.run(
                ["claude", "--version"],
                capture_output=True, text=True, timeout=5, shell=True,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            self._mark_claude_missing()
            return

        if r.returncode == 0:
            ver = (r.stdout or "").strip().split("\n")[0][:30]
            self.claude_badge.setText(f"已安装: {ver}")
            self.claude_badge.setStyleSheet(self._badge_style(GREEN_SOFT, GREEN))
            self.claude_hint.setVisible(False)
        else:
            # Non-zero exit usually means a broken install or auth issue.
            # Treat it as "not installed" from the launcher's POV — the user
            # will see the real error the moment they try to chat.
            self._mark_claude_missing()

    def _mark_claude_missing(self):
        self.claude_badge.setText("未安装")
        self.claude_badge.setStyleSheet(
            self._badge_style("rgba(212,122,114,0.08)", RED)
        )
        self.claude_hint.setVisible(True)

    def _on_backend(self):
        is_claude = self.claude_radio.isChecked()
        self.config_frame.setVisible(not is_claude)
        self.config_frame.updateGeometry()

    def _on_preset(self, name):
        p = API_PRESETS.get(name, {})
        if p.get("base"):
            self.base_url_input.setText(p["base"])
        if p.get("model"):
            self.model_input.setText(p["model"])

    def _load_saved(self):
        saved = config.load_user_config()
        if saved.get("backend") == config.BACKEND_CLAUDE:
            self.claude_radio.setChecked(True)
        else:
            self.openai_radio.setChecked(True)
        self.api_key_input.setText(saved.get("openai_api_key", ""))
        self.base_url_input.setText(saved.get("openai_api_base", config.DEFAULT_API_BASE))
        self.model_input.setText(saved.get("openai_model", config.DEFAULT_MODEL))
        self.pet_name_input.setText(saved.get("pet_name", "小橘"))
        for name, p in API_PRESETS.items():
            if p["base"] == saved.get("openai_api_base", ""):
                self.preset_combo.setCurrentText(name)
                break

    def _on_launch(self):
        cfg = {
            "backend": config.BACKEND_CLAUDE if self.claude_radio.isChecked() else config.BACKEND_OPENAI,
            "openai_api_key": self.api_key_input.text().strip(),
            "openai_api_base": self.base_url_input.text().strip() or config.DEFAULT_API_BASE,
            "openai_model": self.model_input.text().strip() or config.DEFAULT_MODEL,
            "claude_cli_path": config.CLAUDE_CLI_PATH,
            "pet_name": self.pet_name_input.text().strip() or "小橘",
            "island_enabled": True,
            "pet_enabled": True,           # P0 fix: was hard-coded False
            "chat_enabled": True,
        }
        config.save_user_config(cfg)
        self.result_config = cfg
        self.accept()

    # ── drag support ──
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if hasattr(self, '_drag_pos') and self._drag_pos and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def _apply_rounded_mask(self):
        # Use QPainterPath for a single smooth Bézier-rendered rounded rect
        # mask. The earlier rectangle+ellipse approach left visible seams
        # where the 4 corner ellipses joined the central rectangles.
        w, h = self.width(), self.height()
        from PySide6.QtGui import QPainterPath, QRegion, QTransform
        from PySide6.QtCore import QRectF
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.0, 0.0, float(w), float(h)), RADIUS_LG, RADIUS_LG)
        self.setMask(QRegion(path.toFillPolygon(QTransform()).toPolygon()))

    def paintEvent(self, _e):
        # Paint a rounded warm-white background with a 1px border. The 4
        # outer-corner pixels stay transparent (the WA_TranslucentBackground
        # attribute on the dialog lets them be invisible) so any OS-level
        # square corner stays hidden.
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        # Inset by 0.5 so the antialiased edge sits at the pixel boundary
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QColor(BORDER))
        p.setBrush(QColor(BG_DEEP))
        p.drawRoundedRect(rect, RADIUS_LG, RADIUS_LG)
        p.end()
