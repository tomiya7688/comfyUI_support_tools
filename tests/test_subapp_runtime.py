from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from scripts import subapp_runtime


class SubAppRuntimeTests(unittest.TestCase):
    def test_resolves_packaged_exe_from_app_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "Tool.exe"
            exe.write_bytes(b"MZ")
            with mock.patch.object(subapp_runtime, "APP_DIR", root):
                self.assertEqual(subapp_runtime.packaged_executable("Tool"), exe)

    def test_resolves_packaged_exe_from_apps_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "apps" / "Tool" / "Tool.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"MZ")
            with mock.patch.object(subapp_runtime, "APP_DIR", root):
                self.assertEqual(subapp_runtime.packaged_executable("Tool"), exe)

    def test_environment_override_is_explicit_executable_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Custom.exe"
            with mock.patch.dict(os.environ, {"KADOKA_TOOLS_TOOL_EXE": str(exe)}):
                self.assertEqual(subapp_runtime.packaged_executable("Tool"), exe.resolve())

    def test_launch_rejects_missing_executable_without_python_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "Missing.exe"
            with self.assertRaises(FileNotFoundError):
                subapp_runtime.launch_packaged_executable(missing)

    def test_launch_uses_executable_directly(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Tool.exe"
            exe.write_bytes(b"MZ")
            with mock.patch("scripts.subapp_runtime.subprocess.Popen") as popen:
                subapp_runtime.launch_packaged_executable(exe, "--health")
                command = popen.call_args.args[0]
                self.assertEqual(command, [str(exe), "--health"])


if __name__ == "__main__":
    unittest.main()
