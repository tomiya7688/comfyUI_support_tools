"""Record CPython _ssl provenance and its OpenSSL dependency."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.build import native_artifact_inventory


# {
#   責務: [SslRuntimeInventoryTests: related test fixtures and cases for SslRuntimeInventory behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class SslRuntimeInventoryTests(unittest.TestCase):
    # {
    #   責務: [_collect: creates packaged-runtime artifacts and gathers their inventory for the selected versions]
    #   処理: [
    #     1: write a temporary Python/distribution tree and PyInstaller TOC,
    #     2: run the inventory builder for the requested runtime versions,
    #   ],
    #   引数: [python_version: Python runtime version (str), openssl_version: OpenSSL runtime version (str)]
    #   戻り値: [result: value returned by the helper's documented test role]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
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
            {
                "name": "Python",
                "version": python_version,
                "license_files": ["licenses/Python/LICENSE.txt"],
            },
            {
                "name": "OpenSSL",
                "version": openssl_version,
                "license_files": ["licenses/Python/LICENSE.txt"],
            },
        ]
        with patch.object(native_artifact_inventory, "_package_owners", return_value={}):
            return native_artifact_inventory.collect_native_artifact_inventory(
                distribution, toc, components, root / "site-packages", python_root, None
            )[0]

    # {
    #   責務: [
    #     test_links_cpython_extension_and_its_openssl_dependency: verifies the behavior described by "links cpython extension and its openssl dependency",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for links cpython extension and its openssl dependency,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_links_cpython_extension_and_its_openssl_dependency(self):
        artifact = self._collect("3.10.11", "1.1.1t")
        self.assertEqual(artifact["origin_type"], "python-runtime-extension")
        self.assertEqual(artifact["origin_component"], "Python _ssl")
        self.assertEqual(artifact["origin_version"], "3.10.11")
        self.assertEqual(artifact["related_components"], [{"name": "OpenSSL", "version": "1.1.1t"}])
        self.assertEqual(artifact["license_files"], ["licenses/Python/LICENSE.txt"])
        self.assertEqual(artifact["audit_status"], "origin-and-license-document-linked")
        self.assertTrue(
            any(url.endswith("/PCbuild/_ssl.vcxproj") for url in artifact["source_reference_urls"])
        )

    # {
    #   責務: [
    #     test_links_cpython_31118_extension_to_pinned_openssl: verifies the behavior described by "links cpython 31118 extension to pinned openssl",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for links cpython 31118 extension to pinned openssl,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_links_cpython_31118_extension_to_pinned_openssl(self):
        artifact = self._collect("3.11.18", "3.0.15")
        self.assertEqual(artifact["origin_component"], "Python _ssl")
        self.assertEqual(artifact["origin_version"], "3.11.18")
        self.assertEqual(artifact["related_components"], [{"name": "OpenSSL", "version": "3.0.15"}])
        self.assertEqual(
            artifact["source_reference_urls"],
            [
                "https://github.com/python/cpython/blob/v3.11.18/Modules/_ssl.c",
                "https://github.com/python/cpython/blob/v3.11.18/PCbuild/_ssl.vcxproj",
                "https://github.com/python/cpython/blob/v3.11.18/PCbuild/python.props",
                "https://github.com/python/cpython/blob/v3.11.18/Doc/license.rst",
            ],
        )

    # {
    #   責務: [
    #     test_does_not_apply_pinned_evidence_to_another_runtime_version: verifies the behavior described by "does not apply pinned evidence to another runtime version",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for does not apply pinned evidence to another runtime version,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_does_not_apply_pinned_evidence_to_another_runtime_version(self):
        artifact = self._collect("3.11.0", "3.2.0")
        self.assertEqual(artifact["origin_type"], "python-runtime")
        self.assertEqual(
            artifact["audit_status"], "runtime-origin-found-license-scope-review-required"
        )
        self.assertNotIn("source_reference_urls", artifact)


if __name__ == "__main__":
    unittest.main()
