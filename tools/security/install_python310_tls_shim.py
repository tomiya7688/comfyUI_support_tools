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
import importlib.machinery
import importlib.util
import os
import sys
import sysconfig
import tempfile
from pathlib import Path
from typing import BinaryIO

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
#   責務: [validate_runtime: install/removeの実行環境が対象venvか確認する]
#   処理: [1: CPython 3.10を確認する, 2: base Pythonではないことを確認する]
#   引数: []
#   戻り値: []
#   エラー: [RuntimeError: 対象Python 3.10 venv以外で実行した場合]
# }
def validate_runtime() -> None:
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 10):
        raise RuntimeError("Run this installer with the target CPython 3.10 virtual environment")
    if sys.prefix == sys.base_prefix:
        raise RuntimeError(
            "Run this installer from a virtual environment, not a base Python install"
        )


# {
#   責務: [validate_certifi_bundle: 対象環境のpip/certifiとCA bundleを検証する]
#   処理: [1: 共通CA検査を対象Pythonで実行する, 2: 不合格時に更新方法を示して停止する]
#   引数: []
#   戻り値: []
#   エラー: [RuntimeError: pip/certifiの版またはCA bundleが基準を満たさない場合]
# }
def validate_certifi_bundle() -> None:
    errors = ca_audit_errors()
    if errors:
        raise RuntimeError(
            "Target pip/certifi CA validation failed. Upgrade pip and certifi, then retry.\n"
            + "\n".join(errors)
        )


# {
#   責務: [ca_audit_errors: 共通CA監査moduleから検査結果を取得する]
#   処理: [1: 既存checkerをfile pathから読み込む, 2: target Python環境を検査する]
#   引数: []
#   戻り値: [errors: CA検査エラー一覧]
#   エラー: [FileNotFoundError: 共通checkerがない場合, RuntimeError: checkerのloaderがない場合]
# }
def ca_audit_errors() -> list[str]:
    checker = SOURCE_DIRECTORY / "check_python_ca.py"
    spec = importlib.util.spec_from_file_location("_python_ca_checker", checker)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load CA checker: {checker}")
    checker_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker_module)
    return checker_module.check_environment()


# {
#   責務: [validate_startup_resolution: 先行sitecustomizeがshimを隠さないか確認する]
#   処理: [1: sys.path順にsitecustomize候補を確認する, 2: 配置先より前にある競合を拒否する]
#   引数: [directory: shimを配置するsite-packages directory]
#   戻り値: []
#   エラー: [RuntimeError: 先行sitecustomizeが優先される場合]
# }
def validate_startup_resolution(directory: Path, require_managed: bool = False) -> None:
    expected = (directory / "sitecustomize.py").resolve()
    source_directory = SOURCE_DIRECTORY.resolve()
    search_paths = [str(Path.cwd())]
    search_paths.extend(sys.path)
    normalized_paths = list(
        dict.fromkeys(
            str(resolved)
            for entry in search_paths
            if (resolved := Path(entry or os.curdir).resolve()) != source_directory
        )
    )
    spec = importlib.machinery.PathFinder.find_spec("sitecustomize", normalized_paths)
    if spec is not None and spec.origin is not None:
        if Path(spec.origin).resolve() != expected:
            raise RuntimeError(f"Another sitecustomize shadows the managed shim ({spec.origin})")
        return
    if require_managed:
        raise RuntimeError("Managed sitecustomize is not importable from the target environment")


# {
#   責務: [installer_lock: install/remove間の同時実行を直列化する]
#   処理: [1: site-packages内のOS lockを取得する, 2: 操作後にlockを解放する]
#   引数: [directory: shimを配置するsite-packages directory]
#   戻り値: [lock_file: 排他制御中のlock handle]
#   副作用: [site-packages内にlock fileを作成する]
# }
def installer_lock(directory: Path) -> BinaryIO:
    import msvcrt

    lock_file = (directory / ".python310_tls_shim.lock").open("a+b")
    lock_file.seek(0)
    if not lock_file.read(1):
        lock_file.write(b"0")
        lock_file.flush()
    lock_file.seek(0)
    msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
    return lock_file


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
    validate_runtime()
    validate_certifi_bundle()

    directory = target_directory()
    validate_startup_resolution(directory)
    lock_file = installer_lock(directory)
    try:
        _install_managed_files(directory)
        validate_startup_resolution(directory, require_managed=True)
    finally:
        lock_file.close()
    return directory


# {
#   責務: [_install_managed_files: 管理対象shimを排他中に検証して原子的に配置する]
#   処理: [1: 配置先とsourceを検証する, 2: 一時fileを書き出す, 3: markerを再確認して置換する]
#   引数: [directory: 対象site-packages directory]
#   戻り値: []
#   エラー: [FileExistsError: 管理外fileが配置先にある場合]
# }
def _install_managed_files(directory: Path) -> None:
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
            _replace_managed_target(temporary_path, target)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()


# {
#   責務: [_replace_managed_target: 管理外fileを上書きせずshimを配置する]
#   処理: [1: 既存fileのmarkerを確認する, 2: 既存更新は置換し新規配置は排他的linkで作成する]
#   引数: [temporary_path: 完成済み一時file, target: shimの配置先]
#   戻り値: []
#   エラー: [FileExistsError: 新規配置中に管理外fileが作成された場合]
# }
def _replace_managed_target(temporary_path: Path, target: Path) -> None:
    validate_managed_target(target)
    if target.exists():
        os.replace(temporary_path, target)
        return
    try:
        os.link(temporary_path, target)
    except FileExistsError:
        validate_managed_target(target)
        os.replace(temporary_path, target)


# {
#   責務: [remove_shim: 現在のvenvから管理対象のshimだけを削除する]
#   処理: [1: site-packagesを解決する, 2: marker一致を確認して管理対象ファイルを削除する]
#   引数: []
#   戻り値: [removed_files: 削除したファイル名一覧]
#   エラー: [RuntimeError: 管理対象外ファイルがある場合]
# }
def remove_shim() -> list[str]:
    validate_runtime()
    directory = target_directory()
    lock_file = installer_lock(directory)
    try:
        return _remove_managed_files(directory)
    finally:
        lock_file.close()


# {
#   責務: [_remove_managed_files: 排他中にmarker付きshimだけ削除する]
#   処理: [1: 管理外fileを検出して削除を止める, 2: 管理対象fileだけ削除する]
#   引数: [directory: 対象site-packages directory]
#   戻り値: [removed: 削除したファイル名一覧]
# }
def _remove_managed_files(directory: Path) -> list[str]:
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
            print(
                f"Installed Python 3.10 certifi TLS shim in: {directory}. "
                "Restart every process using this environment."
            )
        return 0
    except (FileExistsError, FileNotFoundError, OSError, RuntimeError, ImportError) as exc:
        print(f"Python 3.10 TLS shim operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
