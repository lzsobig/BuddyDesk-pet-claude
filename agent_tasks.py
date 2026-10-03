"""Persistent task and reminder storage for BuddyDesk's voice agent."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterator

import config


SCHEMA_VERSION = 1
MAX_DRAFTS_PER_CONFIRMATION = 100
MAX_REMINDERS_PER_TASK = 16
MAX_DEPENDENCIES = 50
MAX_QUESTIONS = 20
MAX_SNOOZE_MINUTES = 10080
REPEAT_RULES = {"none", "daily", "weekly"}
_PAST_DUE_QUESTION = "截止时间早于当前时间，请确认是否仍然有效。"
_REDACT_PATTERNS = (
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"), "[redacted]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[redacted]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[redacted]"),
    (
        re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*([^\s,;]+)"),
        r"\1=[redacted]",
    ),
    (re.compile(r"(?i)(https?://)[^/@\s]+@"), r"\1[redacted]@"),
)


class TaskStoreError(ValueError):
    """Base exception for task-store errors."""


class TaskNotFoundError(TaskStoreError):
    """Raised when a requested task or reminder does not exist."""


class TaskConflictError(TaskStoreError):
    """Raised when a draft ID is reused for different task content."""


class TaskValidationError(TaskStoreError):
    """Raised when a task or reminder value violates the storage contract."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TaskValidationError("时间必须包含时区")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _parse_datetime(value: Any, field: str, *, nullable: bool = False) -> datetime | None:
    if value is None:
        if nullable:
            return None
        raise TaskValidationError(f"{field}不能为空")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            if nullable:
                return None
            raise TaskValidationError(f"{field}不能为空")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as error:
            raise TaskValidationError(f"{field}必须是有效的 ISO 8601 时间") from error
    else:
        raise TaskValidationError(f"{field}必须是 ISO 8601 字符串")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TaskValidationError(f"{field}必须包含时区")
    return parsed.astimezone(timezone.utc)


def _clean_text(
    value: Any,
    field: str,
    *,
    maximum: int,
    default: str = "",
    required: bool = False,
) -> str:
    if value is None and not required:
        value = default
    if not isinstance(value, str):
        raise TaskValidationError(f"{field}必须是文本")
    result = value.strip()
    if required and not result:
        raise TaskValidationError(f"{field}不能为空")
    if len(result) > maximum:
        raise TaskValidationError(f"{field}不能超过 {maximum} 个字符")
    return result


def _identifier(value: Any, field: str) -> str:
    result = _clean_text(value, field, maximum=128, required=True)
    if any(ord(character) < 32 for character in result):
        raise TaskValidationError(f"{field}不能包含控制字符")
    return result


def _normalize_repeat_rule(value: Any) -> str:
    rule = _clean_text(value, "repeat_rule", maximum=16, default="none").lower()
    if rule not in REPEAT_RULES:
        raise TaskValidationError("repeat_rule 只能是 none、daily 或 weekly")
    return rule


