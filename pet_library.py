from __future__ import annotations

import json
import logging
import os
import re
import shutil
import stat
import tempfile
import zipfile
import zlib
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

import config


logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 16 * 1024 * 1024
SUPPORTED_IMAGES = {".png", ".webp", ".jpg", ".jpeg"}
ANIMATION_FORMAT = "buddydesk-pet-v1"
ANIMATION_STATES = frozenset({"idle", "petting", "drag", "walk", "thinking", "sleep", "happy", "error"})
MAX_PACK_JSON_BYTES = 64 * 1024
MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_FRAMES_PER_STATE = 32
MAX_FRAMES_TOTAL = 160


def library_dir() -> Path:
    return Path(config.CONFIG_DIR) / "pets"


def codex_pets(root: str | None = None) -> list[dict]:
    directory = Path(root) if root else Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "pets"
    if not directory.is_dir():
        return []
    found = []
    for folder in sorted(directory.iterdir())[:128]:
        try:
            if not folder.is_dir() or folder.is_symlink():
                continue
            manifest = folder / "pet.json"
            if manifest.is_symlink() or manifest.stat().st_size > MAX_PACK_JSON_BYTES:
                continue
            data = json.loads(manifest.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
            if not isinstance(data, dict):
                continue
            relative = _safe_relative_path(data.get("spritesheetPath", ""))
            sheet = folder.joinpath(*relative.split("/"))
            if sheet.is_symlink() or not sheet.resolve().is_relative_to(folder.resolve()) or sheet.stat().st_size > 20 * 1024 * 1024:
                continue
            if sheet.suffix.lower() not in (".png", ".webp"):
                continue
            with Image.open(sheet) as image:
                if image.size not in ((1536, 1872), (1536, 2288)):
                    continue
            name = data.get("displayName", data.get("name", folder.name))
            if not isinstance(name, str) or not name.strip() or any(ord(char) < 32 for char in name):
                continue
            description = data.get("description", "")
            found.append({"name": name.strip()[:24], "folder": str(folder), "sheet": str(sheet),
                          "description": description[:300] if isinstance(description, str) else ""})
        except (OSError, ValueError, TypeError, RecursionError, Image.DecompressionBombError):
            logger.debug("Skipped unsupported local Codex pet")
    return found


def import_codex_pet(folder: str) -> dict:
    source = Path(folder)
    choices = codex_pets(str(source.parent))
    entry = next((pet for pet in choices if Path(pet["folder"]).resolve() == source.resolve()), None)
    if entry is None:
        raise ValueError("没有找到有效的本地 Codex 宠物，请选择包含 pet.json 和 spritesheet 的宠物目录")
    rows = {"idle": (0, 6, 160), "walk": (1, 8, 100), "happy": (3, 4, 160),
            "error": (5, 8, 150), "thinking": (7, 6, 140)}
    with tempfile.TemporaryDirectory(prefix="codex-pet-import-") as temporary:
        archive_path = Path(temporary) / "pet-pack.zip"
        states = {}
        with Image.open(entry["sheet"]) as original:
            if original.size not in ((1536, 1872), (1536, 2288)) or not ("A" in original.getbands() or "transparency" in original.info):
                raise ValueError("Codex 宠物必须使用受支持的透明 spritesheet")
            sheet = original.convert("RGBA")
            if sheet.getchannel("A").getextrema()[0] == 255:
                raise ValueError("Codex 宠物图片没有透明背景，未进行导入")
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                import io
                for state, (row, count, duration) in rows.items():
                    frames = []
                    for number in range(count):
                        frame = sheet.crop((number * 192, row * 208, (number + 1) * 192, (row + 1) * 208))
                        if frame.getchannel("A").getbbox() is None:
                            raise ValueError(f"Codex 宠物 {state} 动作存在空白帧，未进行导入")
                        buffer = io.BytesIO()
                        frame.save(buffer, format="PNG")
                        relative = f"{state}/{number:02}.png"
                        archive.writestr(relative, buffer.getvalue())
                        frames.append(relative)
                    states[state] = {"frames": frames, "durations": [duration] * count}
                manifest = {"format": ANIMATION_FORMAT, "name": entry["name"], "states": states}
                archive.writestr("pet-pack.json", json.dumps(manifest, ensure_ascii=False))
        return import_animation_pack(str(archive_path))


def _builtins() -> list[dict]:
    assets = Path(config.ASSETS_DIR)
    return [
        {"id": "orange", "name": "小橘", "description": "柔和橘猫",
         "idle": str(assets / "companion" / "idle.png"),
         "thinking": str(assets / "companion" / "thinking.png"), "custom": False},
        {"id": "pixel-cat", "name": "像素橘猫", "description": "经典像素动作",
         "idle": str(assets / "cat_frames_v2" / "frame_00.png"),
         "thinking": str(assets / "cat_frames_v2" / "frame_64.png"), "custom": False},
    ]


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("动作包包含重复字段")
        result[key] = value
    return result


def _safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("动作包包含无效文件路径")
    if value.startswith("/") or ":" in value:
        raise ValueError("动作包包含无效文件路径")
    parts = value.split("/")
    if len(parts) > 8 or any(not part or part in (".", "..") for part in parts):
        raise ValueError("动作包包含无效文件路径")
    if len(value) > 240 or any(not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", part) for part in parts):
        raise ValueError("动作包包含无效文件路径")
    for part in parts:
        if part.endswith((".", " ")):
            raise ValueError("动作包包含无效文件路径")
        stem = part.split(".", 1)[0].upper()
        if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?:COM|LPT)[1-9]", stem):
            raise ValueError("动作包包含无效文件路径")
    return "/".join(parts)


def _parse_animation_manifest(raw: bytes) -> dict:
    if len(raw) > MAX_PACK_JSON_BYTES:
        raise ValueError("动作包清单不能超过 64 KB")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("动作包清单格式无效") from error
    if not isinstance(data, dict) or set(data) != {"format", "name", "states"}:
        raise ValueError("动作包清单字段无效")
    if data.get("format") != ANIMATION_FORMAT:
        raise ValueError("不支持的动作包格式")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 24 or any(ord(char) < 32 for char in name):
        raise ValueError("动作包名称需为 1～24 个字符")
    states = data.get("states")
    if not isinstance(states, dict) or "idle" not in states or not states:
        raise ValueError("动作包必须包含 idle 状态")
    if any(state not in ANIMATION_STATES for state in states):
        raise ValueError("动作包包含不支持的状态")

    parsed_states = {}
    total_frames = 0
    for state, entry in states.items():
        if not isinstance(entry, dict) or set(entry) != {"frames", "durations"}:
            raise ValueError(f"{state} 状态字段无效")
        frames = entry.get("frames")
        durations = entry.get("durations")
        if not isinstance(frames, list) or not 1 <= len(frames) <= MAX_FRAMES_PER_STATE:
            raise ValueError(f"{state} 状态需包含 1～32 帧")
        if not isinstance(durations, list) or len(durations) != len(frames):
            raise ValueError(f"{state} 状态的帧数和时长数量不一致")
        normalized_frames = [_safe_relative_path(frame) for frame in frames]
        if any(Path(frame).suffix.lower() not in {".png", ".webp"} for frame in normalized_frames):
            raise ValueError("动作帧只支持 PNG 或 WebP")
        if any(type(duration) is not int or not 40 <= duration <= 5000 for duration in durations):
            raise ValueError(f"{state} 状态的帧时长需为 40～5000 毫秒的整数")
        if sum(durations) > 20000:
            raise ValueError(f"{state} 状态总时长不能超过 20000 毫秒")
        parsed_states[state] = {"frames": normalized_frames, "durations": list(durations)}
        total_frames += len(normalized_frames)
    if total_frames > MAX_FRAMES_TOTAL:
        raise ValueError("动作包总帧数不能超过 160 帧")
    return {"name": name.strip(), "states": parsed_states}


def _safe_frame_path(root: Path, relative: str) -> Path:
    relative = _safe_relative_path(relative)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("动作包目录无效")
    root_real = root.resolve()
    candidate = root
    for part in relative.split("/"):
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("动作包不能包含符号链接")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root_real)
    except (OSError, ValueError) as error:
        raise ValueError("动作帧缺失或路径越界") from error
    if not resolved.is_file():
        raise ValueError("动作帧不是普通文件")
    return resolved


