from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
import threading
import time
import wave
from uuid import uuid4
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import requests


MODEL_FILES = (
    ("model.onnx", "model_quant.onnx", 241216270,
     "21dc965f689a78d1604717bf561e40d5a236087c85a95584567835750549e822"),
    ("tokens.json", "tokens.json", 352064,
     "a2594fc1474e78973149cba8cd1f603ebed8c39c7decb470631f66e70ce58e97"),
)
MODEL_SOURCE = "https://modelscope.cn/models/iic/SenseVoiceSmall-onnx/resolve/master/"
MODEL_SOURCES = (
    "https://www.modelscope.cn/models/iic/SenseVoiceSmall-onnx/resolve/master/",
    MODEL_SOURCE,
    "https://huggingface.co/haixuantao/SenseVoiceSmall-onnx/resolve/main/",
)
MODEL_PAGE = "https://modelscope.cn/models/iic/SenseVoiceSmall-onnx"


class InstallCancelled(Exception):
    pass


def default_model_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "BuddyDesk" / "models" / "sensevoice-small"


def legacy_model_dir() -> Path:
    return Path.home() / "AppData" / "Roaming" / "Shandianshuo" / "models" / "sensevoice-small"


def configured_model_dir(settings: dict) -> Path:
    value = str(settings.get("voice_model_dir", "")).strip()
    return Path(value).expanduser() if value else default_model_dir()


def active_model_dir(directory: Path) -> Path:
    pointer = directory / "active.json"
    try:
        if pointer.stat().st_size > 1024:
            return directory
        data = json.loads(pointer.read_text(encoding="utf-8"))
        version = data.get("version", "") if isinstance(data, dict) else ""
        if isinstance(version, str) and re.fullmatch(r"[a-f0-9]{32}", version):
            return directory / "versions" / version
    except (OSError, ValueError):
        pass
    return directory


def has_model(directory: Path) -> bool:
    directory = active_model_dir(directory)
    try:
        return (directory / "model.onnx").stat().st_size > 1_000_000 and (directory / "tokens.json").stat().st_size > 1000
    except OSError:
        return False


def find_model_dir(settings: dict | None = None) -> Path | None:
    settings = settings or {}
    target = configured_model_dir(settings)
    if has_model(target):
        return active_model_dir(target)
    if not str(settings.get("voice_model_dir", "")).strip() and has_model(legacy_model_dir()):
        return legacy_model_dir()
    return None


def missing_components(local: bool = True) -> list[str]:
    names = ["sounddevice", "numpy"]
    if local:
        names += ["onnxruntime", "kaldi_native_fbank"]
    return [name for name in names if importlib.util.find_spec(name) is None]


def validate_cloud_config(settings: dict) -> str:
    base = str(settings.get("voice_api_base", "")).strip().rstrip("/")
    try:
        parsed = urlsplit(base)
        local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
        _ = parsed.port
    except ValueError as error:
        raise ValueError("语音服务地址格式不正确") from error
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("请输入完整的语音 API 基础地址，例如 https://api.openai.com/v1")
    if parsed.scheme != "https" and not local:
        raise ValueError("远程语音服务请使用 HTTPS 地址")
    if not local and not str(settings.get("voice_api_key", "")).strip():
        raise ValueError("请填写语音服务的 API Key")
    if not str(settings.get("voice_api_model", "")).strip():
        raise ValueError("请填写语音识别模型名称")
    return base


def transcribe_cloud(audio: np.ndarray, sample_rate: int, settings: dict) -> str:
    base = validate_cloud_config(settings)
    if audio.size > sample_rate * 180:
        raise ValueError("单次语音请控制在 3 分钟以内")
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    key = str(settings.get("voice_api_key", "")).strip()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        with requests.post(
            base + "/audio/transcriptions", headers=headers,
            files={"file": ("speech.wav", buffer.getvalue(), "audio/wav")},
            data={"model": str(settings["voice_api_model"]).strip(), "language": "zh", "response_format": "json"},
            timeout=(10, 90), allow_redirects=False,
        ) as response:
            if response.status_code in (401, 403):
                raise ValueError("语音服务拒绝了请求，请检查 API Key 和账户权限")
            if response.status_code == 429:
                raise ValueError("语音服务额度不足或请求过于频繁，请稍后重试")
            if not 200 <= response.status_code < 300:
                raise ValueError(f"语音服务返回 HTTP {response.status_code}，请检查地址和模型")
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                raise ValueError("服务没有返回可识别的文本，请确认支持 audio/transcriptions 接口")
            return payload["text"].strip()
    except requests.Timeout as error:
        raise ValueError("语音服务响应超时，请稍后重试") from error
    except requests.RequestException as error:
        raise ValueError("无法连接语音服务，请检查网络和服务地址") from error


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_model(directory: Path) -> None:
    import onnxruntime as ort
    with (directory / "tokens.json").open(encoding="utf-8") as stream:
        tokens = json.load(stream)
    if not isinstance(tokens, list) or len(tokens) != 25055 or not all(isinstance(item, str) for item in tokens):
        raise ValueError("模型词表不兼容，请重新安装")
    session = ort.InferenceSession(str(directory / "model.onnx"), providers=["CPUExecutionProvider"])
    if {entry.name for entry in session.get_inputs()} != {"speech", "speech_lengths", "language", "textnorm"}:
        raise ValueError("模型接口不兼容，请重新安装")


