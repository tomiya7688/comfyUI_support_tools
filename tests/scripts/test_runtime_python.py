from __future__ import annotations

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
            with (
                patch.object(runtime_python, "python_root", return_value=root),
                patch.object(runtime_python, "is_frozen", return_value=True),
                patch.object(runtime_python.sys, "executable", r"C:\dist\KadokaTools.exe"),
            ):
                self.assertEqual(runtime_python.preferred_python(), expected)

    def test_venv_python_prefers_existing_venv_interpreter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            venv_dir = Path(temp_dir)
            interpreter = venv_dir / "Scripts" / "python.exe"
            interpreter.parent.mkdir(parents=True)
            interpreter.touch()

            self.assertEqual(runtime_python.venv_python(venv_dir), interpreter)


if __name__ == "__main__":
    unittest.main()
