"""Tests for AI backend module"""
import unittest
from unittest.mock import patch, MagicMock

from ai.backend import (
    AIBackend,
    ClaudeCodeBackend,
    OpenAIBackend,
    create_backend,
    _find_claude_cli,
)


class TestFindClaudeCli(unittest.TestCase):
    def test_not_found(self):
        with patch("shutil.which", return_value=None):
            with patch("os.path.exists", return_value=False):
                result = _find_claude_cli()
                self.assertEqual(result, "")

    def test_found_in_path(self):
        with patch("shutil.which", return_value="/usr/bin/claude"):
            result = _find_claude_cli()
            self.assertEqual(result, "/usr/bin/claude")

    def test_explicit_path(self):
        with patch("os.path.exists", return_value=True):
            result = _find_claude_cli("/custom/claude")
            self.assertEqual(result, "/custom/claude")


class TestCreateBackend(unittest.TestCase):
    def test_create_openai(self):
        config = {
            "backend": "openai_api",
            "openai_api_key": "test-key",
            "openai_api_base": "https://api.test.com/v1",
            "openai_model": "test-model",
        }
        backend = create_backend(config)
        self.assertIsInstance(backend, OpenAIBackend)
        self.assertEqual(backend.model, "test-model")

    def test_create_claude(self):
        config = {
            "backend": "claude_code",
            "claude_cli_path": "claude",
        }
        with patch("ai.backend._find_claude_cli", return_value="claude"):
            backend = create_backend(config)
            self.assertIsInstance(backend, ClaudeCodeBackend)

    def test_unknown_backend_raises(self):
        with self.assertRaises(ValueError):
            create_backend({"backend": "unknown"})


class TestOpenAIBackend(unittest.TestCase):
    def test_is_available_with_key(self):
        backend = OpenAIBackend(api_key="test-key")
        self.assertTrue(backend.is_available())

    def test_is_available_without_key(self):
        backend = OpenAIBackend(api_key="")
        self.assertFalse(backend.is_available())

    def test_get_name(self):
        backend = OpenAIBackend(model="gpt-4")
        self.assertIn("gpt-4", backend.get_name())


if __name__ == "__main__":
    unittest.main()
