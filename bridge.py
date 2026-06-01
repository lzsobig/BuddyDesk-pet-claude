"""
Qt Signal Bridge — connects AIClient/EventEngine callbacks to Qt signals.

All AI operations run in background threads. This bridge safely marshals
results back to the Qt main thread via signals.
"""
from PySide6.QtCore import QObject, Signal

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

    def update_config(self, user_config: dict):
        self.user_config = user_config
        self.backend = create_backend(user_config)

    def send(self, messages: list):
        """Send messages to AI backend (non-blocking)."""
        self.state_changed.emit("thinking", "")
        self.event_engine.record(EventEngine.CHAT_START, {
            "backend": self.backend.get_name(),
            "message_count": len(messages),
        })

        def on_chunk(chunk):
            # Accumulate full text so far and emit both chunk and full
            on_chunk._full_text += chunk
            self.chunk_received.emit(chunk, on_chunk._full_text)

        on_chunk._full_text = ""

        def on_done(full_text):
            self.stream_done.emit(full_text)
            # Show the "result / task complete" pill on the island for 2.5s
            # before going idle, so the user can see the success state.
            self.state_changed.emit("result", full_text[:80])
            self.event_engine.record(EventEngine.CHAT_COMPLETE, {
                "response_length": len(full_text),
            })
            # After a short pause, return the island to idle.
            import threading
            def _return_to_idle():
                self.state_changed.emit("idle", full_text[:80])
            threading.Timer(2.5, _return_to_idle).start()

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

    def cancel(self):
        """Cancel current stream."""
        self.backend.cancel()

    def _on_event(self, event_type: str, data: dict):
        state_map = {
            "job_started": "thinking",
            "job_finished": "idle",
            "job_failed": "error",
        }
        state = state_map.get(event_type, "idle")
        name = data.get("name", "")
        self.state_changed.emit(state, name)
