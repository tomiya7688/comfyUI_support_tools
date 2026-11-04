from dataclasses import dataclass


# {
#   責務: [CharacterSourceAsset: 1件のtagged sourceとそのprovenanceを表す]
#   フィールド: [caption_file: captionの相対path, image_file: 参照画像の相対path, tags: caption tag, outfit_id: outfit directory ID, source_url: 原作品URL, source_work_id: 原作品ID, license_status: 利用条件状態, training_permission: 学習許可状態]
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
