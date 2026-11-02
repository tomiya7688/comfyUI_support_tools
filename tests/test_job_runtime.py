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
from comfyui_support_tools.applications.main_gui.data.processing.media_io import MediaIO
from comfyui_support_tools.shared.contracts.inspector_contracts import ActionRequest, TaggerSettings


# {
#   責務: [wait_for: waits for a condition until it succeeds or the timeout expires]
#   処理: [1: poll or pump until the requested predicate succeeds, 2: raise a useful timeout failure if it does not]
#   引数: [predicate: completion predicate callback (unspecified), timeout: maximum wait duration (unspecified)]
#   戻り値: [None: test helper returns no value]
# }
def wait_for(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


# {
#   責務: [JobRuntimeTests: related test fixtures and cases for JobRuntime behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class JobRuntimeTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_lifecycle_progress_logs_times_backend_id_and_error: verifies the behavior described by "lifecycle progress logs times backend id and error",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for lifecycle progress logs times backend id and error,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [
    #     test_concurrency_limit_keeps_second_queued_and_queued_cancel_wakes_waiter: verifies the behavior described by "concurrency limit keeps second queued and queued cancel wakes waiter",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for concurrency limit keeps second queued and queued cancel wakes waiter,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_concurrency_limit_keeps_second_queued_and_queued_cancel_wakes_waiter(self):
        runtime = JobRuntime(max_concurrent=1)
        cancel_one, cancel_two = Event(), Event()
        first = runtime.create("one", "first", cancel_event=cancel_one)
        second = runtime.create("two", "second", cancel_event=cancel_two)
        release = Event()
        results = {}

        # {
        #   責務: [worker: waits for its release event and reports completion to the job runtime]
        #   処理: [1: wait until the test releases the worker, 2: report completion through the job runtime]
        #   引数: [
        #     job: job snapshot passed to worker (unspecified),
        #     release_event: test-controlled worker release signal (unspecified),
        #   ],
        #   戻り値: [None: test helper returns no value]
        # }
        def worker(job, release_event=None):
            results[job] = runtime.wait_start(job)
            if results[job] and release_event is not None:
                release_event.wait(3)
                runtime.finish(job, "done", "done")

        t1 = Thread(target=worker, args=(first, release))
        t2 = Thread(target=worker, args=(second,))
        t1.start()
        wait_for(lambda: next(item for item in runtime.snapshots() if item.id == first).state == "running")
        t2.start()
        wait_for(lambda: next(item for item in runtime.snapshots() if item.id == second).state == "queued")
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

    # {
    #   責務: [
    #     test_running_cancel_is_cooperative_and_shutdown_never_waits: verifies the behavior described by "running cancel is cooperative and shutdown never waits",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for running cancel is cooperative and shutdown never waits,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_running_cancel_is_cooperative_and_shutdown_never_waits(self):
        runtime = JobRuntime(max_concurrent=1)
        cancel = Event()
        job = runtime.create("slow", "slow io", cancel_event=cancel)
        self.assertTrue(runtime.wait_start(job))
        self.assertTrue(runtime.cancel(job))
        current = runtime.snapshots()[0]
        self.assertEqual(current.state, "running")
        self.assertTrue(cancel.is_set())
        self.assertIn("停止要求", current.message)
        start = time.monotonic()
        runtime.close()
        self.assertLess(time.monotonic() - start, 0.2)

    # {
    #   責務: [
    #     test_history_is_bounded_and_progress_validation_is_strict: verifies the behavior described by "history is bounded and progress validation is strict",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for history is bounded and progress validation is strict,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [
    #     test_contract_reserves_retry_lineage_without_claiming_handler: verifies the behavior described by "contract reserves retry lineage without claiming handler",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for contract reserves retry lineage without claiming handler,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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


# {
#   責務: [SharedExistingProcessJobTests: related test fixtures and cases for SharedExistingProcessJob behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class SharedExistingProcessJobTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_media_scan_and_tagger_actions_share_one_job_model: verifies the behavior described by "media scan and tagger actions share one job model",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for media scan and tagger actions share one job model,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: tuple/list fixture / mapping built or selected by this helper]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_media_scan_and_tagger_actions_share_one_job_model(self):
        # {
        #   責務: [FakeTransport: deterministic tagger transport for shared job lifecycle tests]
        #   処理: [1: provide the configured fields and methods used by the surrounding cases]
        #   フィールド: []
        #   引数: []
        # }
        class FakeTransport:
            # {
            #   責務: [probe: returns the canned model list used by the backend test double]
            #   処理: [1: return the fixed model list expected by the inspector state test double]
            #   引数: [_settings: settings argument ignored by this controlled test double (unspecified)]
            #   戻り値: [result: tuple/list fixture built or selected by this helper]
            # }
            def probe(self, _settings):
                return ("fixture-model",)

            # {
            #   責務: [tag: returns the canned tag response used by the backend test double]
            #   処理: [
            #     1: record or derive tag output from the supplied sequence inputs,
            #     2: return the deterministic tag payload,
            #   ],
            #   引数: [
            #     _item: media item argument ignored by this controlled test double (unspecified),
            #     _settings: settings argument ignored by this controlled test double (unspecified),
            #   ],
            #   戻り値: [result: mapping built or selected by this helper]
            # }
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
