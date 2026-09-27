"""Record the CPython _ctypes extension and its bundled libffi dependency."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.build import native_artifact_inventory


class CtypesRuntimeInventoryTests(unittest.TestCase):
    def _collect(self, python_version: str, libffi_version: str):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        python_root = root / "python"
        source = python_root / "DLLs" / "_ctypes.pyd"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"ctypes")
        distribution = root / "dist"
        artifact = distribution / "_ctypes.pyd"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"ctypes")
        toc = root / "COLLECT-00.toc"
        toc.write_text(repr(([("_ctypes.pyd", str(source), "BINARY")],)), encoding="utf-8")
        components = [
            {"name": "Python", "version": python_version, "license_files": ["licenses/Python/LICENSE.txt"]},
            {"name": "libffi", "version": libffi_version, "license_files": ["licenses/Python/LICENSE.txt"]},
        ]
        with patch.object(native_artifact_inventory, "_package_owners", return_value={}):
            return native_artifact_inventory.collect_native_artifact_inventory(
                distribution, toc, components, root / "site-packages", python_root, None
            )[0]

    def test_links_cpython_extension_and_its_libffi_dependency(self):
        artifact = self._collect("3.10.11", "3.3.0")
        self.assertEqual(artifact["origin_type"], "python-runtime-extension")
        self.assertEqual(artifact["origin_component"], "Python _ctypes")
        self.assertEqual(artifact["origin_version"], "3.10.11")
        self.assertEqual(artifact["related_components"], [{"name": "libffi", "version": "3.3.0"}])
        self.assertEqual(artifact["license_files"], ["licenses/Python/LICENSE.txt"])
        self.assertEqual(artifact["audit_status"], "origin-and-license-document-linked")
        self.assertIn("/PCbuild/_ctypes.vcxproj", artifact["source_reference_urls"][1])

    def test_does_not_apply_pinned_evidence_to_another_runtime_version(self):
        artifact = self._collect("3.11.0", "3.4.0")
        self.assertEqual(artifact["origin_type"], "python-runtime")
        self.assertEqual(artifact["audit_status"], "runtime-origin-found-license-scope-review-required")
        self.assertNotIn("source_reference_urls", artifact)


if __name__ == "__main__":
    unittest.main()
