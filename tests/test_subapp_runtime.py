from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from scripts import subapp_runtime


# {
#   責務: [SubAppRuntimeTests: related test fixtures and cases for SubAppRuntime behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class SubAppRuntimeTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_resolves_packaged_exe_from_app_root: verifies the behavior described by "resolves packaged exe from app root",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for resolves packaged exe from app root,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_resolves_packaged_exe_from_app_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "Tool.exe"
            exe.write_bytes(b"MZ")
            with mock.patch.object(subapp_runtime, "APP_DIR", root):
                self.assertEqual(subapp_runtime.packaged_executable("Tool"), exe)

    # {
    #   責務: [
    #     test_resolves_packaged_exe_from_apps_directory: verifies the behavior described by "resolves packaged exe from apps directory",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for resolves packaged exe from apps directory,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_resolves_packaged_exe_from_apps_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "apps" / "Tool" / "Tool.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"MZ")
            with mock.patch.object(subapp_runtime, "APP_DIR", root):
                self.assertEqual(subapp_runtime.packaged_executable("Tool"), exe)

    # {
    #   責務: [
    #     test_environment_override_is_explicit_executable_path: verifies the behavior described by "environment override is explicit executable path",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for environment override is explicit executable path,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_environment_override_is_explicit_executable_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Custom.exe"
            with mock.patch.dict(os.environ, {"KADOKA_TOOLS_TOOL_EXE": str(exe)}):
                self.assertEqual(subapp_runtime.packaged_executable("Tool"), exe.resolve())

    # {
    #   責務: [
    #     test_launch_rejects_missing_executable_without_python_fallback: verifies the behavior described by "launch rejects missing executable without python fallback",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for launch rejects missing executable without python fallback,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_launch_rejects_missing_executable_without_python_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "Missing.exe"
            with self.assertRaises(FileNotFoundError):
                subapp_runtime.launch_packaged_executable(missing)

    # {
    #   責務: [
    #     test_launch_uses_executable_directly: verifies the behavior described by "launch uses executable directly",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for launch uses executable directly,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
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
