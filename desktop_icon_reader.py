"""
Desktop Icon Reader — 读取 Windows 桌面图标的简化实现（P3-5）。

注意：Windows 没有 macOS `osascript` 这种直接读桌面图标 API。
完整实现需要 IShellFolder COM 接口（需 pywin32 或 ctypes + COM 绑定）。
本模块用**简化方案**：列出桌面目录下的 .lnk 文件 + 文件名，
作为"嗅"的输入。HermesPet 的实现可以后续用 COM 重做。

P3-5 嗅桌面图标：
1. 用户拖桌宠到桌面某个 .lnk 图标上
2. 桌宠停在图标位置，"嗅一下"（短暂 idle 动画）
3. 把图标文件名发给 AI，AI 给 ≤10 字短评
4. 短评在灵动岛显示
"""
from __future__ import annotations

import os
import subprocess
from typing import Optional


def get_desktop_path() -> str:
    """获取 Windows 桌面路径。"""
    try:
        from PySide6.QtCore import QStandardPaths
        return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    except Exception:
        return os.path.join(os.path.expanduser("~"), "Desktop")


def get_desktop_shortcuts() -> list[dict]:
    """列出桌面所有 .lnk 快捷方式。

    Returns:
        [{name, path, target}] 列表
    """
    desktop = get_desktop_path()
    if not os.path.isdir(desktop):
        return []
    out: list[dict] = []
    for entry in os.listdir(desktop):
        if not entry.lower().endswith(".lnk"):
            continue
        full_path = os.path.join(desktop, entry)
        if not os.path.isfile(full_path):
            continue
        # 解析 .lnk 目标（如果有 pywin32 / 我们的 command_engine 工具）
        target = _resolve_lnk_target(full_path)
        out.append({
            "name": os.path.splitext(entry)[0],
            "path": full_path,
            "target": target,
        })
    # 按名字排序
    out.sort(key=lambda x: x["name"].lower())
    return out


def _resolve_lnk_target(lnk_path: str) -> str:
    """解析 .lnk 目标。如果失败返回空串。"""
    try:
        # 优先用 command_engine 已有的实现
        from engine.command_engine import _read_lnk_target
        return _read_lnk_target(lnk_path)
    except Exception:
        return ""


def sniff_icon(name: str) -> str:
    """P3-5: 给一个图标名，返回准备发给 AI 的 prompt。

    AI 会基于名字生成 ≤10 字的中文短评。
    """
    return f"请用一句话（≤10 个中文字）评价这个桌面图标的名称：'{name}'。只输出短评，不要解释。"


def get_icon_at_position(x: int, y: int, icons: list[dict]) -> Optional[dict]:
    """根据拖放坐标找最近的图标（粗略按距离）。

    Windows 桌面图标位置需要 IShellFolder 才能精确拿到。
    简化方案：按距离找最近的文件名匹配的图标。
    这里仅返回 None（由 main.py 用其他方式触发）。
    """
    # 简化：不做位置匹配，让用户主动选
    return None
