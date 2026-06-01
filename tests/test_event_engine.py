"""Tests for event_engine module"""
import threading
import time
import unittest
from unittest.mock import patch

from engine.event_engine import EventEngine


class TestEventEngine(unittest.TestCase):
    def setUp(self):
        self._patcher_load = patch("config.load_jobs", return_value=[])
        self._patcher_save = patch("config.save_jobs")
        self._patcher_log = patch("config.EVENT_LOG_FILE", "/tmp/test_events.log")
        self._patcher_load.start()
        self._patcher_save.start()
        self._patcher_log.start()
        self.events = []
        self.engine = EventEngine(on_event=lambda t, d: self.events.append((t, d)))

    def tearDown(self):
        self._patcher_load.stop()
        self._patcher_save.stop()
        self._patcher_log.stop()

    def test_record_event(self):
        self.engine.record(EventEngine.CHAT_START, {"backend": "test"})
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0][0], EventEngine.CHAT_START)

    def test_record_fires_callbacks(self):
        received = []
        self.engine.on(EventEngine.CHAT_COMPLETE, lambda e: received.append(e))
        self.engine.record(EventEngine.CHAT_COMPLETE, {"length": 100})
        self.assertEqual(len(received), 1)

    def test_get_recent(self):
        for i in range(15):
            self.engine.record(EventEngine.CHAT_START, {"i": i})
        recent = self.engine.get_recent(5)
        self.assertEqual(len(recent), 5)

    def test_thread_safety(self):
        def add_events(n):
            for i in range(n):
                self.engine.record(EventEngine.CHAT_START, {"i": i})

        threads = [threading.Thread(target=add_events, args=(10,)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(self.events), 50)

    def test_get_job_summary_empty(self):
        self.assertEqual(self.engine.get_job_summary(), "No jobs yet")

    def test_get_job_summary_with_jobs(self):
        with self.engine._lock:
            self.engine.jobs = [
                {"id": 1, "name": "test", "status": "succeeded", "duration": 1.5},
            ]
        summary = self.engine.get_job_summary()
        self.assertIn("test", summary)
        self.assertIn("✓", summary)


if __name__ == "__main__":
    unittest.main()
