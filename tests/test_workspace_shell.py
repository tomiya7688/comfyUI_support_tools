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


# {
#   責務: [NavigationTests: related test fixtures and cases for Navigation behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: [nav: nav fixture state used by the test cases]
#   引数: []
# }
class NavigationTests(unittest.TestCase):
    # {
    #   責務: [setUp: initializes per-test fixture state for NavigationTests]
    #   処理: [
    #     1: create the per-test inputs and fixture resources required by the scenario,
    #     2: register cleanup for resources owned by the fixture,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def setUp(self):
        self.nav = create_navigation(TOOLS)

    # {
    #   責務: [
    #     test_all_sections_and_categories_are_available: verifies the behavior described by "all sections and categories are available",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for all sections and categories are available,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_all_sections_and_categories_are_available(self):
        self.assertEqual(tuple(LABELS), SECTIONS)
        self.assertEqual(self.nav.categories(), ("Tag", "Video"))
        for section in SECTIONS:
            self.nav.select_section(section)

    # {
    #   責務: [
    #     test_search_is_case_insensitive_and_handles_japanese: verifies the behavior described by "search is case insensitive and handles japanese",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for search is case insensitive and handles japanese,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_search_is_case_insensitive_and_handles_japanese(self):
        self.assertEqual(self.nav.filter_tools("  TAGGER  ", ""), (TOOLS[0],))
        self.assertEqual(self.nav.filter_tools("動画", "Video"), (TOOLS[1],))
        self.assertEqual(self.nav.filter_tools("tagger", "Video"), ())

    # {
    #   責務: [
    #     test_recent_tools_are_unique_and_newest_first: verifies the behavior described by "recent tools are unique and newest first",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for recent tools are unique and newest first,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_recent_tools_are_unique_and_newest_first(self):
        self.assertEqual(self.nav.select_section("recent"), ())
        self.nav.request_open("tag")
        self.nav.request_open("video")
        self.nav.request_open("tag")
        self.assertEqual(self.nav.visible_tools(), TOOLS)

    # {
    #   責務: [test_history_is_bounded: verifies the behavior described by "history is bounded"]
    #   処理: [
    #     1: arrange case data and fixture state for history is bounded,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_history_is_bounded(self):
        entries = tuple(ToolEntry(str(i), str(i), "Test") for i in range(20))
        nav = create_navigation(entries)
        for item in entries:
            nav.request_open(item.id)
        self.assertEqual(len(nav.select_section("recent")), 12)
        self.assertEqual(nav.visible_tools()[0].id, "19")

    # {
    #   責務: [
    #     test_unknown_values_fail_without_mutating_state: verifies the behavior described by "unknown values fail without mutating state",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for unknown values fail without mutating state,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_unknown_values_fail_without_mutating_state(self):
        for method, args in ((self.nav.select_section, ("unknown",)),
                             (self.nav.filter_tools, ("tagger", "unknown")),
                             (self.nav.request_open, ("unknown",))):
            with self.assertRaises(ValueError):
                method(*args)
        self.assertEqual(self.nav.visible_tools(), TOOLS)

    # {
    #   責務: [
    #     test_duplicate_ids_rejected_and_empty_catalog_supported: verifies the behavior described by "duplicate ids rejected and empty catalog supported",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for duplicate ids rejected and empty catalog supported,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_duplicate_ids_rejected_and_empty_catalog_supported(self):
        with self.assertRaises(ValueError):
            NavigationProcessing((TOOLS[0], TOOLS[0]))
        nav = create_navigation(())
        self.assertEqual(nav.categories(), ())
        self.assertEqual(nav.visible_tools(), ())

    # {
    #   責務: [
    #     test_legacy_catalog_identifiers_resolve: verifies the behavior described by "legacy catalog identifiers resolve",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for legacy catalog identifiers resolve,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_legacy_catalog_identifiers_resolve(self):
        self.assertEqual(len({item[0] for item in TAB_CATALOG}), len(TAB_CATALOG))
        for index, item in enumerate(TAB_CATALOG):
            self.assertEqual(tab_index(item[0]), index)
        with self.assertRaises(ValueError):
            tab_index("not-a-tool")


# {
#   責務: [CatalogParityTests: related test fixtures and cases for CatalogParity behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class CatalogParityTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_catalog_matches_every_legacy_tab_in_order: verifies the behavior described by "catalog matches every legacy tab in order",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for catalog matches every legacy tab in order,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_catalog_matches_every_legacy_tab_in_order(self):
        # Read source without importing legacy backends or opening their windows.
        tree = ast.parse((ROOT / "scripts/app.py").read_text(encoding="utf-8"))
        lists = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "tab_titles" for t in node.targets)]
        self.assertEqual(len(lists), 1)
        self.assertEqual(tuple(item.elts[1].id for item in lists[0].elts),
                         tuple(item[0] for item in TAB_CATALOG))


