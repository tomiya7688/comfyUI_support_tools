"""Audio-to-facial-morph generation, evaluation, merge, and safe export."""

from __future__ import annotations

import json
import math
import os
import random
import tempfile
from dataclasses import asdict
from pathlib import Path

from .contracts import (
    AudioFaceReport,
    FaceEvaluation,
    FaceFinding,
    MorphCalibration,
    MorphKey,
    PhonemeEvent,
    SpeechAnalysis,
    SpeechAnalyzer,
)
from .phonemes import MORA_VOWELS, read_wav_duration, transcript_to_events
from .preview import render_face_preview
from .vmd import merge_vmd_documents, read_vmd, read_vmd_bytes, write_facial_vmd

VOWEL_MORPHS = {"a": "あ", "i": "い", "u": "う", "e": "え", "o": "お"}
BLINK_NAMES = ("まばたき", "瞬き", "blink")
EMOTION_MORPHS = {
    "happy": ("笑い", 0.45),
    "sad": ("困る", 0.35),
    "angry": ("怒り", 0.4),
    "surprised": ("びっくり", 0.45),
}


# {
# 責務: [AudioFaceService: speech分析からfacial VMD/report/previewを作る]
# フィールド: [analyzer: optional speech/phoneme backend]
# 処理: [timeline, morph curves, evaluation and artifactsをorchestrateする]
# }
class AudioFaceService:
    # {
    # 責務: [__init__: optional analyzerをserviceへ登録する]
    # 処理: [speech backendを保持しrequestで利用する]
    # 引数: [analyzer: speech/phoneme backend]
    # 戻り値: [None: なし]
    # }
    def __init__(self, analyzer: SpeechAnalyzer | None = None) -> None:
        self.analyzer = analyzer

    # {
    # 責務: [run: speech timelineをfacial morph VMDへ変換する]
    # 処理: [1: transcript/audioを分析, 2: calibrated curves/VMD/reportを保存]
    # 引数: [audio_path, output_path, transcript, language, emotion, body_vmd, calibration, seed, merge_mode: generation request]
    # 戻り値: [AudioFaceReport: generated artifacts and validation findings]
    # }
    def run(
        self,
        audio_path: str | Path,
        output_path: str | Path,
        *,
        transcript: str | None = None,
        language: str = "ja",
        emotion: str | None = None,
        body_vmd: str | Path | None = None,
        calibration: MorphCalibration | None = None,
        seed: int = 0,
        merge_mode: str = "max",
    ) -> AudioFaceReport:
        source = Path(audio_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"audio file does not exist: {source}")
        calibration = calibration or MorphCalibration()
        analysis, duration = self._analyze(source, transcript, language)
        selected_emotion = emotion or analysis.emotion
        events = _validate_events(analysis.events, duration)
        findings: list[FaceFinding] = []
        morphs = _generate_morph_keys(
            events, duration, calibration, selected_emotion, seed, findings
        )
        if not morphs:
            raise ValueError(
                "no supported vowel or facial morphs were found in the speech timeline"
            )
        evaluation = _evaluate(events, morphs, duration)
        facial_bytes = write_facial_vmd(morphs)
        facial_document = read_vmd_bytes(facial_bytes)
        destination = Path(output_path).expanduser().resolve()
        if destination.suffix.casefold() != ".vmd":
            raise ValueError("facial VMD output path must end in .vmd")
        report_path = destination.with_suffix(".face.json")
        preview_path = destination.with_suffix(".preview.gif")
        output_bytes: dict[Path, bytes] = {
            destination: facial_bytes,
            report_path: _report_json(source, analysis, events, morphs, findings, evaluation),
            preview_path: render_face_preview(morphs, round(duration * 30)),
        }
        merged_path = None
        if body_vmd is not None:
            body = read_vmd(body_vmd)
            merged_path = destination.with_name(f"{destination.stem}.merged.vmd")
            output_bytes[merged_path] = merge_vmd_documents(body, facial_document, merge_mode)
        _atomic_write_new_many(output_bytes)
        return AudioFaceReport(
            source,
            events,
            morphs,
            tuple(findings),
            evaluation,
            destination,
            merged_path,
            report_path,
            preview_path,
        )

    # {
    # 責務: [_analyze: audio-to-face処理を実行する]
    # 処理: [入力を検証し、再現可能なfacial motion結果を返す]
    # 引数: [audio_path, transcript, language: 処理入力]
    # 戻り値: [tuple[SpeechAnalysis, float]: 処理結果]
    # }
    def _analyze(
        self, audio_path: Path, transcript: str | None, language: str
    ) -> tuple[SpeechAnalysis, float]:
        if self.analyzer is not None:
            result = self.analyzer.analyze(audio_path, transcript, language)
            duration = result.duration_seconds or max(
                (event.end_seconds for event in result.events), default=0.0
            )
            if duration <= 0 and audio_path.suffix.casefold() == ".wav":
                duration = read_wav_duration(audio_path)
            return result, duration
        if not transcript or not transcript.strip():
            raise ValueError(
                "provide a transcript or configure a SpeechAnalyzer for audio transcription"
            )
        if audio_path.suffix.casefold() != ".wav":
            raise ValueError(
                "transcript-only timing currently requires PCM WAV; use a SpeechAnalyzer for MP3"
            )
        duration = read_wav_duration(audio_path)
        events = transcript_to_events(transcript, duration)
        return SpeechAnalysis(events, "neutral", language, "transcript-uniform-estimate"), duration


