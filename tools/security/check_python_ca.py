"""Fail build setup when the active Python still trusts the affected emSign root."""

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
AFFECTED_ROOT = "emSign ECC Root CA - G3"
# SHA-256 of the affected root's DER certificate, not the PEM comment label.
AFFECTED_SHA256 = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"


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
#   責務: [bundle_has_affected_root: CA bundleに問題対象のルートが含まれるか判定する]
#   処理: [1: 実ファイルのPEM証明書を解析する, 2: 各DER指紋を問題対象と照合する]
#   引数: [bundle_path: CA bundleの実パス]
#   戻り値: [is_affected: 問題対象のルートがあれば真]
#   エラー: [OSError: CA bundleを読み込めない場合, ValueError: PEM証明書がないか不正な場合]
# }
def bundle_has_affected_root(bundle_path: Path) -> bool:
    content = bundle_path.read_text(encoding="ascii")
    certificates = re.findall(
        r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
        content,
        flags=re.DOTALL,
    )
    if not certificates:
        raise ValueError(f"No PEM certificates in {bundle_path}")
    return any(
        hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate)).hexdigest() == AFFECTED_SHA256
        for certificate in certificates
    )


# {
#   責務: [check_environment: 実行中のpipとcertifiのバージョンおよびCA bundleを検証する]
#   処理: [1: 実バージョンと実パスを表示する, 2: 必須値と問題対象ルートの不在を確認する]
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
            if bundle_has_affected_root(bundle):
                errors.append(f"{label} bundle still includes {AFFECTED_ROOT}: {bundle}")
        except (OSError, ValueError) as exc:
            errors.append(f"Cannot read {label} bundle {bundle}: {exc}")
    return errors


# {
#   責務: [check_distribution: OneDir成果物の実CA bundleを検証する]
#   処理: [1: 成果物内のCA bundleを列挙する, 2: 各bundleから問題対象ルートの不在を確認する]
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
            if bundle_has_affected_root(bundle):
                errors.append(f"Distribution bundle includes {AFFECTED_ROOT}: {bundle}")
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
    print("PASS: checked Python and distribution CA bundles exclude the affected root")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
