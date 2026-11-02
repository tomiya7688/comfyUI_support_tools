"""Deterministic mesh, skeleton, morph, material, and physics validation."""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

from .contracts import CharacterFinding, PmxCharacterDocument

MMD_HUMANOID_BONES = frozenset(
    {
        "センター",
        "グルーブ",
        "上半身",
        "上半身2",
        "首",
        "頭",
        "左肩",
        "右肩",
        "左腕",
        "右腕",
        "左ひじ",
        "右ひじ",
        "左手首",
        "右手首",
        "下半身",
        "左足",
        "右足",
        "左ひざ",
        "右ひざ",
        "左足首",
        "右足首",
        "左つま先",
        "右つま先",
    }
)


# {
# 責務: [validate_character: inspect geometry, skeleton, skinning, morph, and physics invariants]
# 処理: [return stable diagnostics for invalid topology, mappings, weights, and references]
# 引数: [document: adapter-neutral PMX character bundle]
# 戻り値: [tuple[CharacterFinding, ...]: ordered validation findings]
# }
def validate_character(document: PmxCharacterDocument) -> tuple[CharacterFinding, ...]:
    findings = []
    mesh = document.mesh
    if not document.model_name.strip():
        findings.append(
            _finding("model.name.empty", "error", "model", "Model name must not be empty.")
        )
    if (
        document.model_name in {".", ".."}
        or any(character in document.model_name for character in '/\\<>:"|?*')
        or any(ord(character) < 32 for character in document.model_name)
        or document.model_name.split(".", 1)[0].casefold()
        in {"con", "prn", "aux", "nul", "com1", "lpt1"}
    ):
        findings.append(
            _finding(
                "model.name.unsafe",
                "error",
                "model",
                "Model name cannot contain path separators or control characters.",
            )
        )
    if not mesh.vertices:
        findings.append(_finding("geometry.empty", "error", "mesh", "Mesh has no vertices."))
    for index, vertex in enumerate(mesh.vertices):
        if not _valid_vector(vertex, 3):
            findings.append(
                _finding(
                    "geometry.vertex.nonfinite",
                    "error",
                    f"vertex:{index}",
                    "Vertex position must contain three finite values.",
                )
            )
    findings.extend(_validate_triangles(mesh.vertices, mesh.triangles))
    findings.extend(_validate_duplicates(mesh.vertices))
    findings.extend(_validate_uv(mesh))
    bones = {bone.name: bone for bone in document.bones}
    if len(bones) != len(document.bones):
        findings.append(
            _finding("rig.bone.duplicate", "error", "bones", "Bone names must be unique.")
        )
    missing = sorted(MMD_HUMANOID_BONES - bones.keys())
    for name in missing:
        findings.append(
            _finding(
                "rig.bone.missing",
                "error",
                f"bone:{name}",
                "Required MMD humanoid bone is missing.",
            )
        )
    for bone in document.bones:
        if not _valid_vector(bone.position, 3) or not _valid_vector(bone.tail, 3):
            findings.append(
                _finding(
                    "rig.bone.transform",
                    "error",
                    f"bone:{bone.name}",
                    "Bone position/tail must contain finite coordinates.",
                )
            )
        if bone.parent is not None and bone.parent not in bones:
            findings.append(
                _finding(
                    "rig.parent.missing",
                    "error",
                    f"bone:{bone.name}",
                    f"Parent bone {bone.parent!r} does not exist.",
                )
            )
        if any(name not in bones for name in bone.ik_chain) or (
            bone.ik_target and bone.ik_target not in bones
        ):
            findings.append(
                _finding(
                    "rig.ik.reference_missing",
                    "error",
                    f"bone:{bone.name}",
                    "IK target or chain contains an unknown bone.",
                )
            )
    for child in document.bones:
        visited = set()
        current = child
        while current.parent in bones:
            if current.name in visited:
                findings.append(
                    _finding(
                        "rig.parent.cycle",
                        "error",
                        f"bone:{child.name}",
                        "Bone parent hierarchy contains a cycle.",
                    )
                )
                break
            visited.add(current.name)
            current = bones[current.parent]
    findings.extend(_validate_weights(mesh, bones))
    findings.extend(_validate_morphs(document))
    findings.extend(_validate_materials(document))
    findings.extend(_validate_physics(document, bones))
    return tuple(sorted(findings, key=lambda item: (item.severity, item.code, item.location)))


