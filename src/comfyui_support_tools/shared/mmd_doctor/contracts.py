"""Typed PMX diagnostics, repair candidates, and motion-evaluation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol


# {
# 責務: [DiagnosticSeverity: model doctor findingの優先度を定義する]
# フィールド: [info, warning, error]
# 処理: [repair候補のreview順序を表す]
# }
class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# {
# 責務: [PmxDiagnostic: rig/weight/morph/physics issueの場所と根拠を表す]
# フィールド: [category, severity, target, message, evidence]
# 処理: [修正前後reportで同一findingを追跡する]
# }
@dataclass(frozen=True)
class PmxDiagnostic:
    code: str
    category: str
    severity: DiagnosticSeverity
    target: str
    message: str
    evidence: tuple[tuple[str, object], ...] = ()


# {
# 責務: [BinaryPatch: PMX byte stream上のnon-overlapping local editを表す]
# フィールド: [offset, expected, replacement, target]
# 処理: [既存PMX schemaを再serializeせず限定範囲を変更する]
# }
@dataclass(frozen=True)
class BinaryPatch:
    offset: int
    expected: bytes
    replacement: bytes
    target: str


# {
# 責務: [PmxVertex: weight encodingと局所修正offsetを保持する]
# フィールド: [vertex index, position, bone indices, weights, weight offsets]
# 処理: [skin-weight diagnosticsとnon-destructive repair候補を作る]
# }
@dataclass(frozen=True)
class PmxVertex:
    index: int
    position: tuple[float, float, float]
    weight_type: int
    bone_indices: tuple[int, ...]
    weights: tuple[float, ...]
    bone_offsets: tuple[int, ...]
    weight_offsets: tuple[int, ...]


# {
# 責務: [PmxBone: skeleton hierarchyとIKの検証値を保持する]
# フィールド: [index, names, parent, flags, IK references]
# 処理: [invalid hierarchy/duplicate/IK targetを診断する]
# }
@dataclass(frozen=True)
class PmxBone:
    index: int
    name: str
    parent_index: int
    flags: int
    parent_offset: int = -1
    ik_target: int | None = None
    ik_links: tuple[int, ...] = ()


# {
# 責務: [PmxRigidBody: physics body property offsetsを保持する]
# フィールド: [index, name, mode, numeric property offsets]
# 処理: [不安定mass/damping/friction repairを作る]
# }
@dataclass(frozen=True)
class PmxRigidBody:
    index: int
    name: str
    bone_index: int
    shape: int
    mode: int
    mass: float
    linear_damping: float
    angular_damping: float
    restitution: float
    friction: float
    value_offsets: tuple[int, int, int, int, int]


# {
# 責務: [PmxJoint: rigid-body connectivityとconstraint rangesを保持する]
# フィールド: [index, name, bodies, translation/rotation limits]
# 処理: [dangling physics linkとreversed constraintを検証する]
# }
@dataclass(frozen=True)
class PmxJoint:
    index: int
    name: str
    body_a: int
    body_b: int
    minimum_offsets: tuple[int, int, int, int, int, int]
    maximum_offsets: tuple[int, int, int, int, int, int]
    minimum: tuple[float, ...]
    maximum: tuple[float, ...]


# {
# 責務: [PmxModel: parse済PMX構造とoriginal bytesを束ねる]
# フィールド: [raw bytes, metadata, vertices/bones/morphs/materials/physics]
# 処理: [diagnostic and byte-patch serviceへ読み取り専用modelを渡す]
# }
@dataclass(frozen=True)
class PmxModel:
    source_path: Path | None
    source_bytes: bytes
    version: float
    model_name: str
    vertices: tuple[PmxVertex, ...]
    faces: tuple[tuple[int, int, int], ...]
    bones: tuple[PmxBone, ...]
    morph_count: int
    material_count: int
    rigid_bodies: tuple[PmxRigidBody, ...]
    joints: tuple[PmxJoint, ...]
    diagnostics: tuple[PmxDiagnostic, ...] = ()
    bone_index_size: int = 4


# {
# 責務: [MotionTest: standard rig validation poseを定義する]
# フィールド: [name, instruction, duration frames]
# 処理: [同じmotion suiteで修正前後を比較する]
# }
@dataclass(frozen=True)
class MotionTest:
    name: str
    instruction: str
    frames: int = 30


# {
# 責務: [MotionSuite: standard retarget motion setを束ねる]
# フィールド: [tests, fps, settling duration]
# 処理: [T/A/IK/twist/squat/kick/walk/jumpを再現可能にする]
# }
@dataclass(frozen=True)
class MotionSuite:
    tests: tuple[MotionTest, ...] = (
        MotionTest("T_pose", "neutral T pose, arms horizontal"),
        MotionTest("arm_raise", "raise both arms overhead"),
        MotionTest("elbow_bend", "bend elbow and keep wrist aligned"),
        MotionTest("wrist_twist", "rotate forearm and twist wrist"),
        MotionTest("squat", "deep squat with feet planted"),
        MotionTest("kick", "side kick with stable support leg"),
        MotionTest("walk", "walk cycle with planted contact feet", 60),
        MotionTest("jump", "jump, land, and settle", 60),
    )
    fps: int = 30


# {
# 責務: [RepairEvaluation: motion/penetration/stretch/jitter scoresを表す]
# フィールド: [aggregate, penetration, stretch, jitter, settling, notes]
# 処理: [candidate repairを定量比較する]
# }
@dataclass(frozen=True)
class RepairEvaluation:
    score: float
    penetration: float
    stretch: float
    jitter: float
    settling_time: float
    notes: tuple[str, ...] = ()


# {
# 責務: [RepairCandidate: original/heuristic/ML修正内容を表現する]
# フィールド: [strategy, patches, evaluation, diagnostics]
# 処理: [Best-of-Nで複数repairを比較する]
# }
@dataclass(frozen=True)
class RepairCandidate:
    name: str
    strategy: str
    patches: tuple[BinaryPatch, ...]
    evaluation: RepairEvaluation | None = None
    diagnostics: tuple[PmxDiagnostic, ...] = ()


# {
# 責務: [ModelDoctorReport: model audit, candidates, export resultを伝える]
# フィールド: [source, diagnostics, candidates, selected, warnings]
# 処理: [before/after previewとreview stateを提供する]
# }
@dataclass(frozen=True)
class ModelDoctorReport:
    source_path: str
    model_name: str
    pmx_version: float
    diagnostics: tuple[PmxDiagnostic, ...]
    candidates: tuple[RepairCandidate, ...]
    selected_index: int | None
    output_path: str | None
    diff_report_path: str | None
    warnings: tuple[str, ...] = ()


# {
# 責務: [PmxRepairProvider: optional ML/third-party repair candidate adapter]
# フィールド: [propose callable]
# 処理: [bad regionだけのcandidate patchを返す]
# }
class PmxRepairProvider(Protocol):
    # {
    # 責務: [propose: diagnosed PMXの局所修正候補を返す]
    # 処理: [weight repaint/bone mapping候補を提案する]
    # 引数: [model: PMX, diagnostics: model findings]
    # 戻り値: [BinaryPatch tuples: local changes]
    # }
    def propose(
        self, model: PmxModel, diagnostics: tuple[PmxDiagnostic, ...]
    ) -> tuple[tuple[str, tuple[BinaryPatch, ...]], ...]: ...


# {
# 責務: [MotionEvaluator: motion suiteをPMXへ適用してphysics/rig scoreを測定する]
# フィールド: [evaluate callable]
# 処理: [penetration/stretch/jitter/settlingを数値化する]
# }
class MotionEvaluator(Protocol):
    # {
    # 責務: [evaluate: model candidateのmotion resultを測る]
    # 処理: [motion suite全体を実行してmetricsを集約する]
    # 引数: [pmx_path: candidate PMX, suite: standard suite]
    # 戻り値: [RepairEvaluation: bounded physics/rig metrics]
    # }
    def evaluate(self, pmx_path: Path, suite: MotionSuite) -> RepairEvaluation: ...
