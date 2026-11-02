from pathlib import Path
import sys
import tempfile
import unittest

MODULE_DIR = Path(__file__).parents[3] / "tools" / "architecture"
sys.path.insert(0, str(MODULE_DIR))

import app_boundary_check  # noqa: E402


# {
#   責務: [AppBoundaryCheckTests: related test fixtures and cases for AppBoundaryCheck behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class AppBoundaryCheckTests(unittest.TestCase):
    # {
    #   責務: [test_detects_external_import: verifies the behavior described by "detects external import"]
    #   処理: [
    #     1: arrange case data and fixture state for detects external import,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_detects_external_import(self):
        violations = app_boundary_check.scan_source("scripts/example.py", "import nuno.worker\n")
        self.assertEqual([item.rule for item in violations], ["ARCH001"])

    # {
    #   責務: [
    #     test_detects_sys_executable_script_launch: verifies the behavior described by "detects sys executable script launch",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for detects sys executable script launch,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_detects_sys_executable_script_launch(self):
        source = "import subprocess, sys\nsubprocess.Popen([sys.executable, 'other.py'])\n"
        rules = [item.rule for item in app_boundary_check.scan_source("scripts/tabs/example.py", source)]
        self.assertIn("ARCH002", rules)
        self.assertIn("ARCH004", rules)

    # {
    #   責務: [test_detects_path_python: verifies the behavior described by "detects path python"]
    #   処理: [
    #     1: arrange case data and fixture state for detects path python,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_detects_path_python(self):
        source = "import shutil, subprocess\nshutil.which('python')\nsubprocess.run(['py', 'tool.py'])\n"
        rules = [item.rule for item in app_boundary_check.scan_source("scripts/example.py", source)]
        self.assertEqual(rules.count("ARCH003"), 2)

    # {
    #   責務: [
    #     test_allows_packaged_exe_and_http_client: verifies the behavior described by "allows packaged exe and http client",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for allows packaged exe and http client,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_allows_packaged_exe_and_http_client(self):
        source = "import subprocess\nimport requests\nsubprocess.Popen(['OtherService.exe', '--port', '8188'])\nrequests.get('http://127.0.0.1:8188/health')\n"
        self.assertEqual(app_boundary_check.scan_source("scripts/example.py", source), [])

    # {
    #   責務: [
    #     test_baseline_blocks_new_violation_and_requires_reduction: verifies the behavior described by "baseline blocks new violation and requires reduction",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for baseline blocks new violation and requires reduction,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_baseline_blocks_new_violation_and_requires_reduction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts" / "tabs").mkdir(parents=True)
            target = root / "scripts" / "tabs" / "legacy.py"
            target.write_text("import sys\nx = sys.executable\n", encoding="utf-8")
            baseline = root / "baseline.json"
            baseline.write_text('{"allow":[{"path":"scripts/tabs/legacy.py","rule":"ARCH002","max_count":1,"reason":"legacy"}]}', encoding="utf-8")
            _, errors = app_boundary_check.scan_repository(root, baseline)
            self.assertEqual(errors, [])

            target.write_text("import sys\nx = sys.executable\ny = sys.executable\n", encoding="utf-8")
            _, errors = app_boundary_check.scan_repository(root, baseline)
            self.assertTrue(any("baseline allows 1" in error for error in errors))

            target.write_text("x = 1\n", encoding="utf-8")
            _, errors = app_boundary_check.scan_repository(root, baseline)
            self.assertTrue(any("baseline can be reduced" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
