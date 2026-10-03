"""
Settings Panel — runtime configuration dialog.

Allows changing AI backend, API key, base URL, model, pet name,
sound effects toggle, clipboard monitoring, and autostart without restart.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QComboBox, QCheckBox, QFileDialog, QMessageBox, QScrollArea, QWidget,
)
from PySide6.QtGui import QPainter, QColor

import config as cfg
from theme import (
    BG_DEEP, BG_CARD, BG_SUBTLE, WHITE, BORDER, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_META, TEXT_ON_ACCENT,
    ACCENT, ACCENT_BRIGHT, ACCENT_SOFT, GREEN, RED, RED_SOFT,
    FONT_FAMILY, FONT_MONO,
    RADIUS_SM, RADIUS_MD, RADIUS_LG, INPUT_HEIGHT,
)


# Backend options
BACKEND_OPTIONS = [
    ("OpenAI 兼容 API", cfg.BACKEND_OPENAI),
    ("Claude Code CLI", cfg.BACKEND_CLAUDE),
]

API_PRESETS = cfg.API_PRESETS


def _make_field_row(label_text: str, widget) -> QFrame:
    """Create a label + widget row wrapped in a QFrame (so it can be shown/hidden)."""
    frame = QFrame()
    frame.setObjectName("fieldRow")
    frame.setStyleSheet("QFrame#fieldRow {background:transparent;border:none;}")
    row = QHBoxLayout(frame)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    lbl = QLabel(label_text)
    lbl.setFixedWidth(80)
    lbl.setStyleSheet(
        f"color:{TEXT_SECONDARY};font-size:12px;"
        f"background:transparent;border:none;"
    )
    row.addWidget(lbl)
    row.addWidget(widget, 1)
    return frame


class SettingsCombo(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(TEXT_MUTED))
        x, y = self.width() - 17, self.height() // 2
        painter.drawLine(x - 3, y - 1, x, y + 2)
        painter.drawLine(x, y + 2, x + 3, y - 1)
        painter.end()


class SettingSwitch(QCheckBox):
    def __init__(self, label, parent=None):
        super().__init__(label, parent)
        self.setMinimumHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background:transparent;font-size:12px;")

    def hitButton(self, position):
        return self.rect().contains(position)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self.font())
        painter.setOpacity(1.0 if self.isEnabled() else 0.45)
        painter.setPen(QColor(TEXT_SECONDARY))
        painter.drawText(self.rect().adjusted(0, 0, -48, 0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())
        track = QRectF(self.width() - 34, (self.height() - 18) / 2, 34, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ACCENT if self.isChecked() else BORDER))
        painter.drawRoundedRect(track, 9, 9)
        painter.setBrush(QColor(TEXT_ON_ACCENT if self.isChecked() else TEXT_SECONDARY))
        painter.drawEllipse(QRectF(track.left() + (18 if self.isChecked() else 2), track.top() + 2, 14, 14))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor(ACCENT))
            painter.drawRoundedRect(self.rect().adjusted(0, 1, -1, -1), 7, 7)
        painter.end()


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
        self.resize(420, min(490, self.screen().availableGeometry().height() - 60))
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
        root.setContentsMargins(12, 12, 12, 12)
        card = QFrame()
        card.setObjectName("settingsCard")
        card.setStyleSheet(f"""
            QFrame#settingsCard {{ background:transparent;border:none; }}
            QLineEdit, QComboBox {{ background:{BG_CARD};border:1px solid {BORDER};border-radius:8px;
                padding:6px 10px;min-height:20px;font-size:12px; }}
            QLineEdit:focus, QComboBox:focus {{ border-color:{ACCENT}; }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        header = QFrame()
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 14, 18, 10)
        title = QLabel("设置")
        title.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:17px;font-weight:600;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        close = QPushButton("×")
        close.setFixedSize(28, 28)
        close.setAccessibleName("关闭设置")
        close.setStyleSheet(f"QPushButton {{ background:transparent;border:none;padding:0;color:{TEXT_MUTED};font-size:20px; }}"
                            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}")
        close.clicked.connect(self.reject)
        header_layout.addWidget(close)
        card_layout.addWidget(header)
        self._settings_scroll = QScrollArea()
        self._settings_scroll.setWidgetResizable(True)
        self._settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._settings_scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        body = QWidget()
        body.setObjectName("settingsBody")
        body.setStyleSheet("QWidget#settingsBody {background:transparent;}")
        form = QVBoxLayout(body)
        form.setContentsMargins(24, 4, 24, 16)
        form.setSpacing(10)
        self._settings_tabs = []
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        for index, label in enumerate(("连接", "偏好", "语音", "宠物")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setFixedHeight(32)
            button.setStyleSheet(f"QPushButton {{background:transparent;border:none;padding:0 16px;border-radius:7px;color:{TEXT_MUTED};font-size:12px;}}"
                                f"QPushButton:checked {{background:{BG_CARD};color:{TEXT_PRIMARY};}}")
            button.clicked.connect(lambda _=False, page=index: self._select_settings_page(page))
            self._settings_tabs.append(button)
            tabs.addWidget(button)
        tabs.addStretch()
        form.addLayout(tabs)
        form.addSpacing(12)
        sections = form
        self._connection_page = QFrame()
        form = QVBoxLayout(self._connection_page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)
        sections.addWidget(self._connection_page)
        self._backend_combo = SettingsCombo()
        for label, value in BACKEND_OPTIONS:
            self._backend_combo.addItem(label, value)
        self._backend_combo.setAccessibleName("AI 后端")
        self._backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        form.addWidget(_make_field_row("AI 后端", self._backend_combo))
        self._preset_combo = SettingsCombo()
        for name in API_PRESETS:
            self._preset_combo.addItem(name)
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        self._preset_frame = _make_field_row("平台", self._preset_combo)
        form.addWidget(self._preset_frame)
        self._apikey_input = QLineEdit()
        self._apikey_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._apikey_input.setPlaceholderText("输入 API Key")
        self._apikey_frame = _make_field_row("API Key", self._apikey_input)
        form.addWidget(self._apikey_frame)
        self._baseurl_input = QLineEdit()
        self._baseurl_input.setPlaceholderText("https://api.openai.com/v1")
        self._baseurl_frame = _make_field_row("地址", self._baseurl_input)
        form.addWidget(self._baseurl_frame)
        self._model_input = QLineEdit()
        self._model_input.setPlaceholderText("模型名称")
        self._model_frame = _make_field_row("模型", self._model_input)
        form.addWidget(self._model_frame)
        hint = QLabel("密钥只保存在本机。切换连接后，保存即可生效。")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;padding-top:8px;")
        form.addWidget(hint)
        self._preferences_page = QFrame()
        form = QVBoxLayout(self._preferences_page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        sections.addWidget(self._preferences_page)
        self._access_mode = SettingsCombo()
        self._access_mode.addItem("逐次确认", "confirm")
        self._access_mode.addItem("完全访问本机", "full")
        self._access_mode.setCurrentIndex(1 if self._config.get("agent_access_mode") == "full" else 0)
        form.addWidget(_make_field_row("访问权限", self._access_mode))
        access_hint = QLabel("逐次确认：执行本机操作前先询问。\n完全访问：允许助手直接打开程序、操作本地文件和执行命令，权限受当前 Windows 账户限制。\n涉及附件内容的操作仍会核对，任务清单继续保留确认步骤。")
        access_hint.setWordWrap(True)
        access_hint.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        form.addWidget(access_hint)
        self._sound_cb = SettingSwitch("声音提示")
        self._sound_cb.toggled.connect(self._on_sound_master_toggled)
        self._clipboard_cb = SettingSwitch("剪贴板监听")
        self._autostart_cb = SettingSwitch("开机启动")
        for switch in (self._sound_cb, self._clipboard_cb, self._autostart_cb):
            form.addWidget(switch)
        self._advanced_button = QPushButton("高级设置  +")
        self._advanced_button.setCheckable(True)
        self._advanced_button.setFixedHeight(32)
        self._advanced_button.setStyleSheet(f"QPushButton {{ text-align:left;padding:0;background:transparent;"
                                            f"border:none;color:{TEXT_MUTED};font-size:12px; }}"
                                            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}")
        form.addWidget(self._advanced_button)
        self._advanced_frame = QFrame()
        advanced_layout = QVBoxLayout(self._advanced_frame)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(14)
        self._sound_section_frame = self._build_sound_section()
        self._about_frame = self._build_about_section()
        advanced_layout.addWidget(self._sound_section_frame)
        advanced_layout.addWidget(self._about_frame)
        self._advanced_frame.hide()
        self._advanced_button.toggled.connect(self._advanced_frame.setVisible)
        self._advanced_button.toggled.connect(lambda checked:
            self._advanced_button.setText("高级设置  −" if checked else "高级设置  +"))
        form.addWidget(self._advanced_frame)
        from ui.voice_settings import VoiceSettings
        self._voice_page = VoiceSettings(self._config)
        sections.addWidget(self._voice_page)
        from ui.pet_settings import PetSettings
        self._pet_page = PetSettings(self._config, SettingSwitch, SettingsCombo)
        self._petname_input = self._pet_page.name
        sections.addWidget(self._pet_page)
        sections.addStretch(1)
        self._select_settings_page(0)
        self._settings_scroll.setWidget(body)
        card_layout.addWidget(self._settings_scroll, 1)
        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 14, 24, 20)
        footer_layout.setSpacing(8)
        footer_layout.addStretch()
        cancel = QPushButton("取消")
        cancel.setFixedSize(72, 34)
        cancel.setStyleSheet(f"QPushButton {{ background:transparent;border:1px solid {BORDER};"
                            f"border-radius:8px;padding:0;color:{TEXT_SECONDARY};font-size:12px; }}"
                            f"QPushButton:hover {{ background:{BG_SUBTLE}; }}")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setFixedSize(88, 34)
        save.setDefault(True)
        save.setStyleSheet(f"QPushButton {{ background:{ACCENT};border:none;border-radius:8px;"
                          f"padding:0;color:{TEXT_ON_ACCENT};font-size:12px;font-weight:600; }}"
                          f"QPushButton:hover {{ background:{ACCENT_BRIGHT}; }}")
        save.clicked.connect(self._save)
        self._voice_page.busy_changed.connect(lambda busy: save.setEnabled(not busy))
        footer_layout.addWidget(cancel)
        footer_layout.addWidget(save)
        card_layout.addWidget(footer)
        root.addWidget(card)

    # ── Helpers ─────────────────────────────────────────────────────
    def _select_settings_page(self, index):
        self._connection_page.setVisible(index == 0)
        self._preferences_page.setVisible(index == 1)
        self._voice_page.setVisible(index == 2)
        self._pet_page.setVisible(index == 3)
        for position, button in enumerate(self._settings_tabs):
            button.setChecked(position == index)
        self.resize(440 if index == 3 else 420,
                    min(640 if index == 3 else 490, self.screen().availableGeometry().height() - 60))

    def _section_header(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:11px;font-weight:500;"
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
            f" border:none; }}"
        )
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        # 标题
        title = QLabel("事件音")
        title.setStyleSheet(
            f"color:{TEXT_SECONDARY};font-size:11px;font-weight:600;"
            f"background:transparent;border:none;padding-bottom:2px;"
        )
        v.addWidget(title)

        events = [
            ("voice_start", "开始说话"),
            ("message_received", "收到消息"),
            ("file_dropped", "拖入文件"),
            ("message_sent", "发送消息"),
            ("error", "错误"),
        ]
        for event, label in events:
            row = self._build_sound_event_row(event, label)
            v.addWidget(row)

        return frame

    def _build_sound_event_row(self, event: str, label: str) -> QFrame:
        row_frame = QFrame()
        row_frame.setStyleSheet("background:transparent;border:none;")
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
        test_btn = QPushButton("试听")
        test_btn.setFixedSize(38, 26)
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.setToolTip("试听")
        test_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD};color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER_SUBTLE};border-radius:5px;font-size:11px;padding:0; }}"
            f"QPushButton:hover {{ background:{ACCENT_SOFT};color:{ACCENT}; }}"
        )
        test_btn.clicked.connect(lambda _=False, e=event: self._on_test_sound(e))
        h.addWidget(test_btn)

        # 选择文件
        choose_btn = QPushButton("文件")
        choose_btn.setFixedSize(38, 26)
        choose_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        choose_btn.setToolTip("选择自定义音频文件")
        choose_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD};color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER_SUBTLE};border-radius:5px;font-size:11px;padding:0; }}"
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
            f" border:none;border-radius:5px;font-size:12px;padding:0; }}"
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
            f" border:none; }}"
        )
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        title = QLabel("诊断")
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

        self._crash_scan_btn = QPushButton("重新扫描")
        self._crash_scan_btn.setFixedHeight(28)
        self._crash_scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._crash_scan_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD};color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER_SUBTLE};border-radius:4px;font-size:11px;padding:0 10px; }}"
            f"QPushButton:hover {{ background:{ACCENT_SOFT};color:{ACCENT}; }}"
        )
        self._crash_scan_btn.clicked.connect(self._refresh_crash_status)
        btn_row.addWidget(self._crash_scan_btn)

        self._crash_report_btn = QPushButton("复制报告")
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
                    f"发现 {len(unread)} 个新崩溃（最近: {mtime}）"
                )
                self._crash_status_lbl.setStyleSheet(
                    f"color:{RED};font-size:11px;font-weight:600;"
                    f"background:transparent;border:none;"
                )
                self._crash_report_btn.setEnabled(True)
            else:
                total = len(cr.get_all_crashes())
                if total:
                    self._crash_status_lbl.setText(f"没有新崩溃（{total} 个已读）")
                else:
                    self._crash_status_lbl.setText("没有发现崩溃日志")
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
            custom_path = self._config.get(f"sound_{event}_custom_path", "") or ""
            # Keep the current value in _sound_paths so an unmodified event
            # is preserved when the user saves without touching it.
            self._sound_paths[event] = custom_path
            row["path_label"].setText(
                self._short_path(custom_path)
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
        preferred_height = 490
        self.resize(self.width(), min(preferred_height, self.screen().availableGeometry().height() - 60))

    def _on_preset_changed(self, name: str):
        p = API_PRESETS.get(name, {})
        if p.get("base"):
            self._baseurl_input.setText(p["base"])
        if p.get("model"):
            self._model_input.setText(p["model"])

    def _save(self):
        access_mode = self._access_mode.currentData()
        try:
            voice = self._voice_page.values()
        except ValueError as error:
            QMessageBox.warning(self, "语音设置", str(error))
            self._select_settings_page(2)
            return
        if access_mode == "full" and self._config.get("agent_access_mode", "confirm") != "full":
            if QMessageBox.question(self, "启用完全访问", "开启后，助手可以直接执行本机命令和文件操作。\n请仅对你信任的模型与服务开启；可随时在这里切回逐次确认。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
        self._config.update(voice)
        self._config["agent_access_mode"] = access_mode
        self._config.update(self._pet_page.values())
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

    def done(self, result):
        if not self._voice_page.ready_to_close(lambda: self.done(result)):
            return
        super().done(result)

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
    def paintEvent(self, event):
        from ui.window_surface import paint_window_surface
        paint_window_surface(self)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _e):
        self._drag_pos = None
