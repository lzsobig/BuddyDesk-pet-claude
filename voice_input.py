"""
Voice Input Controller (P3-6) —— Push-to-talk 语音输入。

按住 Ctrl+Shift+V → 录音 + 实时识别 + 填入 chat input。
松开自动结束录音 + 识别 + 触发发送（或仅填入文本，由用户决定发送）。

依赖：
- sensevoice_asr.py：SenseVoice-Small 本地推理
- sounddevice：录音
- 跨平台，但 Windows 上 pynput 已注册 Ctrl+Shift+H 用了类似机制，复用同一钩子

工作流：
1. 按下 Ctrl+Shift+V → 开始录音
2. 松开 → 停止录音 + 推理 + 填入 chat input + 可选自动发送

P3-6.1（闪电说迁移）：新增 level_emitted 信号，把 RMS 喂给悬浮胶囊画波形。
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)
from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import QObject, Signal


class VoiceInputController(QObject):
    """语音输入控制器。"""

    # 录音采集线程发出，主线程槽（VoiceCapsule.push_level）消费。
    level_emitted = Signal(float)

    def __init__(self, sample_rate: int = 16000):
        super().__init__()
        self.sample_rate = sample_rate
        self._recording = False
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._on_recognized: Optional[Callable[[str], None]] = None
        self._on_state: Optional[Callable[[str], None]] = None
        self._available = self._check_dependencies()

    def _check_dependencies(self) -> bool:
        try:
            import sounddevice  # noqa: F401
            import sensevoice_asr  # noqa: F401
            return True
        except ImportError:
            return False

    def is_available(self) -> bool:
        return self._available

    def set_callbacks(self, on_recognized: Callable[[str], None],
                      on_state: Callable[[str], None]):
        """on_recognized(text)：识别完成时调用
        on_state(state)：'recording' / 'processing' / 'ready' / 'error'"""
        self._on_recognized = on_recognized
        self._on_state = on_state

    def begin_recording(self) -> bool:
        """开始录音。返回是否成功。"""
        if not self._available:
            self._emit_state('error')
            return False
        if self._recording:
            return False
        try:
            import sounddevice as sd
            self._chunks = []
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32',
                callback=self._on_audio_chunk,
            )
            self._stream.start()
            self._recording = True
            self._emit_state('recording')
            return True
        except Exception as e:
            print(f"voice_input begin error: {e}")
            self._emit_state('error')
            return False

    def end_recording(self) -> None:
        """停止录音 + 异步识别 + 回调。"""
        if not self._recording:
            return
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
        except (OSError, AttributeError) as exc:
            logger.debug("Failed to stop/close audio stream: %s", exc)
        self._recording = False
        self._emit_state('processing')

        # 异步识别（CPU 推理不阻塞主线程）
        audio = (
            np.concatenate(self._chunks, axis=0).flatten()
            if self._chunks else np.zeros(0)
        )
        threading.Thread(
            target=self._recognize_async, args=(audio,), daemon=True
        ).start()

    def _on_audio_chunk(self, indata, frames, time, status):
        """sounddevice 回调（在 PortAudio 线程跑）。"""
        with self._lock:
            self._chunks.append(indata.copy())
        # 算 RMS → 0~1 电平。emit 是线程安全的（队列连接走主线程槽）。
        try:
            block = indata.reshape(-1).astype(np.float32, copy=False)
            if block.size == 0:
                return
            rms = float(np.sqrt(np.mean(block * block)))
            # 经验：人声 RMS ~0.02-0.2；做一个温和的对数压缩 + clamp
            # level = log1p(rms*40) / log1p(40)，把 0~0.25 大致映射到 0~1
            import math
            level = math.log1p(rms * 40.0) / math.log1p(40.0)
            level = max(0.0, min(1.0, level))
            self.level_emitted.emit(level)
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("audio RMS calc error: %s", e)

    def _recognize_async(self, audio: np.ndarray):
        """后台线程调用 ASR。"""
        try:
            import sensevoice_asr
            dur = audio.size / self.sample_rate if self.sample_rate else 0
            logger.debug("ASR: audio size=%d, duration=%.2fs", audio.size, dur)
            if audio.size < self.sample_rate // 4:  # < 0.25s 视为无效
                logger.debug("ASR: audio too short, skipping")
                self._emit_state('ready')
                return
            logger.debug("ASR: calling transcribe...")
            text = sensevoice_asr.transcribe(audio, self.sample_rate, language='zh')
            logger.debug("ASR result: '%s'", text)
            if text and self._on_recognized:
                logger.debug("calling _on_recognized with text...")
                self._on_recognized(text)
                logger.debug("_on_recognized returned")
        except Exception as e:
            logger.error("ASR error: %s", e, exc_info=True)
            self._emit_state('error')
            return
        self._emit_state('ready')

    def cancel(self) -> None:
        """取消当前录音。"""
        if not self._recording:
            return
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
        except (OSError, AttributeError) as exc:
            logger.debug("Failed to stop/close audio stream during cancel: %s", exc)
        self._recording = False
        self._chunks = []
        self._emit_state('ready')

    def _emit_state(self, state: str):
        if self._on_state:
            try:
                self._on_state(state)
            except Exception as exc:
                logger.debug("State callback error for %s: %s", state, exc)