def _validate_frame(path: Path, dimensions: tuple[int, int] | None) -> tuple[int, int]:
    if path.stat().st_size > MAX_FRAME_BYTES:
        raise ValueError("单张动作帧不能超过 2 MB")
    try:
        with Image.open(path) as image:
            if image.format not in ("PNG", "WEBP") or image.format.lower() != path.suffix.lower().lstrip("."):
                raise ValueError("动作帧内容需与 PNG 或 WebP 扩展名一致")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("动作帧必须是单帧图片")
            width, height = image.size
            if width < 1 or height < 1 or max(width, height) > 512:
                raise ValueError("动作帧尺寸不能超过 512×512")
            current_dimensions = (width, height)
            if dimensions is not None and current_dimensions != dimensions:
                raise ValueError("动作包中的帧必须使用相同尺寸")
            image.load()
            alpha = image.convert("RGBA").getchannel("A").getextrema()
            if alpha[1] == 0 or alpha[0] == 255:
                raise ValueError("动作帧必须包含透明区域")
            return current_dimensions
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ValueError("无法读取动作帧图片") from error


def _load_animation_pack(root: Path, manifest_path: Path) -> dict:
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("动作包清单缺失")
    if manifest_path.stat().st_size > MAX_PACK_JSON_BYTES:
        raise ValueError("动作包清单不能超过 64 KB")
    manifest = _parse_animation_manifest(manifest_path.read_bytes())
    checked_frames = {}
    dimensions = None
    total_frame_bytes = 0
    result_states = {}
    for state, entry in manifest["states"].items():
        resolved_frames = []
        for relative in entry["frames"]:
            path = checked_frames.get(relative)
            if path is None:
                path = _safe_frame_path(root, relative)
                total_frame_bytes += path.stat().st_size
                if total_frame_bytes > MAX_EXPANDED_BYTES:
                    raise ValueError("动作包解压后不能超过 64 MB")
                dimensions = _validate_frame(path, dimensions)
                checked_frames[relative] = path
            resolved_frames.append(str(path))
        result_states[state] = {"frames": resolved_frames, "durations": entry["durations"]}
    return {"name": manifest["name"], "states": result_states,
            "state_count": len(result_states), "frame_count": sum(len(state["frames"]) for state in result_states.values())}


