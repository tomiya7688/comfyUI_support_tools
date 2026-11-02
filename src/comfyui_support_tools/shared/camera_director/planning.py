"""Deterministic framing planner and optional WAV section analysis."""

from __future__ import annotations

import math
import wave
from pathlib import Path

from .contracts import (
    CameraBackend,
    CameraCollisionChecker,
    CameraFinding,
    CameraKey,
    CameraStyle,
    DanceMotion,
    MotionKey,
    MusicSection,
    StageBounds,
)

MAX_AUDIO_BYTES = 512 * 1024 * 1024
MAX_CAMERA_KEYS = 5_000
STYLE_DISTANCE = {
    CameraStyle.IDOL: 9.0,
    CameraStyle.CINEMATIC: 12.0,
    CameraStyle.ENERGETIC: 8.0,
    CameraStyle.CUTE: 7.5,
    CameraStyle.CALM: 13.0,
    CameraStyle.DRAMATIC: 10.0,
    CameraStyle.STAGE_FIXED: 18.0,
    CameraStyle.CLOSE_UP_HEAVY: 6.5,
    CameraStyle.WIDE_SHOT_HEAVY: 22.0,
}
ROOT_BONE_NAMES = {"センター", "グルーブ", "全ての親", "center", "groove", "root"}


# {
# 責務: [WavSectionError: WAV music解析エラーを表す]
# フィールド: [ValueError]
# 処理: [対応外formatや破損audioを通知する]
# }
class WavSectionError(ValueError):
    pass


# {
# 責務: [HeuristicCameraBackend: backendなしでもcamera planを生成する]
# フィールド: [none]
# 処理: [root motionとsection境界からdeterministic keyframeを作る]
# }
class HeuristicCameraBackend:
    # {
    # 責務: [generate: motion saliencyに応じたcamera keyを生成する]
    # 処理: [root trajectoryをsampleしstyle距離とsection intensityを反映する]
    # 引数: [motion, style, sections, bounds, seed: camera planning inputs]
    # 戻り値: [tuple[CameraKey, ...]: planned camera keys]
    # }
    def generate(
        self,
        motion: DanceMotion,
        style: CameraStyle,
        sections: tuple[MusicSection, ...],
        bounds: StageBounds,
        seed: int,
    ) -> tuple[CameraKey, ...]:
        if (
            not math.isfinite(bounds.subject_radius)
            or bounds.subject_radius < 0
            or any(low >= high for low, high in zip(bounds.minimum, bounds.maximum, strict=True))
        ):
            raise ValueError("stage bounds must have increasing finite dimensions")
        if any(not math.isfinite(value) for value in (*bounds.minimum, *bounds.maximum)):
            raise ValueError("stage bounds must be finite")
        _validate_motion_and_sections(motion, sections)
        frames = {0, max(motion.duration_frames, 0)}
        sample_stride = max(
            1,
            motion.fps,
            math.ceil(motion.duration_frames / max(1, MAX_CAMERA_KEYS - 2)),
        )
        frames.update(range(0, motion.duration_frames + 1, sample_stride))
        frames.update(
            section.start_frame
            for section in sections
            if 0 <= section.start_frame <= motion.duration_frames
        )
        frames.update(
            section.end_frame
            for section in sections
            if 0 <= section.end_frame <= motion.duration_frames
        )
        ordered_frames = sorted(frames)
        if len(ordered_frames) > MAX_CAMERA_KEYS:
            raise ValueError(f"camera planning exceeds {MAX_CAMERA_KEYS} keyframes")
        root_keys = sorted(
            (
                key
                for key in motion.keys
                if key.bone.casefold() in {name.casefold() for name in ROOT_BONE_NAMES}
            ),
            key=lambda key: key.frame,
        )
        if not root_keys:
            root_keys = [
                key for key in motion.keys if key.bone in {item.bone for item in motion.keys[:1]}
            ]
        keys = []
        base_distance = STYLE_DISTANCE[style] + bounds.subject_radius * 2.0
        for frame in ordered_frames:
            center = _sample_root(root_keys, frame)
            section = next(
                (item for item in sections if item.start_frame <= frame <= item.end_frame), None
            )
            intensity = min(1.0, max(0.0, section.intensity)) if section else 0.0
            distance = base_distance * (1.0 - min(0.25, intensity * 0.2))
            if style is CameraStyle.WIDE_SHOT_HEAVY:
                distance = max(base_distance, 20.0 + bounds.subject_radius * 2.0)
            elif style is CameraStyle.CLOSE_UP_HEAVY:
                distance = min(distance, 7.0 + bounds.subject_radius)
            if style in (CameraStyle.CINEMATIC, CameraStyle.DRAMATIC, CameraStyle.ENERGETIC):
                phase = (seed % 10_000) / 10_000 * math.tau + frame / motion.fps * math.pi / 4
                distance *= 1.0 + 0.02 * math.sin(phase)
            # VMD camera looks from the negative Z side toward its target.
            position = (center[0], center[1] + bounds.subject_radius * 0.35, center[2])
            yaw = 0.0
            if style in (CameraStyle.CINEMATIC, CameraStyle.DRAMATIC):
                phase = (seed % 10_000) / 10_000 * math.tau + frame / motion.fps * math.pi / 4
                yaw = 0.04 * math.sin(phase)
            keys.append(CameraKey(frame, distance, position, (0.0, yaw, 0.0), 30, True))
        return tuple(keys)


