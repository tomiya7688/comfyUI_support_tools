"""Contracts for identity-anchored pixel sprite sequences and sheets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from PIL import Image


# {
# 責務: [SpriteDirection: sprite poseの向きを標準化する]
# フィールド: [direction values]
# 処理: [4/8方向とmulti-direction layoutを表現する]
# }
class SpriteDirection(str, Enum):
    FRONT = "front"
    FRONT_RIGHT = "front_right"
    RIGHT = "right"
    BACK_RIGHT = "back_right"
    BACK = "back"
    BACK_LEFT = "back_left"
    LEFT = "left"
    FRONT_LEFT = "front_left"


# {
# 責務: [SpriteAction: animation pose sequenceの標準actionを定義する]
# フィールド: [action IDs]
# 処理: [built-in animation familyを選択可能にする]
# }
class SpriteAction(str, Enum):
    IDLE = "idle"
    WALK = "walk"
    RUN = "run"
    ATTACK = "attack"
    HURT = "hurt"
    DEATH = "death"
    JUMP = "jump"
    CAST = "cast"
    CUSTOM = "custom"


# {
# 責務: [SpriteFrameOrder: frame traversal strategyを定義する]
# フィールド: [layout order IDs]
# 処理: [direction/action groupingを固定する]
# }
class SpriteFrameOrder(str, Enum):
    DIRECTION_MAJOR = "direction_major"
    ACTION_MAJOR = "action_major"
    FRAME_MAJOR = "frame_major"


# {
# 責務: [SpriteFrameSpec: generatorへ渡す1 poseの意味情報を表す]
# フィールド: [action, direction, index, phase, pose instruction]
# 処理: [canonical anchorとframe条件を伝える]
# }
@dataclass(frozen=True)
class SpriteFrameSpec:
    action: str
    direction: SpriteDirection
    index: int
    frame_count: int
    phase: float
    pose_instruction: str = ""


# {
# 責務: [SpriteFrame: sequence内の生成imageとpose metadataを保持する]
# フィールド: [spec, image, scores, warnings]
# 処理: [frame quality/evaluation resultを一体で扱う]
# }
@dataclass(frozen=True)
class SpriteFrame:
    spec: SpriteFrameSpec
    image: Image.Image
    identity_score: float | None = None
    shape_score: float | None = None
    palette_score: float | None = None
    warnings: tuple[str, ...] = ()


# {
# 責務: [SpriteSequenceRequest: canonical referenceからsequence exportまでの入力を定義する]
# フィールド: [canonical, prompt, directions/actions, grid/layout, export options]
# 処理: [finite boundsを検証し安全なsprite sequenceを依頼する]
# }
@dataclass(frozen=True)
class SpriteSequenceRequest:
    canonical: Image.Image
    prompt: str
    directions: tuple[SpriteDirection, ...] = (
        SpriteDirection.FRONT,
        SpriteDirection.RIGHT,
        SpriteDirection.BACK,
        SpriteDirection.LEFT,
    )
    actions: tuple[str, ...] = (SpriteAction.IDLE.value,)
    frames_per_action: int = 1
    pose_instructions: tuple[tuple[str, str, int, str], ...] = ()
    cell_width: int = 64
    cell_height: int = 64
    columns: int = 0
    rows: int = 0
    margin: int = 0
    padding: int = 0
    frame_order: SpriteFrameOrder = SpriteFrameOrder.DIRECTION_MAJOR
    palette_colors: int = 32
    fps: int = 8
    export_gif: bool = True
    export_webp: bool = False
    background: tuple[int, int, int, int] = (0, 0, 0, 0)
    output_directory: str = ""

    # {
    # 責務: [__post_init__: SpriteSequenceRequestのshape・layout・frame budgetを検証する]
    # 処理: [1: direction/action/frame数を検証する, 2: layoutと出力境界を検証する]
    # 引数: [self: sequence request]
    # 戻り値: []
    # }
    def __post_init__(self) -> None:
        if self.canonical.width <= 0 or self.canonical.height <= 0:
            raise ValueError("canonical sprite must have positive dimensions")
        if self.canonical.width * self.canonical.height > 50_000_000:
            raise ValueError("canonical sprite exceeds 50 megapixel limit")
        for name, value, minimum, maximum in (
            ("frames_per_action", self.frames_per_action, 1, 32),
            ("cell_width", self.cell_width, 8, 2048),
            ("cell_height", self.cell_height, 8, 2048),
            ("palette_colors", self.palette_colors, 2, 256),
            ("fps", self.fps, 1, 60),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
        for name, value in (
            ("columns", self.columns),
            ("rows", self.rows),
            ("margin", self.margin),
            ("padding", self.padding),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if len(self.background) != 4 or any(
            isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 255
            for channel in self.background
        ):
            raise ValueError("background must contain four integer RGBA channels from 0 to 255")
        if not self.directions or len(set(self.directions)) != len(self.directions):
            raise ValueError("directions must be nonempty and unique")
        if len(self.directions) not in (1, 4, 8):
            raise ValueError("sprite sequences support 1, 4, or 8 unique directions")
        if not self.actions or len(set(self.actions)) != len(self.actions):
            raise ValueError("actions must be nonempty and unique")
        if any(not str(action).strip() for action in self.actions):
            raise ValueError("action identifiers cannot be blank")
        total = len(self.directions) * len(self.actions) * self.frames_per_action
        if total > 256:
            raise ValueError("sprite sequence is limited to 256 frames")
        if total * self.cell_width * self.cell_height > 128_000_000:
            raise ValueError("normalized sprite sequence exceeds the 128 megapixel safety limit")
        if self.columns and self.rows and self.columns * self.rows < total:
            raise ValueError("sprite sheet layout has fewer cells than frames")
        object.__setattr__(
            self, "directions", tuple(SpriteDirection(item) for item in self.directions)
        )
        object.__setattr__(
            self,
            "actions",
            tuple(
                str(item.value if isinstance(item, SpriteAction) else item) for item in self.actions
            ),
        )
        object.__setattr__(self, "frame_order", SpriteFrameOrder(self.frame_order))
        if any(re.fullmatch(r"[A-Za-z0-9_-]{1,48}", action) is None for action in self.actions):
            raise ValueError(
                "action identifiers must use 1-48 ASCII letters, digits, hyphens, or underscores"
            )


# {
# 責務: [SpriteConsistencyEvaluator: identity/shape/palette metric provider protocol]
# フィールド: [evaluate callable]
# 処理: [canonical anchorとframeの整合性を測る]
# }
class SpriteConsistencyEvaluator(Protocol):
    # {
    # 責務: [evaluate: frameのcanonical一致度を数値で返す]
    # 処理: [identity, shape, palette scoreを0..1で測定する]
    # 引数: [canonical: anchor image, frame: candidate frame, spec: frame identity]
    # 戻り値: [identity, shape, palette metric mapping]
    # }
    def evaluate(
        self, canonical: Image.Image, frame: Image.Image, spec: SpriteFrameSpec
    ) -> dict[str, float]: ...


# {
# 責務: [SpriteFrameGenerator: model/backendからpose-guided frameを作るprotocol]
# フィールド: [generate callable]
# 処理: [canonical anchorを保持しpose specificationを画像化する]
# }
class SpriteFrameGenerator(Protocol):
    # {
    # 責務: [generate: canonical/referenceを使ってframe imageを生成する]
    # 処理: [1: prompt/pose/directionを条件にする, 2: candidate imageを返す]
    # 引数: [canonical: anchor sprite, spec: pose metadata, prompt: user intent]
    # 戻り値: [Image: generated frame]
    # }
    def generate(
        self, canonical: Image.Image, spec: SpriteFrameSpec, prompt: str
    ) -> Image.Image: ...


# {
# 責務: [SpriteAnimationResult: packed asset pathsとframe evaluationを返す]
# フィールド: [output paths, layout metadata, frames, warnings]
# 処理: [export outcomeとreview statusを伝える]
# }
@dataclass(frozen=True)
class SpriteAnimationResult:
    sprite_sheet: str
    frames_directory: str
    metadata_path: str
    gif_path: str | None
    webp_path: str | None
    frame_count: int
    columns: int
    rows: int
    frames: tuple[SpriteFrame, ...]
    warnings: tuple[str, ...] = ()
