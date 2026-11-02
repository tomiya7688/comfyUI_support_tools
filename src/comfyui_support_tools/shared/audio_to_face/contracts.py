"""Typed inputs and speech-analysis extension points for Audio-to-MMD-Face."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


# {
# 責務: [PhonemeEvent: 音声中のphoneme/moraとtimingを表す]
# フィールド: [symbol, start_seconds, end_seconds, confidence]
# 処理: [mouth morph curveの区間を定める]
# }
@dataclass(frozen=True)
class PhonemeEvent:
    symbol: str
    start_seconds: float
    end_seconds: float
    confidence: float = 1.0


# {
# 責務: [SpeechAnalysis: speech backendのtimeline/prosody結果を表現する]
# フィールド: [events, emotion, language, provenance]
# 処理: [face motion serviceへ推定結果を渡す]
# }
@dataclass(frozen=True)
class SpeechAnalysis:
    events: tuple[PhonemeEvent, ...]
    emotion: str = "neutral"
    language: str = "ja"
    provenance: str = "external"
    duration_seconds: float | None = None


# {
# 責務: [MorphCalibration: PMXごとのmorph名と可動rangeを保持する]
# フィールド: [available names, per-morph scale and offset]
# 処理: [generatorのnormalized weightをmodel-specific値へ変換する]
# }
@dataclass(frozen=True)
class MorphCalibration:
    available_morphs: tuple[str, ...] = ()
    scales: tuple[tuple[str, float], ...] = ()
    offsets: tuple[tuple[str, float], ...] = ()


# {
# 責務: [MorphKey: VMD morph trackのkeyframeを表す]
# フィールド: [name, frame, weight]
# 処理: [face VMD出力とbody VMD mergeに利用する]
# }
@dataclass(frozen=True)
class MorphKey:
    name: str
    frame: int
    weight: float


# {
# 責務: [FaceFinding: unsupported phoneme/morph/motion riskを報告する]
# フィールド: [code, severity, message]
# 処理: [reportで生成の信頼境界を説明する]
# }
@dataclass(frozen=True)
class FaceFinding:
    code: str
    severity: str
    message: str


# {
# 責務: [FaceEvaluation: lip/expression timing quality metricsを保持する]
# フィールド: [offset, mapping accuracy, over-open, stability]
# 処理: [source-compatible validation reportを提供する]
# }
@dataclass(frozen=True)
class FaceEvaluation:
    mean_lip_sync_offset_ms: float
    vowel_mapping_accuracy: float
    over_open_rate: float
    expression_stability: float


# {
# 責務: [AudioFaceReport: audio inputから作ったfacial VMD結果を束ねる]
# フィールド: [events, morph keys, findings, output paths, evaluation]
# 処理: [VMDとmachine-readable reportを利用元へ返す]
# }
@dataclass(frozen=True)
class AudioFaceReport:
    source_audio: Path
    events: tuple[PhonemeEvent, ...]
    morph_keys: tuple[MorphKey, ...]
    findings: tuple[FaceFinding, ...]
    evaluation: FaceEvaluation
    facial_vmd_path: Path
    merged_vmd_path: Path | None
    report_path: Path
    preview_path: Path


# {
# 責務: [SpeechAnalyzer: ASR/phoneme research backend拡張境界]
# フィールド: [analyze callable]
# 処理: [Whisper/AnyTalk等のmodelをapplicationから分離する]
# }
class SpeechAnalyzer(Protocol):
    # {
    # 責務: [analyze: audioからtimed phonemeとemotionを推定する]
    # 処理: [transcript/language hintを併用しspeech eventsを返す]
    # 引数: [audio_path, transcript, language: input and optional hints]
    # 戻り値: [SpeechAnalysis: timed phoneme events]
    # }
    def analyze(
        self, audio_path: Path, transcript: str | None, language: str
    ) -> SpeechAnalysis: ...