def _pack_signature(root: Path, manifest_path: Path) -> tuple | None:
    try:
        if root.is_symlink() or not root.is_dir() or manifest_path.is_symlink() or not manifest_path.is_file():
            return None
        manifest_stat = manifest_path.stat()
        if manifest_stat.st_size > MAX_PACK_JSON_BYTES:
            return None
        manifest = _parse_animation_manifest(manifest_path.read_bytes())
        frame_stats = []
        for relative in sorted({frame for entry in manifest["states"].values() for frame in entry["frames"]}):
            frame_path = _safe_frame_path(root, relative)
            frame_stat = frame_path.stat()
            frame_stats.append((relative, frame_stat.st_mtime_ns, frame_stat.st_size))
        return (str(root.resolve()), str(manifest_path.resolve()), manifest_stat.st_mtime_ns,
                manifest_stat.st_size, tuple(frame_stats))
    except (OSError, ValueError, TypeError, Image.DecompressionBombError, RecursionError):
        return None


@lru_cache(maxsize=64)
def _cached_pack_info(signature: tuple) -> dict | None:
    root = Path(signature[0])
    manifest_path = Path(signature[1])
    try:
        animation = _load_animation_pack(root, manifest_path)
    except (OSError, ValueError, TypeError, Image.DecompressionBombError, RecursionError):
        return None
    return {"animated": True, "animation_state_count": animation["state_count"],
            "animation_frame_count": animation["frame_count"],
            "animation_states": tuple(animation["states"])}


def _pack_info(root: Path, manifest_path: Path) -> dict | None:
    signature = _pack_signature(root, manifest_path)
    return _cached_pack_info(signature) if signature is not None else None


