"""Cross-section integrity checks for parsed PMX skeleton and physics data."""

import math

from .contracts import (
    DiagnosticSeverity,
    PmxBone,
    PmxDiagnostic,
)


# {
# 責務: [_validate_bones: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [bones: 呼び出しに必要な値]
# 戻り値: [list[PmxDiagnostic]: 処理結果]
# }
def _validate_bones(bones: tuple[PmxBone, ...]) -> list[PmxDiagnostic]:
    diagnostics = []
    seen: dict[str, int] = {}
    for bone in bones:
        if bone.name in seen:
            diagnostics.append(
                _diagnostic(
                    "bone.duplicate_name",
                    "skeleton",
                    f"bone:{bone.index}:{bone.name}",
                    "Bone name is duplicated",
                    other_index=seen[bone.name],
                )
            )
        seen[bone.name] = bone.index
        if (
            bone.parent_index < -1
            or bone.parent_index >= len(bones)
            or bone.parent_index == bone.index
        ):
            diagnostics.append(
                _diagnostic(
                    "bone.invalid_parent",
                    "skeleton",
                    f"bone:{bone.index}:{bone.name}",
                    "Bone parent index is invalid or self-referential",
                    parent=bone.parent_index,
                )
            )
        if bone.ik_target is not None and not 0 <= bone.ik_target < len(bones):
            diagnostics.append(
                _diagnostic(
                    "ik.invalid_target",
                    "ik",
                    f"bone:{bone.index}:{bone.name}",
                    "IK target references a missing bone",
                    target=bone.ik_target,
                )
            )
        for link in bone.ik_links:
            if not 0 <= link < len(bones):
                diagnostics.append(
                    _diagnostic(
                        "ik.invalid_link",
                        "ik",
                        f"bone:{bone.index}:{bone.name}",
                        "IK link references a missing bone",
                        link=link,
                    )
                )
    return diagnostics


# {
# 責務: [_validate_rigid_physics: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [rigid_bodies, joints, bone_count: 呼び出しに必要な値]
# 戻り値: [処理結果: 処理結果]
# }
def _validate_rigid_physics(rigid_bodies, joints, bone_count):
    diagnostics = []
    for body in rigid_bodies:
        if body.bone_index < -1 or body.bone_index >= bone_count:
            diagnostics.append(
                _diagnostic(
                    "physics.invalid_bone",
                    "physics",
                    f"rigid:{body.index}:{body.name}",
                    "Rigid body refers to a missing bone",
                    bone=body.bone_index,
                )
            )
        if body.shape not in (0, 1, 2) or body.mode not in (0, 1, 2):
            diagnostics.append(
                _diagnostic(
                    "physics.invalid_mode",
                    "physics",
                    f"rigid:{body.index}:{body.name}",
                    "Rigid body shape or mode is invalid",
                    shape=body.shape,
                    mode=body.mode,
                )
            )
        if (
            body.mass < 0
            or body.linear_damping < 0
            or body.angular_damping < 0
            or body.restitution < 0
            or body.friction < 0
        ):
            diagnostics.append(
                _diagnostic(
                    "physics.negative_parameter",
                    "physics",
                    f"rigid:{body.index}:{body.name}",
                    "Rigid body has negative mass or damping/material parameter",
                )
            )
        if any(
            not math.isfinite(value)
            for value in (
                body.mass,
                body.linear_damping,
                body.angular_damping,
                body.restitution,
                body.friction,
            )
        ):
            diagnostics.append(
                _diagnostic(
                    "physics.non_finite_parameter",
                    "physics",
                    f"rigid:{body.index}:{body.name}",
                    "Rigid body has non-finite physics parameters",
                )
            )
    for joint in joints:
        if (
            joint.body_a < -1
            or joint.body_b < -1
            or joint.body_a >= len(rigid_bodies)
            or joint.body_b >= len(rigid_bodies)
        ):
            diagnostics.append(
                _diagnostic(
                    "physics.invalid_joint_body",
                    "physics",
                    f"joint:{joint.index}:{joint.name}",
                    "Joint refers to a missing rigid body",
                    bodies=(joint.body_a, joint.body_b),
                )
            )
        if any(low > high for low, high in zip(joint.minimum, joint.maximum, strict=True)):
            diagnostics.append(
                _diagnostic(
                    "physics.reversed_limits",
                    "physics",
                    f"joint:{joint.index}:{joint.name}",
                    "Joint limit minimum exceeds maximum",
                )
            )
        if any(not math.isfinite(value) for value in (*joint.minimum, *joint.maximum)):
            diagnostics.append(
                _diagnostic(
                    "physics.non_finite_limit",
                    "physics",
                    f"joint:{joint.index}:{joint.name}",
                    "Joint contains non-finite limit values",
                )
            )
    return diagnostics


# {
# 責務: [_diagnostic: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [code, category, target, message: 呼び出しに必要な値]
# 戻り値: [PmxDiagnostic: 処理結果]
# }
def _diagnostic(code: str, category: str, target: str, message: str, **evidence) -> PmxDiagnostic:
    return PmxDiagnostic(
        code, category, DiagnosticSeverity.ERROR, target, message, tuple(sorted(evidence.items()))
    )
