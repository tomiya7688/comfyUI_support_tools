from __future__ import annotations

import secrets
from pathlib import Path


# {
#   責務: [select_wildcard_source: root内のwildcard参照を実ファイルへ解決する]
#   処理: [1: 相対または絶対pathを解決する, 2: directoryならtxt候補から1件を選ぶ, 3: 存在しない参照はNoneで返す]
#   引数: [reference: wildcard参照, root: wildcard root directory]
#   戻り値: [Path | None: 選択されたsource file]
# }
def select_wildcard_source(reference: str, root: Path) -> Path | None:
    """Select an existing file or a random text file beneath a directory reference."""
    requested_path = Path(reference)
    path = requested_path if requested_path.is_absolute() else root / requested_path
    if not path.exists() and path.suffix.lower() == ".txt" and path.with_suffix("").is_dir():
        path = path.with_suffix("")
    if path.is_dir():
        candidates = sorted(
            (item for item in path.rglob("*.txt") if item.is_file()),
            key=lambda item: item.as_posix().casefold(),
        )
        return secrets.choice(candidates) if candidates else None
    return path if path.is_file() else None


# {
#   責務: [read_numbered_wildcard_lines: wildcard fileを元行番号付きで読む]
#   処理: [UTF-8で開き, 空行を除いた物理行番号と本文を返す]
#   引数: [path: 読み込むwildcard file]
#   戻り値: [list[tuple[int, str]]: 元行番号と行本文]
#   エラー: [OSError: fileを読めない場合]
# }
def read_numbered_wildcard_lines(path: Path) -> list[tuple[int, str]]:
    """Read nonblank UTF-8 lines and preserve their physical line numbers."""
    with path.open(encoding="utf-8") as source:
        return [
            (line_number, line.strip())
            for line_number, line in enumerate(source, start=1)
            if line.strip()
        ]


# {
#   責務: [read_sequential_prompt_sources: fileまたはdirectoryから順次prompt行を読む]
#   処理: [txt sourceをpath順に列挙し, 空行を除いて物理行番号と本文を収集する]
#   引数: [reference: prompt fileまたはdirectory, root: 相対pathの基準directory]
#   戻り値: [list[tuple[str, int, str]]: source path, 物理行番号, 本文]
# }
def read_sequential_prompt_sources(reference: str, root: Path) -> list[tuple[str, int, str]]:
    """Read all source lines in stable file order for sequential generation."""
    requested_path = Path(reference)
    path = requested_path if requested_path.is_absolute() else root / requested_path
    if not path.exists() and path.suffix.lower() == ".txt" and path.with_suffix("").is_dir():
        path = path.with_suffix("")
    if path.is_file():
        sources = [path]
    elif path.is_dir():
        sources = sorted(
            (item for item in path.rglob("*.txt") if item.is_file()),
            key=lambda item: item.as_posix().casefold(),
        )
    else:
        sources = []
    return [
        (source.as_posix(), line_number, line)
        for source in sources
        for line_number, line in read_numbered_wildcard_lines(source)
    ]
