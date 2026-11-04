from pathlib import Path

from ..processing.wildcard_file_provider import (
    read_numbered_wildcard_lines,
    read_sequential_prompt_sources,
    select_wildcard_source,
)


# {
#   責務: [load_wildcard_lines: wildcard参照を選択して物理行番号付きで読み込む]
#   処理: [data processingへpath選択とfile読込を委譲する]
#   引数: [reference: wildcard参照, root: wildcard root directory]
#   戻り値: [tuple[Path | None, list[tuple[int, str]]]: 選択fileと行一覧]
# }
def load_wildcard_lines(reference: str, root: Path) -> tuple[Path | None, list[tuple[int, str]]]:
    """Delegate wildcard source selection and line loading to the data provider."""
    path = select_wildcard_source(reference, root)
    if path is None:
        return None, []
    return path, read_numbered_wildcard_lines(path)


# {
#   責務: [load_sequential_prompts: 順次生成用にprompt source行を一括取得する]
#   処理: [file providerへsource fileの探索と行読み込みを委譲する]
#   引数: [reference: prompt fileまたはdirectory, root: wildcard root]
#   戻り値: [list[tuple[str, int, str]]: source path, 物理行番号, 本文]
# }
def load_sequential_prompts(reference: str, root: Path) -> list[tuple[str, int, str]]:
    """Load sequential source lines through the wildcard data provider."""
    return read_sequential_prompt_sources(reference, root)
