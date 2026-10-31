# {
#   責務: [Python 3.10 venvへcertifi TLS shimを可逆インストールする]
#   処理: [1: 対象Pythonとcertifiを検証する, 2: site-packagesの既存ファイルを保護する, 3: shimをインストールまたは削除する]
#   引数: [--remove: 管理対象のshimを削除する]
#   戻り値: [exit code: 操作の成功または失敗]
#   副作用: [現在のPython環境のsite-packagesへ管理対象ファイルを追加または削除する]
# }
"""Install or remove the Python 3.10 certifi TLS startup shim."""

from __future__ import annotations

import argparse
import os
import sys
import sysconfig
import tempfile
from pathlib import Path

SOURCE_DIRECTORY = Path(__file__).resolve().parent
SHIM_MARKER = "KADOKA_PYTHON310_CERTIFI_TLS_SHIM: managed runtime file."
MANAGED_FILES = ("sitecustomize.py", "python310_tls_shim.py")
INSTALL_ORDER = ("python310_tls_shim.py", "sitecustomize.py")
REMOVE_ORDER = ("sitecustomize.py", "python310_tls_shim.py")


# {
#   責務: [managed_source: 対象shimの管理元ファイルを取得する]
#   処理: [1: security tools directoryからファイルを解決する]
#   引数: [filename: 管理対象のファイル名]
#   戻り値: [source: 管理元ファイルのpath]
# }
def managed_source(filename: str) -> Path:
    return SOURCE_DIRECTORY / filename


# {
#   責務: [target_directory: 現在のvenvのsite-packagesを取得する]
#   処理: [1: sysconfigからpurelib pathを解決する, 2: directoryの存在を検証する]
#   引数: []
#   戻り値: [directory: site-packages directory]
#   エラー: [FileNotFoundError: site-packages directoryがない場合]
# }
def target_directory() -> Path:
    directory = Path(sysconfig.get_path("purelib"))
    if not directory.is_dir():
        raise FileNotFoundError(f"Python site-packages directory not found: {directory}")
    return directory


# {
#   責務: [validate_managed_target: 既存のsite-packages fileが管理対象か検証する]
#   処理: [1: fileの有無を調べる, 2: 既存fileのmarkerを確認し管理外fileを拒否する]
#   引数: [target: 配置先file path]
#   戻り値: []
#   エラー: [FileExistsError: markerのない既存fileがある場合]
# }
def validate_managed_target(target: Path) -> None:
    if target.exists() and SHIM_MARKER not in target.read_text(encoding="utf-8"):
        raise FileExistsError(f"Refusing to replace unmanaged file: {target}")


# {
#   責務: [install_shim: 現在のPython 3.10 venvへshimをインストールする]
#   処理: [1: CPython 3.10とvenvを検証する, 2: certifi bundleを検証する, 3: 既存ファイルを保護してshimを原子的に配置する]
#   引数: []
#   戻り値: [directory: shimを配置したsite-packages directory]
#   エラー: [RuntimeError: 対象がPython 3.10 venvでない場合, FileExistsError: 管理外ファイルが衝突する場合]
# }
def install_shim() -> Path:
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 10):
        raise RuntimeError("Run this installer with the target CPython 3.10 virtual environment")
    if sys.prefix == sys.base_prefix:
        raise RuntimeError(
            "Run this installer from a virtual environment, not a base Python install"
        )

    import certifi

    if not Path(certifi.where()).is_file():
        raise RuntimeError(f"certifi CA bundle is missing: {certifi.where()}")

    directory = target_directory()
    sources = {name: managed_source(name) for name in MANAGED_FILES}
    for name, source in sources.items():
        if not source.is_file():
            raise FileNotFoundError(f"Managed shim source is missing: {source}")
        target = directory / name
        validate_managed_target(target)

    for name in INSTALL_ORDER:
        source = sources[name]
        target = directory / name
        contents = source.read_text(encoding="utf-8")
        if target.exists() and target.read_text(encoding="utf-8") == contents:
            continue
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                prefix=f".{name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_file.write(contents)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
                temporary_path = Path(temporary_file.name)
            os.replace(temporary_path, target)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
    return directory


# {
#   責務: [remove_shim: 現在のvenvから管理対象のshimだけを削除する]
#   処理: [1: site-packagesを解決する, 2: marker一致を確認して管理対象ファイルを削除する]
#   引数: []
#   戻り値: [removed_files: 削除したファイル名一覧]
#   エラー: [RuntimeError: 管理対象外ファイルがある場合]
# }
def remove_shim() -> list[str]:
    directory = target_directory()
    targets = [directory / name for name in REMOVE_ORDER]
    unmanaged = [
        target
        for target in targets
        if target.exists() and SHIM_MARKER not in target.read_text(encoding="utf-8")
    ]
    if unmanaged:
        raise RuntimeError(f"Refusing to remove unmanaged file: {unmanaged[0]}")

    removed: list[str] = []
    for target in targets:
        if target.exists():
            target.unlink()
            removed.append(target.name)
    return removed


# {
#   責務: [main: shimのinstall/remove CLIを実行する]
#   処理: [1: CLI引数を解析する, 2: 選択された操作を実行する, 3: 結果を表示してexit codeを返す]
#   引数: [argv: CLI引数。省略時はsys.argvを使う]
#   戻り値: [exit_code: 0は成功、それ以外は失敗]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remove", action="store_true", help="remove this managed shim")
    arguments = parser.parse_args(argv)
    try:
        if arguments.remove:
            removed = remove_shim()
            print(f"Removed managed TLS shim files: {', '.join(removed) or 'none'}")
        else:
            directory = install_shim()
            print(f"Installed Python 3.10 certifi TLS shim in: {directory}")
        return 0
    except (FileExistsError, FileNotFoundError, OSError, RuntimeError, ImportError) as exc:
        print(f"Python 3.10 TLS shim operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
