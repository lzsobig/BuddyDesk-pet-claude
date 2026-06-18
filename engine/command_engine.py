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

# Suppress CMD window flash on Windows
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _read_lnk_target(lnk_path: str) -> str:
    """Resolve a Windows .lnk shortcut to its target executable.

    Tries the COM IShellLink first (most reliable); falls back to parsing
    the binary .lnk format directly when COM is unavailable (e.g. headless
    environments). Returns empty string on any failure.
    """
    # Try COM first
    try:
        import win32com.client  # type: ignore
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(lnk_path)
        target = shortcut.Targetpath
        if target and os.path.exists(target):
            return target
    except Exception:
        pass

    # Fall back to raw .lnk parsing (no dependencies)
    try:
        with open(lnk_path, "rb") as f:
            data = f.read()
        # Locate the LinkInfo block (0x4C 0x00 0x00 0x00 marker)
        marker = b"\x4c\x00\x00\x00"
        idx = data.find(marker)
        if idx < 0:
            return ""
        # Skip the first 28 bytes of the LinkInfo header
        base = idx + 28
        # LocalBasePath offset is at base+4 (uint32 LE)
        if base + 8 > len(data):
            return ""
        local_off = int.from_bytes(data[base + 4:base + 8], "little")
        if local_off == 0 or base + local_off + 4 > len(data):
            return ""
        # Read null-terminated UTF-16LE string at local_off
        end = data.find(b"\x00\x00", base + local_off)
        if end < 0:
            return ""
        raw = data[base + local_off:end]
        return raw.decode("utf-16le", errors="ignore")
    except Exception:
        return ""


class CommandResult:
    """命令执行结果"""

    def __init__(self, success: bool, output: str = "", command: str = "", error: str = ""):
        self.success = success
        self.output = output
        self.command = command
        self.error = error
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
        """Look up *name* in WINDOWS_APPS and search Program Files / LocalAppData."""
        if name not in cls.WINDOWS_APPS or cls.WINDOWS_APPS[name] is None:
            return None
        subpath, exe = cls.WINDOWS_APPS[name]
        for program_files in [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ]:
            if not program_files:
                continue
            if "*" in subpath:
                import glob
                matches = glob.glob(os.path.join(program_files, subpath))
                for match in matches:
                    full_path = os.path.join(match, exe)
                    if os.path.exists(full_path):
                        return f'"{full_path}"'
            else:
                full_path = os.path.join(program_files, subpath, exe)
                if os.path.exists(full_path):
                    return f'"{full_path}"'
        return None

    @staticmethod
    def _find_via_aliases(name: str) -> list[str]:
        """Return the list of search keys (alias + original) for Start Menu matching.

        Chinese names are mapped to English equivalents so .lnk shortcut
        filenames can be matched.  If no alias exists, returns ``[name]``.
        """
        alias = {
            "微信": "wechat",
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
        """Search Start Menu .lnk shortcuts for a matching application."""
        search_keys = cls._find_via_aliases(name)
        try:
            import glob
            start_dirs = [
                os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
                os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
            ]
            for d in start_dirs:
                if not d or not os.path.isdir(d):
                    continue
                candidates: list[tuple[int, str]] = []  # (priority, target)
                for lnk in glob.glob(os.path.join(d, "**", "*.lnk"), recursive=True):
                    base = os.path.splitext(os.path.basename(lnk))[0]
                    base_lower = base.lower()
                    matched = any(
                        len(k) >= 2 and k in base_lower for k in search_keys
                    )
                    if not matched:
                        continue
                    target = _read_lnk_target(lnk)
                    if not target or not os.path.exists(target):
                        continue
                    if "uninstall" in target.lower():
                        candidates.append((5, target))
                    else:
                        candidates.append((0, target))
                if candidates:
                    candidates.sort(key=lambda c: c[0])
                    return f'"{candidates[0][1]}"'
        except Exception:
            pass
        return None

    @staticmethod
    def _find_via_path(name: str) -> Optional[str]:
        """Try ``where <name>`` to find the executable on PATH."""
        try:
            result = subprocess.run(
                ["where", name],
                capture_output=True, text=True, timeout=5,
                creationflags=_NO_WINDOW,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")[0]
        except Exception:
            pass
        return None

    # -- Main orchestrator --

    @classmethod
    def _find_windows_app(cls, name: str) -> str:
        """Find app on Windows.

        Tries each lookup strategy in priority order and returns the first
        match.  Falls back to a sanitized ``start`` command when nothing is
        found.
        """
        for finder in (
            cls._find_via_special,
            cls._find_via_registry,
            cls._find_via_start_menu,
            cls._find_via_path,
        ):
            result = finder(name)
            if result is not None:
                return result

        # Final fallback: sanitize name to prevent shell injection via
        # metacharacters (P0-1b).
        safe_name = name
        for ch in ('"', '&', '|', ';', '^', '<', '>', '%', '!'):
            safe_name = safe_name.replace(ch, '')
        return f'start "" "{safe_name}"'

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

    def __init__(self, event_engine=None):
        self.event_engine = event_engine
        self._command_history = []
        self._pending_confirmation = None  # Command waiting for user confirmation

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

        # Execute shell commands — P0-1a: dangerous commands require
        # confirmation; safe shell commands execute directly
        for cmd in shell_matches:
            cmd = cmd.strip()
            result = self.execute_shell(cmd, auto_confirm=auto_confirm,
                                        force_confirm=False)
            results.append(result)

        # Execute Claude Code commands
        for instruction in claude_matches:
            instruction = instruction.strip()
            result = self.execute_claude_code(instruction)
            results.append(result)

        # If no tagged commands found, try natural language parsing
        if not results:
            result = self._try_natural_command(ai_response)
            if result:
                results.append(result)

        return results

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

        try:
            if sys.platform == "win32":
                # Try shell=False first for safety; fall back to shell=True
                # only for commands that genuinely need the shell (start, cmd,
                # explorer, calc, and other built-in shell commands).
                _needs_shell = (
                    cmd.startswith("start ")
                    or cmd in ("cmd", "explorer", "calc", "notepad",
                               "snippingtool", "powershell")
                )
                if not _needs_shell:
                    # Extract executable from quoted path (e.g. '"C:\...\app.exe"')
                    exe_path = cmd.strip().strip('"')
                    subprocess.Popen(
                        [exe_path],
                        shell=False,
                        creationflags=_NO_WINDOW,
                    )
                else:
                    subprocess.Popen(
                        cmd,
                        shell=True,
                        creationflags=_NO_WINDOW,
                    )
            else:
                # macOS/Linux: 'open -a' and bare commands need the shell
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
            self._pending_confirmation = cmd
            if is_dangerous:
                return CommandResult(
                    success=False,
                    command=cmd,
                    error="⚠️ 危险命令，需要确认才能执行。请在聊天中回复'确认执行'。",
                )
            return CommandResult(
                success=False,
                command=cmd,
                error="🔒 命令需要确认才能执行。请在聊天中回复'确认执行'。",
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
                    "command": cmd,
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
        claude_path = config.CLAUDE_CLI_PATH

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
                    "instruction": instruction,
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
        """Confirm and execute the pending dangerous command."""
        if not self._pending_confirmation:
            return CommandResult(
                success=False,
                error="没有待确认的命令",
            )
        cmd = self._pending_confirmation
        self._pending_confirmation = None
        return self.execute_command(cmd, auto_confirm=True)

    def cancel_pending(self):
        """Cancel the pending dangerous command."""
        self._pending_confirmation = None

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
