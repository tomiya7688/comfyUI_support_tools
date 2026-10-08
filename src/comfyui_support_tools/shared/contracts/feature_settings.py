from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


# {
#   責務: [FeatureSettings: GUI非依存のfeature設定値と安定IDを表す]
#   フィールド: [feature_id: 永続化に使う安定した識別子, values: Tk依存を含まない設定値mapping]
#   処理: [設定値を読み取り専用mappingとして保持し, dict形式へ変換する]
# }
@dataclass(frozen=True)
class FeatureSettings:
    feature_id: str
    values: Mapping[str, object]

    # {
    #   責務: [__post_init__: FeatureSettingsの識別子と値mappingを検証する]
    #   処理: [空IDとmapping以外を拒否し, 内部値の浅いcopyを読み取り専用化する]
    #   引数: [self: FeatureSettings instance]
    #   戻り値: []
    #   エラー: [ValueError: IDが空またはvaluesがmappingでない場合]
    # }
    def __post_init__(self) -> None:
        if not isinstance(self.feature_id, str) or not self.feature_id.strip():
            raise ValueError("feature_id must be non-empty text")
        if not isinstance(self.values, Mapping):
            raise ValueError("values must be a mapping")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    # {
    #   責務: [to_dict: 永続化向けに設定値mappingを通常のdictへ変換する]
    #   処理: [feature_idと設定値をJSON互換documentの部品として返す]
    #   引数: [self: FeatureSettings instance]
    #   戻り値: [dict: feature_idとvaluesを含むmapping]
    # }
    def to_dict(self) -> dict[str, object]:
        return {"feature_id": self.feature_id, "values": dict(self.values)}
