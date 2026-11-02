"""Record the CPython _ctypes extension and its bundled libffi dependency."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.build import native_artifact_inventory


# {
#   責務: [CtypesRuntimeInventoryTests: related test fixtures and cases for CtypesRuntimeInventory behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class CtypesRuntimeInventoryTests(unittest.TestCase):
    # {
    #   責務: [_collect: creates packaged-runtime artifacts and gathers their inventory for the selected versions]
    #   処理: [
    #     1: write a temporary Python/distribution tree and PyInstaller TOC,
    #     2: run the inventory builder for the requested runtime versions,
    #   ],
    #   引数: [python_version: Python runtime version (str), libffi_version: libffi runtime version (str)]
    #   戻り値: [result: value returned by the helper's documented test role]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
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
            {
                "name": "Python",
                "version": python_version,
                "license_files": ["licenses/Python/LICENSE.txt"],
            },
            {
                "name": "libffi",
                "version": libffi_version,
                "license_files": ["licenses/Python/LICENSE.txt"],
            },
        ]
        with patch.object(native_artifact_inventory, "_package_owners", return_value={}):
            return native_artifact_inventory.collect_native_artifact_inventory(
                distribution, toc, components, root / "site-packages", python_root, None
            )[0]

    # {
    #   責務: [
    #     test_links_cpython_extension_and_its_libffi_dependency: verifies the behavior described by "links cpython extension and its libffi dependency",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for links cpython extension and its libffi dependency,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_links_cpython_extension_and_its_libffi_dependency(self):
        artifact = self._collect("3.10.11", "3.3.0")
        self.assertEqual(artifact["origin_type"], "python-runtime-extension")
        self.assertEqual(artifact["origin_component"], "Python _ctypes")
        self.assertEqual(artifact["origin_version"], "3.10.11")
        self.assertEqual(artifact["related_components"], [{"name": "libffi", "version": "3.3.0"}])
        self.assertEqual(artifact["license_files"], ["licenses/Python/LICENSE.txt"])
        self.assertEqual(artifact["audit_status"], "origin-and-license-document-linked")
        self.assertIn("/PCbuild/_ctypes.vcxproj", artifact["source_reference_urls"][1])

    # {
    #   責務: [
    #     test_links_cpython_31118_extension_to_pinned_libffi: verifies the behavior described by "links cpython 31118 extension to pinned libffi",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for links cpython 31118 extension to pinned libffi,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_links_cpython_31118_extension_to_pinned_libffi(self):
        artifact = self._collect("3.11.18", "3.4.4")
        self.assertEqual(artifact["origin_component"], "Python _ctypes")
        self.assertEqual(artifact["origin_version"], "3.11.18")
        self.assertEqual(artifact["related_components"], [{"name": "libffi", "version": "3.4.4"}])
        self.assertEqual(
            artifact["source_reference_urls"],
            [
                "https://github.com/python/cpython/blob/v3.11.18/Modules/_ctypes/_ctypes.c",
                "https://github.com/python/cpython/blob/v3.11.18/PCbuild/_ctypes.vcxproj",
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
        artifact = self._collect("3.11.0", "3.4.0")
        self.assertEqual(artifact["origin_type"], "python-runtime")
        self.assertEqual(
            artifact["audit_status"], "runtime-origin-found-license-scope-review-required"
        )
        self.assertNotIn("source_reference_urls", artifact)


if __name__ == "__main__":
    unittest.main()
