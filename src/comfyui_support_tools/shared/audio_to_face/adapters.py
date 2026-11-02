"""Typed adapters for external speech-to-expression research systems."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .contracts import SpeechAnalysis


# {
# 責務: [AnyTalkEngine: AnyTalk-style audio-to-face backend callable]
# フィールド: [analyze_audio callable]
# 処理: [external model runtimeをproject domain APIから分離する]
# }
class AnyTalkEngine(Protocol):
    # {
    # 責務: [analyze_audio: audioをtimed facial eventへ推定する]
    # 処理: [audio/transcript/language hintsをresearch engineへ渡す]
    # 引数: [audio_path, transcript, language: inference inputs]
    # 戻り値: [SpeechAnalysis: phoneme timing, emotion, duration, provenance]
    # }
    def analyze_audio(
        self, audio_path: Path, transcript: str | None, language: str
    ) -> SpeechAnalysis: ...


# {
# 責務: [AnyTalkAdapter: AnyTalk-compatible engineをSpeechAnalyzerへ適合する]
# フィールド: [engine]
# 処理: [AudioFaceServiceからexternal research modelを呼ぶ]
# }
class AnyTalkAdapter:
    # {
    # 責務: [__init__: engineをadapterへ登録する]
    # 処理: [injected research engineを保持する]
    # 引数: [engine: AnyTalk-compatible inference object]
    # 戻り値: [None: なし]
    # }
    def __init__(self, engine: AnyTalkEngine) -> None:
        self.engine = engine

    # {
    # 責務: [analyze: SpeechAnalyzer contractでaudioを分析する]
    # 処理: [input path/text/languageをengineへ転送する]
    # 引数: [audio_path, transcript, language: input and hints]
    # 戻り値: [SpeechAnalysis: timed facial analysis]
    # }
    def analyze(self, audio_path: Path, transcript: str | None, language: str) -> SpeechAnalysis:
        return self.engine.analyze_audio(audio_path, transcript, language)
