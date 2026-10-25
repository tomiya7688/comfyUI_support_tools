from __future__ import annotations

import queue
import threading
import unittest
from types import SimpleNamespace

from scripts.backend.embedded_start_webui import EmbeddedStartWebUI
from scripts.widgets.log_box import LogBox


class ResourceLifetimeTests(unittest.TestCase):
    def test_health_monitor_stops_promptly_when_run_event_is_signalled(self):
        fake = SimpleNamespace(
            _current_proc=None,
            _api_status="",
            _health_check_now=lambda: {"status": "ok", "online": True},
        )
        stop = threading.Event()
        worker = threading.Thread(
            target=EmbeddedStartWebUI._health_check_thread,
            args=(fake, stop),
        )
        worker.start()
        stop.set()
        worker.join(timeout=1.0)
        self.assertFalse(worker.is_alive())

    def test_log_queue_drops_oldest_entry_at_capacity(self):
        fake = SimpleNamespace(
            _pending_logs=queue.Queue(maxsize=2),
            _flush_scheduled=True,
        )
        LogBox.log(fake, "first")
        LogBox.log(fake, "second")
        LogBox.log(fake, "third")
        self.assertEqual(
            [fake._pending_logs.get_nowait(), fake._pending_logs.get_nowait()],
            ["second", "third"],
        )

    def test_visible_log_trimming_keeps_configured_line_budget(self):
        deleted = []
        fake = SimpleNamespace(
            MAX_TEXT_LINES=3,
            index=lambda _index: "6.0",
            delete=lambda start, end: deleted.append((start, end)),
        )
        LogBox._trim_visible_lines(fake)
        self.assertEqual(deleted, [("1.0", "4.0")])


if __name__ == "__main__":
    unittest.main()
