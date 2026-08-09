"""
BuddyDesk - Configuration

Supports deep merge for user overrides, standardized config paths,
and persistence for conversations and job history.
"""
import base64
import copy
import json
import os
import stat
import sys
from typing import Any

# ============================================================
# App Info
# ============================================================
APP_NAME = "BuddyDesk"
APP_VERSION = "0.2.1"
APP_AUTHOR = "BuddyDesk"

# ============================================================
# Paths — standardized under ~/.buddydesk/
# ============================================================
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".buddydesk")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CONVERSATIONS_PATH = os.path.join(CONFIG_DIR, "conversations.json")
ARCHIVE_PATH = os.path.join(CONFIG_DIR, "archive.json")
JOBS_PATH = os.path.join(CONFIG_DIR, "jobs.json")
EVENT_LOG_FILE = os.path.join(CONFIG_DIR, "events.log")

if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(_BASE, "_internal", "assets") if getattr(sys, 'frozen', False) else os.path.join(_BASE, "assets")
PET_FRAMES_DIR = os.path.join(ASSETS_DIR, "pet_frames")

# ============================================================
# OpenAI-compatible API Presets (single source of truth)
# ============================================================
API_PRESETS: dict[str, dict[str, str]] = {
    "OpenAI": {"base": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "DeepSeek": {"base": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "NVIDIA NIM": {"base": "https://integrate.api.nvidia.com/v1", "model": "meta/llama-3.1-8b-instruct"},
    "Ollama (本地)": {"base": "http://localhost:11434/v1", "model": "llama3"},
    "硅基流动": {"base": "https://api.siliconflow.cn/v1", "model": "Qwen/Qwen2.5-7B-Instruct"},
    "Moonshot": {"base": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "自定义": {"base": "", "model": ""},
}

# ============================================================
# Dynamic Island
# ============================================================
ISLAND_WIDTH_COLLAPSED = 200
ISLAND_HEIGHT_COLLAPSED = 32
ISLAND_WIDTH_EXPANDED = 360
ISLAND_HEIGHT_EXPANDED = 120
ISLAND_BORDER_RADIUS = 16
ISLAND_ANIMATION_SPEED = 8
ISLAND_HOVER_DELAY = 300
ISLAND_ANIM_DURATION = 200  # spring animation duration (ms)

# ============================================================
# Pixel Pet
# ============================================================
PET_SIZE = 48
PET_DISPLAY_SCALE = 1.5
PET_MOVE_SPEED = 2
PET_IDLE_INTERVAL = 3000
PET_WALK_DURATION = 5000
PET_EAT_DURATION = 2000
PET_HAPPY_DURATION = 2000
PET_ANIMATION_FPS = 8

# ============================================================
# Font Scale (P1-2)
# ============================================================
# 5 档字号缩放，仅作用于 Markdown 渲染的字号。
# 索引 0-4，DEFAULT_USER_CONFIG["font_scale_idx"] 持久化。
FONT_SCALE_LEVELS = [0.85, 1.0, 1.15, 1.3, 1.5]
FONT_SCALE_DEFAULT_IDX = 1  # 100%

# ============================================================
# AI Chat Window
# ============================================================
CHAT_WIDTH = 480
CHAT_HEIGHT = 640

# ============================================================
# AI Backend
# ============================================================
BACKEND_CLAUDE = "claude_code"
BACKEND_OPENAI = "openai_api"

DEFAULT_BACKEND = BACKEND_OPENAI

DEFAULT_API_BASE = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_API_KEY = ""

CLAUDE_CLI_PATH = "claude"

# ============================================================
# System Tray & Hotkeys
# ============================================================
TRAY_TOOLTIP = f"{APP_NAME} v{APP_VERSION}"
HOTKEY_TOGGLE_CHAT = "ctrl+shift+h"
MAX_EVENT_HISTORY = 100

# ============================================================
# Default config structure (deep-merged with user overrides)
# ============================================================
DEFAULT_USER_CONFIG: dict[str, Any] = {
    "backend": DEFAULT_BACKEND,
    "openai_api_key": DEFAULT_API_KEY,
    "openai_api_base": DEFAULT_API_BASE,
    "openai_model": DEFAULT_MODEL,
    "claude_cli_path": CLAUDE_CLI_PATH,
    "pet_name": "小橘",
    "island_enabled": True,
    "pet_enabled": True,
    "chat_enabled": True,
    # 5 事件音独立开关
    "sound_enabled": True,
    "sound_voice_start_enabled": True,
    "sound_message_received_enabled": True,
    "sound_file_dropped_enabled": True,
    "sound_message_sent_enabled": True,
    "sound_error_enabled": True,
    # 5 事件音自定义路径（空字符串 = 用内置）
    "sound_voice_start_custom_path": "",
    "sound_message_received_custom_path": "",
    "sound_file_dropped_custom_path": "",
    "sound_message_sent_custom_path": "",
    "sound_error_custom_path": "",
    # 字号缩放档位（0-4，对应 FONT_SCALE_LEVELS 索引）
    "font_scale_idx": 1,
    # 杂项开关
    "clipboard_monitor": False,
    "autostart": False,
}


# ============================================================
# Secret obfuscation helpers (minimal; not encryption)
# ============================================================
_SECRET_PREFIX = "b64:"  # Marker to detect already-encoded values


def _encode_secret(val: str) -> str:
    """Obfuscate a secret value with base64 encoding.

    This is NOT encryption -- it prevents casual visual inspection of the
    config file on disk.  Proper secret storage should use the OS keyring.
    """
    if not val or val.startswith(_SECRET_PREFIX):
        return val  # already encoded or empty
    return _SECRET_PREFIX + base64.b64encode(val.encode("utf-8")).decode("ascii")


def _decode_secret(val: str) -> str:
    """Decode a value previously encoded with _encode_secret."""
    if not val or not val.startswith(_SECRET_PREFIX):
        return val  # not encoded or empty
    return base64.b64decode(val[len(_SECRET_PREFIX):]).decode("utf-8")


# Keys whose values are secrets and should be obfuscated in the config file.
_SECRET_KEYS = {"openai_api_key", "anthropic_api_key"}


def _restrict_file_permissions(path: str) -> None:
    """Restrict config file to owner read/write only (chmod 600).

    On Windows, Python's os.chmod does not support fine-grained ACLs.
    We attempt the chmod anyway (no-op on Windows) and leave a note that
    Windows users should verify NTFS permissions manually if running in
    a multi-user environment.
    """
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except (OSError, AttributeError):
        # Windows os.chmod may be a no-op; the OS-level permissions
        # on %USERPROFILE% typically already restrict access to the
        # owning user.
        pass


def _ensure_config_dir() -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge override into base without mutating base."""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_user_config() -> dict[str, Any]:
    """Load user configuration with deep merge against defaults.

    Malformed files and malformed encoded secrets are treated as a reset to
    defaults so a broken config can never prevent the launcher from opening.
    """
    _ensure_config_dir()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if not isinstance(saved, dict):
                raise ValueError("config root must be an object")
            for k in list(saved.keys()):
                if k in _SECRET_KEYS and isinstance(saved[k], str):
                    saved[k] = _decode_secret(saved[k])
            return _deep_merge(DEFAULT_USER_CONFIG, saved)
        except (json.JSONDecodeError, UnicodeError, ValueError, TypeError, IOError):
            return copy.deepcopy(DEFAULT_USER_CONFIG)
    return copy.deepcopy(DEFAULT_USER_CONFIG)


def save_user_config(config: dict[str, Any]) -> None:
    """Save user configuration to file.

    Secret values (API keys) are base64-obfuscated before writing so they
    are not stored in plaintext.  The file permissions are restricted to
    owner read/write (0o600) where the OS supports it.
    """
    _ensure_config_dir()
    # Obfuscate secret values before persisting
    to_save = {}
    for k, v in config.items():
        if k in _SECRET_KEYS and isinstance(v, str) and v:
            to_save[k] = _encode_secret(v)
        else:
            to_save[k] = v

    # Write beside the destination and replace atomically. A crash or power
    # loss must not leave config.json half-written or empty.
    temp_path = CONFIG_PATH + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, CONFIG_PATH)
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
    _restrict_file_permissions(CONFIG_PATH)


def load_conversations() -> list[dict[str, Any]]:
    _ensure_config_dir()
    if os.path.exists(CONVERSATIONS_PATH):
        try:
            with open(CONVERSATIONS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_conversations(convs: list[dict[str, Any]]) -> None:
    _ensure_config_dir()
    with open(CONVERSATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(convs, f, indent=2, ensure_ascii=False)


def load_archive() -> list[dict[str, Any]]:
    _ensure_config_dir()
    if os.path.exists(ARCHIVE_PATH):
        try:
            with open(ARCHIVE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_archive(archive: list[dict[str, Any]]) -> None:
    _ensure_config_dir()
    with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)


def load_jobs() -> list[dict[str, Any]]:
    _ensure_config_dir()
    if os.path.exists(JOBS_PATH):
        try:
            with open(JOBS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_jobs(jobs: list[dict[str, Any]]) -> None:
    _ensure_config_dir()
    with open(JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)