def pets() -> list[dict]:
    choices = _builtins()
    assets = Path(config.ASSETS_DIR)
    builtin_pack = assets / "companion" / "animation" / "pet-pack.json"
    builtin_animation = _pack_info(builtin_pack.parent, builtin_pack)
    for pet in choices:
        pet.update(builtin_animation if pet["id"] == "orange" and builtin_animation else {
            "animated": False, "animation_state_count": 0, "animation_frame_count": 0, "animation_states": ()})

    directory = library_dir()
    if not directory.exists():
        return choices
    for path in sorted(directory.glob("*/pet.json")):
        try:
            if not re.fullmatch(r"[a-f0-9]{32}", path.parent.name) or path.stat().st_size > 8192:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            images = {}
            for kind in ("idle", "thinking"):
                filename = data.get(kind, data.get("idle", ""))
                if not isinstance(filename, str) or Path(filename).name != filename:
                    raise ValueError("Invalid pet image path")
                candidate = path.parent / filename
                if candidate.suffix.lower() not in SUPPORTED_IMAGES or not candidate.is_file():
                    raise ValueError("Missing pet image")
                if candidate.resolve().parent != path.parent.resolve():
                    raise ValueError("Pet image outside its directory")
                images[kind] = str(candidate)
            animation_info = _pack_info(path.parent, path.parent / "pet-pack.json")
            choices.append({"id": path.parent.name, "name": str(data.get("name", "我的宠物"))[:24],
                            "description": "自定义宠物", "custom": True,
                            **(animation_info or {"animated": False, "animation_state_count": 0,
                                                  "animation_frame_count": 0, "animation_states": ()}),
                            **images})
        except (OSError, ValueError, TypeError):
            continue
    return choices


def resolve_pet(pet_id: str = "orange") -> dict:
    choices = pets()
    return next((pet for pet in choices if pet["id"] == pet_id), choices[0])


def load_animation(pet_id: str) -> dict:
    """Load validated animation states as absolute frame paths and millisecond durations."""
    pet_id = str(pet_id)
    if pet_id == "orange":
        root = Path(config.ASSETS_DIR) / "companion" / "animation"
    elif re.fullmatch(r"[a-f0-9]{32}", pet_id):
        root = library_dir() / pet_id
    else:
        return {}
    manifest_path = root / "pet-pack.json"
    if not os.path.lexists(manifest_path):
        return {}
    try:
        return _load_animation_pack(root, manifest_path)["states"]
    except (OSError, ValueError, TypeError, Image.DecompressionBombError, RecursionError) as error:
        logger.warning("Ignoring invalid animation pack for pet %s (%s)", pet_id, type(error).__name__)
        return {}


def _check_image(path: Path) -> None:
    if not path.is_file() or path.suffix.lower() not in SUPPORTED_IMAGES:
        raise ValueError("请选择 PNG、WebP 或 JPG 图片")
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("单张宠物图片不能超过 16 MB")
    try:
        with Image.open(path) as image:
            if image.format not in ("PNG", "WEBP", "JPEG"):
                raise ValueError("图片内容需为 PNG、WebP 或 JPG 格式")
            width, height = image.size
            if width < 8 or height < 8 or max(width, height) > 4096 or width * height > 8 * 1024 * 1024:
                raise ValueError("图片尺寸需在 8～4096 像素之间，且不超过 800 万像素")
            image.load()
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("无法读取这张图片，请选择有效的图片文件") from error


def import_pet(name: str, idle: str, thinking: str | None = None) -> dict:
    idle_path = Path(idle)
    thinking_path = Path(thinking) if thinking else idle_path
    _check_image(idle_path)
    _check_image(thinking_path)
    destination = library_dir()
    destination.mkdir(parents=True, exist_ok=True)
    identity = uuid4().hex
    with tempfile.TemporaryDirectory(prefix=".pet-import-", dir=destination) as temporary:
        stage = Path(temporary)
        idle_name = "idle" + idle_path.suffix.lower()
        thinking_name = "thinking" + thinking_path.suffix.lower()
        shutil.copyfile(idle_path, stage / idle_name)
        shutil.copyfile(thinking_path, stage / thinking_name)
        (stage / "pet.json").write_text(json.dumps({"name": name.strip()[:24] or "我的宠物",
            "idle": idle_name, "thinking": thinking_name}, ensure_ascii=False), encoding="utf-8")
        os.replace(stage, destination / identity)
    return resolve_pet(identity)


def _archive_entry_name(info: zipfile.ZipInfo) -> tuple[str, bool]:
    name = info.filename
    is_directory = info.is_dir()
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise ValueError("动作包包含无效 ZIP 路径")
    if is_directory:
        name = name[:-1]
    normalized = _safe_relative_path(name)
    mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    if file_type == stat.S_IFLNK:
        raise ValueError("动作包不能包含符号链接")
    if file_type and file_type not in (stat.S_IFREG, stat.S_IFDIR):
        raise ValueError("动作包包含不支持的文件类型")
    if (is_directory and file_type == stat.S_IFREG) or (not is_directory and file_type == stat.S_IFDIR):
        raise ValueError("动作包 ZIP 条目类型无效")
    if info.flag_bits & 0x1:
        raise ValueError("不支持加密的动作包")
    return normalized, is_directory


