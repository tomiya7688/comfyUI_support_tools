from dataclasses import dataclass

from .civitai_lora_candidate import CivitaiLoraCandidate


# {
#   責務: [CivitaiLoraVersionMetadata: 選択済みLoRA版から取得したtagger登録前のmetadataを保持する]
#   フィールド: [candidate: model-level利用条件を含むLoRA候補, trained_words: Civitai提供のtrigger word, status/availability: APIの公開状態]
# }
@dataclass(frozen=True)
class CivitaiLoraVersionMetadata:
    candidate: CivitaiLoraCandidate
    trained_words: tuple[str, ...]
    status: str
    availability: str
