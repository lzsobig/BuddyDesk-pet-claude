from __future__ import annotations

import bisect
import configparser
import ctypes
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from dataclasses import replace
from functools import lru_cache
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import config

try:
    from pypinyin import Style, lazy_pinyin
except ImportError:
    lazy_pinyin = None

logger = logging.getLogger(__name__)
_PY_BOUNDARIES = (-20319, -20283, -19775, -19218, -18710, -18526, -18239,
                  -17922, -17417, -16474, -16212, -15640, -15165, -14922,
                  -14914, -14630, -14149, -14090, -13318, -12838, -12556,
                  -11847, -11055, -10247)
_PY_LETTERS = "ABCDEFGHJKLMNOPQRSTWXYZ"


@lru_cache(maxsize=8192)
def normalize(value):
    return "".join(c for c in value.casefold() if c.isalnum())


@lru_cache(maxsize=8192)
def pinyin_initials(value):
    if lazy_pinyin is not None:
        return "".join(lazy_pinyin(value, style=Style.FIRST_LETTER,
            errors=lambda chars: [c.lower() for c in chars if c.isascii() and c.isalnum()])).lower()
    parts = []
    for char in value:
        if char.isascii():
            if char.isalnum():
                parts.append(char.lower())
            continue
        try:
            encoded = char.encode("gb2312")
        except UnicodeEncodeError:
            continue
        if len(encoded) == 2:
            number = encoded[0] * 256 + encoded[1] - 65536
            index = bisect.bisect_right(_PY_BOUNDARIES, number) - 1
            if 0 <= index < len(_PY_LETTERS) and number < -10247:
                parts.append(_PY_LETTERS[index].lower())
    return "".join(parts)


def valid_web_url(value):
    try:
        parsed = urlsplit(value)
        return (len(value) <= 8192 and parsed.scheme.lower() in ("http", "https")
                and bool(parsed.hostname) and not any(ord(c) < 32 for c in value))
    except ValueError:
        return False


def shortcut_url(path):
    parser = configparser.ConfigParser(interpolation=None)
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            parser.read_string(Path(path).read_text(encoding=encoding))
            value = parser.get("InternetShortcut", "URL", fallback="").strip()
            return value if valid_web_url(value) else ""
        except (UnicodeError, configparser.Error):
            continue
    return ""


@dataclass(frozen=True)
class AppEntry:
    id: str
    name: str
    target: str
    kind: str
    source: str
    aliases: tuple[str, ...] = ()
    identity: str = ""
    stamp: tuple[int, int] | None = None

    @property
    def destination(self):
        try:
            value = json.loads(self.identity)
            if isinstance(value, list) and len(value) == 3 and isinstance(value[0], str):
                return value[0]
        except (TypeError, ValueError):
            pass
        return self.target

    @property
    def arguments(self):
        try:
            value = json.loads(self.identity)
            if isinstance(value, list) and len(value) == 3 and isinstance(value[1], str):
                return value[1]
        except (TypeError, ValueError):
            pass
        return ""

    @classmethod
    def make(cls, name, target, kind, source, aliases=(), identity=""):
        target = os.path.abspath(target)
        identity = identity or os.path.normcase(target)
        digest = hashlib.sha256((kind + "\0" + identity).encode("utf-8")).hexdigest()[:24]
        stamp = None
        if target.lower().endswith(".lnk"):
            try:
                status = os.stat(target)
                stamp = (status.st_mtime_ns, status.st_size)
            except OSError:
                pass
        return cls(digest, name[:200], target, kind, source[:100], tuple(aliases), identity, stamp)


def _known_folder(identity, fallback):
    if sys.platform != "win32":
        return Path(fallback)
    class Guid(ctypes.Structure):
        _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16),
                    ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]
    guid = Guid.from_buffer_copy(uuid.UUID(identity).bytes_le)
    pointer = ctypes.c_void_p()
    shell = ctypes.WinDLL("shell32")
    shell.SHGetKnownFolderPath.argtypes = (ctypes.POINTER(Guid), ctypes.c_uint32,
                                          ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole = ctypes.WinDLL("ole32")
    ole.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
    if shell.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(pointer)) == 0:
        try:
            return Path(ctypes.wstring_at(pointer))
        finally:
            ole.CoTaskMemFree(pointer)
    return Path(fallback)