def _read_zip_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, maximum: int) -> bytes:
    if info.file_size < 0 or info.file_size > maximum:
        raise ValueError("动作包文件超过大小限制")
    try:
        with archive.open(info, "r") as source:
            data = source.read(maximum + 1)
    except (OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError, EOFError, zlib.error) as error:
        raise ValueError("动作包内容损坏或无法读取") from error
    if len(data) != info.file_size or len(data) > maximum:
        raise ValueError("动作包文件大小与清单不一致")
    return data


def _extract_zip_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path, remaining_total: int) -> int:
    if info.file_size < 0 or info.file_size > MAX_FRAME_BYTES:
        raise ValueError("单张动作帧不能超过 2 MB")
    if info.file_size > remaining_total:
        raise ValueError("动作包解压后不能超过 64 MB")
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with archive.open(info, "r") as source, target.open("xb") as destination:
            while True:
                chunk = source.read(min(65536, remaining_total + 1 - written))
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_FRAME_BYTES:
                    raise ValueError("单张动作帧不能超过 2 MB")
                if written > remaining_total:
                    raise ValueError("动作包解压后不能超过 64 MB")
                destination.write(chunk)
    except (OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError, EOFError, zlib.error) as error:
        raise ValueError("动作包内容损坏或无法读取") from error
    if written != info.file_size:
        raise ValueError("动作包文件大小与清单不一致")
    return written


def _write_preview(source: Path, target: Path) -> None:
    temporary = target.with_name(".preview-" + uuid4().hex + ".png")
    try:
        with Image.open(source) as image:
            image.convert("RGBA").save(temporary, format="PNG", optimize=True)
        os.replace(temporary, target)
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ValueError("无法生成宠物预览图片") from error
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def import_animation_pack(path: str) -> dict:
    """Validate and atomically add a BuddyDesk animation ZIP without extracting untrusted paths."""
    archive_path = Path(path)
    if archive_path.is_symlink() or not archive_path.is_file() or archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("动作包 ZIP 不能超过 32 MB")
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError("请选择有效的宠物动作包 ZIP") from error

    with archive:
        infos = archive.infolist()
        if not infos or len(infos) > 256:
            raise ValueError("动作包 ZIP 条目数量无效")
        entries = {}
        expanded_size = 0
        for info in infos:
            normalized, is_directory = _archive_entry_name(info)
            key = normalized.casefold()
            if key in entries:
                raise ValueError("动作包包含重复 ZIP 路径")
            if info.file_size < 0:
                raise ValueError("动作包包含无效文件大小")
            expanded_size += info.file_size
            if expanded_size > MAX_EXPANDED_BYTES:
                raise ValueError("动作包解压后不能超过 64 MB")
            if is_directory and info.file_size:
                raise ValueError("动作包目录条目不能包含数据")
            entries[key] = (normalized, is_directory, info)

        manifest_entry = entries.get("pet-pack.json")
        if not manifest_entry or manifest_entry[0] != "pet-pack.json" or manifest_entry[1]:
            raise ValueError("动作包根目录缺少 pet-pack.json")
        manifest_info = manifest_entry[2]
        raw_manifest = _read_zip_member(archive, manifest_info, MAX_PACK_JSON_BYTES)
        manifest = _parse_animation_manifest(raw_manifest)
        frame_names = {frame for state in manifest["states"].values() for frame in state["frames"]}
        expected_files = frame_names | {"pet-pack.json"}
        actual_files = {normalized for normalized, is_directory, _ in entries.values() if not is_directory}
        if actual_files != expected_files:
            raise ValueError("动作包中存在未引用文件或缺少动作帧")
        expected_directories = {"/".join(parts[:index]) for filename in frame_names
                                for parts in [filename.split("/")] for index in range(1, len(parts))}
        actual_directories = {normalized for normalized, is_directory, _ in entries.values() if is_directory}
        if actual_directories - expected_directories:
            raise ValueError("动作包包含未使用目录")
        for directory in expected_directories:
            file_conflict = entries.get(directory.casefold())
            if file_conflict and not file_conflict[1]:
                raise ValueError("动作包路径同时作为文件和目录使用")
        frame_infos = {name: entries[name.casefold()][2] for name in frame_names}

        destination = library_dir()
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".pet-import-", dir=destination) as temporary:
            stage = Path(temporary)
            (stage / "pet-pack.json").write_bytes(raw_manifest)
            expanded_written = len(raw_manifest)
            for relative in sorted(frame_names):
                expanded_written += _extract_zip_member(
                    archive, frame_infos[relative], stage.joinpath(*relative.split("/")),
                    MAX_EXPANDED_BYTES - expanded_written,
                )
            validated = _load_animation_pack(stage, stage / "pet-pack.json")
            idle_source = Path(validated["states"]["idle"]["frames"][0])
            thinking_frames = validated["states"].get("thinking", validated["states"]["idle"])["frames"]
            _write_preview(idle_source, stage / "idle.png")
            _write_preview(Path(thinking_frames[0]), stage / "thinking.png")
            (stage / "pet.json").write_text(json.dumps({"name": manifest["name"], "idle": "idle.png",
                "thinking": "thinking.png", "animated": True}, ensure_ascii=False), encoding="utf-8")

            while True:
                identity = uuid4().hex
                final_path = destination / identity
                if os.path.lexists(final_path):
                    continue
                try:
                    os.rename(stage, final_path)
                except FileExistsError:
                    continue
                break
    return resolve_pet(identity)


