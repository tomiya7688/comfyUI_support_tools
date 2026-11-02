"""Pose cleanup, world-coordinate retargeting, contact correction, and key reduction."""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from .contracts import (
    MotionFinding,
    RecoveredFrame,
    RecoveredMotion,
    RetargetProfile,
    SourceBonePose,
    VmdBoneKey,
)

LOW_CONFIDENCE = 0.35
MAX_MOTION_FRAMES = 1_000_000


# {
# 責務: [process_recovered_motion: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def process_recovered_motion(
    recovered: RecoveredMotion,
    profile: RetargetProfile,
    person_id: str | None = None,
    *,
    camera_compensation: bool = True,
    foot_contact_repair: bool = True,
) -> tuple[tuple[VmdBoneKey, ...], tuple[tuple[int, str, float], ...], tuple[MotionFinding, ...]]:
    _validate_profile(profile)
    if recovered.fps <= 0 or len(recovered.frames) > MAX_MOTION_FRAMES:
        raise ValueError("recovered motion has invalid fps or too many frames")
    selected_person = person_id or _select_person(recovered.frames)
    frames = sorted(
        (frame for frame in recovered.frames if frame.person_id == selected_person),
        key=lambda item: item.frame,
    )
    if not frames:
        raise ValueError(f"recovery backend produced no frames for person {selected_person!r}")
    if len({frame.frame for frame in frames}) != len(frames):
        raise ValueError("recovered motion contains duplicate frame numbers")
    for frame in frames:
        if (
            frame.frame < 0
            or not math.isfinite(frame.ground_height)
            or any(not math.isfinite(value) for value in frame.camera_translation)
        ):
            raise ValueError(f"invalid frame metadata at frame {frame.frame}")
    findings: list[MotionFinding] = []
    confidence_rows: list[tuple[int, str, float]] = []
    tracks: dict[str, list[tuple[int, SourceBonePose, RecoveredFrame]]] = defaultdict(list)
    source_rules = {rule.source_name.casefold(): rule for rule in profile.rules}
    for frame in frames:
        seen = set()
        for pose in frame.bones:
            key = pose.name.casefold()
            if key in seen:
                raise ValueError(f"duplicate source bone {pose.name!r} at frame {frame.frame}")
            seen.add(key)
            if key not in source_rules:
                continue
            if (
                pose.confidence < 0
                or pose.confidence > 1
                or not math.isfinite(pose.confidence)
                or any(not math.isfinite(value) for value in (*pose.translation, *pose.rotation))
            ):
                raise ValueError(f"invalid recovered pose for {pose.name!r} at frame {frame.frame}")
            target = source_rules[key].target_name
            tracks[target].append((frame.frame, pose, frame))
    output: list[VmdBoneKey] = []
    for rule in profile.rules:
        track = sorted(tracks.get(rule.target_name, ()), key=lambda item: item[0])
        if not track:
            findings.append(
                MotionFinding(
                    0,
                    rule.target_name,
                    "retarget.missing_bone",
                    "warning",
                    "Source motion has no mapped bone track",
                )
            )
            continue
        converted = []
        for frame_number, pose, frame in track:
            position = _convert_position(
                pose, frame, rule, recovered.camera_compensated, camera_compensation
            )
            rotation = _convert_rotation(pose.rotation, rule)
            converted.append(
                [
                    frame_number,
                    position,
                    rotation,
                    pose.confidence,
                    pose.foot_contact,
                    frame.ground_height,
                ]
            )
            confidence_rows.append((frame_number, rule.target_name, pose.confidence))
            if pose.confidence < LOW_CONFIDENCE:
                findings.append(
                    MotionFinding(
                        frame_number,
                        rule.target_name,
                        "pose.low_confidence",
                        "warning",
                        "Pose recovery confidence is low",
                    )
                )
        _interpolate_low_confidence(converted)
        _smooth_track(converted, profile.smoothing)
        if foot_contact_repair and any(
            label in f"{rule.source_name} {rule.target_name}".casefold()
            for label in ("foot", "toe", "足")
        ):
            _repair_foot_contacts(converted)
        _limit_speed(converted, profile.maximum_speed, recovered.fps, rule.target_name, findings)
        retained = _reduce_track(converted, profile.key_error_tolerance)
        output.extend(
            VmdBoneKey(rule.target_name, int(item[0]), tuple(item[1]), tuple(item[2]))
            for item in retained
        )
    if camera_compensation and not recovered.camera_compensated:
        findings.append(
            MotionFinding(
                0,
                "camera",
                "camera.compensated",
                "info",
                "Estimated camera translation was removed from mapped bone positions",
            )
        )
    if not output:
        raise ValueError("retarget profile produced no VMD bone keys")
    return (
        tuple(sorted(output, key=lambda key: (key.frame, key.bone.casefold()))),
        tuple(confidence_rows),
        tuple(findings),
    )


