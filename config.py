"""
BuddyDesk - Configuration

Supports deep merge for user overrides, standardized config paths,
and persistence for conversations and job history.
"""
import copy
import json
import os
from typing import Any

# ============================================================
# App Info
# ============================================================
APP_NAME = "BuddyDesk"
APP_VERSION = "0.2.0"
APP_AUTHOR = "BuddyDesk"

# ============================================================
# Paths — standardized under ~/.buddydesk/
# ============================================================
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".buddydesk")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CONVERSATIONS_PATH = os.path.join(CONFIG_DIR, "conversations.json")
JOBS_PATH = os.path.join(CONFIG_DIR, "jobs.json")
EVENT_LOG_FILE = os.path.join(CONFIG_DIR, "events.log")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
PET_FRAMES_DIR = os.path.join(ASSETS_DIR, "pet_frames")

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
}


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
    """Load user configuration with deep merge against defaults."""
    _ensure_config_dir()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            return _deep_merge(DEFAULT_USER_CONFIG, saved)
        except (json.JSONDecodeError, IOError):
            return copy.deepcopy(DEFAULT_USER_CONFIG)
    return copy.deepcopy(DEFAULT_USER_CONFIG)


def save_user_config(config: dict[str, Any]) -> None:
    """Save user configuration to file."""
    _ensure_config_dir()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def load_conversations() -> list[dict[str, Any]]:
    _ensure_config_dir()
    if os.path.exists(CONVERSATIONS_PATH):
        with open(CONVERSATIONS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_conversations(convs: list[dict[str, Any]]) -> None:
    _ensure_config_dir()
    with open(CONVERSATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(convs, f, indent=2, ensure_ascii=False)


def load_jobs() -> list[dict[str, Any]]:
    _ensure_config_dir()
    if os.path.exists(JOBS_PATH):
        with open(JOBS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_jobs(jobs: list[dict[str, Any]]) -> None:
    _ensure_config_dir()
    with open(JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)
