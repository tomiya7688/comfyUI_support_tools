"""Record CPython _overlapped provenance and its Python license."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.build import native_artifact_inventory


class OverlappedRuntimeInventoryTests(unittest.TestCase):
    def _collect(self, python_version: str):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        python_root = root / "python"
        source = python_root / "DLLs" / "_overlapped.pyd"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"overlapped")
        distribution = root / "dist"
        artifact = distribution / "_overlapped.pyd"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"overlapped")
        toc = root / "COLLECT-00.toc"
        toc.write_text(repr(([("_overlapped.pyd", str(source), "BINARY")],)), encoding="utf-8")
        python_component = {
            "name": "Python",
            "version": python_version,
            "license_files": ["licenses/Python/LICENSE.txt"],
        }
        with patch.object(native_artifact_inventory, "_package_owners", return_value={}):
            return native_artifact_inventory.collect_native_artifact_inventory(
                distribution, toc, [python_component], root / "site-packages", python_root, None
            )[0]

    def test_links_pinned_extension_to_python_license_and_sources(self):
        artifact = self._collect("3.10.11")
        self.assertEqual(artifact["origin_type"], "python-runtime-extension")
        self.assertEqual(artifact["origin_component"], "Python _overlapped")
        self.assertEqual(artifact["origin_version"], "3.10.11")
        self.assertEqual(artifact["license_files"], ["licenses/Python/LICENSE.txt"])
        self.assertEqual(artifact["audit_status"], "origin-and-license-document-linked")
        self.assertIn(
            "https://github.com/python/cpython/blob/v3.10.11/Modules/overlapped.c",
            artifact["source_reference_urls"],
        )

    def test_does_not_apply_pinned_evidence_to_another_runtime_version(self):
        artifact = self._collect("3.11.0")
        self.assertEqual(artifact["origin_type"], "python-runtime")
        self.assertEqual(artifact["audit_status"], "runtime-origin-found-license-scope-review-required")
        self.assertNotIn("source_reference_urls", artifact)


if __name__ == "__main__":
    unittest.main()
