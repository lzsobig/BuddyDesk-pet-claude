from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections import deque
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer


logger = logging.getLogger(__name__)


def _write_atomic(directory, name, data):
    temporary = directory / f".{name}.{os.getpid()}.{uuid4().hex}.tmp"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        for attempt in range(4):
            try:
                os.replace(temporary, directory / name)
                break
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(0.005 * (2 ** attempt))
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            logger.debug("WinIsland temporary file cleanup deferred")


def _process_alive(pid):
    if sys.platform == "win32":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def request_existing_chat(directory=None, open_chat=True):
    directory = directory or Path.home() / ".buddydesk" / "winisland"
    try:
        path = directory / "state.json"
        if path.stat().st_size > 16384:
            return False
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("protocol_version") != 1:
            return False
        updated = state.get("updated_at_ms")
        pid = state.get("pid")
        now = int(time.time() * 1000)
        if type(updated) is not int or type(pid) is not int or pid == os.getpid() or pid <= 0:
            return False
        if not -1000 <= now - updated <= 6000:
            return False
        if not _process_alive(pid):
            return False
        if not open_chat:
            return True
        try:
            _write_atomic(directory, "commands.json", {
                "protocol_version": 1, "id": uuid4().hex,
                "issued_at_ms": now, "action": "open_chat",
            })
        except OSError:
            logger.warning("Existing BuddyDesk session detected; open-chat command could not be delivered")
        return True
    except (OSError, UnicodeError, ValueError):
        return False