# {
# 責務: [_sample_root: root bone translationをframe位置で補間する]
# 処理: [key間をlinear interpolateし範囲外をclampする]
# 引数: [keys, frame: root keys and sample frame]
# 戻り値: [tuple[float, float, float]: sampled position]
# }
def _sample_root(keys, frame: int) -> tuple[float, float, float]:
    if not keys:
        return (0.0, 10.0, 0.0)
    if frame <= keys[0].frame:
        return keys[0].position
    if frame >= keys[-1].frame:
        return keys[-1].position
    for left, right in zip(keys, keys[1:], strict=False):
        if left.frame <= frame <= right.frame:
            ratio = (frame - left.frame) / max(right.frame - left.frame, 1)
            return tuple(
                start + (end - start) * ratio
                for start, end in zip(left.position, right.position, strict=True)
            )
    return keys[-1].position


# {
# 責務: [validate_camera_keys: planned keyをframe/bounds制約で検証・clampする]
# 処理: [1: keyを検査, 2: targetをboundsへclampしてfindingを返す]
# 引数: [keys, bounds, duration_frames: plan limits]
# 戻り値: [tuple[tuple[CameraKey, ...], tuple[CameraFinding, ...]]: checked keys and findings]
# }
def validate_camera_keys(
    keys: tuple[CameraKey, ...], bounds: StageBounds, duration_frames: int
) -> tuple[tuple[CameraKey, ...], tuple[CameraFinding, ...]]:
    if (
        not math.isfinite(bounds.subject_radius)
        or bounds.subject_radius < 0
        or any(not math.isfinite(value) for value in (*bounds.minimum, *bounds.maximum))
        or any(low >= high for low, high in zip(bounds.minimum, bounds.maximum, strict=True))
    ):
        raise ValueError("stage bounds must be finite and have increasing dimensions")
    checked = []
    findings = []
    seen_frames = set()
    if len(keys) > MAX_CAMERA_KEYS:
        raise ValueError(f"camera backend returned more than {MAX_CAMERA_KEYS} keyframes")
    for key in sorted(keys, key=lambda item: item.frame):
        if key.frame in seen_frames or not 0 <= key.frame <= max(duration_frames, 0):
            raise ValueError(f"camera frame is duplicated or out of motion range: {key.frame}")
        if (
            not math.isfinite(key.distance)
            or any(not math.isfinite(value) for value in (*key.position, *key.rotation))
            or key.distance < 0
            or not 1 <= key.field_of_view <= 180
        ):
            raise ValueError(f"camera key contains invalid camera values at frame {key.frame}")
        seen_frames.add(key.frame)
        position = tuple(
            min(high, max(low, value))
            for value, low, high in zip(key.position, bounds.minimum, bounds.maximum, strict=True)
        )
        if position != key.position:
            findings.append(
                CameraFinding(
                    key.frame,
                    "visibility.target_clamped",
                    "warning",
                    "Camera target was clamped to stage bounds",
                )
            )
            key = CameraKey(
                key.frame, key.distance, position, key.rotation, key.field_of_view, key.perspective
            )
        if key.distance < bounds.subject_radius * 2.0:
            findings.append(
                CameraFinding(
                    key.frame,
                    "visibility.subject_clip_risk",
                    "warning",
                    "Camera distance may clip the subject bounds",
                )
            )
        checked.append(key)
    if not checked:
        raise ValueError("camera backend returned no keys")
    return tuple(checked), tuple(findings)


