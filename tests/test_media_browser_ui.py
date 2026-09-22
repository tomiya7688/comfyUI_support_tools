from pathlib import Path
import os
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from comfyui_support_tools.entrypoints.workspace import create_navigation
from comfyui_support_tools.entrypoints.media_browser import create_media_browser
from comfyui_support_tools.entrypoints.media_smoke import create_samples, wait_until, exercise_media
from comfyui_support_tools.applications.main_gui.data.processing import media_io
from comfyui_support_tools.applications.main_gui.ui.processing.shell_window import ShellWindow
from comfyui_support_tools.shared.contracts.tool_entry import ToolEntry
from comfyui_support_tools.shared.contracts.media_event import MediaEvent
from comfyui_support_tools.shared.contracts.media_preview import MediaPreview

TOOLS = (ToolEntry("test", "Legacy Test", "Utility"),)


class MediaGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32" and not os.environ.get("DISPLAY"):
            raise unittest.SkipTest("Requires a display; Windows CI always exercises Tk")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)/"日本語 media"
        create_samples(self.root)
        self.opened, self.errors = [], []
        self.window = ShellWindow(create_navigation(TOOLS), self.opened.append, create_media_browser())
        self.window.report_callback_exception = lambda *args: self.errors.append(args)
        self.window.update()
        self.browser = self.window.workspace.media
        self.events = []
        self.window.bind("<<MediaSelectionChanged>>", lambda _event: self.events.append(self.window.media_selection))

    def tearDown(self):
        self.window.destroy()
        for thread in threading.enumerate():
            if thread.name in ("media-scan", "media-preview"):
                thread.join(5)
                self.assertFalse(thread.is_alive())
        self.tmp.cleanup()
        self.assertEqual(self.errors, [])

    def load(self, collection="library"):
        self.browser.load_folder(str(self.root), collection)
        wait_until(self.window, lambda: not self.browser.commander.view()[1]["loading"])
        self.browser._render()
        return self.browser.commander.view()[0]

    def test_real_grid_thumbnails_and_preview(self):
        items = self.load()
        wait_until(self.window, lambda: len(self.browser.grid_view.images) == 4)
        image = next(item for item in items if item.name == "画像 sample.png")
        self.browser.select((image.id,))
        wait_until(self.window, lambda: self.window.media_preview.photo is not None)
        self.assertEqual(self.window.media_selection, (image,))
        self.assertIn(image.name, self.window.inspector_text.cget("text"))
        self.assertTrue(self.events)
        self.assertLessEqual(len(self.browser.grid_view.items), 60)

    def test_thumbnail_ctrl_shift_and_keyboard_selection(self):
        items = self.load()
        grid = self.browser.grid_view
        grid._choose(0)
        self.assertEqual(len(self.window.media_selection), 1)
        grid._choose(2, control=True)
        self.assertEqual(len(self.window.media_selection), 2)
        grid._choose(3, shift=True)
        self.assertEqual({item.id for item in self.window.media_selection}, {items[2].id, items[3].id})
        grid._all()
        self.assertEqual(len(self.window.media_selection), 4)
        grid._key(SimpleNamespace(keysym="Home", state=0))
        self.assertEqual(self.window.media_selection, (items[0],))

    def test_list_multiselection_and_view_switch_preserve_selection(self):
        items = self.load()
        self.browser.mode.set("リスト")
        self.browser._render()
        self.browser.table.selection_set((items[0].id, items[1].id))
        self.window.update()
        self.assertEqual(len(self.window.media_selection), 2)
        self.browser.mode.set("サムネイル")
        self.browser._render()
        self.window.update()
        self.assertEqual(len(self.window.media_selection), 2)

    def test_library_filter_search_sort_and_collection(self):
        self.load("generated")
        self.window.select_section("generated")
        self.assertEqual(self.browser.commander.view()[1]["total"], 4)
        self.window.select_section("dataset")
        self.assertEqual(self.browser.commander.view()[1]["total"], 0)
        self.window.select_section("videos")
        self.assertEqual(self.browser.commander.view()[1]["total"], 1)
        self.window.select_section("images")
        self.browser.query.set("画像")
        self.browser.apply_query()
        self.assertEqual(self.browser.commander.view()[1]["total"], 1)
        self.window.select_section("all")
        self.browser.query.set("")
        self.browser.sort.set("サイズ")
        self.browser.descending.set(True)
        self.browser.apply_query()
        sizes = [item.size for item in self.browser.commander.view()[0]]
        self.assertEqual(sizes, sorted(sizes, reverse=True))

    def test_broken_image_and_missing_folder_keep_ui_alive(self):
        items = self.load()
        broken = next(item for item in items if item.name == "broken.png")
        self.browser.select((broken.id,))
        wait_until(self.window, lambda: "不可" in self.window.media_preview.details.cget("text"))
        self.browser.load_folder(str(self.root/"not-found"))
        wait_until(self.window, lambda: not self.browser.commander.view()[1]["loading"])
        self.assertEqual(self.window.media_selection, ())
        self.assertIn("見つかりません", self.browser.commander.view()[1]["message"])
        self.assertTrue(self.window.winfo_exists())

    def test_blocked_scan_does_not_block_tk_event_loop(self):
        entered, release = threading.Event(), threading.Event()
        def blocked(*args):
            entered.set()
            release.wait(5)
        try:
            with mock.patch.object(media_io, "scan_folder", side_effect=blocked):
                self.browser.load_folder(str(self.root))
                self.assertTrue(entered.wait(2))
                heartbeat = []
                self.window.after(1, lambda: heartbeat.append(True))
                wait_until(self.window, lambda: heartbeat)
                self.assertEqual(heartbeat, [True])
                self.window.geometry("900x600")
                self.window.update()
                self.assertGreater(self.window.workspace.winfo_width(), 250)
        finally:
            release.set()

    def test_hidden_selection_clears_and_old_tools_still_work(self):
        items = self.load()
        self.browser.select((items[0].id,))
        self.window.workspace.show_tools()
        self.window.update()
        self.assertEqual(self.window.media_selection, ())
        self.window.workspace.tree.selection_set("test")
        self.window.update()
        self.window.workspace.open_button.invoke()
        self.assertEqual(self.opened, ["test"])
        self.window.workspace.show_media()
        self.assertEqual(len(self.window.media_selection), 1)
        self.browser.query.set("NO SUCH MEDIA")
        self.browser.apply_query()
        self.assertEqual(self.window.media_selection, ())

    def test_paging_controls_remain_visible_at_minimum_window_size(self):
        self.load()
        self.window.geometry("900x600")
        self.window.update()
        for widget in (self.browser.previous, self.browser.next, self.browser.status_label):
            self.assertTrue(widget.winfo_ismapped())
            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),
                                 self.browser.winfo_rooty()+self.browser.winfo_height())

    def test_stale_preview_token_is_ignored(self):
        self.load()
        before = self.window.media_preview.details.cget("text")
        stale = MediaEvent("preview", -1, preview=MediaPreview("bad", error="STALE RESULT"))
        with mock.patch.object(self.browser.commander, "poll", return_value=(False, (stale,))):
            # Invoke through the real timer so it never creates a duplicate timer.
            time.sleep(0.07)
            self.window.update()
        self.assertEqual(self.window.media_preview.details.cget("text"), before)

    def test_page_selection_cleared_and_rendered_tiles_bounded(self):
        png = (self.root/"画像 sample.png").read_bytes()
        for i in range(125):
            (self.root/f"bulk_{i:03}.png").write_bytes(png)
        self.load()
        self.assertEqual(len(self.browser.grid_view.items), 60)
        self.assertLessEqual(len(self.browser.grid_view.canvas.find_all()), 240)
        self.browser.grid_view._all()
        self.assertEqual(len(self.window.media_selection), 60)
        self.browser.move_page(1)
        self.assertEqual(self.window.media_selection, ())
        self.assertEqual(len(self.browser.grid_view.items), 60)
        self.browser.move_page(1)
        self.assertEqual(len(self.browser.grid_view.items), 9)

    def test_real_frozen_smoke_probe_can_run_from_source(self):
        exercise_media(self.window)


if __name__ == "__main__":
    unittest.main()
