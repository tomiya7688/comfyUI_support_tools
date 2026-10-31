from __future__ import annotations

import ast
import queue
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.backend.embedded_start_webui import EmbeddedStartWebUI
from scripts.widgets.log_box import LogBox


# {
# 責務: [ ResourceLifetimeTests: thread・logのresource寿命回帰を検証する ]
# フィールド: []
# 処理: [ 1: health monitor停止を検証する, 2: log queue上限を検証する, 3: 表示log上限を検証する ]
# }
class ResourceLifetimeTests(unittest.TestCase):
    # {
    # 責務: [ test_health_monitor_stops_promptly_when_run_event_is_signalled: run固有Eventでhealth threadが即時停止することを確認する ]
    # 処理: [ 1: fake backendを作る, 2: threadを起動する, 3: stop Event後に終了を確認する ]
    # 引数: []
    # 戻り値: []
    # }
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

    # {
    # 責務: [ test_log_queue_drops_oldest_entry_at_capacity: pending logが上限超過時に最古要素を捨てることを確認する ]
    # 処理: [ 1: 容量2のqueueへ3件記録する, 2: 最新2件だけ残ることを確認する ]
    # 引数: []
    # 戻り値: []
    # }
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

    # {
    # 責務: [test_log_queue_retries_after_concurrent_refill: concurrent producerがqueueを埋めてもlog追加が落ちないことを確認する]
    # 処理: [1: dropと再挿入の間に別producerがqueueを満たす状態を再現する]
    # 引数: [self]
    # 戻り値: []
    # }
    def test_log_queue_retries_after_concurrent_refill(self):
        pending = SimpleNamespace(
            put_nowait=mock.Mock(side_effect=[queue.Full, None]),
            get_nowait=mock.Mock(side_effect=queue.Empty),
        )
        fake = SimpleNamespace(
            _pending_logs=pending,
            _flush_scheduled=True,
        )

        LogBox.log(fake, "latest")

        self.assertEqual(pending.put_nowait.call_count, 2)

    # {
    # 責務: [test_stop_cancels_waiting_restart: restart完了待ち中のstopが保留restartを無効にすることを確認する]
    # 処理: [1: restart workerを停止完了待ちにする, 2: stop request後に完了eventを立てる, 3: 再起動されないことを確認する]
    # 引数: [self]
    # 戻り値: []
    # }
    def test_stop_cancels_waiting_restart(self):
        lifecycle_done = threading.Event()
        fake = SimpleNamespace(
            _lifecycle_lock=threading.Lock(),
            _lifecycle_generation=0,
            _lifecycle_active=True,
            _lifecycle_done=lifecycle_done,
            _desired_running=True,
            _stop_event=threading.Event(),
            _log_msg=mock.Mock(),
            DISPLAY_NAME="fake backend",
            _start_webui_thread=mock.Mock(),
        )
        restart = threading.Thread(
            target=EmbeddedStartWebUI._restart_webui,
            args=(fake, [], 1, None, True, 0.1, 0.1),
        )
        restart.start()
        deadline = time.monotonic() + 1
        while not fake._stop_event.is_set() and time.monotonic() < deadline:
            time.sleep(0.005)

        EmbeddedStartWebUI.request_stop(fake)
        lifecycle_done.set()
        restart.join(timeout=1)

        self.assertFalse(restart.is_alive())
        fake._start_webui_thread.assert_not_called()

    # {
    # 責務: [test_stop_cancels_start_worker_before_it_runs: worker開始前のstopが予約済みstartを取り消すことを確認する]
    # 処理: [1: 開始generationを予約する, 2: worker起動前にstopする, 3: 古いgenerationがbackendを起動しないことを確認する]
    # 引数: [self]
    # 戻り値: []
    # }
    def test_stop_cancels_start_worker_before_it_runs(self):
        fake = SimpleNamespace(
            _lifecycle_lock=threading.Lock(),
            _lifecycle_generation=0,
            _lifecycle_active=False,
            _lifecycle_done=threading.Event(),
            _desired_running=False,
            _current_proc=None,
            _stop_event=threading.Event(),
        )

        generation = EmbeddedStartWebUI.request_start(fake)
        self.assertEqual(generation, 1)
        EmbeddedStartWebUI.request_stop(fake)
        EmbeddedStartWebUI._start_webui_thread(
            fake, [], 1, None, True, 0.1, 0.1, _generation=generation
        )

        self.assertFalse(fake._desired_running)
        self.assertFalse(fake._lifecycle_active)
        self.assertTrue(fake._stop_event.is_set())

    # {
    # 責務: [test_concurrent_restarts_coalesce_to_latest_request: 複数restart workerが最新要求1件へ集約されることを確認する]
    # 処理: [1: 完了待ち中に2件restartを送る, 2: 先行workerを無効化して1回だけ起動する]
    # 引数: [self]
    # 戻り値: []
    # }
    def test_concurrent_restarts_coalesce_to_latest_request(self):
        lifecycle_done = threading.Event()
        fake = SimpleNamespace(
            _lifecycle_lock=threading.Lock(),
            _lifecycle_generation=0,
            _lifecycle_active=True,
            _lifecycle_done=lifecycle_done,
            _desired_running=True,
            _stop_event=threading.Event(),
            _log_msg=mock.Mock(),
            DISPLAY_NAME="fake backend",
            _start_webui_thread=mock.Mock(),
        )
        workers = [
            threading.Thread(
                target=EmbeddedStartWebUI._restart_webui,
                args=(fake, [], 1, None, True, 0.1, 0.1),
            )
            for _ in range(2)
        ]
        workers[0].start()
        deadline = time.monotonic() + 1
        while not fake._stop_event.is_set() and time.monotonic() < deadline:
            time.sleep(0.005)
        workers[1].start()
        fake._lifecycle_active = False
        lifecycle_done.set()
        for worker in workers:
            worker.join(timeout=1)

        self.assertTrue(all(not worker.is_alive() for worker in workers))
        fake._start_webui_thread.assert_called_once_with([], 1, None, True, 0.1, 0.1, _generation=2)

    # {
    # 責務: [ test_all_opencv_video_captures_are_exception_safe: productionのVideoCaptureがfinallyでreleaseされることを検証する ]
    # 処理: [ 1: 対象Python sourceをAST解析する, 2: VideoCapture代入を探す, 3: 直後のtry-finallyで同じ変数をreleaseすることを確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_all_opencv_video_captures_are_exception_safe(self):
        root = Path(__file__).resolve().parents[1]
        source_roots = (
            root / "scripts",
            root / "nuno",
            root / "src",
        )
        failures = []
        for source_root in source_roots:
            if not source_root.exists():
                continue
            for path in source_root.rglob("*.py"):
                if any(part in {"external", "__pycache__", ".venv"} for part in path.parts):
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                containers = [
                    node for node in ast.walk(tree) if isinstance(getattr(node, "body", None), list)
                ]
                for container in containers:
                    body = getattr(container, "body", [])
                    for index, statement in enumerate(body):
                        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                            continue
                        value = statement.value
                        if not (
                            isinstance(value, ast.Call)
                            and isinstance(value.func, ast.Attribute)
                            and value.func.attr == "VideoCapture"
                        ):
                            continue
                        targets = (
                            statement.targets
                            if isinstance(statement, ast.Assign)
                            else [statement.target]
                        )
                        names = [target.id for target in targets if isinstance(target, ast.Name)]
                        if len(names) != 1:
                            failures.append(
                                f"{path.relative_to(root)}:{statement.lineno}: capture must use one named owner"
                            )
                            continue
                        owner = names[0]
                        try_statement = next(
                            (
                                candidate
                                for candidate in body[index + 1 : index + 4]
                                if isinstance(candidate, ast.Try)
                            ),
                            None,
                        )
                        released = try_statement is not None and any(
                            isinstance(node, ast.Call)
                            and isinstance(node.func, ast.Attribute)
                            and node.func.attr == "release"
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == owner
                            for final_statement in try_statement.finalbody
                            for node in ast.walk(final_statement)
                        )
                        if not released:
                            failures.append(
                                f"{path.relative_to(root)}:{statement.lineno}: {owner}.release() must be in nearby finally"
                            )
        self.assertEqual(failures, [])

    # {
    # 責務: [ test_visible_log_trimming_keeps_configured_line_budget: 表示logが行数上限を超えた分だけ先頭から削除されることを確認する ]
    # 処理: [ 1: fake widgetへ行数を返させる, 2: 期待するdelete範囲を確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_visible_log_trimming_keeps_configured_line_budget(self):
        deleted = []
        fake = SimpleNamespace(
            MAX_RENDERED_LINES=3,
            index=lambda _index: "6.0",
            delete=lambda start, end: deleted.append((start, end)),
        )
        LogBox._trim_visible_lines(fake)
        self.assertEqual(deleted, [("1.0", "4.0")])


if __name__ == "__main__":
    unittest.main()
