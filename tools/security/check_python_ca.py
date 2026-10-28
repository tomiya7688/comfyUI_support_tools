"""Fail setup when active Python still trusts affected CA trust anchors."""

from __future__ import annotations

import argparse
import hashlib
import re
import ssl
from pathlib import Path

import certifi
import pip
from pip._vendor import certifi as pip_certifi

MIN_PIP = "26.2.2"
MIN_CERTIFI = "2026.10.19"
# DER fingerprints identify affected roots and TLS intermediates regardless of PEM labels.
AFFECTED_ROOTS = {
    "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b": "emSign ECC Root CA - G3",
    "d7a7a0fb5d7e2731d771e9484ebcdef71d5f0c3e0a2948782bc83ee0ea699ef4": "AAA Certificate Services",
    "7dd78d5f4f13459a83dff9abbba62edbaf6f2d102bf257fd712f4d9f2746ed8d": "emSign Root TLS CA - G3 (self-signed)",
    "3094025792039a68af6e553686410bdab7c0d4a36b9084cba64202e35d6ebbdd": "emSign Root TLS CA - G3 (cross-signed)",
}
AFFECTED_INTERMEDIATES = {
    "e7568fe6e12331f4fd7de61da4c7559d0f8eb192a218d4741a3ba75184333838": "EM EV TLS CA - G3B (emSign)",
    "98b896625c0c230adeec3eb2cf6aad5001ecf9156a68644e82374ce5833bc25b": "EM OV TLS CA - G3B (emSign)",
    "42c4accd12c4f59597925e1a08a7a90102608543809308d50ec427e118ba1493": "EM DV TLS CA - G3B (emSign)",
    "432ec25f0d28de9006d97bf752f17bbb2cd41f669933fcb072d9a1148d0261f3": "EM EV TLS CA - G3C (emSign)",
    "cb6e15165ac802e9b3f993f16c25d41f4e81c21ebde71ae1b012ac00bf9c7c3f": "EM OV TLS CA - G3C (emSign)",
    "0164d7ceae5bb909c272af151ff44b1177ae9b47d9424b94f1d9558c30934d19": "EM DV TLS CA - G3C (emSign)",
    "579480aea166290bd3c643589e795fc0d0e54e86505d180f1dff99efd3199512": "EM EV TLS CA - G3B (AAA cross-sign)",
    "5f1ded4dd590af74631290cf073b122a2aac6a1fa479778a0bd43579bd832699": "EM OV TLS CA - G3B (AAA cross-sign)",
    "45a883f349aedfd5f3a649b5498ffb121712ba8b448f3f2a91dbc5a766fcddbe": "EM DV TLS CA - G3B (AAA cross-sign)",
    "fd9d5c2dbbd4995ab69b8d50c439d9527b00529199c2fd01b2174eb58f07021f": "EM EV TLS CA - G3C (AAA cross-sign)",
    "7485b51c0ed192878fa1d2f948fb529ae1842cc5086c4b67f7be5b2039de9489": "EM OV TLS CA - G3C (AAA cross-sign)",
    "62b7f9868263f72f6911fc78ceaf72c1979158b7368bf648683bb2aa39b02e72": "EM DV TLS CA - G3C (AAA cross-sign)",
}
AFFECTED_CERTIFICATES = AFFECTED_ROOTS | AFFECTED_INTERMEDIATES


# {
#   責務: [version_at_least: 数値形式の導入済みバージョンが必須値以上か判定する]
#   処理: [1: バージョンを数値列へ変換する, 2: 必須値と比較する]
#   引数: [installed: 導入済みバージョン, minimum: 必須バージョン]
#   戻り値: [is_current: 必須値以上なら真]
# }
def version_at_least(installed: str, minimum: str) -> bool:
    if not re.fullmatch(r"\d+(?:\.\d+)*", installed):
        return False
    installed_parts = tuple(int(part) for part in installed.split("."))
    minimum_parts = tuple(int(part) for part in minimum.split("."))
    return installed_parts >= minimum_parts