# {
#   責務: [ShellGuiTests: related test fixtures and cases for ShellGui behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: [
#     opened: opened fixture state used by the test cases,
#     window: Tk root window owned by the UI test,
#     errors: errors collected from navigation callbacks,
#   ],
#   引数: []
# }
class ShellGuiTests(unittest.TestCase):
    # {
    #   責務: [setUpClass: skips ShellGuiTests when required platform or display prerequisites are unavailable]
    #   処理: [1: check platform/display prerequisites, 2: skip the UI suite when the required display is unavailable]
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32" and not os.environ.get("DISPLAY"):
            raise unittest.SkipTest("Tk integration needs a display; Windows CI runs these tests")

    # {
    #   責務: [setUp: initializes per-test fixture state for ShellGuiTests]
    #   処理: [
    #     1: create the per-test inputs and fixture resources required by the scenario,
    #     2: register cleanup for resources owned by the fixture,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def setUp(self):
        self.opened = []
        self.window = ShellWindow(create_navigation(TOOLS), self.opened.append)
        self.errors = []
        self.window.report_callback_exception = lambda *args: self.errors.append(args)
        self.window.update()

    # {
    #   責務: [tearDown: releases per-test resources created by ShellGuiTests]
    #   処理: [1: stop owned workers/servers and release temporary files or UI resources]
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def tearDown(self):
        self.window.destroy()
        self.assertEqual(self.errors, [])

    # {
    #   責務: [test_five_regions_display: verifies the behavior described by "five regions display"]
    #   処理: [
    #     1: arrange case data and fixture state for five regions display,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_five_regions_display(self):
        for name in ("toolbar", "library", "workspace", "inspector", "jobs"):
            self.assertTrue(getattr(self.window, name).winfo_ismapped(), name)
        self.assertGreater(self.window.workspace.winfo_width(), 300)

    # {
    #   責務: [
    #     test_library_selection_event_changes_center_heading: verifies the behavior described by "library selection event changes center heading",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for library selection event changes center heading,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_library_selection_event_changes_center_heading(self):
        for section in SECTIONS:
            self.window.library.tree.selection_set(section)
            self.window.update()
            self.assertEqual(self.window.workspace.title.cget("text"), LABELS[section])

    # {
    #   責務: [
    #     test_search_and_category_update_visible_tools: verifies the behavior described by "search and category update visible tools",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for search and category update visible tools,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_search_and_category_update_visible_tools(self):
        self.window.query.set("動画")
        self.window.update()
        self.assertEqual(self.window.workspace.tree.get_children(), ("video",))
        self.window.category.set("Tag")
        self.window.filter_tools()
        self.assertEqual(self.window.workspace.tree.get_children(), ())

    # {
    #   責務: [
    #     test_selected_tool_activation_and_inspector: verifies the behavior described by "selected tool activation and inspector",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for selected tool activation and inspector,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_selected_tool_activation_and_inspector(self):
        self.window.workspace.tree.selection_set("tag")
        self.window.update()
        self.assertIn("Folder Tagger", self.window.inspector_text.cget("text"))
        self.window.workspace.open_button.invoke()
        self.assertEqual(self.opened, ["tag"])
        self.window.select_section("recent")
        self.assertEqual(self.window.workspace.tree.get_children(), ("tag",))

    # {
    #   責務: [
    #     test_empty_selection_does_not_open_a_tool: verifies the behavior described by "empty selection does not open a tool",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for empty selection does not open a tool,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_empty_selection_does_not_open_a_tool(self):
        self.window.workspace.open_button.invoke()
        self.assertEqual(self.opened, [])

    # {
    #   責務: [
    #     test_all_collapse_combinations_and_restore_keep_order: verifies the behavior described by "all collapse combinations and restore keep order",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for all collapse combinations and restore keep order,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [
    #     test_small_window_and_draggable_sashes: verifies the behavior described by "small window and draggable sashes",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for small window and draggable sashes,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_small_window_and_draggable_sashes(self):
        self.window.geometry("900x600")
        self.window.update()
        self.window.horizontal.sashpos(0, 170)
        self.window.vertical.sashpos(0, 350)
        self.window.update()
        self.assertGreater(self.window.workspace.winfo_width(), 250)
        self.assertGreater(self.window.jobs.winfo_height(), 80)

    # {
    #   責務: [test_legacy_home_requests_ui_only: verifies the behavior described by "legacy home requests ui only"]
    #   処理: [
    #     1: arrange case data and fixture state for legacy home requests ui only,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_legacy_home_requests_ui_only(self):
        self.window.open_legacy_home()
        self.assertEqual(self.opened, [""])

    # {
    #   責務: [
    #     test_recent_state_survives_window_recreation: verifies the behavior described by "recent state survives window recreation",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for recent state survives window recreation,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [Tk test window/event loopを作成し、test終了時に破棄する]
    # }
    def test_recent_state_survives_window_recreation(self):
        self.window.commander.request_open("video")
        self.window.commander.select_section("recent")
        other = ShellWindow(self.window.commander, self.opened.append)
        try:
            other.update()
            self.assertEqual(other.commander.select_section("recent"), (TOOLS[1],))
        finally:
            other.destroy()


# {
#   責務: [LegacyBridgeTests: related test fixtures and cases for LegacyBridge behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class LegacyBridgeTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_selects_requested_tab_and_can_return_without_subprocess: verifies the behavior described by "selects requested tab and can return without subprocess",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for selects requested tab and can return without subprocess,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: mock.Mock built or selected by this helper]
    # }
    def test_selects_requested_tab_and_can_return_without_subprocess(self):
        spec = importlib.util.spec_from_file_location("workspace_launcher", ROOT / "tabbed_tools_gui.py")
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        fake = ModuleType("scripts.app")
        app = mock.Mock()
        fake.TabbedToolsApp = mock.Mock(return_value=app)
        callbacks = []
        app.winfo_children.return_value = [mock.Mock()]

        # {
        #   責務: [button: creates a mock button that retains the supplied callback]
        #   処理: [1: create a mock button with the supplied callback, 2: return it for invocation by the test]
        #   引数: [
        #     *_args: additional logging arguments intentionally ignored (unspecified),
        #     **kwargs: keyword request options captured by the fake client (unspecified),
        #   ],
        #   戻り値: [result: mock.Mock built or selected by this helper]
        # }
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