# {
# 責務: [_validate_profile: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _validate_profile(profile: RetargetProfile) -> None:
    if not 0.0 <= profile.smoothing <= 1.0:
        raise ValueError("smoothing must be in [0, 1]")
    if not math.isfinite(profile.key_error_tolerance) or profile.key_error_tolerance < 0:
        raise ValueError("key error tolerance must be finite and non-negative")
    if not math.isfinite(profile.maximum_speed) or profile.maximum_speed <= 0:
        raise ValueError("maximum speed must be finite and positive")
    sources = [rule.source_name.casefold() for rule in profile.rules]
    targets = [rule.target_name.casefold() for rule in profile.rules]
    if not profile.rules or len(sources) != len(set(sources)) or len(targets) != len(set(targets)):
        raise ValueError("retarget rules must have unique non-empty source and target bone names")
    for rule in profile.rules:
        if (
            not rule.source_name
            or not rule.target_name
            or not math.isfinite(rule.translation_scale)
            or rule.translation_scale <= 0
            or sorted(rule.position_axis) != [0, 1, 2]
            or any(not math.isfinite(value) for value in rule.position_sign)
        ):
            raise ValueError(f"invalid retarget rule for {rule.source_name!r}")


# {
# 責務: [_select_person: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _select_person(frames: tuple[RecoveredFrame, ...]) -> str:
    if not frames:
        raise ValueError("recovery backend returned no frames")
    counts = Counter(frame.person_id for frame in frames)
    return max(counts, key=lambda item: (counts[item], item))


# {
# 責務: [_convert_position: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _convert_position(pose, frame, rule, already_compensated, enabled):
    position = list(pose.translation)
    if enabled and not already_compensated:
        position = [
            value - offset for value, offset in zip(position, frame.camera_translation, strict=True)
        ]
    return tuple(
        position[rule.position_axis[index]] * rule.position_sign[index] * rule.translation_scale
        for index in range(3)
    )


# {
# 責務: [_convert_rotation: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _convert_rotation(rotation, rule):
    matrix = tuple(
        tuple(
            rule.position_sign[row] if rule.position_axis[row] == column else 0.0
            for column in range(3)
        )
        for row in range(3)
    )
    determinant = (
        matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )
    vector = tuple(
        determinant * sum(matrix[row][column] * rotation[column] for column in range(3))
        for row in range(3)
    )
    converted = (*vector, rotation[3])
    return _normalize_quaternion(converted)


# {
# 責務: [_normalize_quaternion: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _normalize_quaternion(rotation):
    magnitude = math.sqrt(sum(value * value for value in rotation))
    if magnitude < 1e-8:
        return (0.0, 0.0, 0.0, 1.0)
    return tuple(value / magnitude for value in rotation)


# {
# 責務: [_interpolate_low_confidence: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _interpolate_low_confidence(track) -> None:
    for index, current in enumerate(track):
        if current[3] >= LOW_CONFIDENCE:
            continue
        previous = next(
            (item for item in reversed(track[:index]) if item[3] >= LOW_CONFIDENCE), None
        )
        following = next((item for item in track[index + 1 :] if item[3] >= LOW_CONFIDENCE), None)
        if previous and following:
            ratio = (current[0] - previous[0]) / max(following[0] - previous[0], 1)
            current[1] = tuple(
                left + (right - left) * ratio
                for left, right in zip(previous[1], following[1], strict=True)
            )
            current[2] = _slerp(previous[2], following[2], ratio)
        elif previous:
            current[1], current[2] = previous[1], previous[2]
        elif following:
            current[1], current[2] = following[1], following[2]


