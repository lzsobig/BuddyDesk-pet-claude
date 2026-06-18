"""
Audio — 5 事件独立音效系统

5 个事件：voice_start / message_received / file_dropped / message_sent / error
每个事件独立开关 + 可选内置 WAV 或自定义音频文件。

实现：
- 内置音：程序生成短 WAV（winsound / QSoundEffect）
- 自定义音：QSoundEffect 加载 mp3/wav/ogg/m4a
- 持久化：config.DEFAULT_USER_CONFIG 5 个 bool + 5 个 path 字段
- 回退：自定义文件丢失时回退到内置音

Usage:
    audio.play("message_received", config_dict=user_config)
"""
from __future__ import annotations

import io
import logging
import os
import struct
import sys
import wave
from typing import Literal, Optional

logger = logging.getLogger(__name__)

try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False

try:
    from PySide6.QtMultimedia import QSoundEffect
    from PySide6.QtCore import QUrl
    _HAS_QSOUND = True
except Exception:
    _HAS_QSOUND = False


SoundEvent = Literal[
    "voice_start",      # 用户开始按住说话
    "message_received", # AI 流式回复开始 / 完整到达
    "file_dropped",     # 文件拖入（桌宠吞 / 聊天框）
    "message_sent",     # 用户消息发送
    "error",            # AI 错误 / 命令执行失败
]

# 内置音频率/时长参数（每事件可调）
_BUILTIN_PRESETS: dict[str, tuple[float, ...]] = {
    # (freq_hz, duration_ms, volume) — 可单/双/三音
    "voice_start":      (880, 60, 0.20),                                   # 单音：起
    "message_received": (660, 80, 0.22, 880, 100, 0.22),                   # 双音：升
    "file_dropped":     (523, 100, 0.20),                                  # 单音：清脆
    "message_sent":     (440, 50, 0.18),                                   # 单音：低轻
    "error":            (440, 100, 0.22, 220, 150, 0.22),                  # 双音：降
}


def _make_wav_builtin(event: str) -> Optional[bytes]:
    """Generate a programmatic WAV for the given event."""
    if event not in _BUILTIN_PRESETS:
        return None
    params = _BUILTIN_PRESETS[event]
    sample_rate = 22050
    chunks: list[bytes] = []
    # 每 3 个参数为一组：(freq, duration_ms, volume)
    for i in range(0, len(params), 3):
        freq, dur_ms, vol = params[i], params[i + 1], params[i + 2]
        n = int(sample_rate * dur_ms / 1000)
        import math
        for k in range(n):
            t = k / sample_rate
            val = vol * (2**15 - 1) * math.sin(2 * 3.14159 * freq * t)
            chunks.append(struct.pack("<h", int(val)))
        # 音与音之间 30ms 静音
        n_silence = int(sample_rate * 0.03)
        chunks.append(b"\x00\x00" * n_silence)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(chunks))
    return buf.getvalue()


# Lazy QSoundEffect 实例缓存（custom_path → QSoundEffect）
_qsound_cache: dict[str, "QSoundEffect"] = {}


def _get_qsound(path: str) -> Optional["QSoundEffect"]:
    if not _HAS_QSOUND:
        return None
    if path in _qsound_cache:
        return _qsound_cache[path]
    if not os.path.isfile(path):
        return None
    eff = QSoundEffect()
    eff.setSource(QUrl.fromLocalFile(path))
    eff.setVolume(0.7)
    _qsound_cache[path] = eff
    return eff


def play(event: str, config_dict: Optional[dict] = None, enabled: Optional[bool] = None):
    """播放一个事件音效。

    优先级：custom_path > builtin > silent
    Args:
        event: 5 个事件之一
        config_dict: 用户配置 dict（含 *_enabled 和 *_custom_path 字段）
        enabled: 快速覆盖 enabled 开关
    """
    if config_dict is None:
        config_dict = {}

    # 解析开关
    if enabled is None:
        enabled = config_dict.get("sound_enabled", True)
        enabled = enabled and config_dict.get(f"sound_{event}_enabled", True)

    if not enabled or sys.platform != "win32":
        return

    # 1. 自定义音频
    custom_path = config_dict.get(f"sound_{event}_custom_path", "")
    if custom_path and os.path.isfile(custom_path):
        if _HAS_QSOUND:
            eff = _get_qsound(custom_path)
            if eff is not None:
                eff.play()
                return
        # winsound 只支持 WAV，自定义非 WAV 回退到内置
        if custom_path.lower().endswith(".wav") and _HAS_WINSOUND:
            try:
                with open(custom_path, "rb") as f:
                    winsound.PlaySound(f.read(), winsound.SND_MEMORY | winsound.SND_ASYNC)
                return
            except (OSError, RuntimeError) as exc:
                logger.debug("Failed to play custom WAV %s: %s", custom_path, exc)

    # 2. 内置音（winsound 异步播放）
    if _HAS_WINSOUND:
        try:
            data = _make_wav_builtin(event)
            if data:
                winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_ASYNC)
        except (OSError, RuntimeError) as exc:
            logger.debug("Failed to play built-in WAV for %s: %s", event, exc)


# ── 兼容性：保留旧接口 ──────────────────────────────────────────
def play_legacy(name: str, enabled: bool = True):
    """兼容旧 audio.play(name, enabled=...) 接口，映射到新事件名。"""
    legacy_to_new = {
        "click": "message_sent",
        "message": "message_received",
        "success": "message_received",
        "state_change": "message_received",
    }
    event = legacy_to_new.get(name, "message_received")
    play(event, enabled=enabled)