# {
# 責務: [analyze_wav_sections: PCM WAVを粗いenergy sectionsへ分割する]
# 処理: [1: wav metadataを検査, 2: chunk RMSを求め区間ごとのintensityを返す]
# 引数: [path: WAV path, fps: source motion fps, window_seconds: section window]
# 戻り値: [tuple[MusicSection, ...]: detected music sections]
# }
def analyze_wav_sections(
    path: str | Path, fps: int = 30, window_seconds: float = 4.0
) -> tuple[MusicSection, ...]:
    source = Path(path)
    if (
        source.stat().st_size > MAX_AUDIO_BYTES
        or not isinstance(fps, int)
        or isinstance(fps, bool)
        or fps <= 0
        or not math.isfinite(window_seconds)
        or window_seconds <= 0
    ):
        raise WavSectionError("invalid WAV size, fps, or section duration")
    try:
        with wave.open(str(source), "rb") as audio:
            channels, width, rate, frame_count, compression = audio.getparams()[:5]
            if (
                compression != "NONE"
                or width not in (1, 2, 3, 4)
                or channels not in (1, 2)
                or rate <= 0
                or frame_count < 0
            ):
                raise WavSectionError("only uncompressed mono/stereo PCM WAV is supported")
            samples_per_window = max(1, round(rate * window_seconds))
            sections = []
            frame_cursor = 0
            while frame_cursor < frame_count:
                sample_count = min(samples_per_window, frame_count - frame_cursor)
                raw = audio.readframes(sample_count)
                amplitude = _pcm_rms(raw, width)
                start = round(frame_cursor / rate * fps)
                end = round((frame_cursor + sample_count) / rate * fps)
                sections.append(
                    MusicSection(start, max(start, end), amplitude, f"audio-{len(sections) + 1}")
                )
                frame_cursor += sample_count
    except (wave.Error, EOFError, OSError) as error:
        raise WavSectionError(f"cannot analyze WAV: {error}") from error
    peak = max((section.intensity for section in sections), default=0.0)
    if peak <= 0:
        return tuple(
            MusicSection(item.start_frame, item.end_frame, 0.0, item.label) for item in sections
        )
    return tuple(
        MusicSection(item.start_frame, item.end_frame, item.intensity / peak, item.label)
        for item in sections
    )


# {
# 責務: [_pcm_rms: PCM blockのRMS energyをnormalizeする]
# 処理: [sample幅に応じsigned sampleを読み平均二乗根を返す]
# 引数: [raw: PCM bytes, width: bytes per sample]
# 戻り値: [float: normalized RMS]
# }
def _pcm_rms(raw: bytes, width: int) -> float:
    samples = []
    for offset in range(0, len(raw), width):
        chunk = raw[offset : offset + width]
        if len(chunk) != width:
            continue
        if width == 1:
            value = chunk[0] - 128
            scale = 128.0
        else:
            value = int.from_bytes(chunk, "little", signed=True)
            scale = float(1 << (width * 8 - 1))
        samples.append((value / scale) ** 2)
    return math.sqrt(sum(samples) / len(samples)) if samples else 0.0


# {
# 責務: [plan_camera: backend camera keysをvalidateしcollision checkerへ渡す]
# 処理: [1: backend選択, 2: frame/bounds検証, 3: optional collision finding収集]
# 引数: [motion, style, bounds, sections, seed, backend, collision_checker: planning inputs]
# 戻り値: [tuple[tuple[CameraKey, ...], tuple[CameraFinding, ...]]: keys/findings]
# }
def plan_camera(
    motion: DanceMotion,
    style: CameraStyle,
    bounds: StageBounds,
    sections: tuple[MusicSection, ...] = (),
    seed: int = 0,
    backend: CameraBackend | None = None,
    collision_checker: CameraCollisionChecker | None = None,
) -> tuple[tuple[CameraKey, ...], tuple[CameraFinding, ...]]:
    _validate_motion_and_sections(motion, sections)
    selected_backend = backend or HeuristicCameraBackend()
    proposed = selected_backend.generate(motion, style, sections, bounds, seed)
    keys, findings = validate_camera_keys(proposed, bounds, motion.duration_frames)
    findings = (*findings, *_motion_quality_findings(keys, motion.fps))
    if collision_checker is not None:
        findings = (
            *findings,
            *(item for key in keys for item in collision_checker.check(key, bounds)),
        )
    return keys, tuple(findings)


