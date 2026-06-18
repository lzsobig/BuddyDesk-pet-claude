"""
Drag Drop Util — 文件拖入的统一处理 + 敏感词过滤（P1-5）。

P1-5 文件敏感词黑名单：
- 关键词命中（薪资/合同/密码/.env/credentials 等）整条跳过
- 用户主动拖入触发：跳过时发信号让调用方显示"⚠️ 跳过敏感文件 X"通知
- 提供"我确认要发送"按钮绕过（settings_panel 可选）

注意：这是**纵深防御的一层**。真正的安全来自：
1. AI 本身不应在未确认时执行 shell
2. ConfirmDialog 二次确认
3. shell 命令白名单
黑名单只是减少"用户不小心把 .env 拖进对话被 AI 读到"的概率。
"""
from __future__ import annotations

import os
import re
from typing import Iterable


# 关键词黑名单（中文 + 英文 + 扩展名）
SENSITIVE_KEYWORDS: list[str] = [
    # 中文
    "薪资", "工资", "薪酬", "合同", "密码", "账号", "银行", "信用卡", "身份证",
    "社保", "公积金", "个税", "私钥", "令牌",
    # 英文
    "password", "passwd", "secret", "credential", "api_key", "apikey",
    "private_key", "access_token", "session_token", "bearer",
    # 扩展名 / 文件名
    ".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    ".key", ".pem", ".pfx", ".p12",  # 证书/私钥
    "credentials", ".htpasswd", ".pgpass",
]

# 编译成正则（不区分大小写 + 关键词边界）
_KEYWORD_PATTERNS: list[re.Pattern] = [
    re.compile(re.escape(kw), re.IGNORECASE) for kw in SENSITIVE_KEYWORDS
]


def is_sensitive_path(path: str) -> bool:
    """判断单个文件路径是否命中敏感词黑名单。

    Args:
        path: 绝对或相对路径
    Returns:
        True = 应跳过
    """
    if not path:
        return False
    # 拆文件名 + 父目录 + 完整路径，三处都查
    name = os.path.basename(path).lower()
    parent = os.path.basename(os.path.dirname(path)).lower()
    full = path.lower()

    # 先看文件名后缀
    for kw in SENSITIVE_KEYWORDS:
        kw_low = kw.lower()
        # 扩展名前缀匹配（.env / id_rsa）
        if kw_low.startswith("."):
            if name.endswith(kw_low) or f".{kw_low[1:]}" in name:
                return True
            continue
        # 普通关键词：在文件名或父目录命中
        if kw_low in name or kw_low in parent:
            return True
        # 完整路径命中（兜底）
        if kw_low in full:
            return True
    return False


def filter_sensitive_filepaths(paths: Iterable[str]) -> tuple[list[str], list[str]]:
    """过滤一组文件路径，返回 (通过的, 被过滤的)。

    Args:
        paths: 文件路径列表
    Returns:
        (kept, filtered) 元组
    """
    kept: list[str] = []
    filtered: list[str] = []
    for p in paths:
        if is_sensitive_path(p):
            filtered.append(p)
        else:
            kept.append(p)
    return kept, filtered