def update_thinking_image(pet_id: str, source: str) -> dict:
    pet = resolve_pet(pet_id)
    if not pet["custom"] or pet["id"] != pet_id:
        raise ValueError("内置宠物不能覆盖，请先导入自定义宠物")
    image_path = Path(source)
    _check_image(image_path)
    directory = library_dir() / pet_id
    filename = "thinking-" + uuid4().hex + image_path.suffix.lower()
    shutil.copyfile(image_path, directory / filename)
    data = json.loads((directory / "pet.json").read_text(encoding="utf-8"))
    previous = data.get("thinking", "")
    data["thinking"] = filename
    temporary = directory / (".pet-" + uuid4().hex + ".json")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, directory / "pet.json")
    retained = {filename, previous, data.get("idle", "")}
    try:
        bridge_file = Path(config.CONFIG_DIR) / "winisland" / "pet.json"
        if bridge_file.stat().st_size <= 16384:
            bridge = json.loads(bridge_file.read_text(encoding="utf-8"))
            if isinstance(bridge, dict) and bridge.get("pet_id") == pet_id:
                for kind in ("idle_path", "thinking_path"):
                    reference = Path(bridge.get(kind, ""))
                    if reference.resolve().parent == directory.resolve():
                        retained.add(reference.name)
    except (OSError, ValueError, TypeError):
        pass
    for candidate in directory.glob("thinking*"):
        if candidate.name not in retained and candidate.is_file() and candidate.suffix.lower() in SUPPORTED_IMAGES:
            if candidate.resolve().parent == directory.resolve():
                try:
                    candidate.unlink()
                except OSError:
                    pass
    return resolve_pet(pet_id)


def island_settings(settings: dict) -> dict:
    choices = pets()
    pet = next((choice for choice in choices if choice["id"] == settings.get("pet_id")), choices[0])
    available = choices[:32]
    if pet not in available:
        available = [*choices[:31], pet]
    position = settings.get("pet_position")
    if (not isinstance(position, dict) or type(position.get("x")) is not int
            or type(position.get("y")) is not int or not isinstance(position.get("screen"), str)
            or abs(position["x"]) > 1_000_000 or abs(position["y"]) > 1_000_000
            or len(position["screen"]) > 64
            or any(ord(char) < 32 for char in position["screen"])):
        position = None
    else:
        position = {"x": position["x"], "y": position["y"], "screen": position["screen"]}
    return {"protocol_version": 1, "pet_id": pet["id"],
            "pet_name": str(settings.get("pet_name", pet["name"]))[:24],
            "island_enabled": bool(settings.get("pet_island_enabled", True)),
            "desktop_enabled": bool(settings.get("pet_enabled", True)),
            "roam_enabled": bool(settings.get("pet_roam", False)),
            "position": position,
            "available_pets": [{"id": choice["id"], "name": choice["name"][:24]}
                               for choice in available],
            "idle_path": pet["idle"], "thinking_path": pet["thinking"]}
