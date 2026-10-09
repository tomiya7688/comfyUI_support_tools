"""Shared contract for generation-backend model and option catalogs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

ChoiceMap = dict[str, list[str]]
RequestGet = Callable[..., Any]


class GenerationBackendCatalog(Protocol):
    """Common API for retrieving backend-specific generation choices."""

    def query_choices(self, base_url: str, request_get: RequestGet) -> tuple[ChoiceMap, list[str]]:
        """Return API choices and non-fatal per-endpoint warnings."""
        ...

    # {
    #   責務: [primary_model_choices: backendで主checkpointとして選択可能なモデル候補を返す]
    #   処理: [1: 共通候補mappingからbackend固有の主モデル候補を選ぶ, 2: 重複を除いて順序を保持する]
    #   引数: [self: catalog instance, choices: backendから取得したモデル候補mapping]
    #   戻り値: [list[str]: 生成設定で選択できる主モデル名]
    # }
    def primary_model_choices(self, choices: ChoiceMap) -> list[str]:
        """Return the backend-specific models accepted as a primary model."""
        ...
