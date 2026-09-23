"""Stable Tagger backend choices used by UI, Process validation and HTTP Data adapters."""
from dataclasses import dataclass


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


def infer_backend_id(url: str) -> str:
    for backend in BACKENDS:
        if url.split("?", 1)[0].endswith(backend.endpoint_suffix):
            return backend.id
    return ""


def resolve_backend(backend_id: str, url: str) -> TaggerBackendDefinition:
    resolved = infer_backend_id(url) if backend_id == "auto_http" else backend_id
    backend = BACKEND_BY_ID.get(resolved)
    if backend is None:
        raise ValueError("Tagger backendを選択してください")
    if not url.split("?", 1)[0].endswith(backend.endpoint_suffix):
        raise ValueError(f"{backend.label} は {backend.endpoint_suffix} URLを使用します")
    return backend


def backend_label(backend_id: str, url: str = "") -> str:
    try:
        return resolve_backend(backend_id, url).label
    except ValueError:
        return backend_id or "未設定"
