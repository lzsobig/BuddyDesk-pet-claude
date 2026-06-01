"""
AI Backend Abstraction Layer

Supports two backends:
1. Claude Code CLI - Deep integration with system operations
2. OpenAI API - Compatible with DeepSeek/NVIDIA/DeepSeek etc.

Key improvements over original:
- Proper Claude CLI discovery (shutil.which + fallback paths)
- Stream cancellation support
- System prompt drives command tag generation
"""
import json
import shutil
import subprocess
import threading
import os
import sys
from abc import ABC, abstractmethod
from typing import Callable, Optional

import config


# ============================================================
# System Prompt - The brain of the assistant
# ============================================================

SYSTEM_PROMPT = """你是 Hermes Pet Win，一个 Windows 桌面 AI 助手。你不仅是一个聊天机器人，你还能直接帮助用户操作电脑。

## 你的核心能力

### 1. 打开应用
用户说"打开XXX"时，你在回复末尾添加标签来触发操作：
- 格式: `[APP:应用名]`
- 示例: 用户说"打开微信" → 你回复"好的，帮你打开微信~ [APP:微信]"
- 示例: 用户说"打开Chrome" → 你回复"马上打开！ [APP:chrome]"
- 示例: 用户说"我要用VS Code写代码" → 你回复"好的，打开VS Code！ [APP:vscode]"

### 2. 执行系统命令
用户需要执行命令时，使用标签：
- 格式: `[SHELL:命令]`
- 示例: 用户说"查看当前目录" → 你回复 `当前目录内容如下：[SHELL:dir]`
- 示例: 用户说"看看IP地址" → 你回复 `正在查询... [SHELL:ipconfig]`

### 3. 通过 Claude Code 执行复杂任务
当用户需要复杂的编程、文件操作、项目创建等任务时：
- 格式: `[CLAUDE:指令描述]`
- 示例: 用户说"帮我创建一个React项目" → 你回复"好的，让 Claude Code 来帮你！ [CLAUDE:创建一个React项目]"

### 4. 常见应用名映射
用户可能用各种名字指代应用，你需要在 [APP:...] 中使用标准名：
- 微信/WeChat → [APP:微信]
- 谷歌浏览器/Chrome → [APP:chrome]
- VS Code/代码编辑器 → [APP:vscode]
- QQ → [APP:qq]
- 钉钉 → [APP:钉钉]
- 飞书 → [APP:飞书]
- Telegram → [APP:telegram]
- Discord → [APP:discord]
- Steam → [APP:steam]
- Spotify → [APP:spotify]
- Notion → [APP:notion]
- Figma → [APP:figma]
- Terminal/终端 → [APP:terminal]
- 记事本 → [APP:notepad]
- 计算器 → [APP:计算器]
- 文件管理器 → [APP:文件管理器]
- Word → [APP:word]
- Excel → [APP:excel]
- PPT/PowerPoint → [APP:ppt]

## 行为准则
1. 友好、简洁，像一个可爱的桌面宠物助手
2. 执行操作时先确认用户意图（除非很明确）
3. 危险操作（如删除文件）必须警告
4. 不确定的应用名，直接用用户说的名字
5. 回复要简短有趣，不要长篇大论
6. 可以适当使用 emoji 增加趣味性
7. 当用户只是闲聊时，不需要添加任何命令标签
"""


