"""Versioned domain contracts for semantic erase requests and results."""

import hashlib
import math
from dataclasses import dataclass
from enum import Enum
from itertools import chain

MAX_IMAGE_PIXELS = 50_000_000


# {
# 責務: [EraseTargetType: 消去要求で扱う意味targetの種類を定義する]
# フィールド: [enum値: query classification]
# }
class EraseTargetType(str, Enum):
    OBJECT = "object"
    ATTRIBUTE = "attribute"
    STATE = "state"
    MARK = "mark"
    TEXT = "text"
    ARTIFACT = "artifact"


# {
# 責務: [MatchPolicy: 複数候補から消去範囲を選択する方針を定義する]
# フィールド: [enum値: candidate selection rule]
# }
class MatchPolicy(str, Enum):
    REMOVE_ALL = "remove_all"
    SELECTED = "selected"
    INSIDE_RANGE = "inside_range"
    ALL_EXCEPT_SELECTED = "all_except_selected"
    REVIEW = "review"


# {
# 責務: [FillPolicy: 消去領域を補完するdomain strategyを定義する]
# フィールド: [enum値: fill strategy]
# }
class FillPolicy(str, Enum):
    AUTO = "auto"
    RESTORE_SKIN = "restore_natural_skin"
    RESTORE_CLOTH = "restore_cloth"
    RESTORE_BACKGROUND = "restore_background"
    NEUTRAL_CLEAN = "neutral_clean"
    CUSTOM = "custom_prompt"


