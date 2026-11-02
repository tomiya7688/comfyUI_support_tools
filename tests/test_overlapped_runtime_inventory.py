"""Record CPython _overlapped provenance and its Python license."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.build import native_artifact_inventory


# {
#   責務: [OverlappedRuntimeInventoryTests: related test fixtures and cases for OverlappedRuntimeInventory behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class OverlappedRuntimeInventoryTests(unittest.TestCase):
    # {
    #   責務: [_collect: creates packaged-runtime artifacts and gathers their inventory for the selected versions]
    #   処理: [
    #     1: write a temporary Python/distribution tree and PyInstaller TOC,
    #     2: run the inventory builder for the requested runtime versions,
    #   ],
    #   引数: [python_version: Python runtime version (str)]
    #   戻り値: [result: value returned by the helper's documented test role]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
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

    # {
    #   責務: [
    #     test_links_pinned_extension_to_python_license_and_sources: verifies the behavior described by "links pinned extension to python license and sources",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for links pinned extension to python license and sources,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [
    #     test_links_cpython_31118_extension_to_python_license_and_sources: verifies the behavior described by "links cpython 31118 extension to python license and sources",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for links cpython 31118 extension to python license and sources,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_links_cpython_31118_extension_to_python_license_and_sources(self):
        artifact = self._collect("3.11.18")
        self.assertEqual(artifact["origin_component"], "Python _overlapped")
        self.assertEqual(artifact["origin_version"], "3.11.18")
        self.assertEqual(
            artifact["source_reference_urls"],
            [
                "https://github.com/python/cpython/blob/v3.11.18/Modules/overlapped.c",
                "https://github.com/python/cpython/blob/v3.11.18/PCbuild/_overlapped.vcxproj",
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
        artifact = self._collect("3.11.0")
        self.assertEqual(artifact["origin_type"], "python-runtime")
        self.assertEqual(
            artifact["audit_status"], "runtime-origin-found-license-scope-review-required"
        )
        self.assertNotIn("source_reference_urls", artifact)


if __name__ == "__main__":
    unittest.main()
