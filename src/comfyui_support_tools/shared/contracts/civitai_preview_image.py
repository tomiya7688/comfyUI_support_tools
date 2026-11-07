from dataclasses import dataclass

MAX_TAGGER_ANALYSIS_IMAGES = 8


# {
#   責務: [CivitaiPreviewImage: Civitai版の公開プレビュー参照と閲覧レベルを保持する]
#   フィールド: [image_id: Civitai画像ID, url: 許可済みHTTPS CDN URL, nsfw_level: APIが返した閲覧レベル]
# }
@dataclass(frozen=True)
class CivitaiPreviewImage:
    """Keep a Civitai preview reference without downloading its image bytes."""

    image_id: int
    url: str
    nsfw_level: int | None
