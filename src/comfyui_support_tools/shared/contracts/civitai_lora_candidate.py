from dataclasses import dataclass


# {
#   責務: [CivitaiLoraCandidate: Civitai検索結果から得たLoRA版候補と利用条件を保持する]
#   フィールド: [model_id/version_id: Civitai識別子, model_name/version_name: 表示名, creator: 作者名, base_model: 対象model family, tags: Civitai model tags, source_url: 版を特定するcanonical URL, allow_no_credit/allow_commercial_use/allow_derivatives/allow_different_license: APIが返した利用条件, model_mode: moderation状態]
# }
@dataclass(frozen=True)
class CivitaiLoraCandidate:
    model_id: int
    version_id: int
    model_name: str
    version_name: str
    creator: str
    base_model: str
    tags: tuple[str, ...]
    source_url: str
    allow_no_credit: bool | None
    allow_commercial_use: str | None
    allow_derivatives: bool | None
    allow_different_license: bool | None
    model_mode: str | None