# {
# 責務: [QualityProfile: 候補数やretry量を選ぶ作業budgetを定義する]
# フィールド: [enum値: processing budget]
# }
class QualityProfile(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    QUALITY = "quality"
    OVERNIGHT = "overnight"


# {
# 責務: [EraseMode: 実行結果を自動適用するかreviewへ送るか定義する]
# フィールド: [enum値: review behavior]
# }
class EraseMode(str, Enum):
    CONFIDENT_AUTO = "confident_auto"
    REVIEW_UNCERTAIN = "review_uncertain"


# {
# 責務: [RegionBox: 画像内の正規化範囲を表現する]
# フィールド: [x,y,width,height: 0〜1の画像相対座標]
# }
@dataclass(frozen=True)
class RegionBox:
    x: float
    y: float
    width: float
    height: float

    # {
    # 責務: [__post_init__: RegionBoxの座標範囲を検証する]
    # 処理: [ 1: finite値を検証する, 2: boxの境界を検証する ]
    # 引数: [self: 検証対象]
    # 戻り値: []
    # エラー: [ValueError: 画像境界外または不正値の場合]
    # }
    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("region coordinates must be finite")
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("region box must have positive dimensions inside the image")
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("region box must stay inside normalized image bounds")


# {
# 責務: [RLEMask: binary maskをサイズ付きrun-length形式で保存する]
# フィールド: [width,height,runs: row-majorのtrue-run開始offsetと長さ]
# 処理: [1: flattenされたmaskをrun-lengthで表現する]
# }
@dataclass(frozen=True)
class RLEMask:
    width: int
    height: int
    runs: tuple[tuple[int, int], ...]

    # {
    # 責務: [__post_init__: RLEMaskのshapeとrunを検証する]
    # 処理: [1: dimensionsを検証する, 2: sorted non-overlap runsを検証する]
    # 引数: [self: 検証対象]
    # 戻り値: []
    # エラー: [ValueError: runが画像外または重複する場合]
    # }
    def __post_init__(self) -> None:
        total = self.width * self.height
        if self.width <= 0 or self.height <= 0 or total > MAX_IMAGE_PIXELS:
            raise ValueError("mask dimensions are invalid or exceed the safety limit")
        previous_end = 0
        for start, length in self.runs:
            if start < previous_end or length <= 0 or start + length > total:
                raise ValueError("mask runs must be sorted, non-overlapping, and in bounds")
            previous_end = start + length

    # {
    # 責務: [from_rows: boolean rowsからRLEMaskを構築する]
    # 処理: [1: rectangular shapeを確認する, 2: true-runをencodeする]
    # 引数: [rows: maskのboolean rows]
    # 戻り値: [mask: run-length形式のmask]
    # エラー: [ValueError: row shapeが不正の場合]
    # }
    @classmethod
    def from_rows(cls, rows: tuple[tuple[bool, ...], ...] | list[list[bool]]) -> "RLEMask":
        if not rows or not rows[0]:
            raise ValueError("mask rows must be non-empty")
        width = len(rows[0])
        if any(len(row) != width for row in rows):
            raise ValueError("mask rows must have equal width")
        runs = []
        start = None
        position = 0
        for value in chain.from_iterable(rows):
            value = bool(value)
            if value and start is None:
                start = position
            elif not value and start is not None:
                runs.append((start, position - start))
                start = None
            position += 1
        if start is not None:
            runs.append((start, position - start))
        return cls(width, len(rows), tuple(runs))

    # {
    # 責務: [empty: 大きなsource画像に対応するsparse空maskを作る]
    # 処理: [1: dimensionsだけを保持するRLE instanceを作る]
    # 引数: [width: image width, height: image height]
    # 戻り値: [mask: zero-area mask]
    # }
    @classmethod
    def empty(cls, width: int, height: int) -> "RLEMask":
        return cls(width, height, ())

    # {
    # 責務: [from_binary_bytes: HxW uint8 boolean bufferをRLE maskへencodeする]
    # 処理: [1: buffer lengthを検証する, 2: true runsを作る]
    # 引数: [width: image width, height: image height, values: row-major byte buffer]
    # 戻り値: [mask: run-length encoded mask]
    # エラー: [ValueError: byte countとdimensionsが一致しない場合]
    # }
    @classmethod
    def from_binary_bytes(cls, width: int, height: int, values: bytes) -> "RLEMask":
        if len(values) != width * height:
            raise ValueError("binary mask buffer length does not match dimensions")
        runs = []
        start = None
        for index, value in enumerate(values):
            if value and start is None:
                start = index
            elif not value and start is not None:
                runs.append((start, index - start))
                start = None
        if start is not None:
            runs.append((start, len(values) - start))
        return cls(width, height, tuple(runs))

    # {
    # 責務: [to_binary_bytes: RLE maskをcompact HxW byte bufferへ復元する]
    # 処理: [1: zero bufferを作る, 2: true runsをbufferへ展開する]
    # 引数: [self: mask]
    # 戻り値: [values: row-major zero/one bytes]
    # }
    def to_binary_bytes(self) -> bytes:
        values = bytearray(self.width * self.height)
        for start, length in self.runs:
            values[start : start + length] = b"\x01" * length
        return bytes(values)

    # {
    # 責務: [to_rows: RLEMaskをboolean rowsへ展開する]
    # 処理: [1: false gridを作る, 2: true-runを展開する]
    # 引数: [self: 展開対象]
    # 戻り値: [rows: 展開されたmask]
    # }
    def to_rows(self) -> tuple[tuple[bool, ...], ...]:
        flat = [False] * (self.width * self.height)
        for start, length in self.runs:
            flat[start : start + length] = [True] * length
        return tuple(
            tuple(flat[offset : offset + self.width]) for offset in range(0, len(flat), self.width)
        )

    # {
    # 責務: [area: mask内のtrue pixel数を返す]
    # 処理: [1: run長を合計する]
    # 引数: [self: mask]
    # 戻り値: [pixels: true pixel数]
    # }
    @property
    def area(self) -> int:
        return sum(length for _, length in self.runs)


# {
# 責務: [SemanticEraseTarget: 意味queryと制約を一つのerase要求へまとめる]
# フィールド: [query,normalized/provider tag,target/range,mask,match/fill/preserve policy]
# 処理: [1: user queryと任意の空間制約を保持する]
# }
@dataclass(frozen=True)
class SemanticEraseTarget:
    query: str
    normalized_tag: str | None = None
    provider_query: str | None = None
    range_label: str | None = None
    target_type: EraseTargetType = EraseTargetType.OBJECT
    range_constraint: RegionBox | None = None
    mask: RLEMask | None = None
    match_policy: MatchPolicy = MatchPolicy.REVIEW
    selected_match_id: str | None = None
    fill_policy: FillPolicy = FillPolicy.AUTO
    fill_instruction: str | None = None
    preserve_rules: tuple[str, ...] = ("identity", "expression", "clothing", "background", "style")
    confidence_threshold: float = 0.65

    # {
    # 責務: [__post_init__: SemanticEraseTargetの必須queryと閾値を検証する]
    # 処理: [1: queryをstripする, 2: thresholdとfill instructionを検証する]
    # 引数: [self: 検証対象]
    # 戻り値: []
    # エラー: [ValueError: queryまたは閾値が不正の場合]
    # }
    def __post_init__(self) -> None:
        for name, enum_type in (
            ("target_type", EraseTargetType),
            ("match_policy", MatchPolicy),
            ("fill_policy", FillPolicy),
        ):
            try:
                object.__setattr__(self, name, enum_type(getattr(self, name)))
            except ValueError as exc:
                raise ValueError(f"unsupported {name}") from exc
        if not self.query.strip():
            raise ValueError("erase query must not be empty")
        if self.normalized_tag is not None and not self.normalized_tag.strip():
            raise ValueError("normalized tag must not be empty")
        if self.provider_query is not None and not self.provider_query.strip():
            raise ValueError("provider query must not be empty")
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("confidence threshold must be between 0 and 1")
        if self.fill_policy is FillPolicy.CUSTOM and not (self.fill_instruction or "").strip():
            raise ValueError("custom fill policy requires a fill instruction")
        if self.match_policy is MatchPolicy.INSIDE_RANGE and self.range_constraint is None:
            raise ValueError("inside-range match policy requires a range constraint")
        if len(set(self.preserve_rules)) != len(self.preserve_rules):
            raise ValueError("preserve rules must be unique")


# {
# 責務: [RegionCandidate: providerが検出した対象領域候補を表現する]
# フィールド: [mask,confidence,provider,match_id,evidence]
# }
@dataclass(frozen=True)
class RegionCandidate:
    mask: RLEMask
    confidence: float
    provider: str
    match_id: str = ""
    evidence: tuple[str, ...] = ()

    # {
    # 責務: [__post_init__: RegionCandidateのconfidenceと由来を検証する]
    # 処理: [1: confidence範囲を検証する, 2: provider名を確認する]
    # 引数: [self: 検証対象]
    # 戻り値: []
    # エラー: [ValueError: scoreまたはproviderが不正の場合]
    # }
    def __post_init__(self) -> None:
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("region confidence must be finite and between 0 and 1")
        if not self.provider.strip():
            raise ValueError("region provider name must not be empty")
        if not self.match_id:
            material = f"{self.provider}:{self.mask.width}x{self.mask.height}:{self.mask.runs}"
            object.__setattr__(
                self,
                "match_id",
                hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
            )


# {
# 責務: [EraseRequest: 入力画像と処理budgetを束ねる]
# フィールド: [image_path,target,quality_profile,mode,candidate_limit,history_root]
# }
@dataclass(frozen=True)
class EraseRequest:
    image_path: str
    target: SemanticEraseTarget
    quality_profile: QualityProfile = QualityProfile.STANDARD
    mode: EraseMode = EraseMode.REVIEW_UNCERTAIN
    candidate_limit: int = 4
    history_root: str | None = None
    allow_overwrite: bool = False

    # {
    # 責務: [__post_init__: EraseRequestのcandidate budgetを検証する]
    # 処理: [1: pathを確認する, 2: budgetの境界を検証する]
    # 引数: [self: 検証対象]
    # 戻り値: []
    # エラー: [ValueError: pathまたはbudgetが不正の場合]
    # }
    def __post_init__(self) -> None:
        if not str(self.image_path).strip():
            raise ValueError("image path must not be empty")
        object.__setattr__(self, "image_path", str(self.image_path))
        if self.history_root is not None:
            object.__setattr__(self, "history_root", str(self.history_root))
        object.__setattr__(self, "quality_profile", QualityProfile(self.quality_profile))
        object.__setattr__(self, "mode", EraseMode(self.mode))
        if not 1 <= self.candidate_limit <= 32:
            raise ValueError("candidate limit must be between 1 and 32")
        if self.allow_overwrite:
            raise ValueError("semantic erase never overwrites the original image")


# {
# 責務: [EraseEvaluation: 削除・保存・境界の評価値を保持する]
# フィールド: [residual_score,preservation_score,boundary_score,accepted,reasons]
# }
@dataclass(frozen=True)
class EraseEvaluation:
    residual_score: float | None
    preservation_score: float
    boundary_score: float
    accepted: bool
    reasons: tuple[str, ...] = ()


# {
# 責務: [EraseResult: non-destructive eraseの成果物と候補評価を返す]
# フィールド: [operation_id,source,output,mask,candidates,evaluation,review_required]
# }
@dataclass(frozen=True)
class EraseResult:
    operation_id: str
    source_path: str
    output_path: str | None
    selected_mask: RLEMask | None
    candidate_evaluations: tuple[EraseEvaluation, ...]
    review_required: bool
    residual_checked: bool
    backend_id: str = "unknown"
    backend_warnings: tuple[str, ...] = ()


# {
# 責務: [batch_status: batch画像の処理状態を表現する]
# フィールド: [enum値: done, review, failed]
# }
class BatchStatus(str, Enum):
    DONE = "done"
    REVIEW = "review"
    FAILED = "failed"


# {
# 責務: [EraseBatchItem: batch内の一画像の結果を保持する]
# フィールド: [source_path,status,output_path,message]
# }
@dataclass(frozen=True)
class EraseBatchItem:
    source_path: str
    status: BatchStatus
    output_path: str | None = None
    message: str | None = None
