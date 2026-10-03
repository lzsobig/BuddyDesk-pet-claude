from __future__ import annotations

import ast
import math
import operator
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable


class PermissionRequired(ValueError):
    pass


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    permission_level: int
    handler: Callable


class ToolRegistry:
    def __init__(self, audit):
        self._tools = {}
        self._audit = audit

    def register(self, definition):
        if definition.name in self._tools:
            raise ValueError("Duplicate tool")
        self._tools[definition.name] = definition

    def definitions(self):
        return [{"name": tool.name, "description": tool.description, "parameters": tool.parameters,
                 "permissionLevel": tool.permission_level} for tool in self._tools.values()]

    def execute(self, name, arguments, *, authorized=False):
        tool = self._tools.get(name)
        if not tool:
            raise ValueError("工具不存在")
        if not isinstance(arguments, dict):
            raise ValueError("工具参数格式无效")
        allowed = tool.parameters.get("properties", {})
        if set(arguments) - set(allowed) or set(tool.parameters.get("required", [])) - set(arguments):
            raise ValueError("工具参数不符合定义")
        types = {"string": str, "object": dict, "array": list, "integer": int}
        for key, value in arguments.items():
            expected = types.get(allowed[key].get("type"))
            if expected and (not isinstance(value, expected) or expected is int and isinstance(value, bool)):
                raise ValueError("工具参数类型不正确")
            if isinstance(value, str) and len(value) > 12000:
                raise ValueError("工具参数过长")
        if tool.permission_level > 0 and not authorized:
            self._audit(name, None, "permission_required")
            raise PermissionRequired("需要确认后才能执行：" + tool.description)
        try:
            result = tool.handler(**arguments)
            self._audit(name, None, "success" if getattr(result, "success", True) else "failed")
            return result
        except Exception:
            self._audit(name, None, "error")
            raise


def calculator(expression):
    tree = ast.parse(expression[:500], mode="eval")
    if len(list(ast.walk(tree))) > 50:
        raise ValueError("计算式过长")
    operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                  ast.Div: operator.truediv, ast.Mod: operator.mod}
    def calculate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = calculate(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in operations:
            value = operations[type(node.op)](calculate(node.left), calculate(node.right))
        else:
            raise ValueError("仅支持数字和加减乘除取余")
        if not math.isfinite(value) or abs(value) > 1e15:
            raise ValueError("计算结果超出范围")
        return value
    return calculate(tree.body)


def create_registry(store, context, command_engine):
    from personal_context import read_document
    registry = ToolRegistry(store.audit)
    def add(name, description, level, properties, required, handler):
        registry.register(ToolDefinition(name, description, {"type": "object", "properties": properties,
            "required": required, "additionalProperties": False}, level, handler))
    string = {"type": "string"}
    add("get_current_time", "读取当前时间", 0, {}, [], lambda: datetime.now().astimezone().isoformat())
    add("calculator", "计算", 0, {"expression": string}, ["expression"], calculator)
    add("list_tasks", "读取事项", 0, {}, [], store.list_tasks)
    add("search_knowledge", "搜索个人资料", 0, {"query": string}, ["query"], context.search)
    add("read_memories", "读取用户明确保存的记忆", 0, {}, [], context.memories)
    add("create_task", "添加已确认事项", 1, {"draft": {"type": "object"}}, ["draft"], lambda draft: store.confirm_drafts([draft]))
    add("update_task", "修改事项", 1, {"task_id": string, "changes": {"type": "object"}}, ["task_id", "changes"], store.update_task)
    add("complete_task", "完成事项", 1, {"task_id": string}, ["task_id"], store.complete_task)
    def reminder(task_id, trigger_at):
        task = store.get_task(task_id)
        if task is None:
            raise ValueError("事项不存在")
        return store.create_reminder(task_id, trigger_at)
    add("create_reminder", "添加提醒", 1, {"task_id": string, "trigger_at": string}, ["task_id", "trigger_at"], reminder)
    add("read_file", "读取指定文件", 2, {"filename": string}, ["filename"], read_document)
    add("open_app", "打开应用", 2, {"app_name": string}, ["app_name"], command_engine.open_app)
    add("open_file", "打开指定文件", 2, {"filename": string}, ["filename"], lambda filename: os.startfile(filename))
    add("run_command", "执行本地命令", 3, {"command": string}, ["command"], lambda command: command_engine.execute_command(command, auto_confirm=True))
    add("run_shell", "执行 Shell 命令", 3, {"command": string}, ["command"], lambda command: command_engine.execute_shell(command, auto_confirm=True))
    add("run_claude", "允许 Claude Code 执行本地操作", 3, {"instruction": string}, ["instruction"], command_engine.execute_claude_code)
    return registry
