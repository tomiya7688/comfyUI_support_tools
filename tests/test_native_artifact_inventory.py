"""Native onedir artifact provenance checks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.build import native_artifact_inventory as inventory


class NativeArtifactInventoryTests(unittest.TestCase):
    def test_links_distribution_owned_artifact_to_component_license(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "venv" / "Lib" / "site-packages" / "numpy" / "native.dll"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"native")
            distribution = root / "dist"
            artifact = distribution / "numpy" / "native.dll"
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"native")
            toc = root / "COLLECT-00.toc"
            toc.write_text(repr(([("numpy/native.dll", str(source), "BINARY")],)), encoding="utf-8")
            component = {"name": "numpy", "version": "2.0.0", "license_files": ["licenses/numpy/LICENSE.txt"]}
            owners = {inventory._key(source): {"name": "numpy", "version": "2.0.0"}}
            with patch.object(inventory, "_package_owners", return_value=owners):
                entries = inventory.collect_native_artifact_inventory(distribution, toc, [component], root / "venv" / "Lib" / "site-packages", root / "venv", None)
            self.assertEqual(entries[0]["origin_type"], "python-package")
            self.assertEqual(entries[0]["origin_component"], "numpy")
            self.assertEqual(entries[0]["origin_version"], "2.0.0")
            self.assertEqual(entries[0]["license_files"], component["license_files"])
            self.assertEqual(entries[0]["audit_status"], "origin-and-license-document-linked")

    def test_external_source_hint_does_not_disclose_absolute_builder_path(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "builders" / "codex-runtimes" / "dependencies" / "native" / "libheif" / "bin" / "shim.dll"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"native")
            distribution = root / "dist"
            distribution.mkdir()
            (distribution / "shim.dll").write_bytes(b"native")
            toc = root / "COLLECT-00.toc"
            toc.write_text(repr(([("shim.dll", str(source), "BINARY")],)), encoding="utf-8")
            with patch.object(inventory, "_package_owners", return_value={}):
                entries = inventory.collect_native_artifact_inventory(distribution, toc, [], root / "site-packages", root / "python", None)
            self.assertEqual(entries[0]["origin_type"], "external-build-environment")
            self.assertEqual(entries[0]["audit_status"], "external-origin-and-license-unresolved")
            self.assertEqual(entries[0]["source_hint"], "native/libheif/bin")
            self.assertNotIn(str(root), json.dumps(entries))


if __name__ == "__main__":
    unittest.main()
