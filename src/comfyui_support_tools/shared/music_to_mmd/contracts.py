"""Music analysis, choreography, and dance-backend extension contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from comfyui_support_tools.shared.video_to_mmd.contracts import (
    RecoveredMotion,
    VmdBoneKey,
)


# {
# 責務: [AudioSignal: decoded mono PCM audio and sample rate]
# フィールド: [samples: normalized float amplitudes, sample_rate]
# 処理: [provide a decoder-neutral signal to deterministic music analysis]
# }
@dataclass(frozen=True)
class AudioSignal:
    samples: Sequence[float]
    sample_rate: int


# {
# 責務: [AudioSection: coarse song section and loudness interval]
# フィールド: [kind, start_seconds, end_seconds, energy, section_id]
# 処理: [align choreography and local regeneration to music structure]
# }
@dataclass(frozen=True)
class AudioSection:
    kind: str
    start_seconds: float
    end_seconds: float
    energy: float
    section_id: str


# {
# 責務: [AudioAnalysis: measured rhythm and structure for one song]
# フィールド: [duration, bpm, beats, onsets, energy, sections, provenance]
# 処理: [share music timing across planners and motion evaluators]
# }
@dataclass(frozen=True)
class AudioAnalysis:
    duration: float
    bpm: float
    beats: tuple[float, ...]
    onsets: tuple[float, ...]
    energy_curve: tuple[tuple[float, float], ...]
    sections: tuple[AudioSection, ...]
    source: Path
    analysis_method: str


# {
# 責務: [ChoreographySection: editable movement planning unit]
# フィールド: [timing, energy, facing, stage position, motif, instruction]
# 処理: [regenerate a single song segment without replacing whole dance]
# }
@dataclass(frozen=True)
class ChoreographySection:
    section_id: str
    kind: str
    start_frame: int
    end_frame: int
    intensity: float
    facing: str
    stage_position: tuple[float, float]
    motif_id: str
    instruction: str


# {
# 責務: [ChoreographyPlan: song structure converted to editable dance sections]
# フィールド: [fps, bpm, style, sections, repeated motifs, user instruction]
# 処理: [decouple high-level movement intent from 3D motion generation]
# }
@dataclass(frozen=True)
class ChoreographyPlan:
    fps: int
    bpm: float
    style: str
    sections: tuple[ChoreographySection, ...]
    repeated_motifs: tuple[tuple[str, str], ...]
    instruction: str


# {
# 責務: [DanceMotionRequest: request one generated choreography segment]
# フィールド: [analysis, plan, section, reference motion, optional template]
# 処理: [give backend local and global musical context for section generation]
# }
@dataclass(frozen=True)
class DanceMotionRequest:
    analysis: AudioAnalysis
    plan: ChoreographyPlan
    section: ChoreographySection
    reference_motion: RecoveredMotion | None = None
    motif_template: RecoveredMotion | None = None
    seed: int | None = None


# {
# 責務: [DanceGenerationBackend: adapter for AtomicDance/DanceLDM/other model]
# フィールド: [generate_section callable]
# 処理: [isolate large external dance models from MMD motion core]
# }
class DanceGenerationBackend(Protocol):
    # {
    # 責務: [generate_section: generate full-body motion for one planned section]
    # 処理: [consume beat/genre/style and optional reference/motif constraints]
    # 引数: [request: section-specific dance generation request]
    # 戻り値: [RecoveredMotion: normalized source skeleton motion]
    # }
    def generate_section(self, request: DanceMotionRequest) -> RecoveredMotion: ...


# {
# 責務: [AudioDecoderBackend: decode audio formats into normalized mono PCM]
# フィールド: [decode callable]
# 処理: [allow WAV, MP3, FLAC decoders to be replaced independently]
# }
class AudioDecoderBackend(Protocol):
    # {
    # 責務: [decode: decode an audio file to bounded mono floating-point samples]
    # 処理: [convert supported audio container to stable analysis input]
    # 引数: [path: input audio file]
    # 戻り値: [AudioSignal: mono normalized PCM signal]
    # }
    def decode(self, path: Path) -> AudioSignal: ...


# {
# 責務: [DanceEvaluation: report independent motion/music quality proxies]
# フィールド: [scores, counts, limitations]
# 処理: [evaluate rhythm, continuity, floor contact, diversity, and repeated motifs]
# }
@dataclass(frozen=True)
class DanceEvaluation:
    scores: tuple[tuple[str, float], ...]
    counts: tuple[tuple[str, int], ...]
    notes: tuple[str, ...]


# {
# 責務: [MusicToMmdResult: complete editable plan, report, and VMD keys]
# フィールド: [analysis, plan, evaluation, keys, fps, output path]
# 処理: [return one auditable body-motion conversion result]
# }
@dataclass(frozen=True)
class MusicToMmdResult:
    analysis: AudioAnalysis
    plan: ChoreographyPlan
    evaluation: DanceEvaluation
    keys: tuple[VmdBoneKey, ...]
    fps: int
    vmd_path: Path
    report_path: Path
