from pathlib import Path
import os
import sys
import tkinter as tk
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comfyui_support_tools.entrypoints.jobs import create_job_queue, create_job_runtime
from comfyui_support_tools.applications.main_gui.ui.processing.job_queue_panel import JobQueuePanel


# {
#   責務: [JobQueuePanelTests: related test fixtures and cases for JobQueuePanel behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: [
#     root: fixture root or application root under test,
#     logs: log messages emitted by the tested action,
#     runtime: runtime fixture state used by the test cases,
#     commander: job command coordinator under test,
#     panel: panel widget or view under test,
#   ],
#   引数: []
# }
class JobQueuePanelTests(unittest.TestCase):
    # {
    #   責務: [setUpClass: skips JobQueuePanelTests when required platform or display prerequisites are unavailable]
    #   処理: [1: check platform/display prerequisites, 2: skip the UI suite when the required display is unavailable]
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32" and not os.environ.get("DISPLAY"):
            raise unittest.SkipTest("Tk display required; Windows CI exercises it")

    # {
    #   責務: [setUp: initializes per-test fixture state for JobQueuePanelTests]
    #   処理: [
    #     1: create the per-test inputs and fixture resources required by the scenario,
    #     2: register cleanup for resources owned by the fixture,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [Tk test window/event loopを作成し、test終了時に破棄する]
    # }
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("900x420")
        self.logs = []
        self.runtime = create_job_runtime(max_concurrent=1)
        self.commander = create_job_queue(self.runtime)
        self.panel = JobQueuePanel(self.root, self.commander, self.logs.append)
        self.panel.pack(fill="both", expand=True)
        self.root.update()

    # {
    #   責務: [tearDown: releases per-test resources created by JobQueuePanelTests]
    #   処理: [1: stop owned workers/servers and release temporary files or UI resources]
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def tearDown(self):
        self.panel.close()
        self.commander.close()
        self.root.destroy()

    # {
    #   責務: [
    #     test_multiple_jobs_progress_error_and_compact_log_render: verifies the behavior described by "multiple jobs progress error and compact log render",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for multiple jobs progress error and compact log render,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_multiple_jobs_progress_error_and_compact_log_render(self):
        one = self.runtime.create("tagger_tag", "Tag images", source_names=("a.png", "b.png"))
        two = self.runtime.create("media_scan", "Media Scan", source_names=("folder",))
        self.assertTrue(self.runtime.wait_start(one))
        self.runtime.update(one, 0.5, "1/2 処理済み", "a.png: tagged")
        self.runtime.finish(one, "done", "完了")
        self.assertTrue(self.runtime.wait_start(two))
        self.runtime.update(two, None, "128件を検出", "found 128 media items")
        self.runtime.finish(two, "error", "scan failed", "permission denied")
        self.panel.refresh()
        self.root.update()

        self.assertEqual(set(self.panel.tree.get_children()), {one, two})
        values = self.panel.tree.item(one, "values")
        self.assertIn("100%", values)
        self.panel.tree.selection_set(two)
        self.panel._show_details()
        detail = self.panel.detail.get("1.0", "end")
        self.assertIn("permission denied", detail)
        self.assertIn("found 128", detail)

    # {
    #   責務: [
    #     test_cancel_button_cancels_queued_job_and_retry_stays_disabled: verifies the behavior described by "cancel button cancels queued job and retry stays disabled",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for cancel button cancels queued job and retry stays disabled,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_cancel_button_cancels_queued_job_and_retry_stays_disabled(self):
        job = self.runtime.create("queued", "Queued job")
        self.panel.refresh()
        self.panel.tree.selection_set(job)
        self.panel._show_details()
        self.assertEqual(str(self.panel.cancel_button["state"]), "normal")
        self.assertEqual(str(self.panel.retry_button["state"]), "disabled")
        self.panel.cancel_button.invoke()
        self.panel.refresh()
        snapshot = self.commander.snapshots()[0]
        self.assertEqual(snapshot.state, "cancelled")
        self.assertTrue(any("Job停止要求" in line for line in self.logs))

    # {
    #   責務: [
    #     test_backend_job_id_is_visible_in_details: verifies the behavior described by "backend job id is visible in details",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for backend job id is visible in details,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_backend_job_id_is_visible_in_details(self):
        job = self.runtime.create("comfyui", "Future backend")
        self.runtime.set_backend_job_id(job, "prompt-abc")
        self.panel.refresh()
        self.panel.tree.selection_set(job)
        self.panel._show_details()
        self.assertIn("prompt-abc", self.panel.detail.get("1.0", "end"))


if __name__ == "__main__":
    unittest.main()
