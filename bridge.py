"""
Qt Signal Bridge — connects AIClient/EventEngine callbacks to Qt signals.

All AI operations run in background threads. This bridge safely marshals
results back to the Qt main thread via signals.
"""
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

    def __init__(self, user_config: dict):
        super().__init__()
        self.user_config = user_config
        self.backend: AIBackend = create_backend(user_config)
        self.event_engine = EventEngine(on_event=self._on_event)
        self._thinking_start: float = 0.0

    def update_config(self, user_config: dict):
        self.user_config = user_config
        self.backend = create_backend(user_config)

    def send(self, messages: list):
        """Send messages to AI backend (non-blocking)."""
        import time
        self._thinking_start = time.monotonic()
        self.state_changed.emit("thinking", "")
        self.event_engine.record(EventEngine.CHAT_START, {
            "backend": self.backend.get_name(),
            "message_count": len(messages),
        })

        def on_chunk(chunk):
            on_chunk._full_text += chunk
            self.chunk_received.emit(chunk, on_chunk._full_text)

        on_chunk._full_text = ""

        def on_done(full_text):
            self.stream_done.emit(full_text)
            self.event_engine.record(EventEngine.CHAT_COMPLETE, {
                "response_length": len(full_text),
            })
            # Emit result state directly — thread-safe because Qt signals
            # are queued across threads. The island's set_state handles
            # auto-collapse timing via its own QTimer on the main thread.
            self.state_changed.emit("result", full_text[:80])

        def on_error(err):
            self.stream_error.emit(err)
            self.state_changed.emit("error", err)
            self.event_engine.record(EventEngine.CHAT_ERROR, {"error": err})

        def worker():
            try:
                full = self.backend.send_message(messages, on_chunk=on_chunk)
                if full:
                    on_done(full)
            except Exception as e:
                on_error(str(e))

        import threading
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _show_result(self, full_text: str):
        """Show result state, then auto-collapse to idle after 2.5s."""
        self.state_changed.emit("result", full_text[:80])
        QTimer.singleShot(2500, lambda: self.state_changed.emit("idle", full_text[:80]))

    def cancel(self):
        """Cancel current stream."""
        self.backend.cancel()

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
