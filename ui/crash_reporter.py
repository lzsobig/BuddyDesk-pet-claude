"""
Crash Reporter — 扫描本地崩溃日志 + 一键复制 + 跳 GitHub Issue 新建页。

设计：零后端、零隐私顾虑。
- 扫描本地崩溃目录（PyInstaller Crashpad / Qt 崩溃堆栈 / 自定义 log）
- 找到新崩溃 → 在设置面板"关于"页给出"发现 N 个新崩溃"通知
- 用户点"复制并上报" → 把 stacktrace 复制到剪贴板 + 打开浏览器到 GitHub Issue 新建页
- 用户手动粘贴 + 填写 Issue —— HermesPet 不会自动上传任何东西

支持的崩溃日志来源（按优先级）：
1. PyInstaller Crashpad（%LOCALAPPDATA%\\<AppName>\\Crashpad\\reports\\）
2. BuddyDesk 自定义 log（%USERPROFILE%\\.buddydesk\\crash.log）
3. PyInstaller --windowed 模式的 stderr 镜像
"""
from __future__ import annotations

import os
import sys
import json
import glob
import logging
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# GitHub 仓库（用于 Issue 链接）
GITHUB_REPO = "lzsobig/BuddyDesk-pet-claude"
GITHUB_NEW_ISSUE_URL = f"https://github.com/{GITHUB_REPO}/issues/new"

# 已读崩溃记录文件（避免重复提示同一崩溃）
_READ_STATE_PATH = os.path.join(
    os.path.expanduser("~"), ".buddydesk", "crash_reporter_read.json"
)


def _ensure_dir(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _load_read_state() -> set:
    if not os.path.isfile(_READ_STATE_PATH):
        return set()
    try:
        with open(_READ_STATE_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f).get("read", []))
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        logger.debug("Failed to load read state: %s", exc)
        return set()


def _save_read_state(read: set) -> None:
    _ensure_dir(_READ_STATE_PATH)
    try:
        with open(_READ_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"read": sorted(read)}, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.debug("Failed to save read state: %s", exc)


# ── 崩溃日志扫描 ──────────────────────────────────────────────────
def _candidate_dirs() -> list[str]:
    """返回可能包含崩溃日志的目录列表。"""
    candidates: list[str] = []
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            # PyInstaller Crashpad 默认位置
            candidates.append(os.path.join(local, "BuddyDesk", "Crashpad", "reports"))
            candidates.append(os.path.join(local, "Crashpad", "reports"))
            # PyInstaller 的 --onedir 模式
            candidates.append(os.path.join(local, "BuddyDesk"))
    # 自定义崩溃日志
    candidates.append(os.path.join(os.path.expanduser("~"), ".buddydesk"))
    return [c for c in candidates if os.path.isdir(c)]


def _read_crash_files() -> list[dict]:
    """扫描所有候选目录，返回崩溃文件列表 [{path, mtime, size, preview}]。"""
    found: list[dict] = []
    for d in _candidate_dirs():
        # 1) .dmp（Crashpad minidump）—— 提示用户
        for p in glob.glob(os.path.join(d, "*.dmp")):
            try:
                st = os.stat(p)
                found.append({
                    "path": p,
                    "mtime": st.st_mtime,
                    "size": st.st_size,
                    "kind": "minidump",
                    "preview": f"Minidump 文件（{st.st_size//1024} KB）",
                })
            except OSError:
                pass
        # 2) .log / .txt 包含 stacktrace
        for ext in ("*.log", "*.txt", "*.crashlog"):
            for p in glob.glob(os.path.join(d, ext)):
                try:
                    st = os.stat(p)
                    # 太大（>5MB）跳过
                    if st.st_size > 5 * 1024 * 1024:
                        continue
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    # 只挑看起来像崩溃的
                    if any(kw in content.lower() for kw in (
                        "traceback", "exception", "error", "崩溃", "stack",
                        "segmentation fault", "fatal",
                    )):
                        found.append({
                            "path": p,
                            "mtime": st.st_mtime,
                            "size": st.st_size,
                            "kind": "text",
                            "preview": content[:500],
                        })
                except OSError:
                    pass
    # 按 mtime 倒序（最新在前）
    found.sort(key=lambda x: x["mtime"], reverse=True)
    return found


def get_unread_crashes() -> list[dict]:
    """返回用户尚未标记为已读的崩溃列表。"""
    read = _load_read_state()
    all_crashes = _read_crash_files()
    return [c for c in all_crashes if c["path"] not in read]


def get_all_crashes() -> list[dict]:
    """返回所有崩溃（含已读），按时间倒序。"""
    return _read_crash_files()


def mark_all_read() -> None:
    """把当前所有崩溃都标记为已读。"""
    read = _load_read_state()
    for c in _read_crash_files():
        read.add(c["path"])
    _save_read_state(read)


# ── 复制到剪贴板 + 打开 Issue 页面 ────────────────────────────────
def build_issue_body(crashes: list[dict], app_version: str) -> str:
    """构造 Issue body 文本（含 stacktrace 摘要）。"""
    parts: list[str] = []
    parts.append("## 崩溃摘要")
    parts.append(f"- 应用版本: BuddyDesk v{app_version}")
    parts.append(f"- 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    parts.append(f"- 崩溃文件数: {len(crashes)}")
    parts.append("")
    parts.append("## 崩溃详情")
    for i, c in enumerate(crashes[:5], 1):  # 最多 5 个
        parts.append(f"### {i}. {os.path.basename(c['path'])}")
        parts.append(f"- 路径: `{c['path']}`")
        parts.append(f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(c['mtime']))}")
        parts.append(f"- 类型: {c['kind']} ({c['size']} bytes)")
        if c["kind"] == "text":
            parts.append("```")
            parts.append(c["preview"][:1500])
            parts.append("```")
        else:
            parts.append("(minidump 文件，请附在 Issue)")
        parts.append("")
    parts.append("## 复现步骤")
    parts.append("（请描述你怎么遇到这个崩溃的）")
    parts.append("")
    parts.append("## 环境")
    parts.append("- OS: Windows")
    parts.append(f"- BuddyDesk 版本: v{app_version}")
    return "\n".join(parts)


def copy_to_clipboard(text: str) -> bool:
    """把崩溃信息复制到剪贴板。返回是否成功。"""
    try:
        if sys.platform == "win32":
            import subprocess
            # 用 clip.exe（Windows 自带）
            p = subprocess.Popen(["clip"], stdin=subprocess.PIPE, shell=True)
            p.communicate(text.encode("utf-16le"))
            return p.returncode == 0
        # macOS / Linux fallback
        import subprocess
        if sys.platform == "darwin":
            cmd = ["pbcopy"]
        else:
            cmd = ["xclip", "-selection", "clipboard"]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))
        return p.returncode == 0
    except Exception:
        return False


def open_issue_url() -> bool:
    """用系统默认浏览器打开 GitHub Issue 新建页。"""
    import webbrowser
    try:
        return webbrowser.open(GITHUB_NEW_ISSUE_URL, new=2)
    except Exception:
        return False
