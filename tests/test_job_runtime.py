from pathlib import Path
import sys
import tempfile
from threading import Event, Thread
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image
from comfyui_support_tools.applications.main_gui.data.processing.action_io import ActionIO
from comfyui_support_tools.applications.main_gui.data.processing.job_runtime import JobRuntime
from comfyui_support_tools.entrypoints.jobs import create_job_queue
from comfyui_support_tools.applications.main_gui.data.processing.media_io import MediaIO
from comfyui_support_tools.shared.contracts.inspector_contracts import ActionRequest, TaggerSettings
from comfyui_support_tools.shared.contracts.job_contracts import (
    CancelCapability,
    CheckpointCapability,
    ShutdownPolicy,
)
from comfyui_support_tools.shared.contracts.media_item import MediaItem
from comfyui_support_tools.shared.job_snapshot_store import JobSnapshotStore
from comfyui_support_tools.shared.contracts.resource_budget import ResourceBudget, ResourceKind
from comfyui_support_tools.shared.resource_budget import ResourceBudgetManager


def wait_for(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


class JobRuntimeTests(unittest.TestCase):
    # {
    #   責務: [test_separate_runtimes_share_global_resource_admission: 複数JobRuntimeが共通resource capを共有する]
    #   処理: [1: CPU process budgetを1にする 2: 別Applicationのjob開始をblockする 3: lease解放後に開始する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_separate_runtimes_share_global_resource_admission(self):
        manager = ResourceBudgetManager(ResourceBudget(cpu_processes=1))
        first_runtime = JobRuntime(
            max_concurrent=2, resource_manager=manager, application_id="app-one"
        )
        second_runtime = JobRuntime(
            max_concurrent=2, resource_manager=manager, application_id="app-two"
        )
        first = first_runtime.create("cpu", "first")
        second = second_runtime.create("cpu", "second")
        self.assertTrue(first_runtime.wait_start(first))
        started = Event()

        # {
        #   責務: [wait_for_global_slot: second runtimeでshared resource slotを待つ]
        #   処理: [1: wait_startを呼ぶ 2: acquisition後にeventをsetする]
        #   引数: []
        #   戻り値: []
        # }
        def wait_for_global_slot():
            if second_runtime.wait_start(second):
                started.set()

        worker = Thread(target=wait_for_global_slot)
        worker.start()
        time.sleep(0.08)
        self.assertFalse(started.is_set())
        first_runtime.finish(first, "done")
        self.assertTrue(started.wait(1))
        second_runtime.finish(second, "done")
        worker.join(1)
        self.assertFalse(worker.is_alive())
        first_runtime.close()
        second_runtime.close()

    def test_lifecycle_progress_logs_times_backend_id_and_error(self):
        runtime = JobRuntime(max_concurrent=1)
        job = runtime.create(
            "generation",
            "Generate",
            source_ids=("a",),
            source_names=("image.png",),
        )
        before = runtime.snapshots()[0]
        self.assertEqual(before.state, "queued")
        self.assertIsNone(before.started_at)
        self.assertTrue(runtime.prepare(job))
        self.assertEqual(runtime.snapshots()[0].state, "preparing")
        self.assertTrue(runtime.wait_start(job))
        runtime.update(job, 0.5, "half", "step 1")
        runtime.set_backend_job_id(job, "backend-123")
        middle = runtime.snapshots()[0]
        self.assertEqual(middle.state, "running")
        self.assertEqual(middle.progress, 0.5)
        self.assertEqual(middle.backend_job_id, "backend-123")
        self.assertIn("step 1", middle.logs)
        runtime.finish(job, "done", "complete")
        after = runtime.snapshots()[0]
        self.assertEqual(after.state, "done")
        self.assertEqual(after.progress, 1.0)
        self.assertIsNotNone(after.started_at)
        self.assertIsNotNone(after.finished_at)
        self.assertGreaterEqual(after.finished_at, after.started_at)

        failed = runtime.create("api", "Backend call")
        self.assertTrue(runtime.wait_start(failed))
        runtime.finish(failed, "error", "Backend disconnected", "HTTP timeout")
        error = next(item for item in runtime.snapshots() if item.id == failed)
        self.assertEqual(error.state, "error")
        self.assertIn("HTTP timeout", error.error)
        runtime.close()

    def test_concurrency_limit_keeps_second_queued_and_queued_cancel_wakes_waiter(self):
        runtime = JobRuntime(max_concurrent=1)
        cancel_one, cancel_two = Event(), Event()
        first = runtime.create("one", "first", cancel_event=cancel_one)
        second = runtime.create("two", "second", cancel_event=cancel_two)
        release = Event()
        results = {}

        def worker(job, release_event=None):
            results[job] = runtime.wait_start(job)
            if results[job] and release_event is not None:
                release_event.wait(3)
                runtime.finish(job, "done", "done")

        t1 = Thread(target=worker, args=(first, release))
        t2 = Thread(target=worker, args=(second,))
        t1.start()
        wait_for(
            lambda: (
                next(item for item in runtime.snapshots() if item.id == first).state == "running"
            )
        )
        t2.start()
        wait_for(
            lambda: (
                next(item for item in runtime.snapshots() if item.id == second).state == "queued"
            )
        )
        self.assertTrue(runtime.cancel(second))
        t2.join(2)
        self.assertFalse(t2.is_alive())
        self.assertFalse(results[second])
        self.assertTrue(cancel_two.is_set())
        release.set()
        t1.join(2)
        states = {item.id: item.state for item in runtime.snapshots()}
        self.assertEqual(states[first], "done")
        self.assertEqual(states[second], "cancelled")
        runtime.close()

    def test_running_cancel_is_cooperative_and_shutdown_never_waits(self):
        runtime = JobRuntime(max_concurrent=1)
        cancel = Event()
        job = runtime.create("slow", "slow io", cancel_event=cancel)
        self.assertTrue(runtime.wait_start(job))
        self.assertTrue(runtime.cancel(job))
        current = runtime.snapshots()[0]
        self.assertEqual(current.state, "cancelling")
        self.assertTrue(cancel.is_set())
        self.assertIs(runtime.cancellation_token(job), cancel)
        self.assertIn("停止要求", current.message)
        start = time.monotonic()
        runtime.close()
        self.assertLess(time.monotonic() - start, 0.2)

    # {
    #   責務: [test_backend_cancel_handler_receives_external_id_and_failures_are_observable: backend停止通知と失敗記録を検証する]
    #   処理: [1: 外部IDの通知を確認する 2: callback例外がlocal cancelを妨げないことを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_backend_cancel_handler_receives_external_id_and_failures_are_observable(self):
        runtime = JobRuntime(max_concurrent=1)
        requested = []
        job = runtime.create("comfyui", "Generate")
        runtime.set_backend_job_id(job, "prompt-123")
        runtime.register_backend_cancel_handler(job, requested.append)
        self.assertTrue(runtime.wait_start(job))
        self.assertTrue(runtime.cancel(job))
        self.assertFalse(runtime.cancel(job))
        self.assertEqual(requested, ["prompt-123"])
        self.assertTrue(runtime.snapshots()[0].logs)
        runtime.close()

        runtime = JobRuntime(max_concurrent=1)
        job = runtime.create("comfyui", "Generate")
        runtime.set_backend_job_id(job, "prompt-456")

        # {
        #   責務: [fail_cancel: backend cancel callbackの失敗を再現する]
        #   処理: [1: RuntimeErrorを送出する]
        #   引数: [_backend_job_id: 外部backend job ID]
        #   戻り値: []
        # }
        def fail_cancel(_backend_job_id):
            raise RuntimeError("backend unavailable")

        runtime.register_backend_cancel_handler(job, fail_cancel)
        self.assertTrue(runtime.wait_start(job))
        self.assertTrue(runtime.cancel(job))
        snapshot = runtime.snapshots()[0]
        self.assertEqual(snapshot.state, "cancelling")
        self.assertTrue(any("backend cancel request failed" in line for line in snapshot.logs))
        runtime.close()

    # {
    #   責務: [test_shutdown_dispatches_backend_cancel_without_waiting: shutdown時のbackend停止通知を検証する]
    #   処理: [1: running Jobへ外部IDを登録する 2: close後に停止callbackが呼ばれることを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_shutdown_dispatches_backend_cancel_without_waiting(self):
        runtime = JobRuntime(max_concurrent=1)
        requested = []
        job = runtime.create("comfyui", "Generate")
        runtime.set_backend_job_id(job, "prompt-shutdown")
        runtime.register_backend_cancel_handler(job, requested.append)
        self.assertTrue(runtime.wait_start(job))
        runtime.close()
        self.assertEqual(requested, ["prompt-shutdown"])
        self.assertEqual(runtime.snapshots()[0].state, "cancelling")

    # {
    #   責務: [test_checkpoint_pause_resume_reacquires_concurrency_slot: item checkpointでpause/resumeできることを検証する]
    #   処理: [1: checkpoint対応Jobを開始する 2: pause境界で停止する 3: resumeして再実行する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_checkpoint_pause_resume_reacquires_concurrency_slot(self):
        runtime = JobRuntime(max_concurrent=1)
        job = runtime.create(
            "dataset",
            "Process files",
            checkpoint_capability=CheckpointCapability.ITEM,
        )
        self.assertTrue(runtime.wait_start(job))
        self.assertTrue(runtime.pause(job))
        self.assertFalse(
            runtime.checkpoint(
                job,
                "manifest://run/item-4",
                completed_items=("item-1", "item-2", "item-3"),
                pending_items=("item-4", "item-5"),
            )
        )
        paused = runtime.snapshots()[0]
        self.assertEqual(paused.state, "paused")
        self.assertEqual(paused.checkpoint_ref, "manifest://run/item-4")
        self.assertEqual(paused.completed_items, ("item-1", "item-2", "item-3"))

        result = {}
        waiter = Thread(target=lambda: result.setdefault("resumed", runtime.wait_if_paused(job)))
        waiter.start()
        self.assertTrue(runtime.resume(job))
        waiter.join(2)
        self.assertFalse(waiter.is_alive())
        self.assertTrue(result["resumed"])
        runtime.finish(job, "done", "complete")
        runtime.close()

    # {
    #   責務: [test_shutdown_policy_can_preserve_a_resumable_checkpoint: checkpoint-and-stop policyを検証する]
    #   処理: [1: resumable Jobを開始する 2: checkpoint停止を要求する 3: checkpoint保存後にpausedとなることを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_shutdown_policy_can_preserve_a_resumable_checkpoint(self):
        runtime = JobRuntime(max_concurrent=1)
        job = runtime.create(
            "download",
            "Download items",
            checkpoint_capability=CheckpointCapability.ITEM,
            shutdown_policy=ShutdownPolicy.CHECKPOINT_AND_STOP,
        )
        self.assertTrue(runtime.wait_start(job))
        runtime.close()
        paused = runtime.snapshots()[0]
        self.assertEqual(paused.state, "pausing")
        self.assertFalse(runtime.checkpoint(job, "manifest://download/item-2"))
        self.assertEqual(runtime.snapshots()[0].state, "paused")

    # {
    #   責務: [test_restart_recovers_manifest_checkpoint_and_resumes_idempotently: durable restart recoveryを検証する]
    #   処理: [1: running Jobのcheckpointを保存する 2: runtimeを再生成する 3: manifest handlerで同じJob IDをresumeする]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_restart_recovers_manifest_checkpoint_and_resumes_idempotently(self):
        with tempfile.TemporaryDirectory() as temp:
            store_path = Path(temp) / "jobs.sqlite3"
            store = JobSnapshotStore(store_path)
            runtime = JobRuntime(max_concurrent=1, store=store)
            job = runtime.create(
                "dataset",
                "Process dataset",
                retryable=True,
                checkpoint_capability=CheckpointCapability.ITEM,
                shutdown_policy=ShutdownPolicy.DETACH,
                operation_id="operation-123",
                manifest_ref="manifest://run-123",
            )
            self.assertTrue(runtime.wait_start(job))
            runtime.checkpoint(
                job,
                "manifest://run-123/checkpoint-3",
                completed_items=("item-1", "item-2"),
                pending_items=("item-3",),
                artifact_refs=("artifact://one",),
            )
            runtime.close()

            recovered = JobRuntime(max_concurrent=1, store=JobSnapshotStore(store_path))
            snapshot = recovered.snapshots()[0]
            self.assertEqual(snapshot.state, "interrupted")
            self.assertEqual(snapshot.checkpoint_ref, "manifest://run-123/checkpoint-3")
            self.assertEqual(snapshot.completed_items, ("item-1", "item-2"))
            self.assertEqual(snapshot.artifact_refs, ("artifact://one",))
            resumed = Event()
            resumed_items = []

            # {
            #   責務: [resume_from_manifest: persisted manifest snapshotからworkerを再起動する]
            #   処理: [1: restored job idを照合する 2: wait_start workerを起動する]
            #   引数: [restored: 復元されたimmutable Job snapshot]
            #   戻り値: []
            # }
            def resume_from_manifest(restored):
                self.assertEqual(restored.id, job)
                self.assertEqual(restored.completed_items, ("item-1", "item-2"))

                # {
                #   責務: [worker: 未完了itemだけを処理してresumed Jobを完了させる]
                #   処理: [1: restored Jobを開始する 2: pending itemだけを処理する 3: terminal stateを保存する]
                #   引数: []
                #   戻り値: []
                # }
                def worker():
                    if recovered.wait_start(restored.id):
                        resumed_items.extend(restored.pending_items)
                        resumed.set()
                        recovered.finish(restored.id, "done", "resumed")

                Thread(target=worker, daemon=True).start()

            recovered.register_resume_handler("dataset", resume_from_manifest)
            self.assertTrue(recovered.resume(job))
            self.assertTrue(resumed.wait(2))
            self.assertEqual(resumed_items, ["item-3"])
            self.assertEqual(recovered.snapshots()[0].state, "done")
            recovered.close()

    # {
    #   責務: [test_retry_is_manifest_backed_and_idempotent: operation lineage付きretryを一度だけ作る]
    #   処理: [1: 失敗Jobを記録する 2: adapter retryを登録する 3: 重複要求が同じchildを返す]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_retry_is_manifest_backed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            store_path = Path(temp) / "jobs.sqlite3"
            runtime = JobRuntime(max_concurrent=1, store=JobSnapshotStore(store_path))
            original = runtime.create(
                "generation",
                "Generate batch",
                retryable=True,
                operation_id="operation-idempotent",
                manifest_ref="manifest://generation",
            )
            self.assertTrue(runtime.wait_start(original))
            runtime.finish(original, "failed", "backend error")
            created = []

            # {
            #   責務: [retry_from_manifest: retry parentのlineageとoperationを引き継ぐchildを作る]
            #   処理: [1: manifest metadataを引き継ぐ 2: retry_ofでparentへ紐付ける]
            #   引数: [snapshot: retry元Job snapshot]
            #   戻り値: [child: 新規retry Job ID]
            # }
            def retry_from_manifest(snapshot):
                child = runtime.create(
                    snapshot.kind,
                    snapshot.action,
                    retry_of=snapshot.id,
                    operation_id=snapshot.operation_id,
                    manifest_ref=snapshot.manifest_ref,
                )
                created.append(child)
                return child

            runtime.register_retry_handler("generation", retry_from_manifest)
            first = runtime.retry(original)
            second = runtime.retry(original)
            self.assertEqual(first, second)
            self.assertEqual(created, [first])
            child = next(job for job in runtime.snapshots() if job.id == first)
            self.assertEqual(child.retry_of, original)
            self.assertEqual(child.operation_id, "operation-idempotent")
            self.assertEqual(child.state, "retrying")
            runtime.cancel(first)
            runtime.close()

            recovered = JobRuntime(max_concurrent=1, store=JobSnapshotStore(store_path))
            self.assertEqual(recovered.retry(original), first)
            recovered.close()

    # {
    #   責務: [test_uncancellable_capability_rejects_local_cancel: cannot_cancel capabilityを明示する]
    #   処理: [1: cancel非対応Jobを作る 2: UI/CLIと共通のcancel要求が拒否されることを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_uncancellable_capability_rejects_local_cancel(self):
        runtime = JobRuntime(max_concurrent=1)
        job = runtime.create("remote", "Cannot cancel", cancel_capability=CancelCapability.NONE)
        self.assertTrue(runtime.wait_start(job))
        self.assertFalse(runtime.cancel(job))
        self.assertFalse(runtime.snapshots()[0].cancellable)
        runtime.finish(job, "done")
        runtime.close()

    # {
    #   責務: [test_external_cancel_event_is_still_accounted_by_runtime: adapter先行通知後もruntimeがqueueを整理する]
    #   処理: [1: 外部EventをJobへ渡す 2: adapter側でEventをsetする 3: runtime.cancelでJob stateを終端化する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_external_cancel_event_is_still_accounted_by_runtime(self):
        runtime = JobRuntime(max_concurrent=1)
        cancellation = Event()
        job = runtime.create("media_scan", "Replace pending scan", cancel_event=cancellation)
        cancellation.set()
        self.assertTrue(runtime.cancel(job))
        self.assertEqual(runtime.snapshots()[0].state, "cancelled")
        self.assertNotIn(job, runtime._queue)
        runtime.close()

    # {
    #   責務: [test_ui_commander_pause_resume_routes_to_shared_runtime: UI boundary経由でpause/resumeできる]
    #   処理: [1: UI commanderを構築する 2: checkpoint/pause要求を送る 3: resume要求後に同じworkerを再開する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_ui_commander_pause_resume_routes_to_shared_runtime(self):
        runtime = JobRuntime(max_concurrent=1)
        commander = create_job_queue(runtime)
        job = runtime.create(
            "dataset",
            "Files",
            checkpoint_capability=CheckpointCapability.ITEM,
        )
        self.assertTrue(runtime.wait_start(job))
        self.assertTrue(commander.pause(job))
        self.assertFalse(runtime.checkpoint(job, "manifest://files/item-2"))
        result = {}
        waiter = Thread(target=lambda: result.setdefault("running", runtime.wait_if_paused(job)))
        waiter.start()
        self.assertTrue(commander.resume(job))
        waiter.join(2)
        self.assertTrue(result["running"])
        runtime.finish(job, "done")
        commander.close()

    # {
    #   責務: [test_finish_current_item_shutdown_does_not_cancel_inflight_item: policyが現在itemを保護する]
    #   処理: [1: item-checkpoint Jobを開始する 2: shutdown policyを実行する 3: cancel tokenではなく境界停止要求を確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_finish_current_item_shutdown_does_not_cancel_inflight_item(self):
        runtime = JobRuntime(max_concurrent=1)
        job = runtime.create(
            "generation",
            "Generate items",
            checkpoint_capability=CheckpointCapability.ITEM,
            shutdown_policy=ShutdownPolicy.FINISH_CURRENT_ITEM,
        )
        self.assertTrue(runtime.wait_start(job))
        runtime.close()
        self.assertFalse(runtime.cancellation_token(job).is_set())
        self.assertTrue(runtime.finish_current_item_requested(job))
        self.assertEqual(runtime.snapshots()[0].state, "cancelling")
        runtime.finish(job, "cancelled", "finished current item")

    def test_history_is_bounded_and_progress_validation_is_strict(self):
        runtime = JobRuntime(max_concurrent=1, history_limit=10)
        for index in range(12):
            job = runtime.create("test", f"job {index}")
            self.assertTrue(runtime.wait_start(job))
            runtime.finish(job, "done")
        snapshots = runtime.snapshots()
        self.assertEqual(len(snapshots), 10)
        self.assertEqual(snapshots[0].action, "job 11")
        job = runtime.create("bad-progress", "bad")
        self.assertTrue(runtime.wait_start(job))
        for value in (-0.1, 1.1, float("nan")):
            with self.assertRaises(ValueError):
                runtime.update(job, value)
        runtime.finish(job, "cancelled")
        runtime.close()

    def test_contract_reserves_retry_lineage_without_claiming_handler(self):
        runtime = JobRuntime()
        original = runtime.create("tag", "tag", retryable=False)
        self.assertTrue(runtime.wait_start(original))
        runtime.finish(original, "error", error="temporary")
        retry = runtime.create("tag", "tag retry", retry_of=original, retryable=False)
        snapshot = next(item for item in runtime.snapshots() if item.id == retry)
        self.assertEqual(snapshot.retry_of, original)
        self.assertFalse(snapshot.retryable)
        runtime.cancel(retry)
        runtime.close()


class SharedExistingProcessJobTests(unittest.TestCase):
    # {
    #   責務: [test_tagger_pause_checkpoints_completed_items_and_resumes_without_duplicates: Tagger item境界pause/resumeを検証する]
    #   処理: [1: 先頭item処理中にpauseする 2: checkpoint stateを確認する 3: resume後に残りだけを実行する]
    #   引数: []
    #   戻り値: []
    # }
    def test_tagger_pause_checkpoints_completed_items_and_resumes_without_duplicates(self):
        entered = Event()
        release = Event()
        calls = []

        class BlockingTransport:
            def probe(self, _settings):
                return ("fixture-model",)

            def tag(self, item, _settings):
                calls.append(item.id)
                if len(calls) == 1:
                    entered.set()
                    release.wait(2)
                return {"tags": {"fixture": 0.99}}

        runtime = JobRuntime(max_concurrent=1)
        action = ActionIO(BlockingTransport(), runtime)
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                items = []
                for name in ("first.png", "second.png"):
                    path = root / name
                    Image.new("RGB", (20, 20), "blue").save(path)
                    stat = path.stat()
                    items.append(
                        MediaItem(
                            name,
                            str(path),
                            name,
                            "image",
                            "library",
                            stat.st_size,
                            stat.st_mtime_ns,
                        )
                    )
                action.start(
                    ActionRequest(
                        1,
                        "tag",
                        TaggerSettings("http://127.0.0.1:1/pixai/v1/interrogate", "fixture-model"),
                        tuple(items),
                    )
                )
                job_id = action.last_job_id
                self.assertTrue(entered.wait(2))
                self.assertTrue(runtime.pause(job_id))
                release.set()
                wait_for(lambda: runtime.snapshots()[0].state == "paused")
                paused = runtime.snapshots()[0]
                self.assertEqual(paused.completed_items, (items[0].id,))
                self.assertEqual(paused.pending_items, (items[1].id,))
                self.assertTrue(runtime.resume(job_id))
                wait_for(lambda: runtime.snapshots()[0].state == "done")
                self.assertEqual(calls, [items[0].id, items[1].id])
                self.assertEqual(
                    runtime.snapshots()[0].completed_items, tuple(item.id for item in items)
                )
        finally:
            release.set()
            action.close()
            runtime.close()

    def test_media_scan_and_tagger_actions_share_one_job_model(self):
        class FakeTransport:
            def probe(self, _settings):
                return ("fixture-model",)

            def tag(self, _item, _settings):
                return {"tags": {"fixture": 0.99}}

        runtime = JobRuntime(max_concurrent=2)
        media = MediaIO(runtime)
        action = ActionIO(FakeTransport(), runtime)
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                path = root / "画像.png"
                Image.new("RGB", (20, 20), "blue").save(path)
                media.scan(str(root), "library")
                media_items = []
                done = False
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline and not done:
                    for event in media.poll():
                        media_items.extend(event.items)
                        done = done or event.kind in ("done", "error")
                    time.sleep(0.01)
                self.assertTrue(done)
                self.assertEqual(len(media_items), 1)

                settings = TaggerSettings(
                    "http://127.0.0.1:1/pixai/v1/interrogate",
                    "fixture-model",
                )
                action.start(ActionRequest(1, "probe", settings))
                probe_done = False
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline and not probe_done:
                    probe_done = any(event.kind == "done" for event in action.poll())
                    time.sleep(0.01)
                self.assertTrue(probe_done)

                action.start(ActionRequest(2, "tag", settings, tuple(media_items)))
                tag_done = False
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline and not tag_done:
                    tag_done = any(event.kind == "done" for event in action.poll())
                    time.sleep(0.01)
                self.assertTrue(tag_done)

            snapshots = runtime.snapshots()
            kinds = {job.kind for job in snapshots}
            self.assertTrue({"media_scan", "tagger_probe", "tagger_tag"}.issubset(kinds))
            self.assertTrue(all(job.state == "done" for job in snapshots))
            tag = next(job for job in snapshots if job.kind == "tagger_tag")
            self.assertEqual(tag.progress, 1.0)
            self.assertEqual(tag.source_names, ("画像.png",))
            scan = next(job for job in snapshots if job.kind == "media_scan")
            self.assertIn("読込完了", scan.message)
        finally:
            action.close()
            media.close()
            runtime.close()


if __name__ == "__main__":
    unittest.main()
