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

    def test_venv_python_prefers_existing_venv_interpreter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            venv_dir = Path(temp_dir)
            interpreter = venv_dir / "Scripts" / "python.exe"
            interpreter.parent.mkdir(parents=True)
            interpreter.touch()

            self.assertEqual(runtime_python.venv_python(venv_dir), interpreter)


if __name__ == "__main__":
    unittest.main()
