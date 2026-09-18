from pathlib import Path
import sys
import tempfile
import unittest

MODULE_DIR = Path(__file__).parents[3] / "tools" / "architecture"
sys.path.insert(0, str(MODULE_DIR))

import app_boundary_check  # noqa: E402


class AppBoundaryCheckTests(unittest.TestCase):
    def test_detects_external_import(self):
        violations = app_boundary_check.scan_source("scripts/example.py", "import nuno.worker\n")
        self.assertEqual([item.rule for item in violations], ["ARCH001"])

    def test_detects_sys_executable_script_launch(self):
        source = "import subprocess, sys\nsubprocess.Popen([sys.executable, 'other.py'])\n"
        rules = [item.rule for item in app_boundary_check.scan_source("scripts/tabs/example.py", source)]
        self.assertIn("ARCH002", rules)
        self.assertIn("ARCH004", rules)

    def test_detects_path_python(self):
        source = "import shutil, subprocess\nshutil.which('python')\nsubprocess.run(['py', 'tool.py'])\n"
        rules = [item.rule for item in app_boundary_check.scan_source("scripts/example.py", source)]
        self.assertEqual(rules.count("ARCH003"), 2)

    def test_detects_external_python_path_injection(self):
        source = "import sys\nsys.path.insert(0, 'C:/OtherApp/.venv/Lib/site-packages')\n"
        rules = [item.rule for item in app_boundary_check.scan_source("scripts/example.py", source)]
        self.assertIn("ARCH005", rules)

    def test_allows_local_non_runtime_sys_path(self):
        source = "import sys\nsys.path.insert(0, 'scripts/plugins')\n"
        self.assertEqual(app_boundary_check.scan_source("scripts/example.py", source), [])

    def test_allows_packaged_exe_and_http_client(self):
        source = "import subprocess\nimport requests\nsubprocess.Popen(['OtherService.exe', '--port', '8188'])\nrequests.get('http://127.0.0.1:8188/health')\n"
        self.assertEqual(app_boundary_check.scan_source("scripts/example.py", source), [])

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
