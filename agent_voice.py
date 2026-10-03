from __future__ import annotations

import math
import queue
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal


SAMPLE_RATE = 16000
BLOCK_SIZE = 1024
PUMP_INTERVAL_MS = 40
PARTIAL_INTERVAL_SECONDS = 1.5
SILENCE_END_SECONDS = 1.4
NO_SPEECH_TIMEOUT_SECONDS = 10.0
MAX_RECORDING_SECONDS = 60.0
MIN_VOICED_SECONDS = 0.25
MAX_AUDIO_SECONDS = 60.0
NOISE_FLOOR_INITIAL = 0.0025
NOISE_THRESHOLD_FLOOR = 0.0075
NOISE_MULTIPLIER = 3.0
PRE_ROLL_BLOCKS = 16

_ASR_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent-voice-asr")
_LOCAL_ASR_LOCK = threading.Lock()


def _transcribe(audio: np.ndarray, settings: dict) -> str:
    if settings.get("voice_mode", "local") == "cloud":
        from voice_services import transcribe_cloud

        return transcribe_cloud(audio, SAMPLE_RATE, settings)

    from voice_services import find_model_dir

    model_dir = find_model_dir(settings)
    if model_dir is None:
        raise FileNotFoundError

    import sensevoice_asr

    with _LOCAL_ASR_LOCK:
        return sensevoice_asr.transcribe(
            audio,
            SAMPLE_RATE,
            language="zh",
            model_dir=str(Path(model_dir)),
        )