# {
# 責務: [_smooth_track: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _smooth_track(track, factor: float) -> None:
    if not track or factor <= 0:
        return
    previous_position = track[0][1]
    previous_rotation = track[0][2]
    for item in track[1:]:
        item[1] = tuple(
            previous * factor + current * (1 - factor)
            for previous, current in zip(previous_position, item[1], strict=True)
        )
        item[2] = _slerp(previous_rotation, item[2], 1.0 - factor)
        previous_position, previous_rotation = item[1], item[2]


# {
# 責務: [_repair_foot_contacts: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _repair_foot_contacts(track) -> None:
    anchor = None
    for item in track:
        if not item[4]:
            anchor = None
            continue
        position = item[1]
        if anchor is None:
            anchor = (position[0], position[2])
        item[1] = (anchor[0], item[5], anchor[1])


# {
# 責務: [_limit_speed: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _limit_speed(track, maximum_speed: float, fps: int, bone: str, findings) -> None:
    previous = None
    for item in track:
        if previous is None:
            previous = item
            continue
        frame_delta = max(1, item[0] - previous[0])
        distance = _distance(previous[1], item[1])
        speed = distance / frame_delta * fps
        if speed > maximum_speed:
            item[1] = previous[1]
            findings.append(
                MotionFinding(
                    int(item[0]),
                    bone,
                    "motion.impossible_acceleration",
                    "warning",
                    f"Translation speed {speed:.2f} exceeded the cleanup limit",
                )
            )
        previous = item


# {
# 責務: [_reduce_track: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _reduce_track(track, tolerance: float):
    if len(track) <= 2 or tolerance <= 0:
        return track
    keep = {0, len(track) - 1}
    pending = [(0, len(track) - 1)]
    while pending:
        start, end = pending.pop()
        if end - start < 2:
            continue
        maximum_error = -1.0
        maximum_index = None
        span = max(track[end][0] - track[start][0], 1)
        for index in range(start + 1, end):
            ratio = (track[index][0] - track[start][0]) / span
            position = tuple(
                left + (right - left) * ratio
                for left, right in zip(track[start][1], track[end][1], strict=True)
            )
            rotation = _slerp(track[start][2], track[end][2], ratio)
            error = max(
                _distance(position, track[index][1]),
                _quaternion_angle(rotation, track[index][2]) * 0.1,
            )
            if error > maximum_error:
                maximum_error, maximum_index = error, index
        if maximum_error > tolerance and maximum_index is not None:
            keep.add(maximum_index)
            pending.extend(((start, maximum_index), (maximum_index, end)))
    return [track[index] for index in sorted(keep)]


# {
# 責務: [_distance: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _distance(first, second) -> float:
    return math.sqrt(sum((right - left) ** 2 for left, right in zip(first, second, strict=True)))


# {
# 責務: [_slerp: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _slerp(first, second, ratio: float):
    dot = sum(left * right for left, right in zip(first, second, strict=True))
    if dot < 0:
        second = tuple(-value for value in second)
        dot = -dot
    dot = min(1.0, max(-1.0, dot))
    if dot > 0.9995:
        return _normalize_quaternion(
            tuple(left + (right - left) * ratio for left, right in zip(first, second, strict=True))
        )
    angle = math.acos(dot)
    denominator = math.sin(angle)
    left_weight = math.sin((1.0 - ratio) * angle) / denominator
    right_weight = math.sin(ratio * angle) / denominator
    return _normalize_quaternion(
        tuple(
            left_weight * left + right_weight * right
            for left, right in zip(first, second, strict=True)
        )
    )


# {
# 責務: [_quaternion_angle: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _quaternion_angle(first, second) -> float:
    dot = abs(sum(left * right for left, right in zip(first, second, strict=True)))
    return 2.0 * math.acos(min(1.0, max(0.0, dot)))
