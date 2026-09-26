"""Attribute the CPython _asyncio extension to the Python runtime license."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.build import native_artifact_inventory


class AsyncioRuntimeInventoryTests(unittest.TestCase):
    def test_links_asyncio_extension_to_python_license(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            python_root = root / "python"
            source = python_root / "DLLs" / "_asyncio.pyd"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"python asyncio runtime")
            distribution = root / "dist"
            artifact = distribution / "_asyncio.pyd"
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"python asyncio runtime")
            toc = root / "COLLECT-00.toc"
            toc.write_text(repr(([("_asyncio.pyd", str(source), "BINARY")],)), encoding="utf-8")
            python_component = {
                "name": "Python",
                "version": "3.10.11",
                "license_files": ["licenses/Python/LICENSE.txt"],
            }
            with patch.object(native_artifact_inventory, "_package_owners", return_value={}):
                entries = native_artifact_inventory.collect_native_artifact_inventory(
                    distribution, toc, [python_component], root / "site-packages", python_root, None
                )

        entry = entries[0]
        self.assertEqual(entry["origin_type"], "native-runtime-library")
