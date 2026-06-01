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
import subprocess
import threading
import re
import shutil
from datetime import datetime

import config


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

    @classmethod
    def _find_windows_app(cls, name: str) -> str:
        """Find app on Windows."""
        # Special commands
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
        if name in specials:
            return specials[name]

        # Look up in registry
        if name in cls.WINDOWS_APPS and cls.WINDOWS_APPS[name] is not None:
            subpath, exe = cls.WINDOWS_APPS[name]
            # Try Program Files
            for program_files in [
                os.environ.get("ProgramFiles", "C:\\Program Files"),
                os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
                os.environ.get("LOCALAPPDATA", ""),  # Some apps install here
            ]:
                if not program_files:
                    continue
                # Handle wildcards
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

        # Chinese → English alias lookup so we can match Start Menu shortcuts.
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

        # Also try the original name verbatim (in case the Start Menu entry
        # is named in the same language the user asked for, e.g. the
        # Chinese 微信 .lnk file). Whichever string is a substring of the
        # shortcut name wins.
        search_keys = [alias, name] if alias != name else [name]

        # Try the Start Menu shortcut — many Windows apps (e.g. 微信) only
        # install a Start Menu entry, no Program Files dir. We extract the
        # target .exe from the .lnk file. We prefer real .exe over Uninstall.
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
                    # Require the search key to be a substring of the shortcut
                    # name. The reverse direction is unsafe (wechat in
                    # wechatminiprogram would match the wrong .exe).
                    matched = any(
                        len(k) >= 2 and k in base_lower for k in search_keys
                    )
                    if not matched:
                        continue
                    target = _read_lnk_target(lnk)
                    if not target or not os.path.exists(target):
                        continue
                    # Prefer non-Uninstall executables
                    if "uninstall" in target.lower():
                        candidates.append((5, target))
                    else:
                        candidates.append((0, target))
                if candidates:
                    candidates.sort(key=lambda c: c[0])
                    return f'"{candidates[0][1]}"'
        except Exception:
            pass

        # Try `where` (PATH lookup)
        try:
            result = subprocess.run(
                ["where", name],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")[0]
        except Exception:
            pass

        # Final fallback: Windows `start` searches Start Menu + Apps & Features
        return f'start "" "{name}"'

    @classmethod
    def _find_macos_app(cls, name: str) -> str:
        """Find app on macOS."""
        if name in cls.MACOS_APPS:
            app_name = cls.MACOS_APPS[name]
            return f'open -a "{app_name}"'
        return f'open -a "{name}"'

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
        r"\brm\s+-rf?\b",
        r"\brmdir\s+/[sS]\b",
        r"\bdel\s+/[fFsSQq]",
        r"\bdelete\b",
        r"\berase\b",
        r"\bformat\b",
        r"\bmove\s+.+\s+[a-zA-Z]:\\",
        # Privilege escalation
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bpoweroff\b",
        r"\bhalt\b",
        # User / process kill
        r"\btaskkill\s+/[fF]",
        r"\bstop-process\b",
        r"\bkill\s+-9\b",
        r"\bkillall\b",
        r"\bnet\s+user\b",
        r"\bnet\s+localgroup\b",
        # Registry / system
        r"\breg\s+delete\b",
        r"\bsc\s+(delete|stop)\b",
        r"\bbcdedit\b",
        r"\bdiskpart\b",
        r"\bcipher\s+/w\b",
        # PowerShell destructive cmdlets
        r"\bremove-item\b",
        r"\bclear-content\b",
        r"\bremove-variable\b",
        # Redirectors / pipes that can fan out
        r"\|\s*(?:sh|bash|cmd|powershell|invoke-expression|iex)\b",
        r"\bcurl\b.*\|\s*(?:sh|bash)",
        # Command chaining that defeats single-line check
        r"[;&|]{1,2}\s*(?:rm|del|format|reg\s+delete|remove-item)\b",
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

        # Execute direct commands
        for cmd in cmd_matches:
            cmd = cmd.strip()
            result = self.execute_command(cmd, auto_confirm=auto_confirm)
            results.append(result)

        # Execute shell commands
        for cmd in shell_matches:
            cmd = cmd.strip()
            result = self.execute_shell(cmd, auto_confirm=auto_confirm)
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
                # Use subprocess with shell=True for Windows
                subprocess.Popen(cmd, shell=True)
            else:
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

    def execute_command(self, cmd: str, auto_confirm: bool = False) -> CommandResult:
        """Execute a system command.

        Args:
            cmd: Command to execute
            auto_confirm: Skip confirmation for dangerous commands

        Returns:
            CommandResult with execution status
        """
        # Check for dangerous commands
        if not auto_confirm and self._is_dangerous(cmd):
            self._pending_confirmation = cmd
            return CommandResult(
                success=False,
                command=cmd,
                error="⚠️ 危险命令，需要确认才能执行。请在聊天中回复'确认执行'。",
            )

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
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

    def execute_shell(self, cmd: str, auto_confirm: bool = False) -> CommandResult:
        """Execute a shell command (alias for execute_command)."""
        return self.execute_command(cmd, auto_confirm)

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
        - "打开微信"
        - "open Chrome"
        - "启动 VS Code"
        - "运行 python script.py"

        Args:
            text: User/AI message text

        Returns:
            CommandResult or None if no command detected
        """
        text = text.strip()

        # Chinese patterns
        cn_patterns = [
            r"打开(\S+)",          # 打开微信
            r"启动(\S+)",          # 启动Chrome
            r"运行(\S+)",          # 运行python
            r"开启(\S+)",          # 开启Terminal
        ]

        for pattern in cn_patterns:
            match = re.search(pattern, text)
            if match:
                app_name = match.group(1)
                return self.open_app(app_name)

        # English patterns
        en_patterns = [
            r"open\s+(\S+)",
            r"launch\s+(\S+)",
            r"start\s+(\S+)",
            r"run\s+(\S+)",
        ]

        for pattern in en_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                app_name = match.group(1)
                return self.open_app(app_name)

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
