"""Feature declarations shared by generation backends and callers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationCapabilities:
    features: frozenset[str]

    def supports(self, feature: str) -> bool:
        return feature in self.features
