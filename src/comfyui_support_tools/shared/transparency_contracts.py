"""Data contracts for opt-in transparency metadata and provenance."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# {
# 責務: [ MediaClassification: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class MediaClassification(str, Enum):
    UNKNOWN = "unknown"
    GENERATED = "generated"
    AI_MODIFIED = "ai_modified"
    CONVENTIONAL_EDIT = "conventional_edit"


# {
# 責務: [ PromptDisclosure: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class PromptDisclosure(str, Enum):
    NONE = "none"
    HASH_ONLY = "hash_only"
    SANITIZED_SUMMARY = "sanitized_summary"
    FULL = "full"


# {
# 責務: [ ModelDisclosure: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class ModelDisclosure(str, Enum):
    NONE = "none"
    FAMILY = "family"
    MODEL_ID = "model_id"
    MODEL_ID_AND_VERSION = "model_id_and_version"


# {
# 責務: [ WorkflowDisclosure: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class WorkflowDisclosure(str, Enum):
    NONE = "none"
    ID = "id"
    HASH = "hash"
    FULL = "full"


# {
# 責務: [ VerificationFailurePolicy: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class VerificationFailurePolicy(str, Enum):
    ERROR = "error"
    WARNING = "warning"


# {
# 責務: [ TransparencySettings: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
@dataclass(frozen=True)
class TransparencySettings:
    """Explicit export controls. All disclosure and signing options default off."""

    enabled: bool = False
    profile_id: str = "eu_ai_act_article50_2026"
    prompt_disclosure: PromptDisclosure = PromptDisclosure.NONE
    model_disclosure: ModelDisclosure = ModelDisclosure.NONE
    workflow_disclosure: WorkflowDisclosure = WorkflowDisclosure.NONE
    write_sidecar: bool = True
    write_png_metadata: bool = True
    sign_c2pa: bool = False
    verify_export: bool = True
    verification_failure_policy: VerificationFailurePolicy = VerificationFailurePolicy.ERROR
    visible_disclosure: bool = False
    visible_disclosure_label: str | None = None
    deepfake_disclosure_assist: bool = False


# {
# 責務: [ ProvenanceAction: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
@dataclass(frozen=True)
class ProvenanceAction:
    operation: str
    ai_involvement: bool
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    application: str = "comfyUI_support_tools"
    application_version: str = "unknown"
    source_asset_sha256: str | None = None
    region: str | None = None
    user_oversight: str = "unknown"

    # {
    # 責務: [ __post_init__: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def __post_init__(self) -> None:
        if not self.operation.strip():
            raise ValueError("provenance action operation must not be empty")
        if self.user_oversight not in {
            "unknown",
            "fully_automated",
            "prompt_guided",
            "human_reviewed",
            "human_edited",
        }:
            raise ValueError("unsupported user oversight value")


# {
# 責務: [ ProvenanceRecord: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
@dataclass(frozen=True)
class ProvenanceRecord:
    classification: MediaClassification = MediaClassification.UNKNOWN
    content_type: str = "image"
    application: str = "comfyUI_support_tools"
    application_version: str = "unknown"
    backend: str | None = None
    prompt: str | None = None
    sanitized_prompt_summary: str | None = None
    model_family: str | None = None
    model_id: str | None = None
    model_version: str | None = None
    model_hash: str | None = None
    c2pa_model_type: str | None = None
    workflow_id: str | None = None
    workflow_json: dict[str, Any] | None = None
    actions: tuple[ProvenanceAction, ...] = ()
    source_assets: tuple[str, ...] = ()
    deepfake_disclosure_applicable: bool = False
    represents_real_person_place_or_event: bool = False
    user_overrides: tuple[str, ...] = ()
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# {
# 責務: [ TransparencyProfile: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
@dataclass(frozen=True)
class TransparencyProfile:
    id: str
    jurisdiction: str
    regulation_reference: str
    effective_from: str
    profile_version: str
    supported_media: tuple[str, ...]
    references: tuple[str, ...]


EU_AI_ACT_ARTICLE_50_2026 = TransparencyProfile(
    id="eu_ai_act_article50_2026",
    jurisdiction="EU",
    regulation_reference="Regulation (EU) 2024/1689, Article 50",
    effective_from="2026-08-02",
    profile_version="2026.1",
    supported_media=("image", "video", "audio", "text"),
    references=(
        "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02024R1689-20260727",
        "https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act",
        "https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html",
    ),
)

TRANSPARENCY_PROFILES = {EU_AI_ACT_ARTICLE_50_2026.id: EU_AI_ACT_ARTICLE_50_2026}


# {
# 責務: [ resolve_profile: 入力を処理して結果を返す ]
# 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
# 引数: [profile_id]
# 戻り値: [処理結果]
# }
def resolve_profile(profile_id: str) -> TransparencyProfile:
    try:
        return TRANSPARENCY_PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"unknown transparency profile: {profile_id}") from exc


# {
# 責務: [ resolve_transparency_enabled: 入力を処理して結果を返す ]
# 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
# 引数: [global_enabled, application_override, export_override]
# 戻り値: [処理結果]
# }
def resolve_transparency_enabled(
    global_enabled: bool = False,
    application_override: bool | None = None,
    export_override: bool | None = None,
) -> bool:
    """Resolve settings in per-export > application > global > OFF order."""
    for value in (export_override, application_override, global_enabled):
        if value is not None:
            return bool(value)
    return False
