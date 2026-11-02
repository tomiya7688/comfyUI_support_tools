"""Character planning, geometry, rigging, morph, physics, and export contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


# {
# 責務: [CharacterSpec: prompt/reference and stable MMD humanoid design intent]
# フィールド: [prompt, reference files, route, proportions, character type, seed]
# 処理: [share user intent between stable VRM and free-geometry routes]
# }
@dataclass(frozen=True)
class CharacterSpec:
    prompt: str
    references: tuple[Path, ...] = ()
    route: str = "auto"
    character_type: str = "anime_humanoid"
    height: float = 1.65
    head_ratio: float = 7.5
    shoulder_ratio: float = 0.24
    hip_ratio: float = 0.2
    candidate_count: int = 1
    seed: int | None = None


# {
# 責務: [MeshAsset: triangle mesh geometry, UVs, materials, and skin weights]
# フィールド: [vertices, triangles, uv coordinates, skin weights]
# 処理: [normalize geometry across CharacterGen/Hunyuan3D/VRM adapters]
# }
@dataclass(frozen=True)
class MeshAsset:
    vertices: tuple[tuple[float, float, float], ...]
    triangles: tuple[tuple[int, int, int], ...]
    uv_coordinates: tuple[tuple[float, float], ...] = ()
    weights: tuple[tuple[tuple[str, float], ...], ...] = ()


# {
# 責務: [MmdBone: MMD-aligned skeleton bone and optional IK metadata]
# フィールド: [name, parent, position, tail, deform layer, IK chain]
# 処理: [define stable humanoid rig independent of rigging backend]
# }
@dataclass(frozen=True)
class MmdBone:
    name: str
    parent: str | None
    position: tuple[float, float, float]
    tail: tuple[float, float, float]
    deform_layer: int = 0
    ik_target: str | None = None
    ik_chain: tuple[str, ...] = ()


# {
# 責務: [VertexMorph: one named vertex-deformation morph entry]
# フィールド: [morph name, vertex index, displacement]
# 処理: [represent blink, moods, and mouth vowel shape keys]
# }
@dataclass(frozen=True)
class VertexMorph:
    name: str
    vertex_index: int
    displacement: tuple[float, float, float]


# {
# 責務: [MmdMaterial: PMX material color and texture references]
# フィールド: [name, diffuse RGBA, texture, toon mode, edge flag]
# 処理: [preserve MMD toon/alpha material intent]
# }
@dataclass(frozen=True)
class MmdMaterial:
    name: str
    diffuse: tuple[float, float, float, float]
    texture: str | None = None
    toon_mode: str = "shared"
    edge_enabled: bool = True


# {
# 責務: [RigidBodySpec: MMD physics collision body metadata]
# フィールド: [name, bone, shape, dimensions, mass, collision group]
# 処理: [represent hair/skirt/accessory simulation setup]
# }
@dataclass(frozen=True)
class RigidBodySpec:
    name: str
    bone: str
    shape: str
    dimensions: tuple[float, float, float]
    mass: float
    collision_group: int = 0


# {
# 責務: [JointSpec: spring/damping joint between two rigid bodies]
# フィールド: [name, rigid body references, translation/rotation spring]
# 処理: [validate physics connections before PMX serialization]
# }
@dataclass(frozen=True)
class JointSpec:
    name: str
    body_a: str
    body_b: str
    translation_spring: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_spring: tuple[float, float, float] = (0.0, 0.0, 0.0)


# {
# 責務: [PmxCharacterDocument: complete adapter-neutral MMD character bundle]
# フィールド: [model, mesh, bones, morphs, materials, rigid bodies, joints]
# 処理: [pass validated character data to preview/export adapters]
# }
@dataclass(frozen=True)
class PmxCharacterDocument:
    model_name: str
    mesh: MeshAsset
    bones: tuple[MmdBone, ...]
    morphs: tuple[VertexMorph, ...]
    materials: tuple[MmdMaterial, ...]
    rigid_bodies: tuple[RigidBodySpec, ...] = ()
    joints: tuple[JointSpec, ...] = ()
    textures: tuple[Path, ...] = ()


# {
# 責務: [CharacterFinding: machine-readable quality/repair diagnostic]
# フィールド: [code, severity, location, message, repairable]
# 処理: [drive review output and bounded local repair loops]
# }
@dataclass(frozen=True)
class CharacterFinding:
    code: str
    severity: str
    location: str
    message: str
    repairable: bool = False


# {
# 責務: [CharacterProvenance: record backend/model/license and source hashes]
# フィールド: [backend, model version, license, source paths, seed]
# 処理: [attach inspectable provenance to generated character output]
# }
@dataclass(frozen=True)
class CharacterProvenance:
    backend: str
    model_version: str
    license_id: str
    sources: tuple[str, ...]
    seed: int | None


# {
# 責務: [CharacterGenerationBackend: route-specific mesh generation adapter]
# フィールド: [generate callable]
# 処理: [support VRM, CharacterGen, Hunyuan3D, or other geometry sources]
# }
class CharacterGenerationBackend(Protocol):
    # {
    # 責務: [generate: create a textured or canonical triangle mesh candidate]
    # 処理: [convert CharacterSpec into neutral MeshAsset]
    # 引数: [spec: character design request]
    # 戻り値: [MeshAsset: geometry candidate]
    # }
    def generate(self, spec: CharacterSpec) -> MeshAsset: ...


# {
# 責務: [CharacterRiggingBackend: infer MMD bone mapping and skin weights]
# フィールド: [rig callable]
# 処理: [adapt native rig, SkinTokens, UniRig, or classical autorig]
# }
class CharacterRiggingBackend(Protocol):
    # {
    # 責務: [rig: create an MMD skeleton and vertex skin weights]
    # 処理: [produce bones and weighted mesh from generated geometry]
    # 引数: [mesh: generated geometry, spec: body proportions and character intent]
    # 戻り値: [tuple[MeshAsset, tuple[MmdBone, ...]]: weighted mesh and mapped skeleton]
    # }
    def rig(
        self, mesh: MeshAsset, spec: CharacterSpec
    ) -> tuple[MeshAsset, tuple[MmdBone, ...]]: ...


# {
# 責務: [CharacterDetailBackend: add facial morph and physics metadata]
# フィールド: [morph/physics callable]
# 処理: [generate expression and simulation configuration]
# }
class CharacterDetailBackend(Protocol):
    # {
    # 責務: [morphs: generate face/body vertex morphs]
    # 処理: [provide basic moods and あいうえお mouth shapes]
    # 引数: [mesh: rigged geometry, spec: character style and facial proportions]
    # 戻り値: [tuple[VertexMorph, ...]: named morph deltas]
    # }
    def morphs(self, mesh: MeshAsset, spec: CharacterSpec) -> tuple[VertexMorph, ...]: ...

    # {
    # 責務: [physics: create garment/hair rigid bodies and joints]
    # 処理: [create bounded collision group and spring settings]
    # 引数: [mesh: rigged geometry, bones: MMD skeleton, spec: character intent]
    # 戻り値: [tuple[rigid bodies, joints]: simulation metadata]
    # }
    def physics(
        self, mesh: MeshAsset, bones: tuple[MmdBone, ...], spec: CharacterSpec
    ) -> tuple[tuple[RigidBodySpec, ...], tuple[JointSpec, ...]]: ...


# {
# 責務: [PmxExportBackend: serialize validated model documents to PMX bundles]
# フィールド: [export callable]
# 処理: [allow Blender/mmd_tools or native PMX writer implementation]
# }
class PmxExportBackend(Protocol):
    # {
    # 責務: [export: write PMX and texture artifacts]
    # 処理: [serialize adapter-neutral model under an auditable provenance record]
    # 引数: [document: complete MMD character, destination: reserved temporary PMX file path]
    # 戻り値: [Path: generated PMX file at the requested path]
    # }
    def export(self, document: PmxCharacterDocument, destination: Path) -> Path: ...


# {
# 責務: [CharacterCreationBackend: produce one or more route-specific rigged PMX documents]
# フィールド: [generate_candidates callable and provenance metadata]
# 処理: [adapt Stable VRM, CharacterGen, Hunyuan3D, or animation-ready geometry routes]
# }
class CharacterCreationBackend(Protocol):
    # {
    # 責務: [generate_candidates: generate bounded candidate character documents]
    # 処理: [include geometry, rig, morphs, physics, and provenance-ready content]
    # 引数: [spec: structured prompt/reference character request]
    # 戻り値: [tuple[PmxCharacterDocument, ...]: model candidates]
    # }
    def generate_candidates(self, spec: CharacterSpec) -> tuple[PmxCharacterDocument, ...]: ...

    # {
    # 責務: [provenance: identify source model/license for this character request]
    # 処理: [return explicit provenance rather than assuming generated assets are unrestricted]
    # 引数: [spec: character request]
    # 戻り値: [CharacterProvenance: model/version/license/source trace]
    # }
    def provenance(self, spec: CharacterSpec) -> CharacterProvenance: ...


# {
# 責務: [CharacterRepairBackend: apply local repairs to identified model issues]
# フィールド: [repair callable]
# 処理: [repair local weights, triangles, morph deltas, or physics references]
# }
class CharacterRepairBackend(Protocol):
    # {
    # 責務: [repair: return a corrected candidate without whole-character reroll]
    # 処理: [apply only findings marked repairable and retain source provenance]
    # 引数: [document: current candidate, findings: validation output]
    # 戻り値: [PmxCharacterDocument: repaired candidate]
    # }
    def repair(
        self, document: PmxCharacterDocument, findings: tuple[CharacterFinding, ...]
    ) -> PmxCharacterDocument: ...


# {
# 責務: [CharacterPreviewBackend: render rig/morph/physics preview evidence]
# フィールド: [preview callable]
# 処理: [provide optional Blender/viewport adapter before PMX export]
# }
class CharacterPreviewBackend(Protocol):
    # {
    # 責務: [preview: render rest pose, motion suite, morphs, and simulation]
    # 処理: [return preview artifact paths with validation report]
    # 引数: [document: character candidate, destination: preview folder]
    # 戻り値: [tuple[Path, ...]: reviewable preview artifacts]
    # }
    def preview(self, document: PmxCharacterDocument, destination: Path) -> tuple[Path, ...]: ...
