"""Tests for config module"""
import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from config import (
    DEFAULT_USER_CONFIG,
    _deep_merge,
    load_user_config,
    save_user_config,
)


class TestDeepMerge(unittest.TestCase):
    def test_merge_empty_override(self):
        base = {"a": 1, "b": {"c": 2}}
        result = _deep_merge(base, {})
        self.assertEqual(result, {"a": 1, "b": {"c": 2}})

    def test_merge_nested_dicts(self):
        base = {"a": {"b": 1, "c": 2}}
        override = {"a": {"c": 3, "d": 4}}
        result = _deep_merge(base, override)
        self.assertEqual(result, {"a": {"b": 1, "c": 3, "d": 4}})

    def test_merge_override_top_level(self):
        base = {"a": 1, "b": 2}
        override = {"a": 10}
        result = _deep_merge(base, override)
        self.assertEqual(result, {"a": 10, "b": 2})

    def test_merge_does_not_mutate_base(self):
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}
        original = copy.deepcopy(base)
        _deep_merge(base, override)
        self.assertEqual(base, original)

    def test_merge_deep_nesting(self):
        base = {"l1": {"l2": {"l3": {"val": 1}}}}
        override = {"l1": {"l2": {"l3": {"val": 2, "extra": 3}}}}
        result = _deep_merge(base, override)
        self.assertEqual(result["l1"]["l2"]["l3"], {"val": 2, "extra": 3})


class TestLoadConfig(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher_path = patch("config.CONFIG_PATH",
                                   os.path.join(self._tmpdir, "config.json"))
        self._patcher_dir = patch("config.CONFIG_DIR", self._tmpdir)
        self._patcher_path.start()
        self._patcher_dir.start()

    def tearDown(self):
        self._patcher_path.stop()
        self._patcher_dir.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_load_returns_defaults_when_no_file(self):
        config = load_user_config()
        self.assertEqual(config["backend"], "openai_api")
        self.assertEqual(config["pet_name"], "小橘")

    def test_load_merges_with_defaults(self):
        custom = {"pet_name": "自定义", "backend": "claude_code"}
        save_user_config(custom)
        config = load_user_config()
        self.assertEqual(config["pet_name"], "自定义")
        self.assertEqual(config["backend"], "claude_code")
        # Default values still present
        self.assertEqual(config["openai_api_base"], "https://api.openai.com/v1")

    def test_load_returns_deepcopy(self):
        config1 = load_user_config()
        config1["pet_name"] = "modified"
        config2 = load_user_config()
        self.assertEqual(config2["pet_name"], "小橘")

    def test_load_handles_corrupted_json(self):
        config_path = os.path.join(self._tmpdir, "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("not valid json {{{")
        config = load_user_config()
        self.assertEqual(config["backend"], "openai_api")


class TestSaveConfig(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher_path = patch("config.CONFIG_PATH",
                                   os.path.join(self._tmpdir, "config.json"))
        self._patcher_dir = patch("config.CONFIG_DIR", self._tmpdir)
        self._patcher_path.start()
        self._patcher_dir.start()

    def tearDown(self):
        self._patcher_path.stop()
        self._patcher_dir.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_creates_file(self):
        save_user_config(DEFAULT_USER_CONFIG)
        self.assertTrue(os.path.exists(os.path.join(self._tmpdir, "config.json")))

    def test_save_preserves_content(self):
        cfg = copy.deepcopy(DEFAULT_USER_CONFIG)
        cfg["pet_name"] = "test-pet"
        save_user_config(cfg)
        with open(os.path.join(self._tmpdir, "config.json"), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["pet_name"], "test-pet")


if __name__ == "__main__":
    unittest.main()
