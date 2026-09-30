"""Record CPython _ssl provenance and its OpenSSL dependency."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.build import native_artifact_inventory


class SslRuntimeInventoryTests(unittest.TestCase):
    def _collect(self, python_version: str, openssl_version: str):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        python_root = root / "python"
        source = python_root / "DLLs" / "_ssl.pyd"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"ssl")
        distribution = root / "dist"
        artifact = distribution / "_ssl.pyd"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"ssl")
        toc = root / "COLLECT-00.toc"
        toc.write_text(repr(([("_ssl.pyd", str(source), "BINARY")],)), encoding="utf-8")
        components = [
            {"name": "Python", "version": python_version, "license_files": ["licenses/Python/LICENSE.txt"]},
            {"name": "OpenSSL", "version": openssl_version, "license_files": ["licenses/Python/LICENSE.txt"]},
        ]
        with patch.object(native_artifact_inventory, "_package_owners", return_value={}):
            return native_artifact_inventory.collect_native_artifact_inventory(
                distribution, toc, components, root / "site-packages", python_root, None
            )[0]

    def test_links_cpython_extension_and_its_openssl_dependency(self):
        artifact = self._collect("3.10.11", "1.1.1t")
        self.assertEqual(artifact["origin_type"], "python-runtime-extension")
        self.assertEqual(artifact["origin_component"], "Python _ssl")
        self.assertEqual(artifact["origin_version"], "3.10.11")
        self.assertEqual(artifact["related_components"], [{"name": "OpenSSL", "version": "1.1.1t"}])
        self.assertEqual(artifact["license_files"], ["licenses/Python/LICENSE.txt"])
        self.assertEqual(artifact["audit_status"], "origin-and-license-document-linked")
        self.assertTrue(any(url.endswith("/PCbuild/_ssl.vcxproj") for url in artifact["source_reference_urls"]))

    def test_does_not_apply_pinned_evidence_to_another_runtime_version(self):
        artifact = self._collect("3.11.0", "3.2.0")
        self.assertEqual(artifact["origin_type"], "python-runtime")
        self.assertEqual(artifact["audit_status"], "runtime-origin-found-license-scope-review-required")
        self.assertNotIn("source_reference_urls", artifact)


if __name__ == "__main__":
    unittest.main()
