import os
from pathlib import Path

from ...data.messenger.wildcard_source_messenger import load_sequential_prompts, load_wildcard_lines
from ..processing.wildcard_prompt_resolver import (
    expand_prompt_text,
    parse_wildcard_line,
    select_weighted_wildcard_line,
)

MAX_RECURSION_DEPTH = 50


# {
#   責務: [_wildcard_cache_key: OSのpath case規則に沿ったcache keyを作る]
#   処理: [rootと参照pathを結合し, 絶対path化してplatformのnormcaseを適用する]
#   引数: [reference: wildcard参照, root: wildcard root]
#   戻り値: [str: platform固有に正規化されたabsolute path]
# }
def _wildcard_cache_key(reference: str, root: Path) -> str:
    """Normalize cache identity with the host filesystem's case rules."""
    requested_path = Path(reference)
    path = requested_path if requested_path.is_absolute() else root / requested_path
    return os.path.normcase(os.path.abspath(path))


# {
#   責務: [resolve_wildcard_reference: wildcard sourceを重み付き選択してnested展開する]
#   処理: [data messengerで行を取得し, 再帰上限・cache・重み選択・nested展開を適用する]
#   引数: [reference: wildcard参照, root: wildcard root, depth: nested展開深度, cache: 共有解決cache, trace: 解決元記録, warnings: 解決警告]
#   戻り値: [str: 展開済み本文]
#   エラー: [ValueError: wildcard行の重み記法が不正な場合]
# }
def resolve_wildcard_reference(
    reference: str,
    root: Path,
    depth: int = 0,
    cache: dict[str, str] | None = None,
    trace: list[str] | None = None,
    warnings: list[str] | None = None,
) -> str:
    """Resolve one file reference and recursively expand the selected wildcard line."""
    if depth > MAX_RECURSION_DEPTH:
        if warnings is not None:
            warnings.append(f"Wildcard recursion limit reached: {reference}")
        return ""
    cache_key = _wildcard_cache_key(reference, root)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    path, lines = load_wildcard_lines(reference, root)
    if path is None:
        if warnings is not None:
            warnings.append(f"Wildcard source not found: {reference}")
        return ""
    if trace is not None:
        trace.append(path.as_posix())
    if not lines:
        return ""
    try:
        selected_text = select_weighted_wildcard_line(lines)
    except ValueError as error:
        raise ValueError(f"Invalid wildcard file {path}: {error}") from error

    # {
    #   責務: [resolve_nested: 選択行に含まれるnested wildcard参照を次の深さで解決する]
    #   処理: [親のroot, cache, trace, warningsを再帰resolverへ渡す]
    #   引数: [nested_reference: 子wildcard参照]
    #   戻り値: [str: 子参照の展開済み本文]
    # }
    def resolve_nested(nested_reference: str) -> str:
        return resolve_wildcard_reference(
            nested_reference,
            root,
            depth + 1,
            cache,
            trace,
            warnings,
        )

    expanded_text = expand_prompt_text(selected_text, resolve_nested)
    if cache is not None:
        cache[cache_key] = expanded_text
    return expanded_text


# {
#   責務: [resolve_text: 生prompt本文内のwildcard記法を解決する]
#   処理: [wildcard resolver callbackを構築し, inline/nested記法を展開する]
#   引数: [text: 生prompt本文, root: wildcard root, cache: 共有解決cache, trace: 解決元記録, warnings: 解決警告]
#   戻り値: [str: 展開済みprompt本文]
# }
def resolve_text(
    text: str,
    root: Path,
    cache: dict[str, str] | None,
    trace: list[str],
    warnings: list[str],
) -> str:
    """Expand wildcard syntax in prompt text using this Application's provider path."""

    # {
    #   責務: [resolve_nested: 生prompt内のwildcard参照を解決する]
    #   処理: [参照をrootと共有cache付きのwildcard resolverへ渡す]
    #   引数: [reference: wildcard参照]
    #   戻り値: [str: 展開済み参照本文]
    # }
    def resolve_nested(reference: str) -> str:
        return resolve_wildcard_reference(reference, root, 0, cache, trace, warnings)

    return expand_prompt_text(text, resolve_nested)


__all__ = ["parse_wildcard_line", "resolve_text", "resolve_wildcard_reference"]


# {
#   責務: [load_sequential_prompt_lines: 順次入力sourceの行を取得する]
#   処理: [data messengerへprompt file探索と行読込を依頼する]
#   引数: [reference: 入力fileまたはdirectory, root: wildcard root]
#   戻り値: [list[tuple[str, int, str]]: source path, 物理行番号, 本文]
# }
def load_sequential_prompt_lines(reference: str, root: Path) -> list[tuple[str, int, str]]:
    """Expose ordered source lines to the sequential generation caller."""
    return load_sequential_prompts(reference, root)
