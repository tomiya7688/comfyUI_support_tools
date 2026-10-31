from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import runtime_python


class RuntimePythonTest(unittest.TestCase):
    def test_preferred_python_uses_current_interpreter_when_not_frozen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(runtime_python, "python_root", return_value=root),
                patch.object(runtime_python, "is_frozen", return_value=False),
                patch.object(runtime_python.sys, "executable", r"C:\Python310\python.exe"),
            ):
                self.assertEqual(
                    runtime_python.preferred_python(),
                    Path(r"C:\Python310\python.exe"),
                )

    def test_preferred_python_does_not_use_frozen_application_executable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = root / "python3.10" / "python.exe"
            expected.parent.mkdir()
            expected.touch()
            with (
                patch.object(runtime_python, "python_root", return_value=root),
                patch.object(runtime_python, "is_frozen", return_value=True),
                patch.object(runtime_python.sys, "executable", r"C:\dist\KadokaTools.exe"),
            ):
                self.assertEqual(runtime_python.preferred_python(), expected)

    def test_python_root_is_missing_until_explicitly_configured(self):
        with patch.dict(os.environ, {"KADOKA_PYTHON_ROOT": ""}):
            self.assertIsNone(runtime_python.python_root())

    def test_frozen_app_requires_a_configured_external_python(self):
        with (
            patch.object(runtime_python, "python_root", return_value=None),
            patch.object(runtime_python, "is_frozen", return_value=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "KADOKA_PYTHON_ROOT"):
                runtime_python.preferred_python()

    def test_setup_launchers_do_not_contain_machine_specific_python_roots(self):
        repository = Path(__file__).resolve().parents[1]
        launchers = (
            repository / "setup_kadoka_tools.bat",
            repository / "nuno" / "_touka" / "run_image_enhancer.bat",
        )
        for launcher in launchers:
            with self.subTest(launcher=launcher.name):
                self.assertNotIn("E:\\program_files", launcher.read_text(encoding="utf-8").lower())

    def test_kadoka_setup_requires_supported_cpython_without_unversioned_fallback(self):
        setup = (
            (Path(__file__).resolve().parents[1] / "setup_kadoka_tools.bat")
            .read_text(encoding="utf-8")
            .lower()
        )
        self.assertIn("kadoka_python31118", setup)
        self.assertIn("py -3.11.18 -m venv", setup)
        self.assertIn("sys.implementation.name == 'cpython'", setup)
        self.assertIn("sys.version_info >= (3, 11, 18)", setup)
        self.assertIn(".venv-python-pre-31118", setup)
        self.assertIn(":migrate_unsupported_environment", setup)
        self.assertNotIn("python -m venv", setup)
        self.assertNotIn("py -3.10", setup)

    # {
    #   責務: [test_nuno_launcher_requires_supported_cpython: Nuno起動バッチのPython要件を検証する]
    #   処理: [1: 起動バッチを読む, 2: CPythonの最低版と安全な退避を確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_nuno_launcher_requires_supported_cpython_without_unversioned_fallback(self):
        launcher = (
            (Path(__file__).resolve().parents[1] / "nuno" / "_touka" / "run_image_enhancer.bat")
            .read_text(encoding="utf-8")
            .lower()
        )
        self.assertIn("kadoka_python31118", launcher)
        self.assertIn("py -3.11.18 -m venv", launcher)
        self.assertIn("sys.implementation.name == 'cpython'", launcher)
        self.assertIn("sys.version_info >= (3, 11, 18)", launcher)
        self.assertIn(".venv-python-pre-31118", launcher)
        self.assertNotIn("python -m venv", launcher)
        self.assertNotIn("py -3.10", launcher)

    def test_onedir_batch_falls_back_to_supported_cpython_launcher(self):
        batch = (
            (Path(__file__).resolve().parents[1] / "tools" / "build" / "build_onedir.bat")
            .read_text(encoding="utf-8")
            .lower()
        )
        self.assertIn("py -3.11.18", batch)
        self.assertIn("sys.implementation.name == 'cpython'", batch)
        self.assertIn("sys.version_info >= (3, 11, 18)", batch)
        self.assertIn(":try_python_launcher", batch)

    def test_venv_python_prefers_existing_venv_interpreter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            venv_dir = Path(temp_dir)
            interpreter = venv_dir / "Scripts" / "python.exe"
            interpreter.parent.mkdir(parents=True)
            interpreter.touch()

            self.assertEqual(runtime_python.venv_python(venv_dir), interpreter)


if __name__ == "__main__":
    unittest.main()
