"""Focused checks for the active Python CA-bundle validator."""

from __future__ import annotations

import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from tools.security.check_python_ca import (
    bundle_has_affected_root,
    check_distribution,
    version_at_least,
)


# {
#   責務: [PythonCaTests: Python CA検証のバージョン比較と対象ルート判定を検証する]
#   フィールド: []
#   処理: [1: バージョン境界を検証する, 2: CA bundle内容の判定を検証する]
# }
class PythonCaTests(unittest.TestCase):
    # {
    #   責務: [test_version_boundaries: 必須値未満と以上を区別できることを確認する]
    #   処理: [1: pipとcertifiの境界値を比較する]
    #   引数: [self: テストインスタンス]
    #   戻り値: []
    # }
    def test_version_boundaries(self) -> None:
        self.assertFalse(version_at_least("26.2.1", "26.2.2"))
        self.assertTrue(version_at_least("26.2.2", "26.2.2"))
        self.assertTrue(version_at_least("2026.10.23", "2026.10.19"))
        self.assertFalse(version_at_least("26.2.2rc1", "26.2.2"))

    # {
    #   責務: [test_bundle_fingerprint: PEM中のDER指紋で問題対象を判定する]
    #   処理: [1: テスト用PEMを作る, 2: 一致・不一致の指紋で照合する]
    #   引数: [self: テストインスタンス]
    #   戻り値: []
    # }
    def test_bundle_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            bundle = Path(temporary_dir) / "cacert.pem"
            bundle.write_text(
                "-----BEGIN CERTIFICATE-----\nZHVtbXk=\n-----END CERTIFICATE-----\n",
                encoding="ascii",
            )
            with patch(
                "tools.security.check_python_ca.AFFECTED_SHA256",
                sha256(b"dummy").hexdigest(),
            ):
                self.assertTrue(bundle_has_affected_root(bundle))
            self.assertFalse(bundle_has_affected_root(bundle))

    # {
    #   責務: [test_distribution_requires_bundle: CA bundleのない成果物を不合格にする]
    #   処理: [1: 空の成果物を作り、検証結果を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: []
    # }
    def test_distribution_requires_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            self.assertEqual(len(check_distribution(Path(temporary_dir))), 1)


if __name__ == "__main__":
    unittest.main()
