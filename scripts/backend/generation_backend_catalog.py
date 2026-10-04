"""Shared contract for generation-backend model and option catalogs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

ChoiceMap = dict[str, list[str]]
RequestGet = Callable[..., Any]


# {
# 責務: [GenerationBackendCatalog: 生成バックエンド別カタログの選択肢照会APIを定義する]
# フィールド: []
# 処理: [1: backend固有APIの結果を共通選択肢形式で提供する]
# }
class GenerationBackendCatalog(Protocol):
    """Common API for retrieving backend-specific generation choices."""

    # {
    # 責務: [query_choices: APIからモデル等の選択肢を照会する契約]
    # 処理: [1: API選択肢を共通カテゴリへ正規化する]
    # 引数: [base_url: backend APIのURL, request_get: HTTP GET関数]
    # 戻り値: [カテゴリ別選択肢と警告の組]
    # }
    def query_choices(self, base_url: str, request_get: RequestGet) -> tuple[ChoiceMap, list[str]]:
        """Return API choices and non-fatal per-endpoint warnings."""
        ...
