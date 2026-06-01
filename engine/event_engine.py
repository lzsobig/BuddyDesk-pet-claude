"""
Event Engine - Event recording, command wrapping, and state tracking

Improvements from winpet:
- Command wrapping with automatic status tracking
- Thread-safe job management with persistence
- Logging via standard logging module
"""
import json
import time
import os
import threading
import logging
from datetime import datetime
from typing import Callable, Optional

import config

logger = logging.getLogger(__name__)


class Event:
    """A single event record."""

    def __init__(self, event_type: str, data: dict = None):
        self.timestamp = datetime.now().isoformat()
        self.event_type = event_type
        self.data = data or {}

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "type": self.event_type,
            "data": self.data,
        }

    def __str__(self):
        return f"[{self.timestamp}] {self.event_type}: {self.data}"


class EventEngine:
    """Event engine - records events, wraps commands with tracking, broadcasts callbacks."""

    # Event types
    CHAT_START = "chat_start"
    CHAT_CHUNK = "chat_chunk"
    CHAT_COMPLETE = "chat_complete"
    CHAT_ERROR = "chat_error"
    PET_STATE_CHANGE = "pet_state_change"
    BACKEND_SWITCH = "backend_switch"
    APP_START = "app_start"
    APP_QUIT = "app_quit"
    JOB_STARTED = "job_started"
    JOB_FINISHED = "job_finished"
    JOB_FAILED = "job_failed"

    def __init__(self, on_event: Optional[Callable] = None):
        self.events = []
        self._lock = threading.Lock()
        self._callbacks = {}  # event_type -> [callbacks]
        self._on_event = on_event
        self.jobs = config.load_jobs()
        self._running_job = None
        self._max_id = max((j.get("id", 0) for j in self.jobs), default=0)
        self._load_events()

    def record(self, event_type: str, data: dict = None):
        """Record a new event."""
        event = Event(event_type, data)

        with self._lock:
            self.events.append(event)
            if len(self.events) > config.MAX_EVENT_HISTORY:
                self.events = self.events[-config.MAX_EVENT_HISTORY:]

        # Fire registered callbacks
        callbacks = self._callbacks.get(event_type, [])
        for cb in callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.warning("Event callback error: %s", e)

        # Fire global on_event callback (winpet-style)
        if self._on_event:
            try:
                self._on_event(event_type, event.data if hasattr(event, 'data') else {})
            except Exception as e:
                logger.warning("Global event callback error: %s", e)

        self._save_events()

    def on(self, event_type: str, callback):
        """Register a callback for an event type."""
        if event_type not in self._callbacks:
            self._callbacks[event_type] = []
        self._callbacks[event_type].append(callback)

    def wrap_command(self, name: str, command: str, cwd: str = None):
        """Wrap a command with automatic status tracking and event emission."""
        import subprocess
        import shlex

        def _worker():
            with self._lock:
                self._max_id = self._max_id + 1
                job_id = self._max_id

            job = {
                "id": job_id,
                "name": name,
                "command": command,
                "status": "running",
                "start_time": datetime.now().isoformat(),
                "end_time": None,
                "duration": None,
                "exit_code": None,
                "output": "",
                "error": "",
            }
            with self._lock:
                self.jobs.append(job)
                self._running_job = job
            self._emit_job(self.JOB_STARTED, job)

            try:
                start = time.time()
                try:
                    args = shlex.split(command)
                except ValueError:
                    args = command

                result = subprocess.run(
                    args, shell=False, capture_output=True, text=True,
                    cwd=cwd, timeout=300,
                )
                duration = time.time() - start

                job["end_time"] = datetime.now().isoformat()
                job["duration"] = round(duration, 2)
                job["exit_code"] = result.returncode
                job["output"] = result.stdout[-2000:] if result.stdout else ""
                job["error"] = result.stderr[-2000:] if result.stderr else ""

                if result.returncode == 0:
                    job["status"] = "succeeded"
                    self._emit_job(self.JOB_FINISHED, job)
                else:
                    job["status"] = "failed"
                    self._emit_job(self.JOB_FAILED, job)

            except subprocess.TimeoutExpired:
                job["status"] = "timeout"
                job["end_time"] = datetime.now().isoformat()
                job["error"] = "Command timed out (300s)"
                self._emit_job(self.JOB_FAILED, job)
            except Exception as e:
                job["status"] = "error"
                job["end_time"] = datetime.now().isoformat()
                job["error"] = str(e)
                self._emit_job(self.JOB_FAILED, job)
            finally:
                with self._lock:
                    self._running_job = None
                    config.save_jobs(self.jobs)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        return thread

    def _emit_job(self, event_type: str, job: dict):
        """Emit a job event via both callback systems."""
        if self._on_event:
            try:
                self._on_event(event_type, job)
            except Exception as e:
                logger.warning("Job event callback error: %s", e)

    def get_recent(self, count: int = 10) -> list:
        with self._lock:
            return self.events[-count:]

    def get_recent_jobs(self, limit: int = 10) -> list:
        with self._lock:
            return self.jobs[-limit:]

    def get_failed_jobs(self, limit: int = 5) -> list:
        with self._lock:
            failed = [j for j in self.jobs if j.get("status") == "failed"]
            return failed[-limit:]

    def get_job_summary(self) -> str:
        with self._lock:
            if not self.jobs:
                return "No jobs yet"
            recent = self.jobs[-5:]
            lines = []
            for j in recent:
                icon = {"succeeded": "✓", "failed": "✗",
                        "running": "⟳", "timeout": "⏰"}.get(j.get("status"), "?")
                dur = f"{j.get('duration', '...')}s" if j.get("duration") else "..."
                lines.append(f"  {icon} {j.get('name', '?')} ({dur})")
            return "\n".join(lines)

    def _load_events(self):
        """Load events from log file if it exists."""
        if os.path.exists(config.EVENT_LOG_FILE):
            try:
                with open(config.EVENT_LOG_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                event = Event(data.get("type", ""), data.get("data", {}))
                                event.timestamp = data.get("timestamp", "")
                                self.events.append(event)
                            except json.JSONDecodeError:
                                pass
                # Keep only recent
                self.events = self.events[-config.MAX_EVENT_HISTORY:]
            except IOError:
                pass

    def _save_events(self):
        """Persist events to log file."""
        try:
            os.makedirs(os.path.dirname(config.EVENT_LOG_FILE), exist_ok=True)
            with open(config.EVENT_LOG_FILE, "w", encoding="utf-8") as f:
                for event in self.events[-config.MAX_EVENT_HISTORY:]:
                    f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except IOError as e:
            logger.warning("Failed to save events: %s", e)