def _string_list(
    value: Any,
    field: str,
    *,
    maximum_items: int,
    maximum_length: int,
    identifiers: bool = False,
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TaskValidationError(f"{field}必须是列表")
    if len(value) > maximum_items:
        raise TaskValidationError(f"{field}最多只能包含 {maximum_items} 项")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = (
            _identifier(item, field)
            if identifiers
            else _clean_text(item, field, maximum=maximum_length, required=True)
        )
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _normalize_draft(
    draft: dict[str, Any],
    now: datetime,
    *,
    allow_existing_times: bool = False,
) -> dict[str, Any]:
    if not isinstance(draft, dict):
        raise TaskValidationError("事项草稿必须是对象")

    task_id = draft.get("id")
    draft_id = draft.get("draft_id")
    if task_id and draft_id and str(task_id).strip() != str(draft_id).strip():
        raise TaskValidationError("id 与 draft_id 不一致")
    task_id = task_id or draft_id or uuid.uuid4().hex
    task_id = _identifier(task_id, "id")

    title = _clean_text(draft.get("title"), "title", maximum=240, required=True)
    description = _clean_text(draft.get("description"), "description", maximum=8000)
    priority = draft.get("priority", 2)
    if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 3:
        raise TaskValidationError("priority 必须是 0 到 3 之间的整数")

    status = draft.get("status", "pending")
    if status != "pending":
        raise TaskValidationError("新建事项的 status 必须是 pending")

    due = _parse_datetime(draft.get("due_at"), "due_at", nullable=True)
    estimated = draft.get("estimated_minutes")
    if estimated is not None:
        if (
            isinstance(estimated, bool)
            or not isinstance(estimated, int)
            or not 1 <= estimated <= 10080
        ):
            raise TaskValidationError("estimated_minutes 必须是 1 到 10080 之间的整数或空值")

    raw_reminders = draft.get("reminder_times", [])
    if raw_reminders is None:
        raw_reminders = []
    if not isinstance(raw_reminders, list):
        raise TaskValidationError("reminder_times 必须是列表")
    if len(raw_reminders) > MAX_REMINDERS_PER_TASK:
        raise TaskValidationError(f"reminder_times 最多只能包含 {MAX_REMINDERS_PER_TASK} 项")

    raw_rules = draft.get("_reminder_rules", draft.get("reminder_repeat_rules"))
    if raw_rules is not None and not isinstance(raw_rules, list):
        raise TaskValidationError("reminder_repeat_rules 必须是列表")
    if isinstance(raw_rules, list) and len(raw_rules) != len(raw_reminders):
        raise TaskValidationError("reminder_repeat_rules 项数必须与 reminder_times 一致")
    default_rule = _normalize_repeat_rule(draft.get("repeat_rule", "none"))

    reminders: list[tuple[str, str]] = []
    for index, item in enumerate(raw_reminders):
        item_rule = default_rule
        item_time = item
        if isinstance(item, dict):
            item_time = item.get("trigger_at", item.get("time"))
            item_rule = _normalize_repeat_rule(item.get("repeat_rule", default_rule))
        elif isinstance(raw_rules, list):
            item_rule = _normalize_repeat_rule(raw_rules[index])
        reminder_time = _parse_datetime(item_time, "reminder_times")
        if reminder_time is None:
            raise TaskValidationError("reminder_times 不能包含空值")
        if reminder_time <= now and not allow_existing_times:
            raise TaskValidationError("新的提醒时间必须晚于当前时间")
        reminders.append((_iso_utc(reminder_time), item_rule))

    reminders.sort(key=lambda entry: (entry[0], entry[1]))
    deduplicated: list[tuple[str, str]] = []
    reminder_rules_by_time: dict[str, str] = {}
    for reminder_time, rule in reminders:
        existing_rule = reminder_rules_by_time.get(reminder_time)
        if existing_rule is not None and existing_rule != rule:
            raise TaskValidationError("相同提醒时间不能设置不同的重复规则")
        if existing_rule is None:
            reminder_rules_by_time[reminder_time] = rule
            deduplicated.append((reminder_time, rule))

    questions = _string_list(
        draft.get("questions", []),
        "questions",
        maximum_items=MAX_QUESTIONS,
        maximum_length=500,
    )
    if due is not None and due < now and not allow_existing_times and _PAST_DUE_QUESTION not in questions:
        if len(questions) >= MAX_QUESTIONS:
            questions[-1] = _PAST_DUE_QUESTION
        else:
            questions.append(_PAST_DUE_QUESTION)

    confidence = draft.get("confidence", 0.0)
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(float(confidence))
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise TaskValidationError("confidence 必须是 0 到 1 之间的有限数字")

    dependencies = _string_list(
        draft.get("dependencies", []),
        "dependencies",
        maximum_items=MAX_DEPENDENCIES,
        maximum_length=128,
        identifiers=True,
    )
    if task_id in dependencies:
        raise TaskValidationError("事项不能依赖自身")

    normalized = {
        "id": task_id,
        "title": title,
        "description": description,
        "priority": priority,
        "status": "pending",
        "due_at": _iso_utc(due) if due is not None else None,
        "estimated_minutes": estimated,
        "reminder_times": [entry[0] for entry in deduplicated],
        "category": _clean_text(draft.get("category"), "category", maximum=120),
        "source": _clean_text(draft.get("source"), "source", maximum=120),
        "reasoning": _clean_text(draft.get("reasoning"), "reasoning", maximum=4000),
        "confidence": float(confidence),
        "questions": questions,
        "dependencies": dependencies,
        "_reminder_rules": [entry[1] for entry in deduplicated],
    }
    return normalized


def validate_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized task draft and assign an ID when the caller omitted one."""
    return _normalize_draft(draft, _utc_now())


def _draft_hash(draft: dict[str, Any]) -> str:
    content = {key: value for key, value in draft.items() if key != "_reminder_rules"}
    content["_reminder_rules"] = draft.get("_reminder_rules", [])
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _row_to_task(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "priority": row["priority"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "due_at": row["due_at"],
        "estimated_minutes": row["estimated_minutes"],
        "reminder_times": _json_load(row["reminder_times"], []),
        "category": row["category"],
        "source": row["source"],
        "reasoning": row["reasoning"],
        "confidence": row["confidence"],
        "questions": _json_load(row["questions"], []),
        "dependencies": _json_load(row["dependencies"], []),
    }


def _row_to_reminder(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "trigger_at": row["trigger_at"],
        "status": row["status"],
        "repeat_rule": row["repeat_rule"],
        "scheduled_at": row["scheduled_at"],
        "series_id": row["series_id"],
        "series_index": row["series_index"],
        "title": row["title"] if "title" in row.keys() else None,
    }


def _task_sort_key(task: dict[str, Any]) -> tuple[Any, ...]:
    return (
        task["priority"],
        task["due_at"] is None,
        task["due_at"] or "",
        task["created_at"],
        task["id"],
    )


def _dependency_order(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    remaining = {task["id"] for task in tasks}
    while remaining:
        ready = [task for task in tasks if task["id"] in remaining
                 and not remaining.intersection(task.get("dependencies", []))]
        if not ready:
            raise TaskValidationError("事项依赖存在循环")
        task = ready[0]
        result.append(task)
        remaining.remove(task["id"])
    return result


def _time_text(due_at: str | None, reminder_at: str | None, now: datetime) -> str:
    if not due_at:
        if reminder_at:
            reminder = _parse_datetime(reminder_at, "reminder_at")
            if reminder is not None:
                local = reminder.astimezone()
                if local.date() == now.astimezone().date():
                    return f"{local.strftime('%H:%M')} 提醒"
                if local.date() == now.astimezone().date() + timedelta(days=1):
                    return f"明天 {local.strftime('%H:%M')} 提醒"
                return f"{local.strftime('%m/%d %H:%M')} 提醒"
        return ""
    due = _parse_datetime(due_at, "due_at")
    if due is None:
        return ""
    local_due = due.astimezone()
    local_now = now.astimezone()
    if local_due.date() == local_now.date():
        return local_due.strftime('%H:%M')
    if local_due.date() == local_now.date() + timedelta(days=1):
        return f"明天 {local_due.strftime('%H:%M')}"
    return local_due.strftime("%m/%d %H:%M")


def _redact_detail(detail: str) -> str:
    result = detail
    for pattern, replacement in _REDACT_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


class TaskStore:
    """SQLite-backed tasks and reminders using a short connection per operation."""

    def __init__(self, path: str | os.PathLike[str] | None = None):
        selected_path = os.fspath(path) if path is not None else os.path.join(
            config.CONFIG_DIR, "agent.sqlite3"
        )
        self._memory_anchor: sqlite3.Connection | None = None
        self._use_uri = False
        if selected_path == ":memory:":
            selected_path = f"file:agent_tasks_{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._use_uri = True
            self._memory_anchor = sqlite3.connect(selected_path, uri=True)
        elif selected_path.startswith("file:"):
            self._use_uri = True
        else:
            parent = os.path.dirname(os.path.abspath(selected_path))
            os.makedirs(parent, exist_ok=True)
        self.path = selected_path
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.path,
            timeout=5.0,
            isolation_level=None,
            uri=self._use_uri,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    @staticmethod
    def _add_column_if_missing(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        declaration: str,
    ) -> None:
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("BEGIN IMMEDIATE")
            try:
                current_version = connection.execute("PRAGMA user_version").fetchone()[0]
                if current_version > SCHEMA_VERSION:
                    raise TaskStoreError(
                        f"数据库版本 {current_version} 高于支持版本 {SCHEMA_VERSION}"
                    )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        priority INTEGER NOT NULL DEFAULT 2 CHECK(priority BETWEEN 0 AND 3),
                        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'done')),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        due_at TEXT,
                        estimated_minutes INTEGER,
                        reminder_times TEXT NOT NULL DEFAULT '[]',
                        category TEXT NOT NULL DEFAULT '',
                        source TEXT NOT NULL DEFAULT '',
                        reasoning TEXT NOT NULL DEFAULT '',
                        confidence REAL NOT NULL DEFAULT 0.0,
                        questions TEXT NOT NULL DEFAULT '[]',
                        dependencies TEXT NOT NULL DEFAULT '[]',
                        completed_at TEXT,
                        draft_hash TEXT NOT NULL DEFAULT ''
                    )"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS reminders (
                        id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                        trigger_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending', 'firing', 'done', 'dismissed')),
                        repeat_rule TEXT NOT NULL DEFAULT 'none'
                            CHECK(repeat_rule IN ('none', 'daily', 'weekly')),
                        scheduled_at TEXT NOT NULL,
                        series_id TEXT NOT NULL,
                        series_index INTEGER NOT NULL DEFAULT 0,
                        is_initial INTEGER NOT NULL DEFAULT 1 CHECK(is_initial IN (0, 1)),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(series_id, scheduled_at)
                    )"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS audit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        action TEXT NOT NULL,
                        target_id TEXT,
                        outcome TEXT NOT NULL,
                        detail TEXT NOT NULL DEFAULT ''
                    )"""
                )
                self._add_column_if_missing(connection, "tasks", "completed_at", "TEXT")
                self._add_column_if_missing(
                    connection, "tasks", "draft_hash", "TEXT NOT NULL DEFAULT ''"
                )
                self._add_column_if_missing(
                    connection, "reminders", "repeat_rule", "TEXT NOT NULL DEFAULT 'none'"
                )
                self._add_column_if_missing(
                    connection, "reminders", "scheduled_at", "TEXT NOT NULL DEFAULT ''"
                )
                self._add_column_if_missing(
                    connection, "reminders", "series_id", "TEXT NOT NULL DEFAULT ''"
                )
                self._add_column_if_missing(
                    connection,
                    "reminders",
                    "series_index",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                self._add_column_if_missing(
                    connection,
                    "reminders",
                    "is_initial",
                    "INTEGER NOT NULL DEFAULT 1",
                )
                self._add_column_if_missing(
                    connection, "reminders", "created_at", "TEXT NOT NULL DEFAULT ''"
                )
                self._add_column_if_missing(
                    connection, "reminders", "updated_at", "TEXT NOT NULL DEFAULT ''"
                )
                connection.execute(
                    "UPDATE reminders SET scheduled_at = trigger_at WHERE scheduled_at = ''"
                )
                connection.execute("UPDATE reminders SET series_id = id WHERE series_id = ''")
                now = _iso_utc(_utc_now())
                connection.execute(
                    "UPDATE reminders SET created_at = ? WHERE created_at = ''", (now,)
                )
                connection.execute(
                    "UPDATE reminders SET updated_at = ? WHERE updated_at = ''", (now,)
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_status_priority_due "
                    "ON tasks(status, priority, due_at, created_at, id)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_completed_at "
                    "ON tasks(completed_at)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_reminders_due_status "
                    "ON reminders(status, trigger_at, task_id)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_reminders_task_status "
                    "ON reminders(task_id, status, trigger_at)"
                )
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_reminders_series_schedule "
                    "ON reminders(series_id, scheduled_at)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_timestamp "
                    "ON audit(timestamp, id)"
                )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    @staticmethod
    def _audit_conn(
        connection: sqlite3.Connection,
        action: str,
        target_id: str | None,
        outcome: str,
        detail: str = "",
    ) -> None:
        action_value = _clean_text(action, "action", maximum=80, required=True)
        target_value = None if target_id is None else _identifier(target_id, "target_id")
        outcome_value = _clean_text(outcome, "outcome", maximum=80, required=True)
        detail_value = _clean_text(detail, "detail", maximum=1000)
        connection.execute(
            "INSERT INTO audit(timestamp, action, target_id, outcome, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                _iso_utc(_utc_now()),
                action_value,
                target_value,
                outcome_value,
                _redact_detail(detail_value),
            ),
        )

    def audit(
        self,
        action: str,
        target_id: str | None,
        outcome: str,
        detail: str = "",
    ) -> None:
        """Persist a redacted audit entry without task payloads or credentials."""
        with self._transaction() as connection:
            self._audit_conn(connection, action, target_id, outcome, detail)

    @staticmethod
    def _task_dependencies(connection: sqlite3.Connection) -> dict[str, list[str]]:
        return {
            row["id"]: _json_load(row["dependencies"], [])
            for row in connection.execute("SELECT id, dependencies FROM tasks")
        }

    @staticmethod
    def _ensure_dependencies(
        graph: dict[str, list[str]],
        new_tasks: list[dict[str, Any]],
    ) -> None:
        for task in new_tasks:
            graph[task["id"]] = task["dependencies"]
        for task_id, dependencies in graph.items():
            for dependency in dependencies:
                if dependency not in graph:
                    raise TaskValidationError(
                        f"事项 {task_id} 依赖的事项 {dependency} 不存在"
                    )
                if dependency == task_id:
                    raise TaskValidationError("事项不能依赖自身")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visited:
                return
            if task_id in visiting:
                raise TaskValidationError("事项依赖关系不能形成循环")
            visiting.add(task_id)
            for dependency in graph.get(task_id, []):
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in graph:
            visit(task_id)

    @staticmethod
    def _insert_reminder(
        connection: sqlite3.Connection,
        task_id: str,
        trigger_at: str,
        repeat_rule: str,
        *,
        reminder_id: str | None = None,
        series_id: str | None = None,
        series_index: int = 0,
        is_initial: bool = True,
    ) -> str:
        identifier = reminder_id or uuid.uuid4().hex
        actual_series_id = series_id or identifier
        now = _iso_utc(_utc_now())
        connection.execute(
            """INSERT INTO reminders(
                id, task_id, trigger_at, status, repeat_rule, scheduled_at,
                series_id, series_index, is_initial, created_at, updated_at
            ) VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)""",
            (
                identifier,
                task_id,
                trigger_at,
                repeat_rule,
                trigger_at,
                actual_series_id,
                series_index,
                int(is_initial),
                now,
                now,
            ),
        )
        return identifier

    @staticmethod
    def _fetch_reminder(
        connection: sqlite3.Connection,
        reminder_id: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """SELECT reminders.*, tasks.title AS title
               FROM reminders JOIN tasks ON tasks.id = reminders.task_id
               WHERE reminders.id = ?""",
            (reminder_id,),
        ).fetchone()

    def confirm_drafts(self, drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Atomically persist reviewed drafts, keyed by their stable draft IDs."""
        if not isinstance(drafts, list):
            raise TaskValidationError("drafts 必须是列表")
        if len(drafts) > MAX_DRAFTS_PER_CONFIRMATION:
            raise TaskValidationError(
                f"一次最多只能确认 {MAX_DRAFTS_PER_CONFIRMATION} 个事项"
            )
        if not drafts:
            return []

        now = _utc_now()
        with self._transaction() as connection:
            normalized = []
            existing_by_id = {}
            for draft in drafts:
                if not isinstance(draft, dict):
                    raise TaskValidationError("事项草稿必须是对象")
                draft_id = draft.get("id") or draft.get("draft_id")
                existing = None
                if draft_id:
                    existing = connection.execute(
                        "SELECT * FROM tasks WHERE id = ?", (_identifier(draft_id, "id"),)
                    ).fetchone()
                item = _normalize_draft(
                    draft, now, allow_existing_times=existing is not None
                )
                normalized.append(item)
                existing_by_id[item["id"]] = existing
            ids = [draft["id"] for draft in normalized]
            if len(set(ids)) != len(ids):
                raise TaskConflictError("同一批事项中包含重复的 draft id")
            if any(draft["questions"] for draft in normalized):
                raise TaskValidationError("仍有待确认问题，请先由用户核对并清除 questions")
            hashes = {draft["id"]: _draft_hash(draft) for draft in normalized}
            graph = self._task_dependencies(connection)
            self._ensure_dependencies(graph, normalized)
            output: list[dict[str, Any]] = []
            for draft in normalized:
                existing = existing_by_id[draft["id"]]
                if existing is not None:
                    if existing["draft_hash"] != hashes[draft["id"]]:
                        raise TaskConflictError(
                            f"draft id {draft['id']} 已用于不同内容，未覆盖已有事项"
                        )
                    output.append(_row_to_task(existing))
                    continue

                created_at = _iso_utc(now)
                connection.execute(
                    """INSERT INTO tasks(
                        id, title, description, priority, status, created_at, updated_at,
                        due_at, estimated_minutes, reminder_times, category, source,
                        reasoning, confidence, questions, dependencies, draft_hash
                    ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        draft["id"],
                        draft["title"],
                        draft["description"],
                        draft["priority"],
                        created_at,
                        created_at,
                        draft["due_at"],
                        draft["estimated_minutes"],
                        json.dumps(draft["reminder_times"], ensure_ascii=False),
                        draft["category"],
                        draft["source"],
                        draft["reasoning"],
                        draft["confidence"],
                        json.dumps(draft["questions"], ensure_ascii=False),
                        json.dumps(draft["dependencies"], ensure_ascii=False),
                        hashes[draft["id"]],
                    ),
                )
                for reminder_time, repeat_rule in zip(
                    draft["reminder_times"], draft["_reminder_rules"]
                ):
                    self._insert_reminder(connection, draft["id"], reminder_time, repeat_rule)
                self._audit_conn(
                    connection,
                    "task.confirm",
                    draft["id"],
                    "created",
                    "fields=" + ",".join(
                        key
                        for key in (
                            "title",
                            "due_at",
                            "estimated_minutes",
                            "reminder_times",
                            "priority",
                        )
                        if draft.get(key) is not None
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM tasks WHERE id = ?", (draft["id"],)
                ).fetchone()
                output.append(_row_to_task(row))
            return output

    def list_tasks(self, include_done: bool = False) -> list[dict[str, Any]]:
        with self._connection() as connection:
            if include_done:
                rows = connection.execute("SELECT * FROM tasks").fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM tasks WHERE status = 'pending'"
                ).fetchall()
        tasks = [_row_to_task(row) for row in rows]
        ordered = sorted(tasks, key=_task_sort_key)
        return (_dependency_order([task for task in ordered if task["status"] == "pending"])
                + [task for task in ordered if task["status"] == "done"])

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        identifier = _identifier(task_id, "id")
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (identifier,)).fetchone()
        return _row_to_task(row) if row is not None else None

    def update_task(self, task_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        identifier = _identifier(task_id, "id")
        if not isinstance(changes, dict):
            raise TaskValidationError("changes 必须是对象")
        allowed = {
            "title",
            "description",
            "priority",
            "due_at",
            "estimated_minutes",
            "reminder_times",
            "reminder_repeat_rules",
            "repeat_rule",
            "category",
            "source",
            "reasoning",
            "confidence",
            "questions",
            "dependencies",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise TaskValidationError("不可更新字段: " + ", ".join(sorted(unknown)))
        if ("reminder_repeat_rules" in changes or "repeat_rule" in changes) and (
            "reminder_times" not in changes
        ):
            raise TaskValidationError("修改重复规则时必须同时提供 reminder_times")
        if not changes:
            current = self.get_task(identifier)
            if current is None:
                raise TaskNotFoundError(f"找不到事项 {identifier}")
            return current

        with self._transaction() as connection:
            current_row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (identifier,)
            ).fetchone()
            if current_row is None:
                raise TaskNotFoundError(f"找不到事项 {identifier}")
            current = _row_to_task(current_row)
            merged = dict(current)
            merged.update(changes)
            merged["id"] = identifier
            merged["status"] = "pending"
            if "reminder_repeat_rules" not in changes and "repeat_rule" not in changes:
                merged.pop("_reminder_rules", None)
            normalized = _normalize_draft(
                merged,
                _utc_now(),
                allow_existing_times="reminder_times" not in changes,
            )

            graph = self._task_dependencies(connection)
            graph[identifier] = normalized["dependencies"]
            self._ensure_dependencies(graph, [])

            updated_at = _iso_utc(_utc_now())
            connection.execute(
                """UPDATE tasks SET title = ?, description = ?, priority = ?, updated_at = ?,
                    due_at = ?, estimated_minutes = ?, reminder_times = ?, category = ?,
                    source = ?, reasoning = ?, confidence = ?, questions = ?, dependencies = ?
                   WHERE id = ?""",
                (
                    normalized["title"],
                    normalized["description"],
                    normalized["priority"],
                    updated_at,
                    normalized["due_at"],
                    normalized["estimated_minutes"],
                    json.dumps(normalized["reminder_times"], ensure_ascii=False),
                    normalized["category"],
                    normalized["source"],
                    normalized["reasoning"],
                    normalized["confidence"],
                    json.dumps(normalized["questions"], ensure_ascii=False),
                    json.dumps(normalized["dependencies"], ensure_ascii=False),
                    identifier,
                ),
            )
            if "reminder_times" in changes:
                connection.execute(
                    "UPDATE reminders SET status = 'dismissed', updated_at = ? "
                    "WHERE task_id = ? AND status IN ('pending', 'firing')",
                    (updated_at, identifier),
                )
                for reminder_time, repeat_rule in zip(
                    normalized["reminder_times"], normalized["_reminder_rules"]
                ):
                    self._insert_reminder(connection, identifier, reminder_time, repeat_rule)
            self._audit_conn(
                connection,
                "task.update",
                identifier,
                "updated",
                "fields=" + ",".join(sorted(changes)),
            )
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (identifier,)).fetchone()
            return _row_to_task(row)

    def complete_task(self, task_id: str) -> dict[str, Any]:
        identifier = _identifier(task_id, "id")
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (identifier,)).fetchone()
            if row is None:
                raise TaskNotFoundError(f"找不到事项 {identifier}")
            if row["status"] != "done":
                completed_at = _iso_utc(_utc_now())
                connection.execute(
                    "UPDATE tasks SET status = 'done', completed_at = ?, updated_at = ? "
                    "WHERE id = ?",
                    (completed_at, completed_at, identifier),
                )
                self._audit_conn(connection, "task.complete", identifier, "completed")
            completed = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (identifier,)
            ).fetchone()
            return _row_to_task(completed)

    def reopen_task(self, task_id: str) -> dict[str, Any]:
        identifier = _identifier(task_id, "id")
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (identifier,)).fetchone()
            if row is None:
                raise TaskNotFoundError(f"找不到事项 {identifier}")
            if row["status"] == "done":
                current_time = _utc_now()
                now = _iso_utc(current_time)
                expired = connection.execute(
                    "SELECT * FROM reminders WHERE task_id = ? "
                    "AND status IN ('pending', 'firing') AND trigger_at <= ?",
                    (identifier, now),
                ).fetchall()
                connection.execute(
                    "UPDATE tasks SET status = 'pending', completed_at = NULL, updated_at = ? WHERE id = ?",
                    (now, identifier),
                )
                connection.execute(
                    "UPDATE reminders SET status = 'dismissed', updated_at = ? "
                    "WHERE task_id = ? AND status IN ('pending', 'firing') AND trigger_at <= ?",
                    (now, identifier, now),
                )
                for reminder in expired:
                    if reminder["repeat_rule"] != "none":
                        self._queue_next_occurrence(connection, reminder, current_time)
                self._audit_conn(connection, "task.reopen", identifier, "reopened")
            return _row_to_task(connection.execute("SELECT * FROM tasks WHERE id = ?", (identifier,)).fetchone())

    def delete_task(self, task_id: str) -> bool:
        identifier = _identifier(task_id, "id")
        with self._transaction() as connection:
            if connection.execute("SELECT id FROM tasks WHERE id = ?", (identifier,)).fetchone() is None:
                return False
            now = _iso_utc(_utc_now())
            for row in connection.execute("SELECT id, dependencies FROM tasks WHERE id != ?", (identifier,)).fetchall():
                dependencies = json.loads(row["dependencies"])
                if identifier in dependencies:
                    connection.execute(
                        "UPDATE tasks SET dependencies = ?, updated_at = ? WHERE id = ?",
                        (json.dumps([value for value in dependencies if value != identifier]), now, row["id"]),
                    )
            connection.execute("DELETE FROM tasks WHERE id = ?", (identifier,))
            self._audit_conn(connection, "task.delete", identifier, "deleted")
            return True

    def create_reminder(
        self,
        task_id: str,
        trigger_at: datetime | str,
        repeat_rule: str = "none",
    ) -> dict[str, Any]:
        identifier = _identifier(task_id, "id")
        now = _utc_now()
        trigger = _parse_datetime(trigger_at, "trigger_at")
        if trigger is None or trigger <= now:
            raise TaskValidationError("新的提醒时间必须晚于当前时间")
        trigger_iso = _iso_utc(trigger)
        rule = _normalize_repeat_rule(repeat_rule)
        with self._transaction() as connection:
            task = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (identifier,)
            ).fetchone()
            if task is None:
                raise TaskNotFoundError(f"找不到事项 {identifier}")
            if task["status"] != "pending":
                raise TaskValidationError("已完成事项不能添加提醒")
            existing = connection.execute(
                """SELECT reminders.*, tasks.title AS title FROM reminders
                   JOIN tasks ON tasks.id = reminders.task_id
                   WHERE reminders.task_id = ? AND reminders.trigger_at = ?
                     AND reminders.status IN ('pending', 'firing')
                   ORDER BY reminders.created_at, reminders.id LIMIT 1""",
                (identifier, trigger_iso),
            ).fetchone()
            if existing is not None:
                if existing["repeat_rule"] != rule:
                    raise TaskConflictError("相同提醒时间已有不同的重复规则")
                return _row_to_reminder(existing)
            reminder_id = self._insert_reminder(connection, identifier, trigger_iso, rule)
            times = _json_load(task["reminder_times"], [])
            if trigger_iso not in times:
                if len(times) >= MAX_REMINDERS_PER_TASK:
                    raise TaskValidationError(
                        f"每件事项最多只能保存 {MAX_REMINDERS_PER_TASK} 个提醒时间"
                    )
                times.append(trigger_iso)
                times.sort()
            connection.execute(
                "UPDATE tasks SET reminder_times = ?, updated_at = ? WHERE id = ?",
                (json.dumps(times, ensure_ascii=False), _iso_utc(now), identifier),
            )
            self._audit_conn(connection, "reminder.create", reminder_id, "created")
            reminder = self._fetch_reminder(connection, reminder_id)
            return _row_to_reminder(reminder)

    def due_reminders(self, now: datetime | str | None = None) -> list[dict[str, Any]]:
        current = _utc_now() if now is None else _parse_datetime(now, "now")
        if current is None:
            current = _utc_now()
        current_iso = _iso_utc(current)
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT reminders.*, tasks.title AS title
                   FROM reminders JOIN tasks ON tasks.id = reminders.task_id
                   WHERE tasks.status = 'pending'
                     AND (reminders.status = 'firing'
                          OR (reminders.status = 'pending' AND reminders.trigger_at <= ?))
                   ORDER BY reminders.trigger_at, reminders.id""",
                (current_iso,),
            ).fetchall()
        return [_row_to_reminder(row) for row in rows]

    def mark_reminder_firing(self, reminder_id: str) -> dict[str, Any]:
        identifier = _identifier(reminder_id, "id")
        now = _utc_now()
        with self._transaction() as connection:
            row = self._fetch_reminder(connection, identifier)
            if row is None:
                raise TaskNotFoundError(f"找不到提醒 {identifier}")
            if row["status"] in ("done", "dismissed"):
                return _row_to_reminder(row)
            task = connection.execute(
                "SELECT status FROM tasks WHERE id = ?", (row["task_id"],)
            ).fetchone()
            if task is None or task["status"] != "pending":
                connection.execute(
                    "UPDATE reminders SET status = 'dismissed', updated_at = ? WHERE id = ?",
                    (_iso_utc(now), identifier),
                )
            elif row["status"] == "pending":
                if row["trigger_at"] > _iso_utc(now):
                    raise TaskValidationError("提醒尚未到时间")
                connection.execute(
                    "UPDATE reminders SET status = 'firing', updated_at = ? WHERE id = ?",
                    (_iso_utc(now), identifier),
                )
                self._audit_conn(connection, "reminder.fire", identifier, "firing")
            updated = self._fetch_reminder(connection, identifier)
            return _row_to_reminder(updated)

    def snooze_reminder(self, reminder_id: str, minutes: int) -> dict[str, Any]:
        identifier = _identifier(reminder_id, "id")
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            raise TaskValidationError("minutes 必须是整数")
        if not 1 <= minutes <= MAX_SNOOZE_MINUTES:
            raise TaskValidationError(f"minutes 必须是 1 到 {MAX_SNOOZE_MINUTES} 之间")
        now = _utc_now()
        with self._transaction() as connection:
            row = self._fetch_reminder(connection, identifier)
            if row is None:
                raise TaskNotFoundError(f"找不到提醒 {identifier}")
            if row["status"] in ("done", "dismissed"):
                return _row_to_reminder(row)
            task = connection.execute(
                "SELECT status FROM tasks WHERE id = ?", (row["task_id"],)
            ).fetchone()
            updated_at = _iso_utc(now)
            if task is None or task["status"] != "pending":
                connection.execute(
                    "UPDATE reminders SET status = 'dismissed', updated_at = ? WHERE id = ?",
                    (updated_at, identifier),
                )
            else:
                trigger_at = _iso_utc(now + timedelta(minutes=minutes))
                connection.execute(
                    "UPDATE reminders SET status = 'pending', trigger_at = ?, updated_at = ? "
                    "WHERE id = ?",
                    (trigger_at, updated_at, identifier),
                )
                self._audit_conn(
                    connection,
                    "reminder.snooze",
                    identifier,
                    "snoozed",
                    f"minutes={minutes}",
                )
            updated = self._fetch_reminder(connection, identifier)
            return _row_to_reminder(updated)

    @staticmethod
    def _next_occurrence(scheduled_at: str, repeat_rule: str, now: datetime) -> tuple[str, int]:
        interval = timedelta(days=1 if repeat_rule == "daily" else 7)
        scheduled = _parse_datetime(scheduled_at, "scheduled_at")
        if scheduled is None:
            raise TaskStoreError("提醒缺少有效的计划时间")
        next_time = scheduled + interval
        skipped = 0
        if next_time <= now:
            skipped = int((now - next_time) // interval) + 1
            next_time += interval * skipped
        return _iso_utc(next_time), skipped + 1

    def dismiss_reminder(self, reminder_id: str) -> dict[str, Any]:
        identifier = _identifier(reminder_id, "id")
        now = _utc_now()
        with self._transaction() as connection:
            row = self._fetch_reminder(connection, identifier)
            if row is None:
                raise TaskNotFoundError(f"找不到提醒 {identifier}")
            if row["status"] in ("done", "dismissed"):
                return _row_to_reminder(row)
            task = connection.execute(
                "SELECT status FROM tasks WHERE id = ?", (row["task_id"],)
            ).fetchone()
            new_status = "done" if task is not None and task["status"] == "pending" else "dismissed"
            updated_at = _iso_utc(now)
            connection.execute(
                "UPDATE reminders SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, updated_at, identifier),
            )
            if new_status == "done" and row["repeat_rule"] != "none":
                self._queue_next_occurrence(connection, row, now)
            self._audit_conn(connection, "reminder.dismiss", identifier, new_status)
            updated = self._fetch_reminder(connection, identifier)
            return _row_to_reminder(updated)

    def _queue_next_occurrence(self, connection, row, now):
        next_at, increment = self._next_occurrence(row["scheduled_at"], row["repeat_rule"], now)
        next_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{row['series_id']}:{next_at}").hex
        updated_at = _iso_utc(now)
        connection.execute(
            """INSERT OR IGNORE INTO reminders(
                id, task_id, trigger_at, status, repeat_rule, scheduled_at,
                series_id, series_index, is_initial, created_at, updated_at
            ) VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, 0, ?, ?)""",
            (next_id, row["task_id"], next_at, row["repeat_rule"], next_at,
             row["series_id"], row["series_index"] + increment, updated_at, updated_at),
        )

    def snapshot(self) -> dict[str, Any]:
        now = _utc_now()
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM tasks").fetchall()
            local_today = datetime.now().astimezone().date()
            local_start = datetime.combine(local_today, time.min).astimezone(timezone.utc)
            local_end = datetime.combine(
                local_today + timedelta(days=1), time.min
            ).astimezone(timezone.utc)
            completed_today = connection.execute(
                """SELECT COUNT(*) AS total FROM tasks
                   WHERE status = 'done' AND completed_at >= ? AND completed_at < ?""",
                (_iso_utc(local_start), _iso_utc(local_end)),
            ).fetchone()["total"]
            reminder_rows = connection.execute(
                """SELECT reminders.*, tasks.title AS title
                   FROM reminders JOIN tasks ON tasks.id = reminders.task_id
                   WHERE tasks.status = 'pending'
                     AND reminders.status IN ('pending', 'firing')
                   ORDER BY CASE reminders.status WHEN 'firing' THEN 0 ELSE 1 END,
                            reminders.trigger_at, reminders.id"""
            ).fetchall()

        reminders_by_task: dict[str, list[str]] = {}
        for reminder in reminder_rows:
            reminders_by_task.setdefault(reminder["task_id"], []).append(
                reminder["trigger_at"]
            )
        def relevance(task):
            reminder_times = reminders_by_task.get(task["id"]) or (
                task["reminder_times"] if task["status"] == "done" else [])
            times = [value for value in [task["due_at"], *reminder_times] if value]
            nearest = min(times) if times else None
            today = nearest is not None and _parse_datetime(nearest, "time").astimezone().date() <= local_today
            return (not today, task["priority"], nearest or "9999", task["created_at"], task["id"])
        ordered = sorted((_row_to_task(row) for row in rows), key=relevance)
        tasks = (_dependency_order([task for task in ordered if task["status"] == "pending"])
                 + [task for task in ordered if task["status"] == "done"])
        snapshot_tasks = [
            {
                "id": task["id"],
                "title": task["title"],
                "time_text": _time_text(
                    task["due_at"],
                    (reminders_by_task.get(task["id"]) or [None])[0],
                    now,
                ),
                "due_at": task["due_at"],
                "reminder_at": (reminders_by_task.get(task["id"]) or [None])[0],
                "status": task["status"],
            }
            for task in tasks[:20]
        ]
        next_reminder = reminder_rows[0] if reminder_rows else None
        return {
            "tasks": snapshot_tasks,
            "total_count": len(tasks),
            "completed_today": completed_today,
            "next_reminder": next_reminder["trigger_at"] if next_reminder else "",
            "reminder_id": next_reminder["id"] if next_reminder else "",
        }
