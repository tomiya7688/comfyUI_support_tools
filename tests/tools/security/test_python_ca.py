"""Focused checks for the active Python CA-bundle validator."""

from __future__ import annotations

import tempfile
import ssl
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from comfyui_support_tools.shared.python_tls import create_certifi_context
from tools.security.check_python_ca import (
    AFFECTED_CERTIFICATES,
    AFFECTED_INTERMEDIATES,
    AFFECTED_ROOTS,
    affected_certificates_in_bundle,
    bundle_has_affected_certificate,
    check_distribution,
    version_at_least,
)


# {
#   責務: [PythonCaTests: Python CA検証のバージョン比較と対象ルート判定を検証する]
#   フィールド: []
#   処理: [1: バージョン境界を検証する, 2: CA bundle内の対象証明書判定を検証する]
# }
class PythonCaTests(unittest.TestCase):
    # {
    #   責務: [test_certifi_context_excludes_affected_roots: 専用TLS contextから問題対象ルートを除外する]
    #   処理: [1: contextが信頼するDER証明書を取得する, 2: 問題対象の指紋が含まれないことを確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: []
    # }
    def test_certifi_context_excludes_affected_roots(self) -> None:
        context = create_certifi_context()
        trusted_fingerprints = {
            sha256(certificate).hexdigest()
            for certificate in context.get_ca_certs(binary_form=True)
        }
        self.assertTrue(trusted_fingerprints)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertFalse(trusted_fingerprints & set(AFFECTED_CERTIFICATES))

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
    #   責務: [test_bundle_fingerprints: emSignとAAAの指紋をCA bundleから検出する]
    #   処理: [1: ルートと中間CAの指紋登録を確認する, 2: 複数PEMの検出と非該当を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: []
    # }
    def test_bundle_fingerprints(self) -> None:
        self.assertEqual(
            AFFECTED_ROOTS,
            {
                "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b": "emSign ECC Root CA - G3",
                "d7a7a0fb5d7e2731d771e9484ebcdef71d5f0c3e0a2948782bc83ee0ea699ef4": "AAA Certificate Services",
                "7dd78d5f4f13459a83dff9abbba62edbaf6f2d102bf257fd712f4d9f2746ed8d": "emSign Root TLS CA - G3 (self-signed)",
                "3094025792039a68af6e553686410bdab7c0d4a36b9084cba64202e35d6ebbdd": "emSign Root TLS CA - G3 (cross-signed)",
            },
        )
        self.assertEqual(
            set(AFFECTED_INTERMEDIATES),
            {
                "e7568fe6e12331f4fd7de61da4c7559d0f8eb192a218d4741a3ba75184333838",
                "98b896625c0c230adeec3eb2cf6aad5001ecf9156a68644e82374ce5833bc25b",
                "42c4accd12c4f59597925e1a08a7a90102608543809308d50ec427e118ba1493",
                "432ec25f0d28de9006d97bf752f17bbb2cd41f669933fcb072d9a1148d0261f3",
                "cb6e15165ac802e9b3f993f16c25d41f4e81c21ebde71ae1b012ac00bf9c7c3f",
                "0164d7ceae5bb909c272af151ff44b1177ae9b47d9424b94f1d9558c30934d19",
                "579480aea166290bd3c643589e795fc0d0e54e86505d180f1dff99efd3199512",
                "5f1ded4dd590af74631290cf073b122a2aac6a1fa479778a0bd43579bd832699",
                "45a883f349aedfd5f3a649b5498ffb121712ba8b448f3f2a91dbc5a766fcddbe",
                "fd9d5c2dbbd4995ab69b8d50c439d9527b00529199c2fd01b2174eb58f07021f",
                "7485b51c0ed192878fa1d2f948fb529ae1842cc5086c4b67f7be5b2039de9489",
                "62b7f9868263f72f6911fc78ceaf72c1979158b7368bf648683bb2aa39b02e72",
            },
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            bundle = Path(temporary_dir) / "cacert.pem"
            bundle.write_text(
                "-----BEGIN CERTIFICATE-----\nZHVtbXk=\n-----END CERTIFICATE-----\n"
                "-----BEGIN CERTIFICATE-----\nb3RoZXI=\n-----END CERTIFICATE-----\n",
                encoding="ascii",
            )
            with patch(
                "tools.security.check_python_ca.AFFECTED_CERTIFICATES",
                {
                    sha256(b"dummy").hexdigest(): "test root",
                    sha256(b"other").hexdigest(): "test intermediate",
                },
            ):
                self.assertEqual(
                    affected_certificates_in_bundle(bundle),
                    ("test intermediate", "test root"),
                )
                self.assertTrue(bundle_has_affected_certificate(bundle))
            self.assertFalse(bundle_has_affected_certificate(bundle))

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
