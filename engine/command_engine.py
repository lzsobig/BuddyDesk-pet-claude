"""
Command Engine - 命令解析与执行引擎

核心功能：
- 解析 AI 回复中的可执行指令
- 打开应用程序（Windows/Mac/Linux）
- 执行系统命令（Claude Code / Shell）
- 快捷指令注册（如 "打开微信" -> 启动微信）
- 安全确认机制（危险命令需要确认）
"""
import os
import sys
import json
import shlex
import subprocess
import threading
import re
import shutil
from datetime import datetime
from typing import Optional

import config

# Suppress CMD window flash on Windows for all subprocess calls
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Windows registry — imported once at module load so helper methods don't
# each need a local import. winreg only exists on win32.
if sys.platform == "win32":
    import winreg as _winreg  # type: ignore
else:
    _winreg = None  # type: ignore


def _read_lnk_target(lnk_path: str) -> str:
    """Resolve a shortcut target through Windows Shell when pywin32 exists.

    Windows shortcuts have several valid binary layouts. When COM is not
    available callers launch the .lnk itself with Windows Shell instead of
    relying on a partial binary parser.
    """
    try:
        import win32com.client  # type: ignore
        shell = win32com.client.Dispatch("WScript.Shell")
        return shell.CreateShortCut(lnk_path).Targetpath or ""
    except Exception:
        return ""


_SENSITIVE_COMMAND_RE = re.compile(
    r"(?i)(?:\b(?:api[_-]?key|token|password|passwd|secret)\b\s*[=:]\s*|\bauthorization\b\s*[:=]\s*(?:Bearer\s+)?|\bBearer\s+)([^\s\"']+)"
)


def _redact_command(value: str) -> str:
    """Mask common credentials before command text reaches persistent logs."""
    if not value:
        return value
    return _SENSITIVE_COMMAND_RE.sub("[REDACTED]", value)