class WinIslandBridge(QObject):
    STATES = {"idle", "thinking", "result", "error", "notify", "listening", "transcribing",
              "understanding", "asking_confirmation", "executing", "reminding", "success"}
    PET_STATES = {"idle", "happy", "sleep", "love", "walk"}

    def __init__(self, main_app):
        super().__init__(main_app.app)
        self.main_app = main_app
        self.directory = Path.home() / ".buddydesk" / "winisland"
        self._seen_ids = deque(maxlen=64)
        self._state = "idle"
        self._thinking_started_at_ms = 0
        self._preview = ""
        self._closed = False
        self._command_mtime = None
        self._failures = {}
        self._dispatching = False
        self._restore_acknowledgement()
        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._poll_commands)
        self._heartbeat = QTimer(self)
        self._heartbeat.setInterval(1000)
        self._heartbeat.timeout.connect(self._write_state)
        self._publish_integration()
        self.refresh_pet()
        self._write_state()
        self._timer.start()
        self._heartbeat.start()
        main_app.app.aboutToQuit.connect(self.close)

    def _restore_acknowledgement(self):
        try:
            path = self.directory / "ack.json"
            if not path.exists() or path.stat().st_size > 8192:
                return
            ack = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(ack, dict) or ack.get("protocol_version") != 1:
                return
            command_id = ack.get("id")
            if isinstance(command_id, str) and 1 <= len(command_id) <= 128:
                self._seen_ids.append(command_id)
        except (OSError, UnicodeError, ValueError) as error:
            logger.debug("WinIsland acknowledgement: %s", error)

    def _atomic_write(self, name, data):
        _write_atomic(self.directory, name, data)

    def _report_error(self, error, operation):
        now = time.monotonic()
        failure = self._failures.setdefault(operation, {"started": now, "count": 0, "reported": False})
        failure["count"] += 1
        if failure["count"] == 1:
            record = {"time": int(time.time()), "operation": operation,
                      "error": type(error).__name__, "winerror": getattr(error, "winerror", None),
                      "errno": getattr(error, "errno", None)}
            logger.warning("WinIsland operation failed: %s", record)
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                path = self.directory / "diagnostics.log"
                if path.exists() and path.stat().st_size > 32768:
                    path.replace(self.directory / "diagnostics.previous.log")
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record) + "\n")
            except OSError:
                pass
        if now - failure["started"] >= 3.0 and failure["count"] >= 3:
            failure["reported"] = True
            chat = self.main_app.chat
            if chat and hasattr(chat, "set_integration_warning"):
                chat.set_integration_warning("灵动岛同步暂时中断，正在重试。聊天仍可正常使用。")

    def _clear_failure(self, operation):
        self._failures.pop(operation, None)
        if not any(failure["reported"] for failure in self._failures.values()):
            chat = self.main_app.chat
            if chat and hasattr(chat, "set_integration_warning"):
                chat.set_integration_warning("")

    def _publish_integration(self):
        try:
            self._atomic_write("integration.json", {
                "protocol_version": 1,
                "source_dir": str(Path(__file__).resolve().parent),
                "python_path": sys.executable,
                "assistant_executable": sys.executable if getattr(sys, "frozen", False) else None,
            })
            self._clear_failure("integration")
        except OSError as error:
            self._report_error(error, "integration")

    def refresh_pet(self):
        from pet_library import island_settings
        try:
            self._atomic_write("pet.json", island_settings(self.main_app._user_config))
            self._clear_failure("pet")
        except OSError as error:
            self._report_error(error, "pet")

    def update_state(self, state, preview=""):
        if state not in self.STATES:
            return
        if state == "thinking" and self._state != "thinking":
            self._thinking_started_at_ms = int(time.time() * 1000)
        elif state != "thinking":
            self._thinking_started_at_ms = 0
        self._state = state
        self._preview = str(preview).replace("\x00", "")[:300]
        self._write_state()

    def _write_state(self):
        if self._closed:
            return
        if "integration" in self._failures:
            self._publish_integration()
        if "pet" in self._failures:
            self.refresh_pet()
        try:
            self._atomic_write("state.json", {
                "protocol_version": 1,
                "updated_at_ms": int(time.time() * 1000),
                "pid": os.getpid(),
                "state": self._state,
                "thinking_started_at_ms": self._thinking_started_at_ms,
                "preview": self._preview,
                "pet_name": str(self.main_app._user_config.get("pet_name", "小橘"))[:40],
                "backend": self.main_app.bridge.backend.get_name()[:120],
            })
            self._clear_failure("state")
        except (OSError, AttributeError) as error:
            self._report_error(error, "state")

    def _poll_commands(self):
        if self._closed or self._dispatching:
            return
        self._poll_agent_commands()
        failed = False
        try:
            path = self.directory / "commands.json"
            if not path.exists():
                return
            stat = path.stat()
            if stat.st_mtime_ns == self._command_mtime or stat.st_size > 8192:
                return
            command = json.loads(path.read_text(encoding="utf-8"))
            self._command_mtime = stat.st_mtime_ns
            if not isinstance(command, dict) or command.get("protocol_version") != 1:
                return
            command_id = command.get("id")
            if not isinstance(command_id, str) or not 1 <= len(command_id) <= 128:
                return
            if command_id in self._seen_ids:
                return
            issued_at = command.get("issued_at_ms")
            if type(issued_at) is not int:
                return
            age = int(time.time() * 1000) - issued_at
            if age > 120_000 or age < -5_000:
                return
            action = command.get("action")
            agent_actions = ("open_tasks", "task_complete", "task_reopen", "task_detail", "reminder_snooze", "reminder_complete", "reminder_dismiss")
            if action not in ("open_chat", "open_launcher", "open_settings", "open_pet_settings", "pet_state", *agent_actions):
                return
            if action == "open_launcher" and (not isinstance(command.get("query", ""), str) or len(command.get("query", "")) > 500):
                return
            if action == "pet_state" and (
                not isinstance(command.get("state"), str)
                or command["state"] not in self.PET_STATES
            ):
                return
            self._atomic_write("ack.json", {
                "protocol_version": 1,
                "id": command_id,
                "consumed_at_ms": int(time.time() * 1000),
            })
            self._seen_ids.append(command_id)
            self._dispatching = True
            try:
                if action in agent_actions and self.main_app.agent:
                    self.main_app.agent.handle_command(command)
                elif action == "open_chat":
                    self.main_app._show_chat()
                elif action == "open_launcher" and self.main_app.agent:
                    launcher = self.main_app.agent.launcher
                    if not launcher.active:
                        launcher.toggle()
                    if launcher.active:
                        launcher.card.editor.setPlainText(command.get("query", ""))
                        launcher.search()
                elif action == "open_settings":
                    self.main_app._open_settings()
                elif action == "open_pet_settings":
                    self.main_app._open_settings(3)
                elif self.main_app.pet:
                    self.main_app.pet.set_state(command["state"])
            finally:
                self._dispatching = False
        except (OSError, UnicodeError, ValueError, RuntimeError) as error:
            failed = True
            self._command_mtime = None
            self._report_error(error, "commands")
        finally:
            if not failed:
                self._clear_failure("commands")

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        self._heartbeat.stop()
        try:
            path = self.directory / "state.json"
            state = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(state, dict) and state.get("pid") == os.getpid():
                state["updated_at_ms"] = 0
                self._atomic_write("state.json", state)
        except (OSError, UnicodeError, ValueError) as error:
            logger.debug("WinIsland shutdown: %s", error)

    def _poll_agent_commands(self):
        import itertools
        directory = self.directory / "agent-commands"
        if not directory.is_dir() or directory.is_symlink():
            return
        agent_actions = ("open_tasks", "task_complete", "task_reopen", "task_detail",
                         "reminder_snooze", "reminder_complete", "reminder_dismiss")
        self._dispatching = True
        try:
            for path in sorted(itertools.islice(directory.glob("*.json"), 128))[:32]:
                if path.is_symlink():
                    continue
                try:
                    if path.stat().st_size > 8192:
                        path.unlink()
                        continue
                    command = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(command, dict):
                        path.unlink()
                        continue
                    identity = command.get("id")
                    issued = command.get("issued_at_ms")
                    action = command.get("action")
                    valid = (command.get("protocol_version") == 1 and isinstance(identity, str)
                        and 0 < len(identity) <= 128 and type(issued) is int
                        and -5000 <= int(time.time() * 1000) - issued <= 120000
                        and action in (*agent_actions, "pet_update", "open_pet_settings"))
                    if valid and identity not in self._seen_ids:
                        if action in agent_actions:
                            if not getattr(self.main_app, "agent", None):
                                continue
                            self.main_app.agent.handle_command(command)
                        elif action == "open_pet_settings":
                            if set(command) != {"protocol_version", "id", "issued_at_ms", "action"}:
                                path.unlink(missing_ok=True)
                                continue
                            self.main_app._open_settings(3)
                        else:
                            if set(command) != {"protocol_version", "id", "issued_at_ms", "action", "key", "value"}:
                                path.unlink(missing_ok=True)
                                continue
                            key = command["key"]
                            value = command["value"]
                            if key == "pet_id":
                                from pet_library import pets
                                allowed = isinstance(value, str) and value in {pet["id"] for pet in pets()}
                            elif key == "pet_name":
                                allowed = (isinstance(value, str) and 0 < len(value.strip())
                                           and len(value) <= 24
                                           and not any(ord(char) < 32 for char in value))
                            elif key in ("pet_enabled", "pet_island_enabled", "pet_roam"):
                                allowed = type(value) is bool
                            else:
                                allowed = key == "pet_position" and value is None
                            if not allowed:
                                path.unlink(missing_ok=True)
                                continue
                            import config as cfg
                            new_config = dict(self.main_app._user_config)
                            new_config[key] = value.strip() if key == "pet_name" else value
                            if key == "pet_id":
                                new_config["pet_name"] = next(
                                    pet["name"] for pet in pets() if pet["id"] == value)
                            cfg.save_user_config(new_config)
                            self.main_app.apply_external_pet_settings(new_config, key)
                        self._seen_ids.append(identity)
                    path.unlink()
                    self._clear_failure("agent_commands")
                except (UnicodeError, ValueError):
                    path.unlink(missing_ok=True)
        except (OSError, RuntimeError) as error:
            self._report_error(error, "agent_commands")
        finally:
            self._dispatching = False
