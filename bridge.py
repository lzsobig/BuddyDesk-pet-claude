"""
Qt Signal Bridge — connects AIClient/EventEngine callbacks to Qt signals.

All AI operations run in background threads. This bridge safely marshals
results back to the Qt main thread via signals.
"""
import threading

from PySide6.QtCore import QObject, Signal, QTimer

from ai.backend import AIBackend, create_backend
from engine.event_engine import EventEngine


class AIBridge(QObject):
    """Bridges AI backend callbacks to Qt signals for thread-safe UI updates."""

    chunk_received = Signal(str, str)   # (chunk_text, full_text)
    stream_done = Signal(str)           # full_text
    stream_error = Signal(str)          # error message
    state_changed = Signal(str, str)    # (state, preview)
    command_result = Signal(str, bool, str)  # (command, success, output)
    command_needs_confirm = Signal(str) # dangerous command awaiting confirmation
    # P3-3: 上下文用量更新 (used_tokens, context_window)
    context_usage = Signal(int, int)

    def __init__(self, user_config: dict):
        super().__init__()
        self.user_config = user_config
        self.backend: AIBackend = create_backend(user_config)
        self.event_engine = EventEngine(on_event=self._on_event)
        self._thinking_start: float = 0.0
        self._send_lock = threading.Lock()
        # P1-1: monotonic request id replaces broken boolean flag
        self._request_counter = 0
        # P3-3: 估算 token 用量
        self._estimate_tokens = self._make_estimator()

    def _make_estimator(self):
        """P3-3: 返回一个可调用的 estimator(messages) -> int。"""
        # 不同模型 context window 差异大；这里按 backend 类型给个保守值
        model_lower = (self.user_config.get("openai_model", "") or "").lower()
        if "128k" in model_lower or "200k" in model_lower:
            window = 200_000
        elif "32k" in model_lower or "16k" in model_lower:
            window = 32_000
        elif "8k" in model_lower:
            window = 8_000
        else:
            window = 8_000  # 默认

        def estimate(messages: list) -> tuple[int, int]:
            # 粗略：1 token ≈ 4 字符（含中英）
            total = 0
            for m in messages:
                content = m.get("content", "")
                if isinstance(content, str):
                    total += len(content) // 4 + 4  # +4 for role
            return total, window
        return estimate

    def _emit_usage(self, messages: list):
        try:
            used, window = self._estimate_tokens(messages)
            self.context_usage.emit(used, window)
        except Exception:
            pass

    def update_config(self, user_config: dict):
        """Replace the backend without allowing an old request to leak through."""
        new_backend = create_backend(user_config)
        with self._send_lock:
            self._request_counter += 1
            old_backend = self.backend
            self.backend = new_backend
            old_backend.cancel()
            self.user_config = user_config
            self._estimate_tokens = self._make_estimator()

    def send(self, messages: list):
        """Send messages to AI backend (non-blocking, cancels previous request).

        P1-1: Uses a monotonic request_id so that callbacks from a stale
        request are silently discarded instead of overwriting fresh results.
        """
        import time
        # Cancel any in-flight backend request and capture the backend used by
        # this request. Settings changes must not swap it underneath the worker.
        with self._send_lock:
            self._request_counter += 1
            my_id = self._request_counter
            backend = self.backend
            backend.cancel()

        self._thinking_start = time.monotonic()
        self.state_changed.emit("thinking", "")
        self.event_engine.record(EventEngine.CHAT_START, {
            "backend": backend.get_name(),
            "message_count": len(messages),
        })
        # P3-3: 发送时即更新 token 用量
        self._emit_usage(messages)

        full_text_parts: list[str] = []

        def on_chunk(chunk):
            if my_id != self._request_counter:
                return
            full_text_parts.append(chunk)
            self.chunk_received.emit(chunk, "".join(full_text_parts))

        def on_done(full_text):
            if my_id != self._request_counter:
                return
            self.stream_done.emit(full_text)
            self.event_engine.record(EventEngine.CHAT_COMPLETE, {
                "response_length": len(full_text),
            })
            self.state_changed.emit("result", full_text[:80])

        def on_error(err):
            if my_id != self._request_counter:
                return
            self.stream_error.emit(err)
            self.state_changed.emit("error", err)
            self.event_engine.record(EventEngine.CHAT_ERROR, {"error": err})

        def worker():
            try:
                full = backend.send_message(messages, on_chunk=on_chunk)
                if my_id == self._request_counter:
                    # Backends may return an empty string after cancellation or
                    # an empty provider response. Always close the UI stream;
                    # otherwise ChatWindow remains disabled forever.
                    on_done(full or "")
            except Exception as e:
                if my_id == self._request_counter:
                    on_error(str(e))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def cancel(self):
        """Invalidate the current stream before asking its backend to stop."""
        with self._send_lock:
            self._request_counter += 1
            backend = self.backend
        backend.cancel()

    def _on_event(self, event_type: str, data: dict):
        state_map = {
            "job_started": "thinking",
            "job_finished": "idle",
            "job_failed": "error",
        }
        if event_type not in state_map:
            return  # ignore events that don't map to a state change
        state = state_map[event_type]
        name = data.get("name", "")
        self.state_changed.emit(state, name)