# {
# 責務: [_validate_events: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [events, duration: 処理入力]
# 戻り値: [tuple[PhonemeEvent, ...]: 処理結果]
# }
def _validate_events(events: tuple[PhonemeEvent, ...], duration: float) -> tuple[PhonemeEvent, ...]:
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("audio duration must be a positive finite number")
    ordered = tuple(sorted(events, key=lambda event: event.start_seconds))
    for event in ordered:
        if (
            not event.symbol
            or not math.isfinite(event.start_seconds)
            or not math.isfinite(event.end_seconds)
            or not math.isfinite(event.confidence)
            or event.start_seconds < 0
            or event.end_seconds < event.start_seconds
            or event.end_seconds > duration + 0.05
            or not 0 <= event.confidence <= 1
        ):
            raise ValueError(f"invalid phoneme event: {event}")
    return ordered


# {
# 責務: [_generate_morph_keys: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [events, duration, calibration, emotion, seed, findings: 処理入力]
# 戻り値: [tuple[MorphKey, ...]: 処理結果]
# }
def _generate_morph_keys(
    events: tuple[PhonemeEvent, ...],
    duration: float,
    calibration: MorphCalibration,
    emotion: str,
    seed: int,
    findings: list[FaceFinding],
) -> tuple[MorphKey, ...]:
    available = {name.casefold(): name for name in calibration.available_morphs}
    scales = {name.casefold(): value for name, value in calibration.scales}
    offsets = {name.casefold(): value for name, value in calibration.offsets}
    _validate_calibration(calibration)
    curves: dict[str, dict[int, float]] = {}
    mapped_count = 0
    vowel_count = 0
    for event in events:
        vowel = _event_vowel(event.symbol)
        if vowel is None:
            continue
        vowel_count += 1
        target = _resolve_morph(VOWEL_MORPHS[vowel], available)
        if target is None:
            findings.append(
                FaceFinding(
                    "morph.missing_vowel",
                    "warning",
                    f"PMX calibration has no morph for vowel {vowel!r}",
                )
            )
            continue
        mapped_count += 1
        start = max(0, round(event.start_seconds * 30))
        end = max(start + 2, round(event.end_seconds * 30))
        peak = min(end, start + max(1, round((end - start) * 0.35)))
        _set_curve(curves, target, start, _calibrate(target, 0.0, scales, offsets))
        peak_value = 0.78 * (0.5 + 0.5 * event.confidence)
        _set_curve(curves, target, peak, _calibrate(target, peak_value, scales, offsets))
        plateau_end = max(peak, end - 1)
        _set_curve(curves, target, plateau_end, _calibrate(target, 0.62, scales, offsets))
        _set_curve(curves, target, end, _calibrate(target, 0.0, scales, offsets))
    if vowel_count and mapped_count < vowel_count:
        findings.append(
            FaceFinding(
                "calibration.incomplete",
                "warning",
                f"Only {mapped_count} of {vowel_count} vowel events map to available PMX morphs",
            )
        )
    _add_emotion_curve(curves, emotion, duration, available, scales, offsets, findings)
    _add_blinks(curves, duration, available, scales, offsets, seed)
    return tuple(
        MorphKey(name, frame, weight)
        for name, values in sorted(curves.items())
        for frame, weight in sorted(values.items())
    )


