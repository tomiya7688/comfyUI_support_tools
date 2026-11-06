from dataclasses import dataclass

from .civitai_lora_candidate import CivitaiLoraCandidate
from .civitai_preview_image import CivitaiPreviewImage


# {
#   責務: [CivitaiLoraVersionMetadata: 選択済みLoRA版から取得したtagger登録前のmetadataを保持する]
#   フィールド: [candidate: model-level利用条件を含むLoRA候補, trained_words: 分割済みtrigger word, raw_trained_words: API文字列の原文, preview_images: 画像bytesを取得しない公開プレビュー参照, status/availability: APIの公開状態]
# }
@dataclass(frozen=True)
class CivitaiLoraVersionMetadata:
    """Keep normalized trigger tags and original metadata from one selected version."""

    candidate: CivitaiLoraCandidate
    trained_words: tuple[str, ...]
    status: str
    availability: str
    raw_trained_words: str | None = None
    preview_images: tuple[CivitaiPreviewImage, ...] = ()
