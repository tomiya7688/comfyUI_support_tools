from pathlib import Path
import sys
import unittest

MODULE_DIR = Path(__file__).parents[3] / "tools" / "architecture"
sys.path.insert(0, str(MODULE_DIR))

import upd_check  # noqa: E402


# {
#   責務: [UpdCheckTests: related test fixtures and cases for UpdCheck behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class UpdCheckTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_clean_repository_scaffold_has_no_findings: verifies the behavior described by "clean repository scaffold has no findings",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for clean repository scaffold has no findings,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_clean_repository_scaffold_has_no_findings(self):
        root = Path(__file__).parents[3]
        self.assertEqual(upd_check.scan_repository(root), [])

    # {
    #   責務: [
    #     test_detects_ui_to_data_direct_dependency: verifies the behavior described by "detects ui to data direct dependency",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for detects ui to data direct dependency,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_detects_ui_to_data_direct_dependency(self):
        path = "src/comfyui_support_tools/applications/main/ui/processing/view.py"
        source = (
            "from comfyui_support_tools.applications.main.data.processing.store import load\n"
            "def render(): return load()\n"
        )
        rules = [item.rule for item in upd_check.scan_source(path, source)]
        self.assertIn("UPD101", rules)

    # {
    #   責務: [
    #     test_detects_cross_application_internal_dependency: verifies the behavior described by "detects cross application internal dependency",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for detects cross application internal dependency,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_detects_cross_application_internal_dependency(self):
        path = "src/comfyui_support_tools/applications/main/process/processing/job.py"
        source = (
            "from comfyui_support_tools.applications.tagger.process.processing.engine import run\n"
        )
        rules = [item.rule for item in upd_check.scan_source(path, source)]
        self.assertIn("UPD102", rules)

    # {
    #   責務: [
    #     test_allows_adjacent_messenger_to_commander_boundary: verifies the behavior described by "allows adjacent messenger to commander boundary",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for allows adjacent messenger to commander boundary,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_allows_adjacent_messenger_to_commander_boundary(self):
        path = "src/comfyui_support_tools/applications/main/ui/messenger/process.py"
        source = (
            "from comfyui_support_tools.applications.main.process.commander.bootstrap import BootstrapCommander\n"
        )
        self.assertEqual(upd_check.scan_source(path, source), [])

    # {
    #   責務: [
    #     test_detects_direct_work_in_commander: verifies the behavior described by "detects direct work in commander",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for detects direct work in commander,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_detects_direct_work_in_commander(self):
        path = "src/comfyui_support_tools/applications/main/data/commander/config.py"
        source = "def run(path):\n    return open(path).read()\n"
        rules = [item.rule for item in upd_check.scan_source(path, source)]
        self.assertIn("UPD203", rules)

    # {
    #   責務: [
    #     test_detects_loop_and_calculation_in_commander: verifies the behavior described by "detects loop and calculation in commander",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for detects loop and calculation in commander,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_detects_loop_and_calculation_in_commander(self):
        path = "src/comfyui_support_tools/applications/main/process/commander/work.py"
        source = "def run(values):\n    total = 0\n    for value in values:\n        total = total + value\n"
        rules = [item.rule for item in upd_check.scan_source(path, source)]
        self.assertIn("UPD201", rules)
        self.assertIn("UPD202", rules)


if __name__ == "__main__":
    unittest.main()