# {
# 責務: [_validate_triangles: verify triangle indices, area, and manifold edge counts]
# 処理: [detect invalid/degenerate faces and boundary/non-manifold topology]
# 引数: [vertices: XYZ points, triangles: mesh face indices]
# 戻り値: [list[CharacterFinding]: geometry diagnostics]
# }
def _validate_triangles(vertices, triangles):
    findings = []
    edge_counts = Counter()
    for index, triangle in enumerate(triangles):
        if (
            not isinstance(triangle, (tuple, list))
            or len(triangle) != 3
            or any(not isinstance(item, int) or isinstance(item, bool) for item in triangle)
            or len(set(triangle)) != 3
            or any(item < 0 or item >= len(vertices) for item in triangle)
            or any(not _valid_vector(vertices[item], 3) for item in triangle)
        ):
            findings.append(
                _finding(
                    "geometry.triangle.index",
                    "error",
                    f"triangle:{index}",
                    "Triangle must reference three distinct existing vertices.",
                    True,
                )
            )
            continue
        first, second, third = (vertices[item] for item in triangle)
        if _area_squared(first, second, third) < 1e-16:
            findings.append(
                _finding(
                    "geometry.triangle.degenerate",
                    "warning",
                    f"triangle:{index}",
                    "Triangle area is effectively zero.",
                    True,
                )
            )
        for start, end in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        ):
            edge_counts[tuple(sorted((start, end)))] += 1
    boundary = sum(count == 1 for count in edge_counts.values())
    nonmanifold = sum(count > 2 for count in edge_counts.values())
    if boundary:
        findings.append(
            _finding(
                "geometry.boundary_edges",
                "warning",
                "mesh",
                f"Mesh has {boundary} boundary edges/open boundaries.",
                False,
            )
        )
    if nonmanifold:
        findings.append(
            _finding(
                "geometry.nonmanifold_edges",
                "error",
                "mesh",
                f"Mesh has {nonmanifold} non-manifold edges.",
                True,
            )
        )
    return findings


# {
# 責務: [_validate_duplicates: detect duplicate or nearly identical mesh vertices]
# 処理: [quantize coordinates into bounded spatial keys]
# 引数: [vertices: XYZ points]
# 戻り値: [list[CharacterFinding]: duplicate vertex diagnostics]
# }
def _validate_duplicates(vertices):
    seen = {}
    duplicates = 0
    for index, vertex in enumerate(vertices):
        if not _valid_vector(vertex, 3):
            continue
        key = tuple(round(value, 7) for value in vertex)
        if key in seen:
            duplicates += 1
        else:
            seen[key] = index
    if duplicates:
        return [
            _finding(
                "geometry.duplicate_vertices",
                "warning",
                "mesh",
                f"Mesh has {duplicates} duplicate-position vertices.",
                True,
            )
        ]
    return []


# {
# 責務: [_validate_uv: validate one UV pair per mesh vertex when UVs are supplied]
# 処理: [check dimensions and finite UV values]
# 引数: [mesh: geometry and UV data]
# 戻り値: [list[CharacterFinding]: UV diagnostics]
# }
def _validate_uv(mesh):
    if mesh.uv_coordinates and len(mesh.uv_coordinates) != len(mesh.vertices):
        return [
            _finding(
                "geometry.uv.count", "error", "mesh", "UV coordinate count must match vertex count."
            )
        ]
    if any(not _valid_vector(uv, 2) for uv in mesh.uv_coordinates):
        return [
            _finding("geometry.uv.invalid", "error", "mesh", "UVs must contain two finite values.")
        ]
    return []