# {
# 責務: [reroll_camera_section: 指定frame区間のcamera keyだけ再生成する]
# 処理: [motion/sectionsを局所化して旧planの区間を置き換える]
# 引数: [motion, style, bounds, previous, start_frame, end_frame, seed, sections, backend: reroll inputs]
# 戻り値: [tuple[CameraKey, ...]: merged camera keys]
# }
def reroll_camera_section(
    motion: DanceMotion,
    style: CameraStyle,
    bounds: StageBounds,
    previous: tuple[CameraKey, ...],
    start_frame: int,
    end_frame: int,
    seed: int,
    sections: tuple[MusicSection, ...] = (),
    backend: CameraBackend | None = None,
) -> tuple[CameraKey, ...]:
    if not 0 <= start_frame < end_frame <= motion.duration_frames:
        raise ValueError("reroll section must be a non-empty range inside the motion")
    sliced_keys = tuple(
        MotionKey(key.bone, key.frame - start_frame, key.position)
        for key in motion.keys
        if start_frame <= key.frame <= end_frame
    )
    local_motion = DanceMotion(motion.source, sliced_keys, end_frame - start_frame, motion.fps)
    local_sections = tuple(
        MusicSection(
            max(0, section.start_frame - start_frame),
            min(end_frame - start_frame, section.end_frame - start_frame),
            section.intensity,
            section.label,
        )
        for section in sections
        if section.end_frame >= start_frame and section.start_frame <= end_frame
    )
    regenerated, _findings = plan_camera(
        local_motion, style, bounds, local_sections, seed, backend=backend
    )
    replacement = tuple(
        CameraKey(
            key.frame + start_frame,
            key.distance,
            key.position,
            key.rotation,
            key.field_of_view,
            key.perspective,
        )
        for key in regenerated
        if key.frame + start_frame <= end_frame
    )
    merged = [key for key in previous if key.frame < start_frame or key.frame > end_frame]
    merged.extend(replacement)
    return tuple(sorted(merged, key=lambda item: item.frame))


# {
# 責務: [_validate_motion_and_sections: planning input dataをsanity checkする]
# 処理: [duration, frame, coordinates, section range/intensityの不正値を拒否する]
# 引数: [motion, sections: camera planning inputs]
# 戻り値: [None: 入力が不正な場合はValueError]
# }
def _validate_motion_and_sections(motion: DanceMotion, sections: tuple[MusicSection, ...]) -> None:
    if motion.duration_frames < 0 or motion.fps <= 0:
        raise ValueError("motion duration must be non-negative and fps must be positive")
    for key in motion.keys:
        if (
            key.frame < 0
            or key.frame > motion.duration_frames
            or any(not math.isfinite(value) for value in key.position)
        ):
            raise ValueError(f"invalid motion key for {key.bone!r} at frame {key.frame}")
    for section in sections:
        if (
            section.start_frame < 0
            or section.end_frame < section.start_frame
            or not math.isfinite(section.intensity)
            or not 0.0 <= section.intensity <= 1.0
        ):
            raise ValueError(f"invalid music section {section.label!r}")


# {
# 責務: [_motion_quality_findings: camera trackのjerk/shake riskを検出する]
# 処理: [隣接keyのframe-normalized translation/rotation speedをしきい値比較する]
# 引数: [keys, fps: camera track and source frame rate]
# 戻り値: [tuple[CameraFinding, ...]: quality findings]
# }
def _motion_quality_findings(keys: tuple[CameraKey, ...], fps: int) -> tuple[CameraFinding, ...]:
    findings = []
    for before, after in zip(keys, keys[1:], strict=False):
        frame_delta = max(1, after.frame - before.frame)
        translation_delta = math.sqrt(
            sum(
                (right - left) ** 2
                for left, right in zip(before.position, after.position, strict=True)
            )
        )
        rotation_delta = math.sqrt(
            sum(
                (right - left) ** 2
                for left, right in zip(before.rotation, after.rotation, strict=True)
            )
        )
        if translation_delta / frame_delta * fps > 12.0:
            findings.append(
                CameraFinding(
                    after.frame,
                    "quality.sudden_jerk",
                    "warning",
                    "Camera target moves faster than the conservative motion limit",
                )
            )
        if rotation_delta / frame_delta * fps > 1.5:
            findings.append(
                CameraFinding(
                    after.frame,
                    "quality.excessive_shake",
                    "warning",
                    "Camera rotation changes too quickly between adjacent keys",
                )
            )
    return tuple(findings)
