"""Offline procedural dance baseline driven by plan sections and beat structure."""

from __future__ import annotations

import math
from bisect import bisect_right

from comfyui_support_tools.shared.video_to_mmd.contracts import (
    RecoveredFrame,
    RecoveredMotion,
    SourceBonePose,
)

from .contracts import DanceMotionRequest

STYLE_AMPLITUDE = {
    "idol": 0.8,
    "pop": 0.85,
    "cute": 0.65,
    "energetic": 1.0,
    "cool": 0.75,
    "hip_hop_like": 0.9,
    "contemporary_like": 0.7,
    "simple": 0.45,
    "mmd_stage": 0.8,
    "custom": 0.65,
}


# {
# 責務: [ProceduralDanceBackend: provide an offline editable full-body choreography baseline]
# フィールド: [none: motion is derived from the request plan]
# 処理: [combine beat phase, style, energy, and section motif into deterministic joints]
# }
class ProceduralDanceBackend:
    # {
    # 責務: [generate_section: generate deterministic beat-structured 3D joint motion]
    # 処理: [create per-frame root/body/arm/leg/foot poses with alternating contacts]
    # 引数: [request: music analysis and one choreography section]
    # 戻り値: [RecoveredMotion: local section motion for shared MMD retarget]
    # }
    def generate_section(self, request: DanceMotionRequest) -> RecoveredMotion:
        section = request.section
        fps = request.plan.fps
        style = STYLE_AMPLITUDE.get(request.plan.style, STYLE_AMPLITUDE["custom"])
        seed_offset = (request.seed or 0) % 4
        frames = []
        for frame in range(section.end_frame - section.start_frame):
            seconds = frame / fps
            beat_position = seconds * request.analysis.bpm / 60
            beat_index = int(beat_position)
            beat_phase = beat_position - beat_index
            step_phase = (beat_index + seed_offset) % 4
            energy = _sample_energy(request.analysis, section.start_frame / fps + seconds)
            amplitude = style * section.intensity * (0.65 + 0.35 * min(1.0, energy * 2))
            side = -1.0 if (beat_index + seed_offset) % 2 == 0 else 1.0
            step = side * amplitude * 0.12 * math.sin(math.pi * beat_phase)
            sway = amplitude * 0.16 * math.sin(beat_position * math.pi / 2)
            chorus = section.kind == "chorus"
            arm_pattern = (0.55, -0.35, 0.75, -0.45) if chorus else (0.35, -0.2, 0.45, -0.25)
            left_arm = arm_pattern[step_phase] * amplitude
            right_arm = -arm_pattern[(step_phase + 2) % 4] * amplitude
            kick = max(0.0, math.sin(math.pi * beat_phase)) * amplitude * 0.28
            left_contact = beat_index % 2 == 0 and beat_phase < 0.78
            right_contact = not left_contact
            bones = (
                _pose("root", (0.0, 1.0, 0.0), (0.0, 0.0, 0.0), 0.95),
                _pose("center", (step, 0.0, 0.0), (0.0, sway, 0.0), 0.95),
                _pose(
                    "upper_body",
                    (0.0, 0.0, 0.0),
                    (0.04 * math.sin(beat_position * math.pi) * amplitude, -sway * 0.55, 0.0),
                    0.9,
                ),
                _pose(
                    "head",
                    (0.0, 0.0, 0.0),
                    (-0.025 * math.sin(beat_position * math.pi) * amplitude, sway * 0.25, 0.0),
                    0.82,
                ),
                _pose("left_arm", (0.0, 0.0, 0.0), (left_arm * 0.4, 0.0, left_arm), 0.9),
                _pose("right_arm", (0.0, 0.0, 0.0), (right_arm * 0.4, 0.0, right_arm), 0.9),
                _pose(
                    "left_leg", (0.0, 0.0, 0.0), (kick if not left_contact else 0.0, 0.0, 0.0), 0.88
                ),
                _pose(
                    "right_leg",
                    (0.0, 0.0, 0.0),
                    (kick if not right_contact else 0.0, 0.0, 0.0),
                    0.88,
                ),
                _pose(
                    "left_foot",
                    (0.0, 0.0 if left_contact else kick * 0.3, 0.0),
                    (0.0, 0.0, 0.0),
                    0.92,
                    left_contact,
                ),
                _pose(
                    "right_foot",
                    (step, 0.0 if right_contact else kick * 0.3, 0.0),
                    (0.0, 0.0, 0.0),
                    0.92,
                    right_contact,
                ),
            )
            frames.append(RecoveredFrame(frame, "dancer", (0.0, 0.0, 0.0), 0.0, bones))
        return RecoveredMotion(fps, tuple(frames), camera_compensated=True)


# {
# 責務: [_pose: construct normalized axis-angle source bone sample]
# 処理: [convert Euler radians to unit quaternion and retain contact evidence]
# 引数: [name: source joint, translation: xyz, euler: xyz radians, confidence, contact]
# 戻り値: [SourceBonePose: one recovered joint sample]
# }
def _pose(
    name: str, translation, euler, confidence: float, contact: bool = False
) -> SourceBonePose:
    x, y, z = (value / 2 for value in euler)
    cx, cy, cz = math.cos(x), math.cos(y), math.cos(z)
    sx, sy, sz = math.sin(x), math.sin(y), math.sin(z)
    quaternion = (
        sx * cy * cz - cx * sy * sz,
        cx * sy * cz + sx * cy * sz,
        cx * cy * sz - sx * sy * cz,
        cx * cy * cz + sx * sy * sz,
    )
    return SourceBonePose(name, translation, quaternion, confidence, contact)


# {
# 責務: [_sample_energy: sample the song energy curve around an absolute timestamp]
# 処理: [select the latest preceding energy point or return neutral energy]
# 引数: [analysis: audio feature curve, seconds: absolute song time]
# 戻り値: [float: normalized audio energy]
# }
def _sample_energy(analysis, seconds: float) -> float:
    curve = analysis.energy_curve
    index = bisect_right(curve, (seconds, math.inf)) - 1
    return curve[index][1] if index >= 0 else 0.5
