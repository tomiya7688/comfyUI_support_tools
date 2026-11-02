"""Immutable Action/Inspector messages. No widgets, handles or backend modules."""

from dataclasses import dataclass
from comfyui_support_tools.shared.contracts.media_item import MediaItem


# {
# 責務: [ScoredLabel: 一つのtagとconfidence scoreを保持する]
# フィールド: [name: 表示tag名, score: 0から1のconfidence]
# }
@dataclass(frozen=True)
class ScoredLabel:
    name: str
    score: float


# {
# 責務: [NormalizedTagResult: backend応答をInspector共通のtag resultへ正規化した値]
# フィールド: [category別tag名とscore, rating, caption, backend, model]
# }
@dataclass(frozen=True)
class NormalizedTagResult:
    content_tags: tuple[str, ...] = ()
    character_tags: tuple[str, ...] = ()
    copyright_tags: tuple[str, ...] = ()
    rating: str = ""
    caption: str = ""
    content_scores: tuple[ScoredLabel, ...] = ()
    character_scores: tuple[ScoredLabel, ...] = ()
    rating_scores: tuple[ScoredLabel, ...] = ()
    backend: str = ""
    model: str = ""


# {
# 責務: [MediaNotes: media itemに保存・表示するtag、prompt、caption情報]
# フィールド: [content/style/character/copyright tags, prompts, dataset, rating, caption, tagger情報, scores]
# }
@dataclass(frozen=True)
class MediaNotes:
    content_tags: tuple[str, ...] = ()
    style_tags: tuple[str, ...] = ()
    prompt: str = ""
    negative_prompt: str = ""
    character: str = ""
    dataset: str = ""
    character_tags: tuple[str, ...] = ()
    copyright_tags: tuple[str, ...] = ()
    rating: str = ""
    caption: str = ""
    tagger_backend: str = ""
    tagger_model: str = ""
    content_scores: tuple[ScoredLabel, ...] = ()
    character_scores: tuple[ScoredLabel, ...] = ()
    rating_scores: tuple[ScoredLabel, ...] = ()


# {
# 責務: [TaggerSettings: Tagger endpointと推論threshold、timeoutの設定]
# フィールド: [url, model, threshold, character_threshold, timeout, backend]
# }
@dataclass(frozen=True)
class TaggerSettings:
    url: str = ""
    model: str = ""
    threshold: float = 0.35
    character_threshold: float = 0.85
    timeout: float = 30.0
    backend: str = "auto_http"


# {
# 責務: [ExportSettings: captionやmetadata sidecarの出力設定]
# フィールド: [caption_sidecar, metadata_sidecar, batch_txt_path, include_style_in_caption, overwrite]
# }
@dataclass(frozen=True)
class ExportSettings:
    caption_sidecar: bool = True
    metadata_sidecar: bool = True
    batch_txt_path: str = ""
    include_style_in_caption: bool = False
    overwrite: bool = False


# {
# 責務: [MediaExportRecord: 一つのmedia itemとexport用notesを対応付ける]
# フィールド: [item: 対象media, notes: 出力する注釈]
# }
@dataclass(frozen=True)
class MediaExportRecord:
    item: MediaItem
    notes: MediaNotes


# {
# 責務: [ActionDefinition: Inspectorで提供するactionの識別子、表示情報、対象kindを定義する]
# フィールド: [id, label, kinds, unavailable]
# }
@dataclass(frozen=True)
class ActionDefinition:
    id: str
    label: str
    kinds: tuple[str, ...]
    unavailable: str = ""


# {
# 責務: [ActionAvailability: action定義と現在の有効状態、無効理由を組にする]
# フィールド: [definition, enabled, reason]
# }
@dataclass(frozen=True)
class ActionAvailability:
    definition: ActionDefinition
    enabled: bool
    reason: str = ""


# {
# 責務: [ActionRequest: token付きでworkerへ渡すInspector action入力]
# フィールド: [token, kind, settings, items, export_settings, export_records]
# }
@dataclass(frozen=True)
class ActionRequest:
    token: int
    kind: str
    settings: TaggerSettings
    items: tuple[MediaItem, ...] = ()
    export_settings: ExportSettings | None = None
    export_records: tuple[MediaExportRecord, ...] = ()


# {
# 責務: [ActionEvent: action workerからownerへ返す進捗・結果・失敗message]
# フィールド: [token, kind, item, tags, models, message, failed]
# }
@dataclass(frozen=True)
class ActionEvent:
    token: int
    kind: str
    item: MediaItem | None = None
    tags: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    message: str = ""
    failed: bool = False


# {
# 責務: [InspectorStatus: 現在のTagger設定、model一覧、busy/ready状態を公開する]
# フィールド: [settings, models, busy, ready, message]
# }
@dataclass(frozen=True)
class InspectorStatus:
    settings: TaggerSettings
    models: tuple[str, ...]
    busy: bool
    ready: bool
    message: str
