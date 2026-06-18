"""
Settings Panel — runtime configuration dialog.

Allows changing AI backend, API key, base URL, model, pet name,
sound effects toggle, clipboard monitoring, and autostart without restart.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QComboBox, QCheckBox, QFileDialog, QMessageBox,
)
from PySide6.QtGui import QPainter, QColor

import config as cfg
from theme import (
    BG_DEEP, BG_CARD, BG_SUBTLE, WHITE, BORDER, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_META,
    ACCENT, ACCENT_BRIGHT, ACCENT_SOFT, GREEN, RED, RED_SOFT,
    FONT_FAMILY, FONT_MONO,
    RADIUS_SM, RADIUS_MD, RADIUS_LG, INPUT_HEIGHT,
)


# Backend options
BACKEND_OPTIONS = [
    ("OpenAI API (DeepSeek / NVIDIA / Ollama 等)", cfg.BACKEND_OPENAI),
    ("Claude Code CLI", cfg.BACKEND_CLAUDE),
]

API_PRESETS = cfg.API_PRESETS


def _make_field_row(label_text: str, widget) -> QFrame:
    """Create a label + widget row wrapped in a QFrame (so it can be shown/hidden)."""
    frame = QFrame()
    frame.setStyleSheet("background:transparent;border:none;")
    row = QHBoxLayout(frame)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    lbl = QLabel(label_text)
    lbl.setFixedWidth(72)
    lbl.setStyleSheet(
        f"color:{TEXT_MUTED};font-size:11px;font-weight:600;"
        f"background:transparent;border:none;"
    )
    row.addWidget(lbl)
    row.addWidget(widget, 1)
    return frame


class SettingsPanel(QDialog):
    """Frameless settings dialog with all runtime-configurable options."""

    saved = Signal(dict)  # emits new config dict after save

    def __init__(self, current_config: dict, parent=None):
        super().__init__(parent)
        self._config = dict(current_config)
        self._sound_rows: dict[str, dict] = {}  # event → {enabled_cb, path_label, choose_btn}
        self._sound_paths: dict[str, str] = {}  # event → absolute path
        self.setWindowTitle("设置")
        self.setModal(True)
        self.resize(440, 600)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None
        self._build_ui()
        self._populate()

    # ── UI construction ─────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame#settingsCard {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_LG}px;
            }}
        """)
        card.setObjectName("settingsCard")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(24, 20, 24, 20)
        card_l.setSpacing(12)

        # ── Title bar ──
        title_bar = QHBoxLayout()
        title = QLabel("设置")
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:16px;font-weight:700;"
            f"background:transparent;border:none;"
        )
        title_bar.addWidget(title)
        title_bar.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background:transparent;color:{TEXT_MUTED};border:none;
                font-size:14px;border-radius:12px;
            }}
            QPushButton:hover {{ background:{RED_SOFT};color:{RED}; }}
        """)
        close_btn.clicked.connect(self.reject)
        title_bar.addWidget(close_btn)
        card_l.addLayout(title_bar)

        # ── Section: AI Backend ──
        card_l.addWidget(self._section_header("AI 后端"))

        self._backend_combo = QComboBox()
        for label, value in BACKEND_OPTIONS:
            self._backend_combo.addItem(label, value)
        self._backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        card_l.addWidget(self._backend_combo)

        # Platform preset (only for OpenAI)
        self._preset_combo = QComboBox()
        for name in API_PRESETS:
            self._preset_combo.addItem(name)
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        self._preset_frame = _make_field_row("平台预设", self._preset_combo)
        card_l.addWidget(self._preset_frame)

        # API Key (only for OpenAI)
        self._apikey_input = QLineEdit()
        self._apikey_input.setPlaceholderText("sk-...")
        self._apikey_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._apikey_frame = _make_field_row("API Key", self._apikey_input)
        card_l.addWidget(self._apikey_frame)

        # Base URL (only for OpenAI)
        self._baseurl_input = QLineEdit()
        self._baseurl_input.setPlaceholderText("https://api.openai.com/v1")
        self._baseurl_frame = _make_field_row("Base URL", self._baseurl_input)
        card_l.addWidget(self._baseurl_frame)

        # Model (only for OpenAI)
        self._model_input = QLineEdit()
        self._model_input.setPlaceholderText("gpt-4o-mini")
        self._model_frame = _make_field_row("模型", self._model_input)
        card_l.addWidget(self._model_frame)

        # ── Divider ──
        card_l.addWidget(self._divider())

        # ── Section: Pet ──
        card_l.addWidget(self._section_header("宠物"))

        self._petname_input = QLineEdit()
        self._petname_input.setPlaceholderText("小橘")
        card_l.addWidget(_make_field_row("名称", self._petname_input))

        # ── Section: Features ──
        card_l.addWidget(self._section_header("功能"))

        self._sound_cb = QCheckBox("启用音效")
        self._sound_cb.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:12px;")
        self._sound_cb.toggled.connect(self._on_sound_master_toggled)
        card_l.addWidget(self._sound_cb)

        self._clipboard_cb = QCheckBox("剪贴板监听")
        self._clipboard_cb.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:12px;")
        card_l.addWidget(self._clipboard_cb)

        self._autostart_cb = QCheckBox("开机自启动")
        self._autostart_cb.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:12px;")
        card_l.addWidget(self._autostart_cb)

        # ── Section: Sound Events (5 events) ──
        self._sound_section_frame = self._build_sound_section()
        card_l.addWidget(self._sound_section_frame)

        # ── Section: About / Crash reporter (P1-4) ──
        self._about_frame = self._build_about_section()
        card_l.addWidget(self._about_frame)

        card_l.addStretch(1)

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background:{BG_SUBTLE};color:{TEXT_PRIMARY};
                border:1.5px solid {BORDER};border-radius:{RADIUS_SM}px;
                font-size:13px;font-weight:600;
            }}
            QPushButton:hover {{ background:{RED_SOFT};border-color:{RED};color:{RED}; }}
        """)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("保存")
        save_btn.setFixedHeight(38)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background:{ACCENT};color:{WHITE};
                border:none;border-radius:{RADIUS_SM}px;
                font-size:13px;font-weight:600;
            }}
            QPushButton:hover {{ background:{ACCENT_BRIGHT}; }}
        """)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        card_l.addLayout(btn_row)

        root.addWidget(card)

    # ── Helpers ─────────────────────────────────────────────────────
    def _section_header(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{ACCENT};font-size:12px;font-weight:700;"
            f"background:transparent;border:none;padding-top:4px;"
        )
        return lbl

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{BORDER};border:none;")
        return line

    # ── Sound events section ────────────────────────────────────────
    def _build_sound_section(self) -> QFrame:
        """Build a frame containing 5 sound event rows (enabled + custom path)."""
        frame = QFrame()
        frame.setObjectName("soundSection")
        frame.setStyleSheet(
            f"QFrame#soundSection {{ background:{BG_SUBTLE};"
            f" border:1px solid {BORDER_SUBTLE};"
            f" border-radius:{RADIUS_MD}px; }}"
        )
        v = QVBoxLayout(frame)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(4)

        # 标题
        title = QLabel("事件音（5 个事件独立开关）")
        title.setStyleSheet(
            f"color:{TEXT_SECONDARY};font-size:11px;font-weight:600;"
            f"background:transparent;border:none;padding-bottom:2px;"
        )
        v.addWidget(title)

        events = [
            ("voice_start", "🎙 开始说话"),
            ("message_received", "📨 收到消息"),
            ("file_dropped", "📎 拖入文件"),
            ("message_sent", "📤 发送消息"),
            ("error", "⚠️ 错误"),
        ]
        for event, label in events:
            row = self._build_sound_event_row(event, label)
            v.addWidget(row)

        return frame

    def _build_sound_event_row(self, event: str, label: str) -> QFrame:
        row_frame = QFrame()
        row_frame.setStyleSheet(f"background:{BG_CARD};border:none;")
        h = QHBoxLayout(row_frame)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(8)

        # 启用开关
        cb = QCheckBox(label)
        cb.setStyleSheet(
            f"color:{TEXT_SECONDARY};font-size:12px;"
            f"background:transparent;border:none;"
        )
        h.addWidget(cb)

        # 路径标签
        path_label = QLabel("（内置）")
        path_label.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:11px;"
            f"background:transparent;border:none;"
        )
        path_label.setMinimumWidth(120)
        h.addWidget(path_label, 1)

        # 试听
        test_btn = QPushButton("▶")
        test_btn.setFixedSize(28, 24)
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.setToolTip("试听")
        test_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD};color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER_SUBTLE};border-radius:4px;font-size:11px; }}"
            f"QPushButton:hover {{ background:{ACCENT_SOFT};color:{ACCENT}; }}"
        )
        test_btn.clicked.connect(lambda _=False, e=event: self._on_test_sound(e))
        h.addWidget(test_btn)

        # 选择文件
        choose_btn = QPushButton("选…")
        choose_btn.setFixedSize(36, 24)
        choose_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        choose_btn.setToolTip("选择自定义音频文件")
        choose_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD};color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER_SUBTLE};border-radius:4px;font-size:11px; }}"
            f"QPushButton:hover {{ background:{ACCENT_SOFT};color:{ACCENT}; }}"
        )
        choose_btn.clicked.connect(lambda _=False, e=event: self._on_choose_sound_file(e))
        h.addWidget(choose_btn)

        # 清除
        clear_btn = QPushButton("✕")
        clear_btn.setFixedSize(24, 24)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setToolTip("清除（用内置音）")
        clear_btn.setStyleSheet(
            f"QPushButton {{ background:transparent;color:{TEXT_MUTED};"
            f" border:none;border-radius:4px;font-size:12px; }}"
            f"QPushButton:hover {{ background:{RED_SOFT};color:{RED}; }}"
        )
        clear_btn.clicked.connect(lambda _=False, e=event: self._on_clear_sound_file(e))
        h.addWidget(clear_btn)

        self._sound_rows[event] = {
            "enabled_cb": cb,
            "path_label": path_label,
        }
        return row_frame

    def _on_sound_master_toggled(self, checked: bool):
        """总开关关闭时，5 个事件行变灰。"""
        for row in self._sound_rows.values():
            for w in (row["enabled_cb"], row["path_label"]):
                w.setEnabled(checked)

    def _on_choose_sound_file(self, event: str):
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"选择「{event}」音效文件",
            "",
            "音频文件 (*.wav *.mp3 *.ogg *.m4a *.flac);;所有文件 (*.*)",
        )
        if not path:
            return
        self._sound_paths[event] = path
        self._sound_rows[event]["path_label"].setText(self._short_path(path))

    def _on_clear_sound_file(self, event: str):
        self._sound_paths[event] = ""
        self._sound_rows[event]["path_label"].setText("（内置）")

    def _on_test_sound(self, event: str):
        """试听：临时构造 config dict 喂给 audio.play。"""
        cfg = dict(self._config)
        cfg[f"sound_{event}_enabled"] = True
        cfg[f"sound_{event}_custom_path"] = self._sound_paths.get(event, "")
        import audio
        audio.play(event, config_dict=cfg)

    def _short_path(self, path: str, max_len: int = 36) -> str:
        if not path:
            return "（内置）"
        if len(path) <= max_len:
            return path
        return "…" + path[-(max_len - 1):]

    # ── About / Crash reporter (P1-4) ───────────────────────────────
    def _build_about_section(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("aboutSection")
        frame.setStyleSheet(
            f"QFrame#aboutSection {{ background:{BG_SUBTLE};"
            f" border:1px solid {BORDER_SUBTLE};"
            f" border-radius:{RADIUS_MD}px; }}"
        )
        v = QVBoxLayout(frame)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(6)

        title = QLabel("关于 / 崩溃上报")
        title.setStyleSheet(
            f"color:{TEXT_SECONDARY};font-size:11px;font-weight:600;"
            f"background:transparent;border:none;"
        )
        v.addWidget(title)

        version = QLabel(f"BuddyDesk v{cfg.APP_VERSION}")
        version.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:12px;"
            f"background:transparent;border:none;"
        )
        v.addWidget(version)

        # 崩溃状态
        self._crash_status_lbl = QLabel()
        self._crash_status_lbl.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:11px;"
            f"background:transparent;border:none;"
        )
        self._crash_status_lbl.setWordWrap(True)
        v.addWidget(self._crash_status_lbl)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._crash_scan_btn = QPushButton("🔍 重新扫描")
        self._crash_scan_btn.setFixedHeight(28)
        self._crash_scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._crash_scan_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD};color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER_SUBTLE};border-radius:4px;font-size:11px;padding:0 10px; }}"
            f"QPushButton:hover {{ background:{ACCENT_SOFT};color:{ACCENT}; }}"
        )
        self._crash_scan_btn.clicked.connect(self._refresh_crash_status)
        btn_row.addWidget(self._crash_scan_btn)

        self._crash_report_btn = QPushButton("📋 复制并上报")
        self._crash_report_btn.setFixedHeight(28)
        self._crash_report_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._crash_report_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT};color:{WHITE};"
            f" border:none;border-radius:4px;font-size:11px;font-weight:600;padding:0 10px; }}"
            f"QPushButton:hover {{ background:{ACCENT_BRIGHT}; }}"
        )
        self._crash_report_btn.clicked.connect(self._on_report_crash)
        self._crash_report_btn.setEnabled(False)
        btn_row.addWidget(self._crash_report_btn)
        btn_row.addStretch()

        v.addLayout(btn_row)

        # 初次构建时刷一次状态
        self._refresh_crash_status()

        return frame

    def _refresh_crash_status(self):
        try:
            import ui.crash_reporter as cr
            unread = cr.get_unread_crashes()
            self._unread_crashes = unread
            if unread:
                latest = unread[0]
                import time
                mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(latest["mtime"]))
                self._crash_status_lbl.setText(
                    f"⚠️ 发现 {len(unread)} 个新崩溃（最近: {mtime}）"
                )
                self._crash_status_lbl.setStyleSheet(
                    f"color:{RED};font-size:11px;font-weight:600;"
                    f"background:transparent;border:none;"
                )
                self._crash_report_btn.setEnabled(True)
            else:
                total = len(cr.get_all_crashes())
                if total:
                    self._crash_status_lbl.setText(f"✓ 没有新崩溃（{total} 个已读）")
                else:
                    self._crash_status_lbl.setText("✓ 没有发现崩溃日志")
                self._crash_status_lbl.setStyleSheet(
                    f"color:{GREEN};font-size:11px;"
                    f"background:transparent;border:none;"
                )
                self._crash_report_btn.setEnabled(False)
        except Exception as e:
            self._crash_status_lbl.setText(f"扫描出错: {e}")

    def _on_report_crash(self):
        try:
            import ui.crash_reporter as cr
            crashes = getattr(self, "_unread_crashes", cr.get_unread_crashes())
            if not crashes:
                QMessageBox.information(self, "崩溃上报", "没有可上报的崩溃。")
                return
            body = cr.build_issue_body(crashes, cfg.APP_VERSION)
            if cr.copy_to_clipboard(body):
                cr.open_issue_url()
                cr.mark_all_read()
                QMessageBox.information(
                    self,
                    "崩溃已复制",
                    f"已将 {len(crashes)} 个崩溃信息复制到剪贴板，\n"
                    f"浏览器已打开 GitHub Issue 新建页。\n"
                    f"请手动粘贴（Ctrl+V）并补充复现步骤。",
                )
                self._refresh_crash_status()
            else:
                QMessageBox.warning(self, "复制失败", "无法复制到剪贴板。")
        except Exception as e:
            QMessageBox.warning(self, "上报失败", str(e))

    def _populate(self):
        """Fill inputs from the current config dict."""
        backend = self._config.get("backend", cfg.DEFAULT_BACKEND)
        for i, (_, val) in enumerate(BACKEND_OPTIONS):
            if val == backend:
                self._backend_combo.setCurrentIndex(i)
                break

        api_base = self._config.get("openai_api_base", cfg.DEFAULT_API_BASE)
        model = self._config.get("openai_model", cfg.DEFAULT_MODEL)
        api_key = self._config.get("openai_api_key", "")

        self._apikey_input.setText(api_key)
        self._baseurl_input.setText(api_base)
        self._model_input.setText(model)
        self._petname_input.setText(self._config.get("pet_name", "小橘"))
        self._sound_cb.setChecked(self._config.get("sound_enabled", True))
        self._clipboard_cb.setChecked(self._config.get("clipboard_monitor", False))
        self._autostart_cb.setChecked(self._config.get("autostart", False))

        # Populate 5 sound event rows
        for event, row in self._sound_rows.items():
            row["enabled_cb"].setChecked(
                self._config.get(f"sound_{event}_enabled", True)
            )
            row["path_label"].setText(
                self._short_path(self._config.get(f"sound_{event}_custom_path", ""))
            )
        self._on_sound_master_toggled(self._sound_cb.isChecked())

        # Try to match preset
        self._preset_combo.blockSignals(True)
        matched = False
        for i, (name, p) in enumerate(API_PRESETS.items()):
            if p["base"] == api_base:
                self._preset_combo.setCurrentIndex(i)
                matched = True
                break
        if not matched:
            self._preset_combo.setCurrentText("自定义")
        self._preset_combo.blockSignals(False)

        self._on_backend_changed()

    def _on_backend_changed(self):
        backend = self._backend_combo.currentData()
        is_openai = (backend == cfg.BACKEND_OPENAI)
        self._preset_frame.setVisible(is_openai)
        self._apikey_frame.setVisible(is_openai)
        self._baseurl_frame.setVisible(is_openai)
        self._model_frame.setVisible(is_openai)

    def _on_preset_changed(self, name: str):
        p = API_PRESETS.get(name, {})
        if p.get("base"):
            self._baseurl_input.setText(p["base"])
        if p.get("model"):
            self._model_input.setText(p["model"])

    def _save(self):
        self._config["backend"] = self._backend_combo.currentData()
        self._config["openai_api_key"] = self._apikey_input.text().strip()
        self._config["openai_api_base"] = self._baseurl_input.text().strip()
        self._config["openai_model"] = self._model_input.text().strip()
        self._config["pet_name"] = self._petname_input.text().strip() or "小橘"
        self._config["sound_enabled"] = self._sound_cb.isChecked()
        self._config["clipboard_monitor"] = self._clipboard_cb.isChecked()

        # 5 事件音
        for event, row in self._sound_rows.items():
            self._config[f"sound_{event}_enabled"] = row["enabled_cb"].isChecked()
            # 路径从 path_label 关联的 _sound_paths 字典读
            self._config[f"sound_{event}_custom_path"] = self._sound_paths.get(event, "")

        autostart = self._autostart_cb.isChecked()
        self._config["autostart"] = autostart
        self._apply_autostart(autostart)

        cfg.save_user_config(self._config)
        self.saved.emit(self._config)
        self.accept()

    def _apply_autostart(self, enabled: bool):
        """Write or delete the Windows autostart registry key."""
        if sys.platform != "win32":
            return
        try:
            import winreg
            import os
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            if enabled:
                exe = sys.executable
                entry = f'"{exe}" "{os.path.join(cfg._BASE, "main.py")}"'
                winreg.SetValueEx(key, "BuddyDesk", 0, winreg.REG_SZ, entry)
            else:
                try:
                    winreg.DeleteValue(key, "BuddyDesk")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception:
            pass

    # ── Frameless window drag ───────────────────────────────────────
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(0, 0, self.width(), self.height(), QColor(0, 0, 0, 35))
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _e):
        self._drag_pos = None