# {
# 責務: [_validate_weights: check per-vertex skinning assignments and weight sums]
# 処理: [detect unweighted vertices, missing bones, negatives, and non-unit sums]
# 引数: [mesh: skinned geometry, bones: valid MMD bones]
# 戻り値: [list[CharacterFinding]: skinning diagnostics]
# }
def _validate_weights(mesh, bones):
    findings = []
    if len(mesh.weights) != len(mesh.vertices):
        return [
            _finding(
                "rig.weights.count",
                "error",
                "mesh",
                "There must be one skinning weight set per vertex.",
            )
        ]
    unweighted = 0
    invalid = 0
    for vertex_index, weights in enumerate(mesh.weights):
        if not weights:
            unweighted += 1
            continue
        if any(
            not isinstance(item, (tuple, list))
            or len(item) != 2
            or not isinstance(item[0], str)
            or not _valid_number(item[1])
            or item[1] < 0
            or item[0] not in bones
            for item in weights
        ):
            invalid += 1
            continue
        if abs(sum(item[1] for item in weights) - 1.0) > 1e-4:
            findings.append(
                _finding(
                    "rig.weights.sum",
                    "warning",
                    f"vertex:{vertex_index}",
                    "Skinning weights must sum to one.",
                    True,
                )
            )
    if unweighted:
        findings.append(
            _finding(
                "rig.weights.unweighted",
                "error",
                "mesh",
                f"{unweighted} vertices are unweighted.",
                True,
            )
        )
    if invalid:
        findings.append(
            _finding(
                "rig.weights.invalid",
                "error",
                "mesh",
                f"{invalid} vertices reference missing bones or invalid weights.",
                True,
            )
        )
    return findings


# {
# 責務: [_validate_morphs: check morph names, indices, and finite displacement]
# 処理: [validate vertex morph deltas against mesh bounds]
# 引数: [document: model bundle]
# 戻り値: [list[CharacterFinding]: facial/body morph diagnostics]
# }
def _validate_morphs(document):
    findings = []
    names = set()
    for index, morph in enumerate(document.morphs):
        if not morph.name or morph.name in names:
            findings.append(
                _finding(
                    "morph.name.duplicate",
                    "error",
                    f"morph:{index}",
                    "Morph names must be non-empty and unique.",
                )
            )
        names.add(morph.name)
        if (
            not isinstance(morph.vertex_index, int)
            or isinstance(morph.vertex_index, bool)
            or morph.vertex_index < 0
            or morph.vertex_index >= len(document.mesh.vertices)
            or not _valid_vector(morph.displacement, 3)
        ):
            findings.append(
                _finding(
                    "morph.offset.invalid",
                    "error",
                    f"morph:{morph.name}",
                    "Morph offset references an invalid vertex or displacement.",
                    True,
                )
            )
    required = {"まばたき", "笑い", "怒り", "悲しみ", "驚き", "あ", "い", "う", "え", "お"}
    for name in sorted(required - names):
        findings.append(
            _finding(
                "morph.required.missing",
                "warning",
                f"morph:{name}",
                "Expected blink or mouth morph is missing.",
            )
        )
    return findings


# {
# 責務: [_validate_materials: validate visible PMX material parameters and texture paths]
# 処理: [check alpha/color ranges and texture references]
# 引数: [document: model bundle]
# 戻り値: [list[CharacterFinding]: material diagnostics]
# }
def _validate_materials(document):
    textures = {path.name for path in document.textures}
    findings = []
    for index, material in enumerate(document.materials):
        if not _valid_vector(material.diffuse, 4) or any(
            not 0 <= value <= 1 for value in material.diffuse
        ):
            findings.append(
                _finding(
                    "material.diffuse.invalid",
                    "error",
                    f"material:{index}",
                    "Diffuse RGBA values must be within 0..1.",
                )
            )
        if material.texture and Path(material.texture).name not in textures:
            findings.append(
                _finding(
                    "material.texture.missing",
                    "warning",
                    f"material:{material.name}",
                    "Referenced texture is not included in the character bundle.",
                )
            )
    return findings