def _download_file(target: Path, remote: str, expected_size: int, completed: int, total: int,
                   progress, cancel: threading.Event) -> None:
    received = 0
    failures = 0
    started = time.monotonic()
    with requests.Session() as session:
        while received < expected_size:
            if cancel.is_set():
                raise InstallCancelled()
            if time.monotonic() - started > 900:
                raise ValueError("模型下载超时，请检查网络后重试")
            end = min(received + 8 * 1024 * 1024, expected_size) - 1
            try:
                source = MODEL_SOURCES[failures % len(MODEL_SOURCES)]
                url = source + remote + f"?download=true&part={received}-{end}"
                with session.get(url, headers={"Range": f"bytes={received}-{end}"},
                                 stream=True, timeout=(10, 15)) as response:
                    response.raise_for_status()
                    if response.status_code == 206:
                        if not response.headers.get("Content-Range", "").startswith(f"bytes {received}-"):
                            raise requests.ConnectionError("Unexpected download segment")
                    elif response.status_code == 200:
                        received = 0
                    else:
                        raise ValueError("下载服务器暂时不可用，请重试")
                    before = received
                    with target.open("ab" if received else "wb") as stream:
                        for chunk in response.iter_content(256 * 1024):
                            if cancel.is_set():
                                raise InstallCancelled()
                            if not chunk:
                                continue
                            received += len(chunk)
                            if received > expected_size:
                                raise ValueError("下载文件大小异常，请稍后重试")
                            stream.write(chunk)
                            percent = int((completed + received) * 90 / total)
                            progress(percent, f"正在下载 {target.name} · {(completed + received) / 1048576:.0f} / {total / 1048576:.0f} MB")
                    if received == before:
                        raise requests.ConnectionError("Empty download segment")
            except requests.RequestException as error:
                received = target.stat().st_size if target.exists() else 0
                failures += 1
                if failures >= 8:
                    raise ValueError("模型下载多次中断，请检查网络后重试。原有模型未改动。") from error
                progress(int((completed + received) * 90 / total), "网络中断，正在自动重试…")
                if cancel.wait(min(failures, 3)):
                    raise InstallCancelled()


def install_model(destination: Path, progress, cancel: threading.Event, reuse_existing: bool = True) -> None:
    missing = missing_components()
    if missing:
        raise ValueError("缺少语音运行组件，请使用包含本地语音的完整版本：" + ", ".join(missing))
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = sum(item[2] for item in MODEL_FILES)
    if shutil.disk_usage(destination.parent).free < total * 2:
        raise ValueError("安装目录所在磁盘至少需要 500 MB 可用空间")
    completed = 0
    with tempfile.TemporaryDirectory(prefix=".sensevoice-install-", dir=destination.parent) as folder:
        staging = Path(folder)
        for name, remote, expected_size, checksum in MODEL_FILES:
            if cancel.is_set():
                raise InstallCancelled()
            target = staging / name
            reused = False
            if reuse_existing:
                for directory in (active_model_dir(destination), legacy_model_dir()):
                    candidate = directory / name
                    if candidate.is_file() and candidate.stat().st_size == expected_size and _digest(candidate) == checksum:
                        progress(int(completed * 90 / total), "复用本机模型" if name == "model.onnx" else "复制词表")
                        shutil.copyfile(candidate, target)
                        reused = True
                        break
            if not reused:
                _download_file(target, remote, expected_size, completed, total, progress, cancel)
            if target.stat().st_size != expected_size or _digest(target) != checksum:
                raise ValueError("模型校验失败，未安装不完整文件，请重试")
            completed += expected_size
        if cancel.is_set():
            raise InstallCancelled()
        progress(94, "正在验证模型")
        validate_model(staging)
        if cancel.is_set():
            raise InstallCancelled()
        destination.mkdir(parents=True, exist_ok=True)
        versions = destination / "versions"
        versions.mkdir(exist_ok=True)
        version_id = MODEL_FILES[0][3][:16] + MODEL_FILES[1][3][:16]
        published = versions / version_id
        valid_published = published.is_dir() and all(
            (published / name).is_file()
            and (published / name).stat().st_size == size
            and _digest(published / name) == checksum
            for name, _, size, checksum in MODEL_FILES
        )
        if not valid_published:
            if published.exists():
                version_id = uuid4().hex
                published = versions / version_id
            os.replace(staging, published)
        pointer = destination / f".active-{uuid4().hex}.tmp"
        try:
            pointer.write_text(json.dumps({"version": version_id}), encoding="utf-8")
            os.replace(pointer, destination / "active.json")
        finally:
            pointer.unlink(missing_ok=True)
        progress(100, "安装完成，可以使用本地语音了")
