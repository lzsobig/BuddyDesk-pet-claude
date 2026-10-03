from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class AgentStateStore(QObject):
    changed = Signal(dict)
    STATES = frozenset({"idle", "listening", "transcribing", "understanding", "thinking",
                        "asking_confirmation", "executing", "reminding", "success", "error"})

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "idle"
        self.label = ""
        self.transcript = ""
        self.level = 0.0
        self.revision = 0

    def set(self, state: str, label: str = "", transcript: str | None = None):
        if state not in self.STATES:
            raise ValueError("Unknown agent state")
        self.state, self.label = state, label[:240]
        if transcript is not None:
            self.transcript = transcript[:12000]
        if state != "listening":
            self.level = 0.0
        self.revision += 1
        self.changed.emit(self.snapshot())

    def update_transcript(self, text: str):
        self.transcript = text[:12000]
        self.changed.emit(self.snapshot())

    def update_level(self, level: float):
        if self.state == "listening":
            self.level = max(0.0, min(1.0, level))
            self.changed.emit(self.snapshot())

    def snapshot(self) -> dict:
        return {"state": self.state, "label": self.label, "transcript": self.transcript,
                "level": self.level, "revision": self.revision}
