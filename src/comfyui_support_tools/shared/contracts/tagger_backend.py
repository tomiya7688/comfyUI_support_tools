"""Stable Tagger backend choices used by UI, Process validation and HTTP Data adapters."""

from dataclasses import dataclass


# {
# 責務: [TaggerBackendDefinition: UI/validation/HTTP adapterで共有するbackend選択肢]
# フィールド: [id, label, endpoint_suffix, supports_character_threshold, note]
# }
@dataclass(frozen=True)
class TaggerBackendDefinition:
    id: str
    label: str
    endpoint_suffix: str
    supports_character_threshold: bool
    note: str


BACKENDS = (
    TaggerBackendDefinition(
        "pixai_http",
        "PixAI HTTP",
        "/pixai/v1/interrogate",
        True,
        "既存PixAI External Adapter。置換せず維持します。",
    ),
    TaggerBackendDefinition(
        "tagger_service_http",
        "Tagger Service HTTP",
        "/tagger/v1/interrogate",
        False,
        "共通Tagger Service。AnimeTimm等は#229/#231実装後にモデルとして同じ導線へ追加できます。",
    ),
)
BACKEND_BY_ID = {backend.id: backend for backend in BACKENDS}
BACKEND_ID_BY_LABEL = {backend.label: backend.id for backend in BACKENDS}


# {
#   責務: [infer_backend_id: 登録endpoint suffixからbackend IDを推定する]
#   処理: [query stringを除いたURL末尾を各backend suffixと照合する]
#   引数: [url: backend endpoint URL]
#   戻り値: [backend ID。一致なしなら空文字]
# }
def infer_backend_id(url: str) -> str:
    for backend in BACKENDS:
        if url.split("?", 1)[0].endswith(backend.endpoint_suffix):
            return backend.id
    return ""


# {
#   責務: [resolve_backend: 指定IDまたはauto_httpとURLに対応するbackendを解決する]
#   処理: [IDを解決し、登録backendとendpoint suffixの整合性を検証する]
#   引数: [backend_id: 明示IDまたはauto_http, url: endpoint URL]
#   戻り値: [TaggerBackendDefinition: 対応するbackend設定]
#   エラー: [ValueError: backend未選択またはURL suffix不一致]
# }
def resolve_backend(backend_id: str, url: str) -> TaggerBackendDefinition:
    resolved = infer_backend_id(url) if backend_id == "auto_http" else backend_id
    backend = BACKEND_BY_ID.get(resolved)
    if backend is None:
        raise ValueError("Tagger backendを選択してください")
    if not url.split("?", 1)[0].endswith(backend.endpoint_suffix):
        raise ValueError(f"{backend.label} は {backend.endpoint_suffix} URLを使用します")
    return backend


# {
#   責務: [backend_label: backend IDと任意URLから表示labelを取得する]
#   処理: [URLがあればresolve_backendで検証し、失敗時はIDまたは未設定を返す]
#   引数: [backend_id: backend ID, url: optional endpoint URL]
#   戻り値: [label: UI表示名または未設定値]
# }
def backend_label(backend_id: str, url: str = "") -> str:
    if backend_id in BACKEND_BY_ID and not url:
        return BACKEND_BY_ID[backend_id].label
    try:
        return resolve_backend(backend_id, url).label
    except ValueError:
        return backend_id or "未設定"
