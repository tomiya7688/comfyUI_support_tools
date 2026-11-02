from pathlib import Path
import os
import sys
import tempfile
import tkinter as tk
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comfyui_support_tools.entrypoints.jobs import create_job_queue, create_job_runtime
from comfyui_support_tools.applications.main_gui.ui.processing.job_queue_panel import JobQueuePanel
from comfyui_support_tools.shared.contracts.job_contracts import CheckpointCapability


class JobQueuePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32" and not os.environ.get("DISPLAY"):
            raise unittest.SkipTest("Tk display required; Windows CI exercises it")

    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("900x420")
        self.logs = []
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.runtime = create_job_runtime(
            max_concurrent=1,
            store_path=Path(self._temp_dir.name) / "jobs.sqlite3",
        )
        self.commander = create_job_queue(self.runtime)
        self.panel = JobQueuePanel(self.root, self.commander, self.logs.append)
        self.panel.pack(fill="both", expand=True)
        self.root.update()

    def tearDown(self):
        self.panel.close()
        self.commander.close()
        self.root.destroy()

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

    def test_backend_job_id_is_visible_in_details(self):
        job = self.runtime.create("comfyui", "Future backend")
        self.runtime.set_backend_job_id(job, "prompt-abc")
        self.panel.refresh()
        self.panel.tree.selection_set(job)
        self.panel._show_details()
        self.assertIn("prompt-abc", self.panel.detail.get("1.0", "end"))

    # {
    #   責務: [test_pause_and_resume_controls_use_shared_commander_path: UI pause/resume controlを検証する]
    #   処理: [1: checkpoint可能Jobを作る 2: pauseする 3: resumeしてqueueへ戻す]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_pause_and_resume_controls_use_shared_commander_path(self):
        job = self.runtime.create(
            "dataset",
            "Dataset batch",
            checkpoint_capability=CheckpointCapability.ITEM,
        )
        self.panel.refresh()
        self.panel.tree.selection_set(job)
        self.panel._show_details()
        self.assertEqual(str(self.panel.pause_button["state"]), "normal")
        self.panel.pause_button.invoke()
        self.panel.refresh()
        self.assertEqual(self.runtime.snapshots()[0].state, "paused")
        self.assertEqual(str(self.panel.resume_button["state"]), "normal")
        self.panel.resume_button.invoke()
        self.panel.refresh()
        self.assertEqual(self.runtime.snapshots()[0].state, "queued")


if __name__ == "__main__":
    unittest.main()