# {
# 責務: [_event_vowel: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [symbol: 処理入力]
# 戻り値: [str | None: 処理結果]
# }
def _event_vowel(symbol: str) -> str | None:
    normalized = symbol.casefold().replace(":", "").strip()
    for character in reversed(normalized):
        if character in MORA_VOWELS:
            return MORA_VOWELS[character]
        if character in "aeiou":
            return character
    return None


# {
# 責務: [_resolve_morph: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [target, available: 処理入力]
# 戻り値: [str | None: 処理結果]
# }
def _resolve_morph(target: str, available: dict[str, str]) -> str | None:
    if not available:
        return target
    aliases = {
        "あ": ("あ", "口あ", "a"),
        "い": ("い", "口い", "i"),
        "う": ("う", "口う", "u"),
        "え": ("え", "口え", "e"),
        "お": ("お", "口お", "o"),
    }
    return next(
        (
            available[name.casefold()]
            for name in aliases.get(target, (target,))
            if name.casefold() in available
        ),
        None,
    )


# {
# 責務: [_calibrate: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [name, value, scales, offsets: 処理入力]
# 戻り値: [float: 処理結果]
# }
def _calibrate(
    name: str, value: float, scales: dict[str, float], offsets: dict[str, float]
) -> float:
    return min(
        1.0, max(0.0, value * scales.get(name.casefold(), 1.0) + offsets.get(name.casefold(), 0.0))
    )


# {
# 責務: [_set_curve: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [curves, name, frame, weight: 処理入力]
# 戻り値: [None: 処理結果]
# }
def _set_curve(curves: dict[str, dict[int, float]], name: str, frame: int, weight: float) -> None:
    existing = curves.setdefault(name, {}).get(frame, 0.0)
    curves[name][frame] = max(existing, weight)


# {
# 責務: [_add_emotion_curve: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [curves, emotion, duration, available, scales, offsets, findings: 処理入力]
# 戻り値: [None: 処理結果]
# }
def _add_emotion_curve(curves, emotion, duration, available, scales, offsets, findings) -> None:
    normalized = emotion.casefold().strip()
    if normalized in {"", "neutral", "none"}:
        return
    mapping = EMOTION_MORPHS.get(normalized)
    if mapping is None:
        findings.append(
            FaceFinding("emotion.unsupported", "info", f"Unsupported emotion: {emotion}")
        )
        return
    target = _resolve_morph(mapping[0], available)
    if target is None:
        findings.append(
            FaceFinding(
                "morph.missing_emotion", "warning", f"No PMX morph is available for {normalized}"
            )
        )
        return
    _set_curve(curves, target, 0, _calibrate(target, mapping[1], scales, offsets))
    _set_curve(curves, target, max(1, round(duration * 30)), 0.0)


# {
# 責務: [_add_blinks: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [curves, duration, available, scales, offsets, seed: 処理入力]
# 戻り値: [None: 処理結果]
# }
def _add_blinks(curves, duration, available, scales, offsets, seed) -> None:
    target = next(
        (
            available.get(name.casefold(), name)
            for name in BLINK_NAMES
            if not available or name.casefold() in available
        ),
        None,
    )
    if target is None:
        return
    generator = random.Random(seed)
    frame_limit = max(1, round(duration * 30))
    cursor = generator.randint(45, 90)
    while cursor < frame_limit:
        _set_curve(curves, target, cursor, _calibrate(target, 0.0, scales, offsets))
        _set_curve(curves, target, cursor + 1, _calibrate(target, 1.0, scales, offsets))
        _set_curve(curves, target, cursor + 3, _calibrate(target, 0.0, scales, offsets))
        cursor += generator.randint(90, 150)