class CommandResult:
    """命令执行结果"""

    def __init__(self, success: bool, output: str = "", command: str = "", error: str = "",
                 requires_confirmation: bool = False):
        self.success = success
        self.output = output
        self.command = command
        self.error = error
        self.requires_confirmation = requires_confirmation
        self.timestamp = datetime.now().isoformat()

    def to_dict(self):
        return {
            "success": self.success,
            "output": self.output[:500],  # Truncate long output
            "command": self.command,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class AppRegistry:
    """Windows 应用注册表 - 常见应用的启动路径"""

    # Common Windows apps with multiple possible paths. The Tencent WeChat
    # install is unusual: it lives under `\Tencent\Weixin\Weixin.exe` on
    # Chinese Windows installs (Weixin = 微信 pinyin), so we point at the
    # real path rather than guessing "WeChat\WeChat.exe".
    WINDOWS_APPS = {
        # Browsers
        "微信": [r"Tencent\Weixin", "Weixin.exe"],
        "wechat": [r"Tencent\Weixin", "Weixin.exe"],
        "chrome": [r"Google\Chrome\Application", "chrome.exe"],
        "谷歌浏览器": [r"Google\Chrome\Application", "chrome.exe"],
        "firefox": [r"Mozilla Firefox", "firefox.exe"],
        "火狐": [r"Mozilla Firefox", "firefox.exe"],
        "edge": [r"Microsoft\Edge\Application", "msedge.exe"],
        "浏览器": [r"Google\Chrome\Application", "chrome.exe"],

        # Dev tools
        "vscode": [r"Microsoft VS Code", "Code.exe"],
        "vs code": [r"Microsoft VS Code", "Code.exe"],
        "visual studio code": [r"Microsoft VS Code", "Code.exe"],
        "代码编辑器": [r"Microsoft VS Code", "Code.exe"],
        "idea": [r"JetBrains\IntelliJ IDEA Community Edition*", "idea64.exe"],
        "pycharm": [r"JetBrains\PyCharm Community Edition*", "pycharm64.exe"],
        "webstorm": [r"JetBrains\WebStorm*", "webstorm64.exe"],
        "cursor": [r"Cursor", "Cursor.exe"],

        # Office
        "word": [r"Microsoft Office\root\Office16", "WINWORD.EXE"],
        "excel": [r"Microsoft Office\root\Office16", "EXCEL.EXE"],
        "powerpoint": [r"Microsoft Office\root\Office16", "POWERPNT.EXE"],
        "ppt": [r"Microsoft Office\root\Office16", "POWERPNT.EXE"],
        "notion": [r"Notion", "Notion.exe"],
        "obsidian": [r"Obsidian", "Obsidian.exe"],

        # Communication
        "qq": [r"Tencent\QQ", "QQ.exe"],
        "钉钉": [r"DingDing", "DingtalkLauncher.exe"],
        "dingtalk": [r"DingDing", "DingtalkLauncher.exe"],
        "飞书": [r"Lark", "Lark.exe"],
        "lark": [r"Lark", "Lark.exe"],
        "telegram": [r"Telegram Desktop", "Telegram.exe"],
        "电报": [r"Telegram Desktop", "Telegram.exe"],
        "discord": [r"Discord", "Discord.exe"],

        # Media
        "spotify": [r"Spotify", "Spotify.exe"],
        "音乐": [r"Spotify", "Spotify.exe"],
        "vlc": [r"VideoLAN\VLC", "vlc.exe"],
        "potplayer": [r"Daum\PotPlayer", "PotPlayerMini64.exe"],
        "播放器": [r"VideoLAN\VLC", "vlc.exe"],

        # Tools
        "terminal": [r"WindowsApps", "wt.exe"],
        "终端": [r"WindowsApps", "wt.exe"],
        "cmd": None,  # Special handling
        "powershell": None,
        "文件管理器": None,  # explorer
        "explorer": None,
        "计算器": None,  # calc
        "calc": None,
        "截图": None,  # snippingtool
        "notepad": None,
        "记事本": None,

        # Games
        "steam": [r"Steam", "steam.exe"],
        "epic": [r"Epic Games", "EpicGamesLauncher.exe"],

        # Design
        "figma": [r"Figma", "Figma.exe"],
        "photoshop": [r"Adobe\Adobe Photoshop*", "Photoshop.exe"],
        "ps": [r"Adobe\Adobe Photoshop*", "Photoshop.exe"],

        # Chinese apps — commonly used on Chinese Windows installs
        "wps": [r"Kingsoft\WPS Office\*", "wps.exe"],
        "wps office": [r"Kingsoft\WPS Office\*", "wps.exe"],
        "百度网盘": [r"Baidu\BaiduNetdisk", "BaiduNetdisk.exe"],
        "百度云": [r"Baidu\BaiduNetdisk", "BaiduNetdisk.exe"],
        "迅雷": [r"Thunder Network\Thunder\Program", "Thunder.exe"],
        "网易云音乐": [r"Netease\CloudMusic", "cloudmusic.exe"],
        "网易云": [r"Netease\CloudMusic", "cloudmusic.exe"],
        "企业微信": [r"Tencent\WXWork", "WXWork.exe"],
        "腾讯会议": [r"Tencent\WeMeet", "wemeetapp.exe"],
        "搜狗输入法": [r"SogouInput\*", "SGTool.exe"],
        # Additional Chinese apps
        "哔哩哔哩": [r"哔哩哔哩\*" , "bilibili.exe"],
        "bilibili": [r"哔哩哔哩\*", "bilibili.exe"],
        "b站": [r"哔哩哔哩\*", "bilibili.exe"],
        "腾讯视频": [r"Tencent\TVPlus\*", "qqlive.exe"],
        "爱奇艺": [r"iQIYI\*", "iQIYIWidget.exe"],
        "阿里云盘": [r"Alibaba\Aliyunpan", "Aliyunpan.exe"],
        "微博": [r"Sina\Weibo\*", "Weibo.exe"],
        "有道词典": [r"NetEase\YoudaoDict", "YoudaoDict.exe"],
        "有道翻译": [r"NetEase\YoudaoDict", "YoudaoDict.exe"],
    }

    # macOS apps (for cross-platform support)
    MACOS_APPS = {
        "微信": "WeChat",
        "wechat": "WeChat",
        "chrome": "Google Chrome",
        "谷歌浏览器": "Google Chrome",
        "vscode": "Visual Studio Code",
        "vs code": "Visual Studio Code",
        "code": "Visual Studio Code",
        "terminal": "Terminal",
        "终端": "Terminal",
        "finder": "Finder",
        "文件管理器": "Finder",
        "spotify": "Spotify",
        "notion": "Notion",
        "discord": "Discord",
        "telegram": "Telegram",
        "figma": "Figma",
        "steam": "Steam",
        "safari": "Safari",
    }

    # Linux apps (common package names)
    LINUX_APPS = {
        "chrome": "google-chrome",
        "firefox": "firefox",
        "vscode": "code",
        "terminal": "gnome-terminal",
        "终端": "gnome-terminal",
        "文件管理器": "nautilus",
        "notepad": "gedit",
        "记事本": "gedit",
    }

    @classmethod
    def find_app(cls, name: str) -> str:
        """Find the command/path to launch an application.

        Args:
            name: Application name (Chinese or English)

        Returns:
            Command string to launch the app, or empty string if not found
        """
        name_lower = name.lower().strip()

        if sys.platform == "win32":
            return cls._find_windows_app(name_lower)
        elif sys.platform == "darwin":
            return cls._find_macos_app(name_lower)
        else:
            return cls._find_linux_app(name_lower)

    # -- Helper lookup methods for _find_windows_app --

    @staticmethod
    def _find_via_special(name: str) -> Optional[str]:
        """Check the built-in special commands dict (cmd, calc, explorer …)."""
        specials = {
            "cmd": "cmd",
            "powershell": "powershell",
            "文件管理器": "explorer",
            "explorer": "explorer",
            "计算器": "calc",
            "calc": "calc",
            "截图": "snippingtool",
            "notepad": "notepad",
            "记事本": "notepad",
        }
        return specials.get(name)

    @classmethod
    def _find_via_registry(cls, name: str) -> Optional[str]:
        """Look up *name* in WINDOWS_APPS and search Program Files / LocalAppData.

        Validates symlink targets so a broken junction (e.g. WeChat migrated
        away by 电脑管家) is skipped instead of returning a dead path.
        """
        if name not in cls.WINDOWS_APPS or cls.WINDOWS_APPS[name] is None:
            return None
        subpath, exe = cls.WINDOWS_APPS[name]
        search_roots = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
            # Common user-scoped install roots that 电脑管家 / Tencent use
            os.environ.get("USERPROFILE", ""),
        ]
        for root in search_roots:
            if not root:
                continue
            if "*" in subpath:
                import glob
                for match in glob.glob(os.path.join(root, subpath)):
                    full_path = os.path.join(match, exe)
                    if cls._path_launchable(full_path):
                        return f'"{full_path}"'
            else:
                full_path = os.path.join(root, subpath, exe)
                if cls._path_launchable(full_path):
                    return f'"{full_path}"'
        return None

    @staticmethod
    def _path_launchable(path: str) -> bool:
        """Return whether *path* is a real launchable file.

        Directories are deliberately rejected: an App Paths or Uninstall entry
        pointing at a directory must not be reported as a successfully opened
        application.
        """
        try:
            return os.path.isfile(path)
        except (OSError, ValueError):
            return False

    @classmethod
    def _find_via_uninstall_registry(cls, name: str) -> Optional[str]:
        """Query HKLM/HKCU Uninstall keys for InstallLocation + DisplayIcon.

        Covers apps that don't live under Program Files (e.g. D-drive
        installs, 电脑管家-migrated WeChat, portable apps). Only Windows.
        """
        if _winreg is None:
            return None
        search_keys = cls._find_via_aliases(name)
        for hive, subkey, flags in (
            (_winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
             _winreg.KEY_READ | _winreg.KEY_WOW64_64KEY),
            (_winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
             _winreg.KEY_READ | _winreg.KEY_WOW64_32KEY),
            (_winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
             _winreg.KEY_READ),
        ):
            try:
                with _winreg.OpenKey(hive, subkey, 0, flags) as parent:
                    for i in range(0, _winreg.QueryInfoKey(parent)[0]):
                        try:
                            child_name = _winreg.EnumKey(parent, i)
                        except OSError:
                            break
                        try:
                            with _winreg.OpenKey(parent, child_name) as child:
                                display = cls._reg_get(child, "DisplayName", "")
                                if not display or not cls._display_name_matches(display, search_keys):
                                    continue
                                install_loc = cls._reg_get(child, "InstallLocation", "")
                                display_icon = cls._reg_get(child, "DisplayIcon", "")
                                exe = cls._extract_exe_path(display_icon)
                                if exe and cls._path_launchable(exe):
                                    return f'"{exe}"'
                                for candidate in cls._candidate_executables(install_loc, name):
                                    if cls._path_launchable(candidate):
                                        return f'"{candidate}"'
                        except OSError:
                            continue
            except OSError:
                continue
        return None

    @staticmethod
    def _display_name_matches(display: str, search_keys: list[str]) -> bool:
        """Match a registry DisplayName against aliases without broad substrings."""
        normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", display.lower()).strip()
        words = set(normalized.split())
        compact = normalized.replace(" ", "")
        for key in search_keys:
            normalized_key = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", key.lower())
            if normalized_key and (normalized_key in words or normalized_key == compact):
                return True
        return False

    @classmethod
    def _candidate_executables(cls, install_location: str, name: str) -> list[str]:
        """Return only explicit executable candidates under InstallLocation."""
        if not install_location or not os.path.isdir(install_location):
            return []
        candidates = []
        for exe_name in cls._app_exe_candidates(name):
            candidates.append(os.path.join(install_location, exe_name))
        return candidates

    @staticmethod
    def _reg_get(key, name: str, default: str = "") -> str:
        try:
            value, _ = _winreg.QueryValueEx(key, name)
            return str(value) if value else default
        except OSError:
            return default

    @staticmethod
    def _extract_exe_path(raw: str) -> str:
        """Pull a real .exe path out of a messy registry value.

        DisplayIcon is often ``"C:\\path\\app.exe,0"`` or a quoted path;
        InstallLocation is a bare directory. We extract the first drive-letter
        path ending in .exe.
        """
        if not raw:
            return ""
        import re
        m = re.search(r'([A-Za-z]:[\\/][^\x00-\x1f<>|*?"]*?\.exe)', raw, re.IGNORECASE)
        if m:
            return m.group(1).strip('"').strip()
        return ""

    @classmethod
    def _find_via_app_paths(cls, name: str) -> Optional[str]:
        """Query HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths."""
        if _winreg is None:
            return None
        exe_names = cls._app_exe_candidates(name)
        for exe in exe_names:
            for hive, flags in (
                (_winreg.HKEY_LOCAL_MACHINE, _winreg.KEY_READ | _winreg.KEY_WOW64_64KEY),
                (_winreg.HKEY_LOCAL_MACHINE, _winreg.KEY_READ | _winreg.KEY_WOW64_32KEY),
                (_winreg.HKEY_CURRENT_USER, _winreg.KEY_READ),
            ):
                try:
                    with _winreg.OpenKey(
                        hive,
                        rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}",
                        0, flags,
                    ) as key:
                        default = cls._reg_get(key, "", "")
                        path = cls._extract_exe_path(default) or default.strip('"')
                        if path and cls._path_launchable(path):
                            return f'"{path}"'
                except OSError:
                    continue
        return None

    @classmethod
    def _app_exe_candidates(cls, name: str) -> list[str]:
        """Possible .exe filenames for *name* (for App Paths / Store lookup)."""
        if name in cls.WINDOWS_APPS and cls.WINDOWS_APPS[name]:
            return [cls.WINDOWS_APPS[name][1]]
        return [f"{name}.exe"]

    @staticmethod
    def _find_via_aliases(name: str) -> list[str]:
        """Return the list of search keys (alias + original) for Start Menu matching.

        Chinese names are mapped to English equivalents so .lnk shortcut
        filenames can be matched.  If no alias exists, returns ``[name]``.
        """
        alias = {
            "微信": "wechat",
            "wechat": "微信",
            "谷歌浏览器": "chrome",
            "火狐": "firefox",
            "浏览器": "chrome",
            "代码编辑器": "code",
            "终端": "terminal",
            "文件管理器": "explorer",
            "计算器": "calculator",
            "截图": "snipping",
            "记事本": "notepad",
            "音乐": "spotify",
            "播放器": "vlc",
        }.get(name, name)
        return [alias, name] if alias != name else [name]

    @classmethod
    def _find_via_start_menu(cls, name: str) -> Optional[str]:
        """Find a matching Start Menu shortcut.

        Windows Shell owns .lnk parsing. Returning the shortcut itself keeps
        Unicode, arguments, working directory, and app-specific activation
        behavior intact even where pywin32 is unavailable.
        """
        search_keys = cls._find_via_aliases(name)
        try:
            import glob
            start_dirs = [
                os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
                os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
            ]
            candidates: list[tuple[int, str]] = []
            for directory in start_dirs:
                if not directory or not os.path.isdir(directory):
                    continue
                for lnk in glob.glob(os.path.join(directory, "**", "*.lnk"), recursive=True):
                    base = os.path.splitext(os.path.basename(lnk))[0]
                    if not cls._display_name_matches(base, search_keys):
                        continue
                    target = _read_lnk_target(lnk)
                    priority = 5 if "uninstall" in base.lower() else 0
                    if target and not cls._path_launchable(target):
                        continue
                    candidates.append((priority, lnk))
            if candidates:
                candidates.sort(key=lambda item: item[0])
                return f'"{candidates[0][1]}"'
        except Exception:
            pass
        return None

    @staticmethod
    def _find_via_path(name: str) -> Optional[str]:
        """Find a real executable, cmd, or bat file on PATH."""
        try:
            result = subprocess.run(
                ["where", name],
                capture_output=True, text=True, timeout=5,
                creationflags=_NO_WINDOW,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    path = line.strip().strip('"')
                    if not AppRegistry._path_launchable(path):
                        continue
                    if os.path.splitext(path)[1].lower() in {".exe", ".cmd", ".bat"}:
                        return f'"{path}"'
        except Exception:
            pass
        return None

    # -- Main orchestrator --

    @classmethod
    def _find_windows_app(cls, name: str) -> str:
        """Find a verified Windows application launch target.

        Unknown text never becomes a shell command. The caller receives an
        empty string and can show a useful "not found" message instead.
        """
        for finder in (
            cls._find_via_special,
            cls._find_via_start_menu,
            cls._find_via_registry,
            cls._find_via_app_paths,
            cls._find_via_uninstall_registry,
            cls._find_via_path,
        ):
            result = finder(name)
            if result is not None:
                return result
        return ""

    @classmethod
    def _find_macos_app(cls, name: str) -> str:
        """Find app on macOS."""
        if name in cls.MACOS_APPS:
            app_name = cls.MACOS_APPS[name]
        else:
            app_name = name
        # Sanitize to prevent shell injection
        safe_name = app_name.replace('"', '').replace('&', '').replace(';', '')
        return f'open -a "{safe_name}"'

    @classmethod
    def _find_linux_app(cls, name: str) -> str:
        """Find app on Linux."""
        if name in cls.LINUX_APPS:
            cmd = cls.LINUX_APPS[name]
            if shutil.which(cmd):
                return cmd
        # Try the name directly
        if shutil.which(name):
            return name
        return ""


class CommandEngine:
    """命令执行引擎 - 解析 AI 意图并执行系统命令"""

    # Dangerous commands that require confirmation. Tested in IGNORECASE.
    # Order matters — broader / higher-risk patterns first.
    DANGEROUS_PATTERNS = [
        # Filesystem destruction
        r"\brm\s+-[a-zA-Z]*[rf]",               # rm with -r or -f (any combo)
        r"\brm\s+--recursive",
        r"\brm\s+--force",
        r"\brmdir\s+/[sS]\b",
        r"\brd\s+/[sS]\b",                          # rd alias for rmdir
        r"\bdel\s+/[fFsSQq]",
        r"\bdel\s+/",                                # del with any flag
        r"\bdelete\b",
        r"\berase\b",
        r"\bformat\b",
        r"\bmove\s+.+\s+[a-zA-Z]:\\",
        # Privilege escalation
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bpoweroff\b",
        r"\bhalt\b",
        r"\blogoff\b",
        # User / process kill
        r"\btaskkill\s+/[fF]",
        r"\bstop-process\b",
        r"\bkill\s+-9\b",
        r"\bkillall\b",
        r"\bnet\s+user\b",
        r"\bnet\s+localgroup\b",
        r"\bnet\s+share\b",
        r"\bnet\s+use\b",
        # Registry / system
        r"\breg\s+(delete|add)\b",
        r"\bsc\s+(delete|stop)\b",
        r"\bbcdedit\b",
        r"\bdiskpart\b",
        r"\bcipher\s+/w\b",
        r"\bicacls\b",
        r"\btakeown\b",
        r"\bschtasks\s+/create\b",
        # PowerShell destructive cmdlets
        r"\bremove-item\b",
        r"\bclear-content\b",
        r"\bremove-variable\b",
        r"\binvoke-expression\b",
        r"\biex\b",
        r"\bstart-process\b",
        r"\bpowershell\b.*-enc(odedcommand)?\b",    # base64-encoded payloads
        # Script hosts that can execute arbitrary code
        r"\bwscript\b",
        r"\bcscript\b",
        r"\bmshta\b",
        r"\bcertutil\b.*-urlcache",
        r"\bbitsadmin\b.*/transfer",
        # Redirectors / pipes that can fan out
        r"\|\s*(?:sh|bash|cmd|powershell|invoke-expression|iex)\b",
        r"\bcurl\b.*\|\s*(?:sh|bash)",
        # Command chaining that defeats single-line check
        r"[;&|]{1,2}\s*(?:rm|del|format|reg\s+delete|remove-item)\b",
        # P0-1b: additional dangerous patterns (bypass techniques)
        r"\bpython\s+-c\b",                    # python -c "import os;os.system(...)"
        r"\bpython3?\s+-m\s+subprocess\b",     # python -m subprocess
        r"\bcmd\s+/c\b",                       # cmd /c "arbitrary command"
        r"\bcmd\s+/k\b",                       # cmd /k (keeps window open)
        r"\bmsiexec\b",                        # MSI installer
        r"\bcertutil\s+-decode\b",             # certutil decode (file drop)
        r"\bcertutil\s+-urlcache\b",           # certutil URL download
        r"\bbitsadmin\b",                      # BITS download (already partial)
        r"\brundll32\b",                       # DLL loading
        r"\bregsvr32\b",                       # COM registration
        r"\bmsconfig\b",                       # system config
        r"\bnetsh\b",                          # network shell
        r"\bftp\b",                            # FTP client
        r"\btftp\b",                           # trivial FTP
        r"\battrib\s+[+-][shr]",              # attrib hide/unhide system files
    ]

    def __init__(self, event_engine=None, user_config: dict | None = None):
        self.event_engine = event_engine
        self.user_config = user_config or {}
        self._command_history = []
        self._pending_confirmations: list[tuple[str, str]] = []

    @property
    def _pending_confirmation(self):
        """Backward-compatible view of the first queued confirmation."""
        return self._pending_confirmations[0] if self._pending_confirmations else None

    @_pending_confirmation.setter
    def _pending_confirmation(self, value):
        self._pending_confirmations = [] if value is None else [value]

    def parse_and_execute(self, ai_response: str, auto_confirm: bool = False) -> list:
        """Parse AI response for executable commands and execute them.

        This is the main entry point. The AI response may contain:
        - Direct commands wrapped in [CMD:...] tags
        - App open requests wrapped in [APP:...] tags
        - Shell commands wrapped in [SHELL:...] tags
        - Claude Code instructions wrapped in [CLAUDE:...] tags

        Args:
            ai_response: The full AI response text
            auto_confirm: If True, skip confirmation for dangerous commands

        Returns:
            List of CommandResult objects
        """
        results = []

        # Tag regex is forgiving on the right bracket — sometimes the model
        # omits it (truncation, trailing newline). We accept either.
        cmd_matches = re.findall(r'\[CMD:([^\]\n]+)\]?', ai_response)
        app_matches = re.findall(r'\[APP:([^\]\n]+)\]?', ai_response)
        shell_matches = re.findall(r'\[SHELL:([^\]\n]+)\]?', ai_response)
        claude_matches = re.findall(r'\[CLAUDE:([^\]\n]+)\]?', ai_response)

        # Execute app commands
        for app_name in app_matches:
            app_name = app_name.strip()
            result = self.open_app(app_name)
            results.append(result)

        # Execute direct commands — P0-1a: always require confirmation
        # for [CMD:] tags (user must explicitly confirm)
        for cmd in cmd_matches:
            cmd = cmd.strip()
            result = self.execute_command(cmd, auto_confirm=auto_confirm,
                                          force_confirm=True)
            results.append(result)

        # Execute shell commands — every model-generated shell command needs
        # explicit user approval. A blacklist is not a security boundary.
        for cmd in shell_matches:
            cmd = cmd.strip()
            result = self.execute_shell(cmd, auto_confirm=auto_confirm,
                                        force_confirm=True)
            results.append(result)

        # Claude Code can modify files and run tools, so it also requires
        # explicit approval before leaving the chat response parser.
        for instruction in claude_matches:
            instruction = instruction.strip()
            if not auto_confirm:
                self._pending_confirmations.append(("claude", instruction))
                results.append(CommandResult(
                    success=False,
                    command=f"claude: {instruction}",
                    error="🔒 Claude Code 操作需要确认才能执行。",
                    requires_confirmation=True,
                ))
            else:
                results.append(self.execute_claude_code(instruction))

        # If no tagged commands found, try natural language parsing
        if not results:
            result = self._try_natural_command(ai_response)
            if result:
                results.append(result)

        return results

    @staticmethod
    def _external_launch_env() -> dict[str, str]:
        """Return an environment safe for launching non-BuddyDesk apps.

        BuddyDesk pins PySide6's Qt plugin directory at startup. External Qt
        applications such as WeChat must not inherit that path: loading a
        PySide6 `qwindows.dll` into WeChat produces its "no Qt platform
        plugin could be initialized" crash dialog.
        """
        env = os.environ.copy()
        for key in (
            "QT_QPA_PLATFORM_PLUGIN_PATH",
            "QT_PLUGIN_PATH",
            "QT_QPA_PLATFORM",
            "QT_DEBUG_PLUGINS",
        ):
            env.pop(key, None)
        return env

    def open_app(self, app_name: str) -> CommandResult:
        """Open an application by name.

        Args:
            app_name: Application name (supports Chinese and English)

        Returns:
            CommandResult with execution status
        """
        cmd = AppRegistry.find_app(app_name)

        if not cmd:
            return CommandResult(
                success=False,
                command=f"open:{app_name}",
                error=f"未找到应用: {app_name}",
            )

        # Only verified files and a small system-command allowlist reach this
        # method. Never re-interpret a discovered path as shell text.
        _SYSTEM_COMMANDS = {"cmd", "explorer", "calc", "notepad", "snippingtool", "powershell"}

        try:
            if sys.platform == "win32":
                external_env = self._external_launch_env()
                if cmd in _SYSTEM_COMMANDS:
                    subprocess.Popen(
                        [cmd],
                        shell=False,
                        creationflags=_NO_WINDOW,
                        env=external_env,
                    )
                elif cmd.startswith('"') and cmd.endswith('"'):
                    launch_path = cmd[1:-1]
                    extension = os.path.splitext(launch_path)[1].lower()
                    if not AppRegistry._path_launchable(launch_path):
                        raise FileNotFoundError(launch_path)
                    if extension in {".lnk", ".cmd", ".bat"}:
                        # os.startfile() cannot receive an isolated env. Launch
                        # through cmd/start with the cleaned child environment
                        # so Qt apps never inherit BuddyDesk's PySide6 plugins.
                        subprocess.Popen(
                            ["cmd", "/d", "/s", "/c", "start", "", launch_path],
                            shell=False,
                            creationflags=_NO_WINDOW,
                            env=external_env,
                        )
                    elif extension == ".exe":
                        subprocess.Popen(
                            [launch_path],
                            shell=False,
                            cwd=os.path.dirname(launch_path) or None,
                            creationflags=_NO_WINDOW,
                            env=external_env,
                        )
                    else:
                        raise ValueError(f"不支持的应用类型: {extension or '无扩展名'}")
                else:
                    raise ValueError("未验证的应用启动目标")
            else:
                # macOS/Linux: 'open -a' and bare commands need the shell.
                subprocess.Popen(cmd, shell=True)

            if self.event_engine:
                from engine.event_engine import EventEngine
                self.event_engine.record("command_execute", {
                    "type": "open_app",
                    "app": app_name,
                    "command": cmd,
                    "success": True,
                })

            return CommandResult(
                success=True,
                command=f"open:{app_name}",
                output=f"已打开: {app_name}",
            )

        except FileNotFoundError as e:
            return CommandResult(
                success=False,
                command=f"open:{app_name}",
                error=f"应用文件不存在: {e}",
            )
        except PermissionError as e:
            return CommandResult(
                success=False,
                command=f"open:{app_name}",
                error=f"权限不足，无法启动 {app_name}: {e}",
            )
        except Exception as e:
            return CommandResult(
                success=False,
                command=f"open:{app_name}",
                error=f"打开应用失败: {e}",
            )

    def execute_command(self, cmd: str, auto_confirm: bool = False,
                        force_confirm: bool = False) -> CommandResult:
        """Execute a system command.

        Args:
            cmd: Command to execute
            auto_confirm: Skip confirmation for dangerous commands
            force_confirm: Always require confirmation (for [SHELL:]/[CMD:] tags)

        Returns:
            CommandResult with execution status
        """
        # P0-1a: [SHELL:]/[CMD:] tags always require confirmation unless
        # the caller explicitly set auto_confirm (e.g. user replied "确认执行").
        is_dangerous = self._is_dangerous(cmd)
        if not auto_confirm and (force_confirm or is_dangerous):
            self._pending_confirmations.append(("shell", cmd))
            if is_dangerous:
                return CommandResult(
                    success=False,
                    command=cmd,
                    error="⚠️ 危险命令，需要确认才能执行。请在聊天中回复'确认执行'。",
                    requires_confirmation=True,
                )
            return CommandResult(
                success=False,
                command=cmd,
                error="🔒 命令需要确认才能执行。请在聊天中回复'确认执行'。",
                requires_confirmation=True,
            )

        try:
            # Use shell=False for safety. Parse with shlex.split() to
            # handle quoted arguments. Fall back to shell=True only when
            # the command contains shell-specific syntax that shlex cannot
            # handle (pipes, redirects, env variable expansion, etc.).
            _shell_specials = set('|><&^')
            _needs_shell = (
                any(c in cmd for c in _shell_specials)
                or '$' in cmd
                or '`' in cmd
            )
            if _needs_shell:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=_NO_WINDOW,
                )
            else:
                try:
                    args = shlex.split(cmd, posix=False)
                except ValueError:
                    args = None

                if args is not None:
                    try:
                        result = subprocess.run(
                            args,
                            shell=False,
                            capture_output=True,
                            text=True,
                            timeout=30,
                            encoding="utf-8",
                            errors="replace",
                            creationflags=_NO_WINDOW,
                        )
                    except FileNotFoundError:
                        # Windows shell builtins (echo, dir, etc.) are not
                        # standalone executables — fall back to cmd /c.
                        result = subprocess.run(
                            cmd,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=30,
                            encoding="utf-8",
                            errors="replace",
                            creationflags=_NO_WINDOW,
                        )
                else:
                    result = subprocess.run(
                        cmd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        encoding="utf-8",
                        errors="replace",
                        creationflags=_NO_WINDOW,
                    )

            output = result.stdout + result.stderr
            success = result.returncode == 0

            self._command_history.append({
                "command": cmd,
                "output": output[:1000],
                "success": success,
                "timestamp": datetime.now().isoformat(),
            })

            if self.event_engine:
                from engine.event_engine import EventEngine
                self.event_engine.record("command_execute", {
                    "type": "shell",
                    "command": _redact_command(cmd),
                    "success": success,
                })

            return CommandResult(
                success=success,
                command=cmd,
                output=output[:2000],
                error="" if success else output[:500],
            )

        except subprocess.TimeoutExpired:
            return CommandResult(
                success=False,
                command=cmd,
                error="命令执行超时（30秒）",
            )
        except Exception as e:
            return CommandResult(
                success=False,
                command=cmd,
                error=f"执行失败: {e}",
            )

    def execute_shell(self, cmd: str, auto_confirm: bool = False,
                      force_confirm: bool = False) -> CommandResult:
        """Execute a shell command (alias for execute_command)."""
        return self.execute_command(cmd, auto_confirm=auto_confirm,
                                    force_confirm=force_confirm)

    def execute_claude_code(self, instruction: str) -> CommandResult:
        """Execute a command via Claude Code CLI.

        Args:
            instruction: Natural language instruction for Claude Code

        Returns:
            CommandResult with execution status
        """
        claude_path = self.user_config.get("claude_cli_path") or config.CLAUDE_CLI_PATH

        try:
            # Use claude --print for non-interactive mode
            result = subprocess.run(
                [claude_path, "--print", instruction],
                capture_output=True,
                text=True,
                timeout=120,
                encoding="utf-8",
                errors="replace",
                creationflags=_NO_WINDOW,
            )

            output = result.stdout.strip()
            success = result.returncode == 0

            if self.event_engine:
                from engine.event_engine import EventEngine
                self.event_engine.record("command_execute", {
                    "type": "claude_code",
                    "instruction": _redact_command(instruction),
                    "success": success,
                })

            return CommandResult(
                success=success,
                command=f"claude: {instruction}",
                output=output,
                error="" if success else result.stderr[:500],
            )

        except FileNotFoundError:
            return CommandResult(
                success=False,
                command=f"claude: {instruction}",
                error="Claude Code CLI 未安装。请先安装 Claude Code。",
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                success=False,
                command=f"claude: {instruction}",
                error="Claude Code 执行超时（120秒）",
            )
        except Exception as e:
            return CommandResult(
                success=False,
                command=f"claude: {instruction}",
                error=f"Claude Code 执行失败: {e}",
            )

    def confirm_pending(self) -> CommandResult:
        """Confirm and execute the oldest pending shell or Claude operation."""
        if not self._pending_confirmations:
            return CommandResult(
                success=False,
                error="没有待确认的命令",
            )
        kind, value = self._pending_confirmations.pop(0)
        if kind == "claude":
            return self.execute_claude_code(value)
        return self.execute_command(value, auto_confirm=True)

    def cancel_pending(self):
        """Cancel the oldest pending operation."""
        if self._pending_confirmations:
            self._pending_confirmations.pop(0)

    def _is_dangerous(self, cmd: str) -> bool:
        """Check if a command is potentially dangerous."""
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True
        return False

    def _try_natural_command(self, text: str) -> CommandResult:
        """Try to parse natural language commands.

        Detects patterns like:
        - "打开微信"         -> open_app (safe, app lookup only)
        - "启动 VS Code"     -> open_app (safe, app lookup only)
        - "open Chrome"      -> open_app (safe, app lookup only)
        - "运行 python script.py" -> execute_command with confirmation
        - "run some_command"  -> execute_command with confirmation

        The "运行/run" patterns route through execute_command so the
        existing dangerous-command detection and confirmation flow
        are applied before anything is executed.

        Args:
            text: User/AI message text

        Returns:
            CommandResult or None if no command detected
        """
        text = text.strip()

        # --- Safe app-launch patterns (open_app path) ---
        safe_cn = [
            (r"打开(\S+)", 1),    # 打开微信
            (r"启动(\S+)", 1),    # 启动Chrome
            (r"开启(\S+)", 1),    # 开启Terminal
        ]
        for pattern, group in safe_cn:
            match = re.search(pattern, text)
            if match:
                return self.open_app(match.group(group))

        safe_en = [
            (r"open\s+(\S+)", 1),
            (r"launch\s+(\S+)", 1),
        ]
        for pattern, group in safe_en:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return self.open_app(match.group(group))

        # --- Execution patterns (require confirmation) ---
        exec_cn = [
            (r"运行\s+(.+)$", 1),  # 运行python script.py (greedy to capture full command)
        ]
        exec_en = [
            (r"run\s+(.+)$", 1),   # run python script.py
            (r"start\s+(.+)$", 1), # start some_command
        ]

        for pattern, group in exec_cn + exec_en:
            match = re.search(pattern, text)
            if match:
                cmd = match.group(group).strip()
                # Route through execute_command which applies
                # dangerous-command detection and confirmation.
                return self.execute_command(cmd, force_confirm=True)

        return None

    def get_history(self, count: int = 20) -> list:
        """Get recent command execution history."""
        return self._command_history[-count:]

    def search_and_open(self, query: str) -> CommandResult:
        """Search for an app and open it (fuzzy match).

        Args:
            query: Partial app name to search for

        Returns:
            CommandResult with execution status
        """
        # Try exact match first
        result = self.open_app(query)
        if result.success:
            return result

        # Try fuzzy match in registry
        query_lower = query.lower()
        if sys.platform == "win32":
            registry = AppRegistry.WINDOWS_APPS
        elif sys.platform == "darwin":
            registry = AppRegistry.MACOS_APPS
        else:
            registry = AppRegistry.LINUX_APPS

        for name in registry:
            if query_lower in name.lower() or name.lower() in query_lower:
                result = self.open_app(name)
                if result.success:
                    return result

        return CommandResult(
            success=False,
            command=f"search:{query}",
            error=f"未找到匹配的应用: {query}\n提示：你可以直接说应用名称，比如'打开微信'、'打开Chrome'",
        )
