from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout,
)

from theme import ACCENT, BG_CARD, BORDER, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY
from agent_voice import AgentVoice
from voice_services import (
    MODEL_PAGE, InstallCancelled, configured_model_dir, default_model_dir,
    find_model_dir, has_model, install_model, missing_components,
    model_directory_problem, validate_cloud_config,
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
        self._saved_voice_mode = settings.get("voice_mode") if settings.get("voice_mode") in ("local", "cloud") else "local"
        self._direct_mode = self._saved_voice_mode
        self._trial = AgentVoice({}, self)
        self._trial_running = False
        self._doubao_trial = None
        self._local_ready = False
        self._cloud_ready = False
        self._doubao_ready = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        from ui.settings_panel import SettingsCombo
        self.mode = SettingsCombo()
        self.mode.setStyleSheet("QComboBox::drop-down {border:none;background:transparent;width:24px;}"
                               "QComboBox::down-arrow {image:none;}")
        self.mode.addItem("本地模型（直接录音）", "local")
        self.mode.addItem("云端 API（直接录音）", "cloud")
        self.mode.addItem("豆包兼容（两步）", "doubao")
        initial = "doubao" if settings.get("agent_voice_provider") == "doubao" else self._direct_mode
        self.mode.setCurrentIndex(self.mode.findData(initial))
        layout.addWidget(field("识别方式", self.mode))
        self.local = QFrame()
        local = QVBoxLayout(self.local)
        local.setContentsMargins(0, 0, 0, 0)
        local.setSpacing(10)
        name = QLabel("SenseVoice-Small ONNX")
        name.setStyleSheet(f"font-size:14px;font-weight:600;color:{TEXT_PRIMARY};")
        local.addWidget(name)
        note = QLabel("录音留在本机。模型目录须含 model.onnx 与 tokens.json。")
        note.setToolTip("支持 SenseVoice-Small ONNX 格式；普通 Whisper 模型请通过兼容的本机 API 接入。")
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
        privacy = QLabel("录音发送至该服务，远程服务可能收费。\n使用兼容 /audio/transcriptions 的 API；本机服务可不填 Key。")
        privacy.setToolTip("填写 API 基础地址，例如 https://api.openai.com/v1。语音 Key 与聊天 Key 分开。\nWhisper、Qwen 等本地服务也可填兼容 API 地址；网页界面地址本身不等于 API。")
        privacy.setWordWrap(True)
        privacy.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        cloud.addWidget(privacy)
        self.cloud_status = QLabel()
        self.cloud_status.setWordWrap(True)
        self.cloud_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        cloud.addWidget(self.cloud_status)
        layout.addWidget(self.cloud)
        self.doubao = QFrame()
        doubao_layout = QVBoxLayout(self.doubao)
        doubao_layout.setContentsMargins(0, 0, 0, 0)
        doubao_layout.setSpacing(10)
        guidance = QLabel("第 1 步：在电脑上安装并启用豆包输入法，按右 Alt 说话。\n第 2 步：在弹出的输入区核对文字，再点发送。此模式由输入法接收语音，不能直接录音。")
        guidance.setWordWrap(True)
        guidance.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        doubao_layout.addWidget(guidance)
        self.doubao_status = QLabel()
        self.doubao_status.setWordWrap(True)
        self.doubao_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        doubao_layout.addWidget(self.doubao_status)
        layout.addWidget(self.doubao)
        trial_actions = QHBoxLayout()
        self.try_button = QPushButton("试说一句")
        self.stop_button = QPushButton("停止")
        self.cancel_trial_button = QPushButton("取消")
        for button in (self.try_button, self.stop_button, self.cancel_trial_button):
            button.setFixedHeight(32)
            button.setStyleSheet(f"QPushButton {{padding:0 10px;border:1px solid {BORDER};border-radius:8px;"
                                 f"background:{BG_CARD};color:{TEXT_SECONDARY};font-size:12px;}}"
                                 f"QPushButton:hover {{border-color:{ACCENT};}}")
            trial_actions.addWidget(button)
        self.stop_button.hide()
        self.cancel_trial_button.hide()
        layout.addLayout(trial_actions)
        self.trial_result = QLabel("试说只显示识别结果，不会发送给小橘，也不会保存设置。")
        self.trial_result.setTextFormat(Qt.TextFormat.PlainText)
        self.trial_result.setWordWrap(True)
        self.trial_result.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        layout.addWidget(self.trial_result)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.directory.textChanged.connect(self.refresh_status)
        for widget in (self.base, self.key, self.model):
            widget.textChanged.connect(self.refresh_cloud_status)
        self.choose_button.clicked.connect(self._choose_directory)
        self.install_button.clicked.connect(self._install)
        self.cancel_button.clicked.connect(self.cancel_install)
        self.try_button.clicked.connect(self._start_trial)
        self.stop_button.clicked.connect(self._stop_trial)
        self.cancel_trial_button.clicked.connect(self.cancel_trial)
        self._trial.state_changed.connect(self._trial_state)
        self._trial.partial.connect(self._trial_partial)
        self._trial.final.connect(self._trial_final)
        self._trial.failed.connect(self._trial_failed)
        self._mode_changed()
        self.refresh_status()
        self.refresh_cloud_status()

    def _mode_changed(self):
        choice = self.mode.currentData()
        if choice in ("local", "cloud"):
            self._direct_mode = choice
        self.local.setVisible(choice == "local")
        self.cloud.setVisible(choice == "cloud")
        self.doubao.setVisible(choice == "doubao")
        self.refresh_doubao_status()
        self._update_trial_available()

    def values(self, validate=True):
        directory = self.directory.text().strip()
        choice = self.mode.currentData()
        if validate and choice == "local" and directory and not Path(directory).expanduser().is_absolute():
            raise ValueError("模型目录请使用绝对路径，或点击选择目录")
        values = {
            "voice_mode": self._direct_mode, "agent_voice_provider": "doubao" if choice == "doubao" else "local",
            "voice_model_dir": directory,
            "voice_api_base": self.base.text().strip().rstrip("/"),
            "voice_api_key": self.key.text().strip(), "voice_api_model": self.model.text().strip(),
        }
        if validate and choice == "cloud":
            validate_cloud_config(values)
        return values

    def refresh_status(self):
        if self._installer and self._installer.running:
            return
        self._local_ready = False
        try:
            directory = self.directory.text().strip()
            if directory and not Path(directory).expanduser().is_absolute():
                raise ValueError("模型目录请使用绝对路径，或点击选择目录")
            settings = self.values(validate=False)
            available = find_model_dir(settings)
            missing = missing_components()
            if missing:
                self.status.setText("缺少语音运行组件，请使用完整版本：" + ", ".join(missing))
                self.install_button.setEnabled(False)
            else:
                self.install_button.setEnabled(True)
                if available:
                    self._local_ready = True
                    installed = has_model(configured_model_dir(settings))
                    self.status.setText("SenseVoice 文件齐全 · 请试说验证转写" if installed else "找到本机已有 SenseVoice 文件 · 请试说验证转写")
                    self.status.setToolTip(str(available))
                    self.install_button.setText("校验并修复" if installed else "安装到本应用")
                else:
                    target = configured_model_dir(settings)
                    problem = model_directory_problem(target) if target.exists() else None
                    self.status.setText((problem + "\n" if problem else "尚未安装。\n") + "安装位置：" + str(target))
                    self.install_button.setText("一键安装")
        except ValueError as error:
            self.status.setText(str(error))
            self.install_button.setEnabled(False)
        self._update_trial_available()

    def refresh_cloud_status(self):
        self._cloud_ready = False
        missing = missing_components(local=False)
        if missing:
            self.cloud_status.setText("缺少录音组件：" + ", ".join(missing))
        else:
            try:
                validate_cloud_config(self.values(validate=False))
            except ValueError as error:
                self.cloud_status.setText("配置待补齐 · " + str(error))
            else:
                self._cloud_ready = True
                self.cloud_status.setText("配置已填写 · 试说成功后再保存")
        self._update_trial_available()

    def refresh_doubao_status(self):
        from doubao_input import installed_profile

        self._doubao_ready = installed_profile() is not None
        self.doubao_status.setText(
            "已检测到豆包输入法 · 可先体验两步输入" if self._doubao_ready
            else "未检测到豆包输入法 · 请先在系统中安装并启用，再返回体验"
        )
        self._update_trial_available()

    def _update_trial_available(self):
        ready = {
            "local": self._local_ready,
            "cloud": self._cloud_ready,
            "doubao": self._doubao_ready,
        }.get(self.mode.currentData(), False)
        self.try_button.setEnabled(bool(ready) and not self._trial_running and not (self._installer and self._installer.running))

    def _choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择模型目录", self.directory.text() or str(default_model_dir().parent))
        if directory:
            self.directory.setText(directory)

    def _install(self):
        if self._trial_running or (self._installer and self._installer.running):
            return
        try:
            destination = configured_model_dir(self.values())
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
        self._update_trial_available()
        if self._close_callback:
            callback, self._close_callback = self._close_callback, None
            callback()

    def cancel_install(self):
        if self._installer and self._installer.running:
            self._installer.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("正在取消…")

    def _set_trial_busy(self, busy):
        self._trial_running = busy
        for widget in (self.mode, self.directory, self.choose_button, self.install_button,
                       self.base, self.key, self.model):
            widget.setEnabled(not busy)
        self.stop_button.setVisible(busy)
        self.cancel_trial_button.setVisible(busy)
        self.stop_button.setEnabled(busy)
        self.busy_changed.emit(busy)
        if not busy:
            self.refresh_status()
            self.refresh_cloud_status()
        else:
            self._update_trial_available()

    def _start_trial(self):
        if self._trial_running or (self._installer and self._installer.running):
            return
        choice = self.mode.currentData()
        if choice == "doubao":
            if not self._doubao_ready:
                self.trial_result.setText("未检测到豆包输入法，请先安装并启用。")
                return
            if self._doubao_trial is None:
                from doubao_input import DoubaoInput

                self._doubao_trial = DoubaoInput(self)
                self._doubao_trial.partial.connect(self._trial_partial)
                self._doubao_trial.final.connect(self._trial_final)
                self._doubao_trial.failed.connect(self._trial_failed)
                self._doubao_trial.cancelled.connect(self.cancel_trial)
                self._doubao_trial.state_changed.connect(self._trial_state)
            self._set_trial_busy(True)
            self.trial_result.setText("豆包体验：按右 Alt 说话，在弹出的输入区核对文字，再点发送。")
            if not self._doubao_trial.start() and self._trial_running:
                self._set_trial_busy(False)
            elif self._trial_running:
                self._doubao_trial.card.editor.setAccessibleName("豆包语音试说接收区")
                self._doubao_trial.card.finish_button.setAccessibleName("显示试说结果")
                self._doubao_trial.card.finish_button.setToolTip("显示试说结果 · Ctrl+Enter")
                self._doubao_trial.card.hint.setText("右 Alt 说话 · Ctrl+Enter 显示试说结果")
            return
        try:
            settings = self.values()
        except ValueError as error:
            self.trial_result.setText(str(error))
            return
        self._trial.update_settings(settings)
        self._set_trial_busy(True)
        self.trial_result.setText("正在打开麦克风…")
        if not self._trial.start() and self._trial_running:
            self._set_trial_busy(False)

    def _stop_trial(self):
        if not self._trial_running:
            return
        self.stop_button.setEnabled(False)
        if self.mode.currentData() == "doubao":
            if self._doubao_trial is not None:
                self._doubao_trial.finish()
        else:
            self._trial.finish()

    def cancel_trial(self):
        if not self._trial_running:
            return
        self._trial.cancel()
        if self._doubao_trial is not None and self._doubao_trial.active:
            self._doubao_trial.cancel()
        self._set_trial_busy(False)
        message = "已取消试说，麦克风已关闭。"
        if self.mode.currentData() == "cloud":
            message += "已经发出的语音请求可能已到达服务，返回结果会被忽略。"
        self.trial_result.setText(message)

    def _trial_state(self, state):
        if not self._trial_running:
            return
        if state in ("recording", "listening"):
            if self.mode.currentData() == "doubao":
                self.trial_result.setText("豆包输入区已打开：右 Alt 说话，核对文字后点发送以显示试说结果。")
            else:
                self.trial_result.setText("正在听，请说一句话；可以点停止，或等静音自动结束。")
            self.stop_button.setEnabled(True)
        elif state == "transcribing":
            self.trial_result.setText("录音已停止，正在转写…")
            self.stop_button.setEnabled(False)

    def _trial_partial(self, text):
        if self._trial_running and text:
            self.trial_result.setText("识别预览：" + text[:300])

    def _trial_final(self, text):
        if not self._trial_running:
            return
        self._set_trial_busy(False)
        self.trial_result.setText("试说结果：" + text[:500])

    def _trial_failed(self, message):
        if not self._trial_running:
            return
        self._set_trial_busy(False)
        self.trial_result.setText("试说失败：" + message[:300])

    def hideEvent(self, event):
        self.cancel_trial()
        super().hideEvent(event)

    def ready_to_close(self, callback):
        self.cancel_trial()
        if self._doubao_trial is not None:
            self._doubao_trial.card.deleteLater()
            self._doubao_trial = None
        if self._installer and self._installer.running:
            self._close_callback = callback
            self.cancel_install()
            return False
        return True
