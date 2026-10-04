"""Feature declarations shared by generation backends and callers."""

from __future__ import annotations

from dataclasses import dataclass


# {
# 責務: [GenerationCapabilities: 生成backendが対応する機能集合を保持する]
# フィールド: [features: 利用可能な機能名の不変集合]
# 処理: [1: 機能対応状況を呼び出し元へ公開する]
# }
@dataclass(frozen=True)
class GenerationCapabilities:
    features: frozenset[str]

    # {
    # 責務: [supports: 指定機能をbackendが提供するか判定する]
    # 処理: [1: featureが対応集合に含まれるか調べる]
    # 引数: [feature: 確認する機能名]
    # 戻り値: [対応している場合はTrue]
    # }
    def supports(self, feature: str) -> bool:
        return feature in self.features
