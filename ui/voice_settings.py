from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout,
)

from theme import ACCENT, BG_CARD, BORDER, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY
from voice_services import (
    MODEL_PAGE, InstallCancelled, configured_model_dir, default_model_dir,
    find_model_dir, has_model, install_model, missing_components, validate_cloud_config,
)


class ModelInstaller(QObject):
    progress = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(self, directory):
        super().__init__(QApplication.instance())
        self.directory = directory
        self.cancel = threading.Event()
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            install_model(self.directory, self.progress.emit, self.cancel)
            result = (True, "安装完成，保存后即可使用")
        except InstallCancelled:
            result = (False, "已取消安装，原有模型未改动")
        except Exception as error:
            result = (False, str(error)[:240])
        self.running = False
        self.finished.emit(*result)


def field(label, widget):
    row = QFrame()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    caption = QLabel(label)
    caption.setFixedWidth(80)
    caption.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:12px;background:transparent;")
    layout.addWidget(caption)
    layout.addWidget(widget, 1)
    return row


class VoiceSettings(QFrame):
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._installer = None
        self._close_callback = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.mode = QComboBox()
        self.mode.addItem("本地模型 · 离线识别", "local")
        self.mode.addItem("云端 API", "cloud")
        self.mode.setCurrentIndex(1 if settings.get("voice_mode") == "cloud" else 0)
        layout.addWidget(field("识别方式", self.mode))
        self.local = QFrame()
        local = QVBoxLayout(self.local)
        local.setContentsMargins(0, 0, 0, 0)
        local.setSpacing(10)
        name = QLabel("SenseVoice-Small")
        name.setStyleSheet(f"font-size:14px;font-weight:600;color:{TEXT_PRIMARY};")
        local.addWidget(name)
        note = QLabel("约 230 MB · 使用 CPU · 安装后可离线识别\n录音保留在本机，无需语音 API Key。")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        local.addWidget(note)
        self.directory = QLineEdit(str(settings.get("voice_model_dir", "")))
        self.directory.setPlaceholderText(str(default_model_dir()))
        self.directory.setToolTip(str(default_model_dir()))
        local.addWidget(field("模型目录", self.directory))
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        local.addWidget(self.status)
        actions = QHBoxLayout()
        self.install_button = QPushButton("一键安装")
        self.choose_button = QPushButton("选择目录")
        self.cancel_button = QPushButton("取消下载")
        for button in (self.install_button, self.choose_button, self.cancel_button):
            button.setFixedHeight(32)
            button.setStyleSheet(f"QPushButton {{padding:0 10px;border:1px solid {BORDER};border-radius:8px;"
                                f"background:{BG_CARD};color:{TEXT_SECONDARY};font-size:12px;}}"
                                f"QPushButton:hover {{border-color:{ACCENT};}}")
            actions.addWidget(button)
        self.cancel_button.hide()
        local.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(18)
        self.progress.hide()
        local.addWidget(self.progress)
        source = QLabel(f'<a href="{MODEL_PAGE}">模型来源与许可</a>')
        source.setOpenExternalLinks(True)
        source.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        local.addWidget(source)
        layout.addWidget(self.local)
        self.cloud = QFrame()
        cloud = QVBoxLayout(self.cloud)
        cloud.setContentsMargins(0, 0, 0, 0)
        cloud.setSpacing(12)
        self.base = QLineEdit(str(settings.get("voice_api_base", "https://api.openai.com/v1")))
        self.base.setPlaceholderText("https://api.openai.com/v1")
        self.key = QLineEdit(str(settings.get("voice_api_key", "")))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("填写语音服务的 API Key")
        self.model = QLineEdit(str(settings.get("voice_api_model", "whisper-1")))
        self.model.setPlaceholderText("例如 whisper-1")
        for caption, widget in (("服务地址", self.base), ("API Key", self.key), ("识别模型", self.model)):
            cloud.addWidget(field(caption, widget))
        privacy = QLabel("需支持 OpenAI 兼容的语音转文字接口。\n录音会发送到填写的服务地址，可能产生服务费用。\n这里的密钥与聊天 API Key 分开保存。")
        privacy.setWordWrap(True)
        privacy.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        cloud.addWidget(privacy)
        layout.addWidget(self.cloud)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.directory.textChanged.connect(self.refresh_status)
        self.choose_button.clicked.connect(self._choose_directory)
        self.install_button.clicked.connect(self._install)
        self.cancel_button.clicked.connect(self.cancel_install)
        self._mode_changed()
        self.refresh_status()

    def _mode_changed(self):
        local = self.mode.currentData() == "local"
        self.local.setVisible(local)
        self.cloud.setVisible(not local)

    def values(self, validate=True):
        directory = self.directory.text().strip()
        if directory and not Path(directory).expanduser().is_absolute():
            raise ValueError("模型目录请使用绝对路径，或点击选择目录")
        values = {
            "voice_mode": self.mode.currentData(), "voice_model_dir": directory,
            "voice_api_base": self.base.text().strip().rstrip("/"),
            "voice_api_key": self.key.text().strip(), "voice_api_model": self.model.text().strip(),
        }
        if validate and values["voice_mode"] == "cloud":
            validate_cloud_config(values)
        return values

    def refresh_status(self):
        if self._installer and self._installer.running:
            return
        try:
            settings = self.values(validate=False)
            available = find_model_dir(settings)
            missing = missing_components()
            if missing:
                self.status.setText("缺少语音运行组件，请使用完整版本：" + ", ".join(missing))
                self.install_button.setEnabled(False)
            else:
                self.install_button.setEnabled(True)
                if available:
                    installed = has_model(configured_model_dir(settings))
                    self.status.setText("已就绪 · 本地识别可用" if installed else "已就绪 · 复用本机已有模型")
                    self.status.setToolTip(str(available))
                    self.install_button.setText("校验并修复" if installed else "安装到本应用")
                else:
                    self.status.setText("尚未安装。将安装到：\n" + str(configured_model_dir(settings)))
                    self.install_button.setText("一键安装")
        except ValueError as error:
            self.status.setText(str(error))
            self.install_button.setEnabled(False)

    def _choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择模型目录", self.directory.text() or str(default_model_dir().parent))
        if directory:
            self.directory.setText(directory)

    def _install(self):
        if self._installer and self._installer.running:
            return
        try:
            destination = configured_model_dir(self.values(validate=False))
        except ValueError as error:
            self.status.setText(str(error))
            return
        self._installer = ModelInstaller(destination)
        self._installer.progress.connect(self._progress)
        self._installer.finished.connect(self._finished)
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText("正在准备安装…")
        self.cancel_button.show()
        self.cancel_button.setEnabled(True)
        for widget in (self.directory, self.choose_button, self.install_button, self.mode):
            widget.setEnabled(False)
        self.busy_changed.emit(True)
        self._installer.start()

    def _progress(self, value, message):
        self.progress.setValue(value)
        self.status.setText(message)

    def _finished(self, success, message):
        for widget in (self.directory, self.choose_button, self.install_button, self.mode):
            widget.setEnabled(True)
        self.cancel_button.hide()
        self.busy_changed.emit(False)
        if success:
            self.refresh_status()
        else:
            self.status.setText(message)
        self._installer.deleteLater()
        self._installer = None
        if self._close_callback:
            callback, self._close_callback = self._close_callback, None
            callback()

    def cancel_install(self):
        if self._installer and self._installer.running:
            self._installer.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("正在取消…")

    def ready_to_close(self, callback):
        if self._installer and self._installer.running:
            self._close_callback = callback
            self.cancel_install()
            return False
        return True