# {
# 責務: [_validate_calibration: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [calibration: 処理入力]
# 戻り値: [None: 処理結果]
# }
def _validate_calibration(calibration: MorphCalibration) -> None:
    for items, label in ((calibration.scales, "scale"), (calibration.offsets, "offset")):
        names = [name.casefold() for name, _value in items]
        if len(names) != len(set(names)):
            raise ValueError(f"morph calibration contains duplicate {label} entries")
    if any(not math.isfinite(value) or value < 0 for _name, value in calibration.scales):
        raise ValueError("morph scales must be finite and non-negative")
    if any(not math.isfinite(value) for _name, value in calibration.offsets):
        raise ValueError("morph offsets must be finite")


# {
# 責務: [_evaluate: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [events, morphs, duration: 処理入力]
# 戻り値: [FaceEvaluation: 処理結果]
# }
def _evaluate(
    events: tuple[PhonemeEvent, ...], morphs: tuple[MorphKey, ...], duration: float
) -> FaceEvaluation:
    mouth_names = {
        alias.casefold(): vowel
        for vowel, aliases in {
            "a": ("あ", "口あ", "a"),
            "i": ("い", "口い", "i"),
            "u": ("う", "口う", "u"),
            "e": ("え", "口え", "e"),
            "o": ("お", "口お", "o"),
        }.items()
        for alias in aliases
    }
    mouth_keys = [key for key in morphs if key.name.casefold() in mouth_names]
    offsets = []
    vowel_events = 0
    for event in events:
        vowel = _event_vowel(event.symbol)
        if vowel is None:
            continue
        vowel_events += 1
        start = round(event.start_seconds * 30)
        end = round(event.end_seconds * 30)
        active = next(
            (
                key.frame
                for key in mouth_keys
                if mouth_names[key.name.casefold()] == vowel
                and start <= key.frame <= end
                and key.weight >= 0.1
            ),
            None,
        )
        if active is not None:
            offsets.append(abs(active - start) / 30 * 1000)
    mapped = len(offsets)
    over_open = sum(key.weight >= 0.98 for key in mouth_keys) / max(len(mouth_keys), 1)
    change = 0.0
    previous: dict[str, float] = {}
    for key in sorted(morphs, key=lambda item: (item.frame, item.name)):
        change += abs(key.weight - previous.get(key.name, 0.0))
        previous[key.name] = key.weight
    stability = 1.0 / (1.0 + change / max(duration, 1 / 30))
    return FaceEvaluation(
        sum(offsets) / len(offsets) if offsets else 0.0,
        mapped / max(vowel_events, 1),
        over_open,
        stability,
    )


# {
# 責務: [_report_json: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [source, analysis, events, morphs, findings, evaluation: 処理入力]
# 戻り値: [bytes: 処理結果]
# }
def _report_json(source, analysis, events, morphs, findings, evaluation) -> bytes:
    payload = {
        "source_audio": str(source),
        "analysis_provenance": analysis.provenance,
        "emotion": analysis.emotion,
        "language": analysis.language,
        "events": [asdict(event) for event in events],
        "morph_keys": [asdict(key) for key in morphs],
        "findings": [asdict(item) for item in findings],
        "evaluation": asdict(evaluation),
        "evaluation_note": "Metrics validate generated timing consistency; use a speech backend and labeled references for real lip-sync accuracy.",
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


# {
# 責務: [_atomic_write_new_many: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [outputs: 処理入力]
# 戻り値: [None: 処理結果]
# }
def _atomic_write_new_many(outputs: dict[Path, bytes]) -> None:
    temporary: dict[Path, Path] = {}
    published = []
    try:
        for destination, data in outputs.items():
            if destination.exists():
                raise FileExistsError(f"refusing to overwrite {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(
                prefix=f".{destination.name}.", dir=destination.parent
            )
            temp_path = Path(name)
            temporary[destination] = temp_path
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        for destination, temp_path in temporary.items():
            os.link(temp_path, destination)
            published.append(destination)
    except Exception:
        for destination in published:
            destination.unlink(missing_ok=True)
        raise
    finally:
        for temp_path in temporary.values():
            temp_path.unlink(missing_ok=True)
