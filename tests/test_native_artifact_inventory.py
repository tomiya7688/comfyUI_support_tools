"""Native onedir artifact provenance checks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.build import native_artifact_inventory as inventory


class NativeArtifactInventoryTests(unittest.TestCase):
    def test_attributes_python_native_runtime_libraries_separately(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            distribution = root / "dist"
            python_root = root / "python"
            source_root = python_root / "DLLs"
            source_root.mkdir(parents=True)
            artifact_names = ["libcrypto-1_1.dll", "libffi-7.dll", "_bz2.pyd", "_lzma.pyd", "VCRUNTIME140.dll"]
            entries = []
            for filename in artifact_names:
                source = source_root / filename
                source.write_bytes(b"runtime")
                target = distribution / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"runtime")
                entries.append((filename, str(source), "BINARY"))
            toc = root / "COLLECT-00.toc"
            toc.write_text(repr((entries,)), encoding="utf-8")
            license_file = "licenses/Python/LICENSE.txt"
            components = [
                {"name": "OpenSSL", "version": "1.1.1t", "license_files": [license_file]},
                {"name": "libffi", "version": "3.3.0", "license_files": [license_file]},
                {"name": "bzip2", "version": "1.0.8", "license_files": [license_file]},
                {"name": "XZ Utils liblzma", "version": "5.2.5", "license_files": [], "audit_status": "compiled-binary-toolchain-scope-review-required"},
                {"name": "Microsoft Visual C++ Runtime", "version": None, "license_files": [], "audit_status": "redistribution-terms-review-required"},
            ]
            with patch.object(inventory, "_package_owners", return_value={}):
                artifacts = inventory.collect_native_artifact_inventory(distribution, toc, components, root / "site-packages", python_root, None)

        by_path = {item["path"]: item for item in artifacts}
        self.assertEqual(by_path["libcrypto-1_1.dll"]["origin_component"], "OpenSSL")
        self.assertEqual(by_path["libcrypto-1_1.dll"]["origin_version"], "1.1.1t")
        self.assertEqual(by_path["libffi-7.dll"]["origin_version"], "3.3.0")
        self.assertEqual(by_path["libffi-7.dll"]["audit_status"], "origin-and-license-document-linked")
        self.assertEqual(by_path["_bz2.pyd"]["origin_component"], "bzip2")
        self.assertEqual(by_path["_bz2.pyd"]["origin_version"], "1.0.8")
        self.assertEqual(by_path["_lzma.pyd"]["origin_component"], "XZ Utils liblzma")
        self.assertEqual(by_path["_lzma.pyd"]["origin_version"], "5.2.5")
        self.assertEqual(by_path["_lzma.pyd"]["audit_status"], "compiled-binary-toolchain-scope-review-required")
        self.assertEqual(by_path["VCRUNTIME140.dll"]["audit_status"], "redistribution-terms-review-required")

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
