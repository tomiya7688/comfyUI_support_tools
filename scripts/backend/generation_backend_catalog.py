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