def _find_claude_cli(cli_path: str = None) -> str:
    """Find Claude CLI with proper discovery.

    Checks: explicit path > shutil.which > common fallback paths.
    Returns empty string if not found.
    """
    if cli_path and cli_path != "claude":
        if os.path.exists(cli_path):
            return cli_path

    # shutil.which finds .cmd/.bat on Windows when shell=True is used
    found = shutil.which("claude")
    if found:
        return found

    candidates = [
        os.path.expanduser("~/.npm-global/bin/claude"),
        os.path.expanduser("~/node_modules/.bin/claude"),
        "C:/npm-global/claude.cmd",
        "/usr/local/bin/claude",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c

    return ""


class AIBackend(ABC):
    """Abstract base class for AI backends."""

    @abstractmethod
    def send_message(self, messages: list, on_chunk=None) -> str:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def get_name(self) -> str:
        pass

    def cancel(self):
        """Cancel the current streaming request. Override in subclasses."""
        pass

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT


class ClaudeCodeBackend(AIBackend):
    """Claude Code CLI backend - deep system integration."""

    def __init__(self, cli_path: str = None, working_dir: str = None,
                 model: str = None):
        self.cli_path = _find_claude_cli(cli_path) or "claude"
        self.working_dir = working_dir or os.path.expanduser("~")
        self.model = model or "claude-sonnet-4-20250514"
        self._cancel_event = threading.Event()
        self._process = None

    def send_message(self, messages: list, on_chunk=None) -> str:
        self._cancel_event.clear()
        prompt_parts = [f"[System Instructions]\n{self.get_system_prompt()}\n"]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"[System] {content}")
            elif role == "user":
                prompt_parts.append(f"[User] {content}")
            elif role == "assistant":
                prompt_parts.append(f"[Assistant] {content}")
        prompt = "\n".join(prompt_parts)

        # Try streaming first; on any error, fall back to non-streaming
        # but surface the streaming error in logs instead of swallowing it.
        stream_error: str | None = None
        try:
            self._process = subprocess.Popen(
                [self.cli_path, "--print", "--output-format", "stream-json",
                 "--verbose", "--model", self.model],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=self.working_dir,
                shell=True,
            )

            self._process.stdin.write(prompt)
            self._process.stdin.close()

            full_response = ""
            saw_json_chunk = False
            for line in self._process.stdout:
                if self._cancel_event.is_set():
                    self._process.terminate()
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    saw_json_chunk = True
                    if data.get("type") == "assistant" and "message" in data:
                        content = data["message"].get("content", "")
                        if isinstance(content, list):
                            for block in content:
                                if block.get("type") == "text":
                                    text = block.get("text", "")
                                    full_response += text
                                    if on_chunk:
                                        on_chunk(text)
                        elif isinstance(content, str):
                            full_response += content
                            if on_chunk:
                                on_chunk(content)
                except json.JSONDecodeError:
                    # Stream produced non-JSON — fall back to non-streaming
                    stderr = self._process.stderr.read() if self._process.stderr else ""
                    stream_error = f"stream produced non-JSON output (stderr: {stderr[:200]})"
                    break

            try:
                self._process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                stream_error = "stream timed out (120s)"
                self._process = None

            if self._cancel_event.is_set():
                return full_response.strip() if full_response else ""

            if self._process is not None and self._process.returncode != 0 and not full_response:
                stderr = self._process.stderr.read() if self._process.stderr else ""
                stream_error = f"Claude CLI error: {stderr[:500]}"

            # If we got nothing back and the stream failed, fall through
            if full_response or (saw_json_chunk and stream_error is None):
                self._process = None
                return full_response.strip() if full_response else ""
        except FileNotFoundError:
            raise RuntimeError(
                f"Claude CLI not found at '{self.cli_path}'. "
                "Please install Claude Code CLI first."
            )

        # Fallback: non-streaming
        if stream_error:
            print(f"[ClaudeCode] streaming failed ({stream_error}); falling back to non-streaming")
        try:
            result = subprocess.run(
                [self.cli_path, "--print", "--model", self.model],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=120,
                encoding="utf-8",
                errors="replace",
                cwd=self.working_dir,
                shell=True,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI request timed out (120s).")

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Unknown error"
            raise RuntimeError(f"Claude CLI error: {error_msg}")

        response = result.stdout.strip()

        if on_chunk and response:
            chunk_size = max(1, len(response) // 20)
            for i in range(0, len(response), chunk_size):
                if self._cancel_event.is_set():
                    break
                on_chunk(response[i:i + chunk_size])

        return response

    def cancel(self):
        self._cancel_event.set()
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                [self.cli_path, "--version"],
                capture_output=True, text=True, timeout=5, shell=True,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_name(self) -> str:
        return "Claude Code"


class OpenAIBackend(AIBackend):
    """OpenAI-compatible API backend."""

    def __init__(self, api_key: str = None, api_base: str = None, model: str = None):
        self.api_key = api_key or config.DEFAULT_API_KEY
        self.api_base = (api_base or config.DEFAULT_API_BASE).rstrip("/")
        self.model = model or config.DEFAULT_MODEL
        self._client = None
        self._cancel_event = threading.Event()

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise RuntimeError("openai package not installed. Run: pip install openai")
            self._client = OpenAI(api_key=self.api_key, base_url=self.api_base)
        return self._client

    def send_message(self, messages: list, on_chunk=None) -> str:
        self._cancel_event.clear()
        client = self._get_client()

        has_system = any(m.get("role") == "system" for m in messages)
        all_messages = []
        if not has_system:
            all_messages.append({"role": "system", "content": self.get_system_prompt()})
        all_messages.extend(messages)

        try:
            stream = client.chat.completions.create(
                model=self.model,
                messages=all_messages,
                stream=True,
                temperature=0.7,
                max_tokens=4096,
            )

            full_response = ""
            for chunk in stream:
                if self._cancel_event.is_set():
                    break
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_response += text
                    if on_chunk:
                        on_chunk(text)

            return full_response

        except Exception as e:
            raise RuntimeError(f"API error: {e}")

    def cancel(self):
        self._cancel_event.set()

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def get_name(self) -> str:
        return f"OpenAI ({self.model})"


class AnthropicDirectBackend(AIBackend):
    """Direct Anthropic API backend — calls the API endpoint (proxy or
    direct) using requests, bypassing the Claude CLI entirely.

    Detects the proxy URL from env vars (ANTHROPIC_BASE_URL) or
    falls back to https://api.anthropic.com.
    """

    DEFAULT_PROXY = "http://127.0.0.1:15721"
    DEFAULT_MODEL = "mimo-v2.5"

    def __init__(self, api_base: str = None, api_key: str = None, model: str = None):
        import os
        from urllib.parse import urlparse
        raw_base = (
            api_base
            or os.environ.get("ANTHROPIC_BASE_URL", self.DEFAULT_PROXY)
        )
        # Always use scheme://host:port — strip any path suffix like
        # /claude-desktop that some proxy configs add to the env var.
        parsed = urlparse(raw_base)
        self.api_base = f"{parsed.scheme}://{parsed.netloc}"
        self.api_key = api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        self.model = model or self.DEFAULT_MODEL
        self._cancel_event = threading.Event()

    def _url(self) -> str:
        return f"{self.api_base}/v1/messages"

    def send_message(self, messages: list, on_chunk=None) -> str:
        import requests
        self._cancel_event.clear()

        # Build Anthropic-format messages
        anthropic_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                continue  # system prompt is separate
            anthropic_messages.append({"role": role, "content": content})

        payload = {
            "model": self.model,
            "system": self.get_system_prompt(),
            "messages": anthropic_messages,
            "max_tokens": 4096,
            "stream": True,
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        full_response = ""
        try:
            resp = requests.post(
                self._url(), json=payload, headers=headers,
                stream=True, timeout=120,
            )
            resp.raise_for_status()
            # Force UTF-8 decoding — proxies often omit charset in Content-Type,
            # causing requests to default to latin-1 which garbles CJK text.
            resp.encoding = "utf-8"

            for line in resp.iter_lines(decode_unicode=True):
                if self._cancel_event.is_set():
                    break
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    if data.get("type") == "content_block_delta":
                        delta = data.get("delta", {})
                        text = delta.get("text", "")
                        if text:
                            full_response += text
                            if on_chunk:
                                on_chunk(text)
                except json.JSONDecodeError:
                    continue

        except requests.RequestException as e:
            raise RuntimeError(f"Anthropic API error: {e}")

        return full_response

    def cancel(self):
        self._cancel_event.set()

    def is_available(self) -> bool:
        import requests
        try:
            resp = requests.post(
                self._url(), json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 5,
                },
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def get_name(self) -> str:
        return f"Anthropic Direct ({self.model})"


def create_backend(user_config: dict) -> AIBackend:
    """Factory function to create the appropriate backend.

    Priority:
    1. user_config["backend"] == "claude_code" → try AnthropicDirectBackend
       first (bypasses broken CLI); fall back to ClaudeCodeBackend.
    2. user_config["backend"] == "openai_api" → OpenAIBackend.
    3. Auto-detect: if a local proxy is reachable, use AnthropicDirectBackend.
    """
    backend_type = user_config.get("backend", config.DEFAULT_BACKEND)

    if backend_type == config.BACKEND_CLAUDE:
        # Try direct Anthropic API first (bypasses CLI model-routing issues)
        direct = AnthropicDirectBackend(
            api_base=user_config.get("anthropic_api_base", None),
            api_key=user_config.get("anthropic_api_key", None),
            model=user_config.get("claude_model", None),
        )
        if direct.is_available():
            return direct
        # Fall back to CLI
        return ClaudeCodeBackend(
            cli_path=user_config.get("claude_cli_path", config.CLAUDE_CLI_PATH),
            working_dir=user_config.get("working_dir", os.path.expanduser("~")),
            model=user_config.get("claude_model", None),
        )
    elif backend_type == config.BACKEND_OPENAI:
        return OpenAIBackend(
            api_key=user_config.get("openai_api_key", ""),
            api_base=user_config.get("openai_api_base", config.DEFAULT_API_BASE),
            model=user_config.get("openai_model", config.DEFAULT_MODEL),
        )
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")
