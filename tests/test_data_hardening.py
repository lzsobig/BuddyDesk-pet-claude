"""Regression tests for config, event persistence, and command redaction."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from config import load_user_config, save_user_config
from engine.command_engine import _redact_command
from engine.event_engine import EventEngine


class TestConfigHardening(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "config.json")
        self.path_patch = patch("config.CONFIG_PATH", self.path)
        self.dir_patch = patch("config.CONFIG_DIR", self.tmpdir)
        self.path_patch.start()
        self.dir_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.dir_patch.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_non_object_config_resets_to_defaults(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(["not", "an", "object"], f)
        self.assertEqual(load_user_config()["backend"], "openai_api")

    def test_invalid_secret_resets_to_defaults(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"openai_api_key": "b64:not-valid-base64%%%"}, f)
        self.assertEqual(load_user_config()["backend"], "openai_api")

    def test_save_leaves_valid_json_and_no_tmp_file(self):
        save_user_config({"pet_name": "atomic"})
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["pet_name"], "atomic")
        self.assertFalse(os.path.exists(self.path + ".tmp"))


class TestEventPersistenceHardening(unittest.TestCase):
    def test_events_continue_persisting_after_history_trim(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "events.log")
            with patch("config.load_jobs", return_value=[]), \
                 patch("config.save_jobs"), \
                 patch("config.EVENT_LOG_FILE", log_path), \
                 patch("config.MAX_EVENT_HISTORY", 3):
                engine = EventEngine()
                for i in range(8):
                    engine.record(EventEngine.CHAT_START, {"i": i})
                with open(log_path, encoding="utf-8") as f:
                    lines = [line for line in f if line.strip()]
                self.assertEqual(len(lines), 3)
                self.assertEqual(json.loads(lines[-1])["data"]["i"], 7)


class TestCommandRedaction(unittest.TestCase):
    def test_redacts_common_credentials(self):
        raw = "curl -H 'Authorization: Bearer secret123' --api-key=abc123 password:letmein"
        masked = _redact_command(raw)
        self.assertNotIn("secret123", masked)
        self.assertNotIn("abc123", masked)
        self.assertNotIn("letmein", masked)
        self.assertGreaterEqual(masked.count("[REDACTED]"), 3)


if __name__ == "__main__":
    unittest.main()
