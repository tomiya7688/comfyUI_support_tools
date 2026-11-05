from dataclasses import dataclass


# {
#   責務: [CharacterSourceAsset: 1件のtagged sourceとそのprovenanceを表す]
#   フィールド: [caption_file: caption相対pathまたはstable source reference, image_file: 参照画像の相対path, tags: caption tag, outfit_id: outfit directory ID, source_url: 原作品URL, source_work_id: 原作品ID, license_status: 利用条件状態, training_permission: 学習許可状態, source_metadata: source固有の権利/モデルmetadata]
# }
@dataclass(frozen=True)
class CharacterSourceAsset:
    caption_file: str
    image_file: str | None
    tags: tuple[str, ...]
    outfit_id: str | None
    source_url: str
    source_work_id: str
    license_status: str
    training_permission: str
    source_metadata: tuple[tuple[str, bool | str | None], ...] = ()

    # {
    #   責務: [__post_init__: source-specific metadataをJSON保存可能な一意key/value tupleに制限する]
    #   処理: [tuple shape, 非空key, JSON scalar value, 重複keyを検証する]
    #   引数: [self: source asset]
    #   戻り値: []
    #   エラー: [ValueError: source_metadataが不正な場合]
    # }
    def __post_init__(self) -> None:
        if not isinstance(self.source_metadata, tuple):
            raise ValueError("source_metadataはkey/value pairのtupleで指定してください")
        keys: set[str] = set()
        for entry in self.source_metadata:
            if (
                not isinstance(entry, tuple)
                or len(entry) != 2
                or not isinstance(entry[0], str)
                or not entry[0].strip()
                or (not isinstance(entry[1], (bool, str)) and entry[1] is not None)
            ):
                raise ValueError("source_metadataは非空keyとstr/bool/null valueで指定してください")
            if entry[0] in keys:
                raise ValueError("source_metadata keyは重複できません")
            keys.add(entry[0])
