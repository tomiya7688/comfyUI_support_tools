"""Attribute the CPython _asyncio extension to the Python runtime license."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.build import native_artifact_inventory


# {
#   責務: [AsyncioRuntimeInventoryTests: related test fixtures and cases for AsyncioRuntimeInventory behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class AsyncioRuntimeInventoryTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_links_asyncio_extension_to_python_license: verifies the behavior described by "links asyncio extension to python license",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for links asyncio extension to python license,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
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