# {
#   責務: [affected_certificates_in_bundle: CA bundleに含まれる問題対象CA証明書を列挙する]
#   処理: [1: 実ファイルのPEM証明書を解析する, 2: 各DER指紋を問題対象と照合する]
#   引数: [bundle_path: CA bundleの実パス]
#   戻り値: [affected_certificates: 含まれていた問題対象CA証明書名]
#   エラー: [OSError: CA bundleを読み込めない場合, ValueError: PEM証明書がないか不正な場合]
# }
def affected_certificates_in_bundle(bundle_path: Path) -> tuple[str, ...]:
    content = bundle_path.read_text(encoding="ascii")
    certificates = re.findall(
        r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
        content,
        flags=re.DOTALL,
    )
    if not certificates:
        raise ValueError(f"No PEM certificates in {bundle_path}")
    affected_names = {
        AFFECTED_CERTIFICATES[digest]
        for certificate in certificates
        if (digest := hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate)).hexdigest())
        in AFFECTED_CERTIFICATES
    }
    return tuple(sorted(affected_names))


# {
#   責務: [bundle_has_affected_certificate: CA bundleに問題対象証明書が含まれるか判定する]
#   処理: [1: 対象証明書名を列挙する, 2: 含有の真偽を返す]
#   引数: [bundle_path: CA bundleの実パス]
#   戻り値: [is_affected: 問題対象証明書があれば真]
# }
def bundle_has_affected_certificate(bundle_path: Path) -> bool:
    return bool(affected_certificates_in_bundle(bundle_path))


# {
#   責務: [check_environment: 実行中のpipとcertifiのバージョンおよびCA bundleを検証する]
#   処理: [1: 実バージョンと実パスを表示する, 2: 必須値と問題対象CA証明書の不在を確認する]
#   引数: []
#   戻り値: [errors: 検証エラーの一覧]
# }
def check_environment() -> list[str]:
    errors: list[str] = []
    for label, installed, minimum, bundle in (
        ("pip", pip.__version__, MIN_PIP, Path(pip_certifi.where())),
        ("certifi", certifi.__version__, MIN_CERTIFI, Path(certifi.where())),
    ):
        print(f"{label}: {installed}; CA bundle: {bundle}")
        if not version_at_least(installed, minimum):
            errors.append(f"{label} {installed} is below {minimum}")
        try:
            affected_certificates = affected_certificates_in_bundle(bundle)
            if affected_certificates:
                errors.append(
                    f"{label} bundle still includes {', '.join(affected_certificates)}: {bundle}"
                )
        except (OSError, ValueError) as exc:
            errors.append(f"Cannot read {label} bundle {bundle}: {exc}")
    return errors


# {
#   責務: [check_distribution: OneDir成果物の実CA bundleを検証する]
#   処理: [1: 成果物内のCA bundleを列挙する, 2: 各bundleから問題対象CA証明書の不在を確認する]
#   引数: [distribution_root: OneDir成果物のディレクトリ]
#   戻り値: [errors: 検証エラーの一覧]
# }
def check_distribution(distribution_root: Path) -> list[str]:
    bundles = sorted(distribution_root.rglob("cacert.pem"))
    if not bundles:
        return [f"No CA bundle found in distribution: {distribution_root}"]
    errors: list[str] = []
    for bundle in bundles:
        print(f"distribution CA bundle: {bundle}")
        try:
            affected_certificates = affected_certificates_in_bundle(bundle)
            if affected_certificates:
                errors.append(
                    f"Distribution bundle includes {', '.join(affected_certificates)}: {bundle}"
                )
        except (OSError, ValueError) as exc:
            errors.append(f"Cannot inspect distribution bundle {bundle}: {exc}")
    return errors


# {
#   責務: [main: CA検証結果を終了コードとして返す]
#   処理: [1: 実環境を検証する, 2: 指定時に成果物も検証する, 3: 結果を表示する]
#   引数: []
#   戻り値: [exit_code: 合格は0、不合格は1]
# }
def main() -> int:
    parser = argparse.ArgumentParser(description="Verify active and frozen Python CA bundles")
    parser.add_argument("--distribution-root", type=Path)
    args = parser.parse_args()
    errors = check_environment()
    if args.distribution_root is not None:
        errors.extend(check_distribution(args.distribution_root))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: checked Python and distribution CA bundles exclude affected CA certificates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
