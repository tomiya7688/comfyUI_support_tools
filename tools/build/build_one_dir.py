"""Build the Kadoka Tools one-dir distribution with PyInstaller."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_BUILD_TOOL_DIR = str(Path(__file__).resolve().parent)
if _BUILD_TOOL_DIR not in sys.path:
    sys.path.insert(0, _BUILD_TOOL_DIR)
from license_inventory import collect_license_inventory

APP_NAME = "KadokaTools"
EXCLUDED_MODULES = ("torch", "torchvision", "torchaudio")
MINIMUM_PYTHON = (3, 11, 18)
MAXIMUM_PYTHON_EXCLUSIVE = (3, 13)


# {
#   責務: [_require_supported_python: 配布ビルドで使うCPythonの対応範囲を検証する]
#   処理: [1: 実装名を確認する, 2: 最低版と上限版を検証する]
#   引数: [version: 検証対象のPython版, implementation: Python実装名]
#   戻り値: []
# }
def _require_supported_python(
    version: tuple[int, ...] = sys.version_info,
    implementation: str = sys.implementation.name,
) -> None:
    """Reject unsupported or non-CPython build interpreters before packaging."""
    if (
        implementation != "cpython"
        or version[:3] < MINIMUM_PYTHON
        or version[:2] >= MAXIMUM_PYTHON_EXCLUSIVE
    ):
        minimum = ".".join(map(str, MINIMUM_PYTHON))
        maximum = MAXIMUM_PYTHON_EXCLUSIVE[1] - 1
        raise RuntimeError(f"The one-dir build requires CPython {minimum} through 3.{maximum}.")


# {
#   責務: [
#     executable_path: one-dir output folder内の実行ファイルpathを解決する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     output: result output directory (Path),
#   ],
#   戻り値: [
#     result: Path as described by the annotated return type,
#   ],
# }
def executable_path(output: Path) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return output / APP_NAME / f"{APP_NAME}{suffix}"


# {
#   責務: [
#     _build_environment: build subprocess用にenvironment variableとPython pathを整える
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: dict[str, str] as described by the annotated return type,
#   ],
# }
def _build_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH"):
        environment.pop(key, None)
    environment["PYTHONNOUSERSITE"] = "1"
    if os.name == "nt":
        system_root = Path(
            environment.get("SystemRoot") or environment.get("WINDIR") or r"C:\Windows"
        )
        allowed_paths = (
            Path(sys.prefix) / "Scripts",
            Path(sys.base_prefix),
            system_root / "System32",
            system_root,
        )
        environment["PATH"] = os.pathsep.join(str(path) for path in allowed_paths)
    return environment


# {
#   責務: [
#     build: PyInstaller one-dir bundleとlicense artifactsを生成する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: 必要なexternal commandを実行しreturn statusを確認する,
#     3: 計画したfilesystem output/updateを適用する,
#   ],
#   引数: [
#     root: repository or migration root (Path),
#     output: result output directory (Path),
#   ],
#   戻り値: [
#     result: Path as described by the annotated return type,
#   ],
#   副作用: [
#     指定されたfilesystem pathsを作成、更新、移動、置換、または削除する,
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#     external processを起動し、結果を取得する,
#   ],
#   エラー: [
#     FileNotFoundError: invalid input, unsafe path, or command failure,
#   ],
# }
def build(root: Path, output: Path) -> Path:
    _require_supported_python()
    work_dir = root / "build" / "pyinstaller"
    work_dir.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--contents-directory",
        ".",
        "--name",
        APP_NAME,
        "--distpath",
        str(output),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(work_dir),
        "--paths",
        str(root / "src"),
    ]
    for module_name in EXCLUDED_MODULES:
        command.extend(("--exclude-module", module_name))
    command.append(str(root / "tabbed_tools_gui.py"))

    subprocess.run(command, cwd=root, env=_build_environment(), check=True)

    distribution_dir = output / APP_NAME
    (distribution_dir / "user_data" / "input" / "config" / "common").mkdir(
        parents=True,
        exist_ok=True,
    )
    executable = executable_path(output)
    if not executable.is_file():
        raise FileNotFoundError(f"PyInstaller output executable was not created: {executable}")
    for filename in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        source = root / filename
        if not source.is_file():
            raise FileNotFoundError(f"Required license notice was not found: {source}")
        shutil.copy2(source, distribution_dir / filename)
    collect_license_inventory(root, distribution_dir, work_dir / APP_NAME / "COLLECT-00.toc")
    return executable


# {
#   責務: [
#     run_smoke_test: 生成済みexecutableを一時profileで起動し、起動応答を検証する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: 必要なexternal commandを実行しreturn statusを確認する,
#     3: validated resultをcallerへ返す,
#   ],
#   引数: [
#     executable: built binary path (Path),
#   ],
#   戻り値: [
#     result: None as described by the annotated return type,
#   ],
#   副作用: [
#     external processを起動し、結果を取得する,
#   ],
# }
def run_smoke_test(executable: Path) -> None:
    # Do not accidentally import from the checkout or a user's Python setup.
    executable = executable.resolve()
    environment = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH"):
        environment.pop(key, None)
    environment["PYTHONNOUSERSITE"] = "1"
    if os.name == "nt":
        system_root = Path(os.environ["SystemRoot"])
        environment["PATH"] = os.pathsep.join((str(system_root / "System32"), str(system_root)))
    with tempfile.TemporaryDirectory(prefix="Kadoka smoke 日本語 ") as cwd:
        for flags in (("--smoke-test",), ("--new-ui", "--smoke-test"), ("--shell-smoke-test",)):
            subprocess.run(
                [str(executable), *flags],
                cwd=cwd,
                env=environment,
                check=True,
                timeout=60,
            )


# {
#   責務: [
#     main: build CLIを解析し、PyInstaller one-dir artifactを作成して任意でsmoke testする
#   ],
#   処理: [
#     1: CLI argumentsをparseする (--root, --output, --smoke-test),
#     2: build CLIを解析し、PyInstaller one-dir artifactを作成して任意でsmoke testする,
#     3: resultとexit statusを返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: None as described by the annotated return type,
#   ],
#   副作用: [
#     build directoryとdistribution artifactを作成・更新する,
#     PyInstallerとoptional smoke testのexternal processを起動する,
#     CLI結果とerrorを標準出力または標準errorへ表示する,
#   ],
# }
def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Kadoka Tools one-dir distribution")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Test both frozen UIs, including real Tk creation for the workspace.",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output or root / "dist").resolve()
    executable = build(root, output)
    if args.smoke_test:
        run_smoke_test(executable)
    print(f"one-dir build ready: {executable.parent}")


if __name__ == "__main__":
    main()
