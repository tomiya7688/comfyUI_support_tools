"""Offline navigation, real Tk layout, and legacy-bridge regression tests."""
import ast
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from comfyui_support_tools.applications.main_gui.process.processing.navigation_processing import NavigationProcessing, SECTIONS
from comfyui_support_tools.applications.main_gui.ui.processing.library_panel import LABELS
from comfyui_support_tools.applications.main_gui.ui.processing.shell_window import ShellWindow
from comfyui_support_tools.entrypoints.workspace import create_navigation
from comfyui_support_tools.shared.contracts.tool_entry import ToolEntry
from scripts.tab_catalog import TAB_CATALOG, tab_index

TOOLS = (ToolEntry("tag", "Folder Tagger", "Tag"), ToolEntry("video", "動画変換", "Video"))


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.nav = create_navigation(TOOLS)

    def test_all_sections_and_categories_are_available(self):
        self.assertEqual(tuple(LABELS), SECTIONS)
        self.assertEqual(self.nav.categories(), ("Tag", "Video"))
        for section in SECTIONS:
            self.nav.select_section(section)

    def test_search_is_case_insensitive_and_handles_japanese(self):
        self.assertEqual(self.nav.filter_tools("  TAGGER  ", ""), (TOOLS[0],))
        self.assertEqual(self.nav.filter_tools("動画", "Video"), (TOOLS[1],))
        self.assertEqual(self.nav.filter_tools("tagger", "Video"), ())

    def test_recent_tools_are_unique_and_newest_first(self):
        self.assertEqual(self.nav.select_section("recent"), ())
        self.nav.request_open("tag")
        self.nav.request_open("video")
        self.nav.request_open("tag")
        self.assertEqual(self.nav.visible_tools(), TOOLS)

    def test_history_is_bounded(self):
        entries = tuple(ToolEntry(str(i), str(i), "Test") for i in range(20))
        nav = create_navigation(entries)
        for item in entries:
            nav.request_open(item.id)
        self.assertEqual(len(nav.select_section("recent")), 12)
        self.assertEqual(nav.visible_tools()[0].id, "19")

    def test_unknown_values_fail_without_mutating_state(self):
        for method, args in ((self.nav.select_section, ("unknown",)),
                             (self.nav.filter_tools, ("tagger", "unknown")),
                             (self.nav.request_open, ("unknown",))):
            with self.assertRaises(ValueError):
                method(*args)
        self.assertEqual(self.nav.visible_tools(), TOOLS)

    def test_duplicate_ids_rejected_and_empty_catalog_supported(self):
        with self.assertRaises(ValueError):
            NavigationProcessing((TOOLS[0], TOOLS[0]))
        nav = create_navigation(())
        self.assertEqual(nav.categories(), ())
        self.assertEqual(nav.visible_tools(), ())

    def test_legacy_catalog_identifiers_resolve(self):
        self.assertEqual(len({item[0] for item in TAB_CATALOG}), len(TAB_CATALOG))
        for index, item in enumerate(TAB_CATALOG):
            self.assertEqual(tab_index(item[0]), index)
        with self.assertRaises(ValueError):
            tab_index("not-a-tool")


class CatalogParityTests(unittest.TestCase):
    def test_catalog_matches_every_legacy_tab_in_order(self):
        # Read source without importing legacy backends or opening their windows.
        tree = ast.parse((ROOT / "scripts/app.py").read_text(encoding="utf-8"))
        lists = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "tab_titles" for t in node.targets)]
        self.assertEqual(len(lists), 1)
        self.assertEqual(tuple(item.elts[1].id for item in lists[0].elts),
                         tuple(item[0] for item in TAB_CATALOG))


class ShellGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32" and not os.environ.get("DISPLAY"):
            raise unittest.SkipTest("Tk integration needs a display; Windows CI runs these tests")

    def setUp(self):
        self.opened = []
        self.window = ShellWindow(create_navigation(TOOLS), self.opened.append)
        self.errors = []
        self.window.report_callback_exception = lambda *args: self.errors.append(args)
        self.window.update()

    def tearDown(self):
        self.window.destroy()
        self.assertEqual(self.errors, [])

    def test_five_regions_display(self):
        for name in ("toolbar", "library", "workspace", "inspector", "jobs"):
            self.assertTrue(getattr(self.window, name).winfo_ismapped(), name)
        self.assertGreater(self.window.workspace.winfo_width(), 300)

    def test_library_selection_event_changes_center_heading(self):
        for section in SECTIONS:
            self.window.library.tree.selection_set(section)
            self.window.update()
            self.assertEqual(self.window.workspace.title.cget("text"), LABELS[section])

    def test_search_and_category_update_visible_tools(self):
        self.window.query.set("動画")
        self.window.update()
        self.assertEqual(self.window.workspace.tree.get_children(), ("video",))
        self.window.category.set("Tag")
        self.window.filter_tools()
        self.assertEqual(self.window.workspace.tree.get_children(), ())

    def test_selected_tool_activation_and_inspector(self):
        self.window.workspace.tree.selection_set("tag")
        self.window.update()
        self.assertIn("Folder Tagger", self.window.inspector_text.cget("text"))
        self.window.workspace.open_button.invoke()
        self.assertEqual(self.opened, ["tag"])
        self.window.select_section("recent")
        self.assertEqual(self.window.workspace.tree.get_children(), ("tag",))

    def test_empty_selection_does_not_open_a_tool(self):
        self.window.workspace.open_button.invoke()
        self.assertEqual(self.opened, [])

    def test_all_collapse_combinations_and_restore_keep_order(self):
        for mask in range(8):
            for index, name in enumerate(("library", "inspector", "jobs")):
                self.window.set_pane_visible(name, bool(mask & (1 << index)))
            self.window.update()
            self.assertTrue(self.window.workspace.winfo_ismapped())
            for name in ("library", "inspector", "jobs"):
                self.window.set_pane_visible(name, True)
            self.window.update()
            self.assertEqual(self.window.horizontal.panes(),
                             tuple(str(getattr(self.window, name)) for name in ("library", "workspace", "inspector")))

    def test_small_window_and_draggable_sashes(self):
        self.window.geometry("900x600")
        self.window.update()
        self.window.horizontal.sashpos(0, 170)
        self.window.vertical.sashpos(0, 350)
        self.window.update()
        self.assertGreater(self.window.workspace.winfo_width(), 250)
        self.assertGreater(self.window.jobs.winfo_height(), 80)

    def test_legacy_home_requests_ui_only(self):
        self.window.open_legacy_home()
        self.assertEqual(self.opened, [""])

    def test_recent_state_survives_window_recreation(self):
        self.window.commander.request_open("video")
        self.window.commander.select_section("recent")
        other = ShellWindow(self.window.commander, self.opened.append)
        try:
            other.update()
            self.assertEqual(other.commander.select_section("recent"), (TOOLS[1],))
        finally:
            other.destroy()


class LegacyBridgeTests(unittest.TestCase):
    def test_selects_requested_tab_and_can_return_without_subprocess(self):
        spec = importlib.util.spec_from_file_location("workspace_launcher", ROOT / "tabbed_tools_gui.py")
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        fake = ModuleType("scripts.app")
        app = mock.Mock()
        fake.TabbedToolsApp = mock.Mock(return_value=app)
        callbacks = []
        app.winfo_children.return_value = [mock.Mock()]

        def button(*_args, **kwargs):
            callbacks.append(kwargs["command"])
            return mock.Mock()

        app.mainloop.side_effect = lambda: callbacks[0]()
        with mock.patch.dict(sys.modules, {"scripts.app": fake}), mock.patch("tkinter.ttk.Button", side_effect=button):
            self.assertTrue(launcher._legacy_window("FolderTaggerTab"))
        app.show_tab.assert_called_once_with(tab_index("FolderTaggerTab"))
        app._close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