class AgentVoice(QObject):
    state_changed = Signal(str)
    partial = Signal(str)
    final = Signal(str)
    level = Signal(float)
    failed = Signal(str)
    _asr_finished = Signal(int, str, str, str)

    def __init__(self, settings: dict, parent: QObject | None = None):
        super().__init__(parent)
        self._settings = dict(settings or {})
        self._stream = None
        self._recording = False
        self._processing = False
        self._generation = 0
        self._recording_started = 0.0
        self._last_voiced_at = 0.0
        self._last_partial_at = 0.0
        self._noise_floor = NOISE_FLOOR_INITIAL
        self._candidate_voiced_seconds = 0.0
        self._speech_started = False
        self._voiced_seconds = 0.0
        self._pre_roll: deque[np.ndarray] = deque(maxlen=PRE_ROLL_BLOCKS)
        self._utterance: list[np.ndarray] = []
        self._audio_queue: queue.Queue[tuple[np.ndarray, float]] = queue.Queue(maxsize=256)
        self._capture_error = ""
        self._active_task: tuple[int, str] | None = None
        self._active_future: Future[str] | None = None
        self._pending_final: tuple[int, np.ndarray, dict] | None = None

        self._capture_timer = QTimer(self)
        self._capture_timer.setInterval(PUMP_INTERVAL_MS)
        self._capture_timer.timeout.connect(self._drain_audio)
        self._asr_finished.connect(self._on_asr_finished)

    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def processing(self) -> bool:
        return self._processing

    def start(self) -> bool:
        if self._recording or self._processing:
            return False

        settings = dict(self._settings)
        local = settings.get("voice_mode", "local") != "cloud"
        try:
            from voice_services import (
                find_model_dir,
                missing_components,
                validate_cloud_config,
            )

            missing = missing_components(local)
            if missing:
                raise RuntimeError("语音组件缺失：" + ", ".join(missing))
            if local and find_model_dir(settings) is None:
                raise RuntimeError("本地语音模型未就绪，请在语音设置中安装模型")
            if not local:
                validate_cloud_config(settings)

            import sounddevice as sd

            self._reset_capture()
            self._generation += 1
            self._recording_started = time.monotonic()
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception as error:
            self._close_stream()
            self._reset_capture()
            self._emit_failure(self._safe_error(error, settings))
            return False

        self._recording = True
        self._capture_timer.start()
        self.state_changed.emit("recording")
        return True

    def finish(self) -> None:
        if not self._recording:
            return

        self._capture_timer.stop()
        self._recording = False
        close_error = self._close_stream()
        self._drain_queued_audio()
        if close_error:
            self._fail_capture("无法释放麦克风，请检查设备后重试")
            return
        if self._capture_error:
            self._fail_capture(self._capture_error)
            return

        if not self._speech_started or self._voiced_seconds < MIN_VOICED_SECONDS:
            self._reset_capture()
            self._emit_failure("没有检测到足够清晰的语音，请重试")
            return

        audio = self._snapshot_audio()
        if audio.size == 0:
            self._reset_capture()
            self._emit_failure("没有可识别的语音，请重试")
            return

        self._processing = True
        self.state_changed.emit("transcribing")
        self._pending_final = (self._generation, audio, dict(self._settings))
        self._dispatch_pending_final()

    def cancel(self) -> None:
        self._capture_timer.stop()
        self._recording = False
        self._close_stream()
        self._generation += 1
        if self._active_future is not None:
            self._active_future.cancel()
        self._active_future = None
        self._active_task = None
        self._pending_final = None
        self._processing = False
        self._reset_capture()
        self.partial.emit("")
        self.state_changed.emit("idle")

    def update_settings(self, settings: dict) -> None:
        if self._recording or self._processing:
            self.cancel()
        else:
            self._generation += 1
            self._pending_final = None
        self._settings = dict(settings or {})

    def _reset_capture(self) -> None:
        self._recording = False
        self._recording_started = 0.0
        self._last_voiced_at = 0.0
        self._last_partial_at = 0.0
        self._noise_floor = NOISE_FLOOR_INITIAL
        self._candidate_voiced_seconds = 0.0
        self._speech_started = False
        self._voiced_seconds = 0.0
        self._pre_roll.clear()
        self._utterance.clear()
        self._capture_error = ""
        self._clear_audio_queue()

    def _audio_callback(self, indata, _frames, _time_info, status) -> None:
        if status and getattr(status, "input_overflow", False):
            self._capture_error = "麦克风采集不稳定，请重试"
            return
        try:
            mono = np.asarray(indata[:, 0], dtype=np.float32).copy()
            if mono.size:
                self._audio_queue.put_nowait((mono, time.monotonic()))
        except queue.Full:
            self._capture_error = "音频处理跟不上采集速度，请重试"
        except Exception:
            self._capture_error = "麦克风采集失败，请检查设备后重试"

    def _drain_audio(self) -> None:
        if not self._recording:
            return
        self._drain_queued_audio()
        if self._capture_error:
            self._fail_capture(self._capture_error)
            return

        now = time.monotonic()
        elapsed = now - self._recording_started
        if not self._speech_started and elapsed >= NO_SPEECH_TIMEOUT_SECONDS:
            self._fail_capture("10 秒内没有检测到语音，请重试")
            return
        if elapsed >= MAX_RECORDING_SECONDS:
            self.finish()
            return
        if (
            self._speech_started
            and self._last_voiced_at
            and now - self._last_voiced_at >= SILENCE_END_SECONDS
        ):
            self.finish()
            return

        if (
            self._speech_started
            and self._settings.get("voice_mode", "local") != "cloud"
            and self._active_task is None
            and now - self._last_partial_at >= PARTIAL_INTERVAL_SECONDS
        ):
            self._queue_partial()

    def _drain_queued_audio(self) -> None:
        while True:
            try:
                block, captured_at = self._audio_queue.get_nowait()
            except queue.Empty:
                break
            self._process_audio_block(block, captured_at)

    def _process_audio_block(self, block: np.ndarray, now: float) -> None:
        if block.size == 0:
            return
        duration = block.size / SAMPLE_RATE
        rms = float(np.sqrt(np.mean(np.square(block, dtype=np.float32))))
        threshold = max(NOISE_THRESHOLD_FLOOR, self._noise_floor * NOISE_MULTIPLIER + 0.0015)
        voiced = rms >= threshold

        if not self._speech_started:
            self._pre_roll.append(block)
            if voiced:
                self._candidate_voiced_seconds += duration
            else:
                self._candidate_voiced_seconds = max(
                    0.0,
                    self._candidate_voiced_seconds - duration * 0.35,
                )
                self._noise_floor = (
                    self._noise_floor * 0.96 + min(rms, 0.03) * 0.04
                )
            if self._candidate_voiced_seconds >= MIN_VOICED_SECONDS:
                self._speech_started = True
                self._voiced_seconds = self._candidate_voiced_seconds
                self._last_voiced_at = now
                self._last_partial_at = now
                self._utterance.extend(self._pre_roll)
                self._pre_roll.clear()
        else:
            self._utterance.append(block)
            if voiced:
                self._voiced_seconds += duration
                self._last_voiced_at = now

        compressed = math.log1p(rms * 40.0) / math.log1p(40.0)
        self.level.emit(max(0.0, min(1.0, compressed)))

    def _queue_partial(self) -> None:
        audio = self._snapshot_audio()
        if audio.size == 0:
            return
        self._last_partial_at = time.monotonic()
        self._submit_asr(self._generation, "partial", audio, dict(self._settings))

    def _snapshot_audio(self) -> np.ndarray:
        if not self._utterance:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(self._utterance).astype(np.float32, copy=False)
        max_samples = int(MAX_AUDIO_SECONDS * SAMPLE_RATE)
        if audio.size > max_samples:
            audio = audio[-max_samples:]
        return audio.copy()

    def _submit_asr(self, generation: int, kind: str, audio: np.ndarray, settings: dict) -> None:
        self._active_task = (generation, kind)
        future = _ASR_EXECUTOR.submit(_transcribe, audio, settings)
        self._active_future = future
        future.add_done_callback(
            lambda completed: self._publish_asr_result(
                completed, generation, kind, settings
            )
        )

    def _publish_asr_result(
        self,
        future: Future[str],
        generation: int,
        kind: str,
        settings: dict,
    ) -> None:
        if future.cancelled():
            return
        try:
            text = future.result().strip()
            error = ""
        except Exception as exception:
            text = ""
            error = self._safe_error(exception, settings)
        try:
            self._asr_finished.emit(generation, kind, text, error)
        except RuntimeError:
            pass

    def _on_asr_finished(self, generation: int, kind: str, text: str, error: str) -> None:
        if self._active_task == (generation, kind):
            self._active_task = None
            self._active_future = None

        pending_final = self._pending_final
        if pending_final is not None:
            if pending_final[0] == self._generation:
                self._dispatch_pending_final()
            else:
                self._pending_final = None

        if generation != self._generation:
            return
        if kind == "partial":
            if not self._processing and self._recording and not error:
                self.partial.emit(text)
            return

        self._processing = False
        self._utterance.clear()
        self.partial.emit("")
        if error:
            self._emit_failure(error)
        elif text:
            self.final.emit(text)
            self.state_changed.emit("idle")
        else:
            self._emit_failure("没有识别到文字，请重试")

    def _dispatch_pending_final(self) -> None:
        if self._active_task is not None or self._pending_final is None:
            return
        generation, audio, settings = self._pending_final
        self._pending_final = None
        self._submit_asr(generation, "final", audio, settings)

    def _fail_capture(self, message: str) -> None:
        self._capture_timer.stop()
        self._recording = False
        self._close_stream()
        self._generation += 1
        self._pending_final = None
        self._processing = False
        self._reset_capture()
        self._emit_failure(message)

    def _close_stream(self) -> str:
        stream = self._stream
        self._stream = None
        if stream is None:
            return ""
        error = ""
        try:
            stream.stop()
        except Exception:
            error = "无法释放麦克风，请检查设备后重试"
        try:
            stream.close()
        except Exception:
            error = "无法释放麦克风，请检查设备后重试"
        return error

    def _clear_audio_queue(self) -> None:
        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                return

    def _safe_error(self, error: Exception, settings: dict) -> str:
        if isinstance(error, RuntimeError):
            message = str(error)
        elif isinstance(error, ValueError) and settings.get("voice_mode") == "cloud":
            message = str(error)
        elif isinstance(error, FileNotFoundError):
            message = "本地语音模型未就绪，请在语音设置中安装模型"
        else:
            message = "语音识别失败，请检查语音设置后重试"
        for secret_key in ("voice_api_key", "voice_api_base"):
            secret = str(settings.get(secret_key, "")).strip()
            if secret:
                message = message.replace(secret, "（已隐藏）")
        return message

    def _emit_failure(self, message: str) -> None:
        self.failed.emit(message)
        self.state_changed.emit("error")