class AppIndex:
    def __init__(self, path=None):
        self.path = Path(path or Path(config.CONFIG_DIR) / "app-index.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._entries = ()
        self._usage = {}
        self.scanning = False
        self.last_error = ""
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS apps(id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS usage(id TEXT PRIMARY KEY, count INTEGER NOT NULL, last REAL NOT NULL)")
        self._load()

    @contextmanager
    def _db(self):
        database = sqlite3.connect(self.path, timeout=5)
        try:
            with database:
                yield database
        finally:
            database.close()

    def _load(self):
        entries = []
        with self._db() as db:
            for row, in db.execute("SELECT data FROM apps LIMIT 10000"):
                try:
                    value = json.loads(row)
                    if not isinstance(value, dict):
                        continue
                    value["aliases"] = tuple(value.get("aliases", ()))
                    if value.get("stamp") is not None:
                        value["stamp"] = tuple(value["stamp"])
                    entry = AppEntry(**value)
                    if (entry.kind in ("app", "folder", "website") and isinstance(entry.target, str)
                            and isinstance(entry.name, str) and isinstance(entry.source, str)
                            and isinstance(entry.id, str) and len(entry.target) < 32768
                            and all(isinstance(alias, str) for alias in entry.aliases)):
                        entries.append(entry)
                except (TypeError, ValueError):
                    logger.warning("Skipped invalid application index entry")
            usage = {row[0]: (row[1], row[2]) for row in db.execute("SELECT id,count,last FROM usage")}
        with self._lock:
            self._entries, self._usage = tuple(entries), usage

    def get(self, identity):
        with self._lock:
            return next((entry for entry in self._entries if entry.id == identity), None)

    def search(self, query, limit=8, apps_only=False):
        key = normalize(query[:500])
        with self._lock:
            entries, usage = self._entries, dict(self._usage)
        ranked = []
        for entry in entries:
            if apps_only and entry.kind != "app":
                continue
            names = [normalize(entry.name), *(normalize(name) for name in entry.aliases)]
            initials = [pinyin_initials(name) for name in (entry.name, *entry.aliases)]
            if not key:
                score = 0
            elif key in names:
                score = 1000
            elif key in initials:
                score = 930
            elif any(name.startswith(key) for name in names):
                score = 820
            elif any(name.startswith(key) for name in initials):
                score = 760
            elif any(key in name for name in names) or any(key in name for name in initials):
                score = 580
            elif len(key) >= 3 and key in normalize(Path(entry.target).stem):
                score = 420
            else:
                continue
            count, last = usage.get(entry.id, (0, 0))
            score += min(count, 20)
            preference = 2 if "桌面" in entry.source else 1 if "菜单" in entry.source else 0
            ranked.append((score, last, preference, entry))
        ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3].name.casefold(), item[3].id))
        return [entry for *_, entry in ranked[:max(1, min(limit, 50))]]

    def mark_used(self, identity):
        if self.get(identity) is None:
            return
        now = time.time()
        try:
            with self._db() as db:
                db.execute("INSERT INTO usage(id,count,last) VALUES(?,1,?) ON CONFLICT(id) DO UPDATE SET count=count+1,last=excluded.last", (identity, now))
                db.execute("DELETE FROM usage WHERE id NOT IN (SELECT id FROM usage ORDER BY last DESC LIMIT 512)")
        except sqlite3.Error:
            logger.warning("Application launch history could not be saved")
            return
        with self._lock:
            count, _ = self._usage.get(identity, (0, 0))
            self._usage[identity] = (count + 1, now)

    def exact_apps(self, query):
        key = normalize(query.strip())
        if not key:
            return []
        return [entry for entry in self.search(query, 50, apps_only=True)
                if any(key in (normalize(name), pinyin_initials(name)) for name in (entry.name, *entry.aliases))]

    def refresh(self, folders=()):
        with self._lock:
            if self.scanning:
                return False
            self.scanning = True
        try:
            entries = self._scan(folders)
            with self._db() as db:
                db.execute("DELETE FROM apps")
                db.executemany("INSERT INTO apps(id,data) VALUES(?,?)", [(entry.id, json.dumps(asdict(entry), ensure_ascii=False)) for entry in entries])
            with self._lock:
                self._entries = tuple(entries)
                self.last_error = ""
            return True
        except (OSError, sqlite3.Error) as error:
            self.last_error = "应用索引更新失败，继续使用已有结果"
            logger.warning("Application index refresh failed: %s", type(error).__name__)
            return False
        finally:
            with self._lock:
                self.scanning = False

    def _scan(self, folders):
        home = Path.home()
        roaming = Path(os.environ.get("APPDATA", home / "AppData/Roaming"))
        common = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        roots = [
            (_known_folder("B4BFCC3A-DB2C-424C-B029-7FE99A87C641", home / "Desktop"), "桌面", 1),
            (_known_folder("C4AA340D-F20F-4863-AFEF-F87EF2E6BA25", Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"), "公共桌面", 0),
            (_known_folder("A77F5D77-2E2B-44C3-A6A2-ABA601054A51", roaming / "Microsoft/Windows/Start Menu/Programs"), "开始菜单", 10),
            (_known_folder("0139D44E-6AFE-49F2-8690-3DAFCAE6FFB8", common / "Microsoft/Windows/Start Menu/Programs"), "公共开始菜单", 10),
            (roaming / "Microsoft/Internet Explorer/Quick Launch", "快速启动", 3),
        ]
        roots += [(Path(path), "指定文件夹", 2) for path in folders[:16] if isinstance(path, str) and path]
        from engine.command_engine import AppRegistry
        aliases = {}
        for name, target in AppRegistry.WINDOWS_APPS.items():
            if target:
                aliases.setdefault(target[1].casefold(), []).append(name)
        aliases.setdefault("code.exe", []).append("vsc")
        entries = {}
        shell = None
        shortcut = None
        pythoncom = None
        com_initialized = False
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            com_initialized = True
            shell = win32com.client.Dispatch("WScript.Shell")
        except ImportError:
            pythoncom = None
        except Exception:
            logger.warning("Shortcut metadata unavailable; Windows will resolve shortcuts when opened")
        def add(entry):
            if entry.id not in entries:
                entries[entry.id] = entry
            else:
                existing = entries[entry.id]
                entries[entry.id] = replace(existing, aliases=tuple(dict.fromkeys((*existing.aliases, entry.name, *entry.aliases)))[:64])
        try:
            for root, source, depth in roots:
                if str(root).startswith("\\\\") or not root.is_dir():
                    continue
                for directory, dirs, files in os.walk(root, followlinks=False):
                    level = len(Path(directory).relative_to(root).parts)
                    dirs[:] = [name for name in dirs if not name.startswith(".") and not (Path(directory) / name).is_symlink()]
                    if level >= depth:
                        dirs.clear()
                    for name in files[:5000]:
                        path = Path(directory) / name
                        extension = path.suffix.casefold()
                        if extension not in (".lnk", ".exe", ".url"):
                            continue
                        if any(word in path.stem.casefold() for word in ("uninstall", "readme", "release notes", "卸载")):
                            continue
                        source_name = source + (" / " + Path(directory).name if Path(directory) != root else "")
                        if extension == ".url":
                            if shortcut_url(path):
                                add(AppEntry.make(path.stem, str(path), "website", source_name))
                            continue
                        target = str(path)
                        entry_aliases = aliases.get(path.name.casefold(), ())
                        identity = ""
                        kind = "app"
                        if extension == ".lnk" and shell:
                            try:
                                shortcut = shell.CreateShortCut(str(path))
                                resolved = os.path.expandvars(shortcut.Targetpath)
                                if resolved and not resolved.startswith("\\\\"):
                                    if Path(resolved).is_dir():
                                        kind = "folder"
                                    entry_aliases = aliases.get(Path(resolved).name.casefold(), ()) if not shortcut.Arguments.strip() else ()
                                    identity = json.dumps((os.path.normcase(resolved), shortcut.Arguments, shortcut.WorkingDirectory), ensure_ascii=False)
                            except Exception:
                                logger.debug("Shortcut metadata unavailable")
                        add(AppEntry.make(path.stem, target, kind, source_name, entry_aliases, identity))
                        if len(entries) >= 10000:
                            break
                    if len(entries) >= 10000:
                        break
            if sys.platform == "win32":
                import winreg
                for hive, flags in ((winreg.HKEY_CURRENT_USER, winreg.KEY_READ),
                                    (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_READ | winreg.KEY_WOW64_64KEY),
                                    (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)):
                    try:
                        with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths", 0, flags) as key:
                            for number in range(min(winreg.QueryInfoKey(key)[0], 2000)):
                                name = winreg.EnumKey(key, number)
                                try:
                                    with winreg.OpenKey(key, name) as child:
                                        raw = winreg.QueryValueEx(child, "")[0]
                                    target = AppRegistry._extract_exe_path(raw) or raw.strip('"')
                                    if target.lower().endswith(".exe") and Path(target).is_file():
                                        add(AppEntry.make(Path(name).stem, target, "app", "注册表", aliases.get(name.casefold(), ())))
                                except OSError:
                                    continue
                    except OSError:
                        continue
                system = Path(os.environ.get("SystemRoot", r"C:\Windows"))
                for name, target, names in (("文件管理器", system / "explorer.exe", ("explorer", "文件", "资源管理器")),
                        ("记事本", system / "System32/notepad.exe", ("notepad",)),
                        ("计算器", system / "System32/calc.exe", ("calc",)),
                        ("截图工具", system / "System32/SnippingTool.exe", ("截图", "snippingtool"))):
                    if target.is_file():
                        add(AppEntry.make(name, str(target), "app", "Windows", names))
            for path in folders[:16]:
                if isinstance(path, str) and Path(path).is_dir():
                    add(AppEntry.make(Path(path).name or path, path, "folder", "指定文件夹"))
            return list(entries.values())[:10000]
        finally:
            shortcut = None
            shell = None
            if pythoncom and com_initialized:
                pythoncom.CoUninitialize()


_shared = None
_shared_lock = threading.Lock()


def get_app_index():
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = AppIndex()
        return _shared
