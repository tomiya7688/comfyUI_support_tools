from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType


# {
#   責務: [_freeze_value: 入れ子の設定値を変更不能なsnapshotへ変換する]
#   処理: [mapping, sequence, setを再帰的に読み取り専用化し, その他の値はdeep copyする]
#   引数: [value: snapshotへ固定する値]
#   戻り値: [object: 再帰的に固定された値]
# }
def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    return deepcopy(value)


# {
#   責務: [_thaw_value: FeatureSettingsの固定値を独立した可変値へ戻す]
#   処理: [mapping proxyとtupleおよびfrozensetを再帰的に通常のdict, list, setへ変換し, その他の値をdeep copyする]
#   引数: [value: thawする値]
#   戻り値: [object: snapshotから独立した値]
# }
def _thaw_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    if isinstance(value, frozenset):
        return {_thaw_value(item) for item in value}
    return deepcopy(value)


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
    #   処理: [空IDとmapping以外を拒否し, 内部値を再帰的にcopyして読み取り専用化する]
    #   引数: [self: FeatureSettings instance]
    #   戻り値: []
    #   エラー: [ValueError: IDが空またはvaluesがmappingでない場合]
    # }
    def __post_init__(self) -> None:
        if not isinstance(self.feature_id, str) or not self.feature_id.strip():
            raise ValueError("feature_id must be non-empty text")
        if not isinstance(self.values, Mapping):
            raise ValueError("values must be a mapping")
        object.__setattr__(self, "values", _freeze_value(self.values))

    # {
    #   責務: [to_dict: 永続化向けに設定値mappingを通常のdictへ変換する]
    #   処理: [feature_idと設定値をJSON互換documentの部品として返す]
    #   引数: [self: FeatureSettings instance]
    #   戻り値: [dict: feature_idとvaluesを含むmapping]
    # }
    def to_dict(self) -> dict[str, object]:
        return {"feature_id": self.feature_id, "values": _thaw_value(self.values)}
