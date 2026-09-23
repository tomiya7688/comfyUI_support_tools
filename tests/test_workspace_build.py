"""Frozen workspace discovery and isolated launch command regression tests."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("workspace_builder", ROOT / "tools/build/build_one_dir.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class WorkspaceBuildTests(unittest.TestCase):
    def test_build_discovers_own_src_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "dist"
            (root / "LICENSE").write_text("MIT test license", encoding="utf-8")
            (root / "THIRD_PARTY_NOTICES.md").write_text("Test notices", encoding="utf-8")
            (root / "requirements-kadoka-tools.txt").write_text(
                (ROOT / "requirements-kadoka-tools.txt").read_text(encoding="utf-8"), encoding="utf-8"
            )
            tcl_license = root / "licenses" / "TclTk" / "license.terms"
            tcl_license.parent.mkdir(parents=True)
            tcl_license.write_text("Test Tcl/Tk terms", encoding="utf-8")
            exe = builder.executable_path(output)
            exe.parent.mkdir(parents=True)
            exe.touch()
            with mock.patch.object(builder.subprocess, "run") as run:
                self.assertEqual(builder.build(root, output), exe)
            self.assertEqual((exe.parent / "LICENSE").read_text(encoding="utf-8"), "MIT test license")
            self.assertEqual((exe.parent / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8"), "Test notices")
            self.assertTrue((exe.parent / "third_party_components.resolved.json").is_file())
            self.assertTrue((exe.parent / "licenses" / "TclTk" / "license.terms").is_file())
            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--paths") + 1], str(root / "src"))
            self.assertIn("--onedir", command)

    def test_smoke_checks_both_uis_outside_distribution_without_python_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "KadokaTools.exe"
            with mock.patch.dict(os.environ, {"PYTHONPATH": "foreign", "PYTHONHOME": "foreign"}), mock.patch.object(builder.subprocess, "run") as run:
                builder.run_smoke_test(exe)
            self.assertEqual([call.args[0][1:] for call in run.call_args_list],
                             [["--smoke-test"], ["--new-ui", "--smoke-test"], ["--shell-smoke-test"]])
            for call in run.call_args_list:
                self.assertNotEqual(Path(call.kwargs["cwd"]), exe.parent)
                self.assertNotIn("PYTHONPATH", call.kwargs["env"])
                self.assertNotIn("PYTHONHOME", call.kwargs["env"])
                self.assertEqual(call.kwargs["timeout"], 60)
                self.assertTrue(call.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