# {
# 責務: [_validate_physics: check rigid body/joint references and simulation ranges]
# 処理: [validate known bone/body IDs, shape dimensions, mass, and spring values]
# 引数: [document: model bundle, bones: mapped skeleton]
# 戻り値: [list[CharacterFinding]: physics diagnostics]
# }
def _validate_physics(document, bones):
    findings = []
    bodies = {body.name for body in document.rigid_bodies}
    for body in document.rigid_bodies:
        if body.bone not in bones:
            findings.append(
                _finding(
                    "physics.bone.missing",
                    "error",
                    f"rigid_body:{body.name}",
                    "Rigid body references an unknown bone.",
                )
            )
        if (
            body.shape not in {"sphere", "box", "capsule"}
            or not _valid_vector(body.dimensions, 3)
            or any(value <= 0 for value in body.dimensions)
        ):
            findings.append(
                _finding(
                    "physics.shape.invalid",
                    "error",
                    f"rigid_body:{body.name}",
                    "Rigid body shape or dimensions are invalid.",
                )
            )
        if not _valid_number(body.mass) or body.mass < 0:
            findings.append(
                _finding(
                    "physics.mass.invalid",
                    "error",
                    f"rigid_body:{body.name}",
                    "Rigid body mass must be finite and non-negative.",
                )
            )
    for joint in document.joints:
        if joint.body_a not in bodies or joint.body_b not in bodies or joint.body_a == joint.body_b:
            findings.append(
                _finding(
                    "physics.joint.reference",
                    "error",
                    f"joint:{joint.name}",
                    "Joint must connect two distinct existing rigid bodies.",
                )
            )
        if not _valid_vector(joint.translation_spring, 3) or not _valid_vector(
            joint.rotation_spring, 3
        ):
            findings.append(
                _finding(
                    "physics.joint.spring",
                    "error",
                    f"joint:{joint.name}",
                    "Joint spring values must be finite.",
                )
            )
    return findings


# {
# 責務: [_area_squared: compute squared triangle area from 3D vertices]
# 処理: [cross product magnitude avoids square-root precision loss]
# 引数: [first/second/third: 3D vertex tuples]
# 戻り値: [float: four times triangle area squared]
# }
def _area_squared(first, second, third):
    left = tuple(b - a for a, b in zip(first, second, strict=True))
    right = tuple(c - a for a, c in zip(first, third, strict=True))
    cross = (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )
    return sum(value * value for value in cross)


# {
# 責務: [_finding: build one typed mesh or rig diagnostic]
# 処理: [construct immutable finding with consistent defaults]
# 引数: [code/severity/location/message/repairable: finding fields]
# 戻り値: [CharacterFinding: normalized diagnostic]
# }
def _finding(code, severity, location, message, repairable=False):
    return CharacterFinding(code, severity, location, message, repairable)


# {
# 責務: [_valid_number: recognize finite real-valued adapter fields]
# 処理: [reject booleans and malformed values without raising]
# 引数: [value: untrusted numeric value]
# 戻り値: [bool: whether the value is a finite number]
# }
def _valid_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


# {
# 責務: [_valid_vector: validate finite vectors from runtime adapters]
# 処理: [check container, expected width, and numeric elements defensively]
# 引数: [value: candidate vector, width: required component count]
# 戻り値: [bool: whether every vector component is valid]
# }
def _valid_vector(value, width):
    return (
        isinstance(value, (tuple, list))
        and len(value) == width
        and all(_valid_number(component) for component in value)
    )
