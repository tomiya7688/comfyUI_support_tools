"""Tests for MMD character routing, diagnostics, repair, and provenance gating."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from comfyui_support_tools.shared.mmd_character import (
    MMD_HUMANOID_BONES,
    CharacterProvenance,
    CharacterRouteRegistry,
    CharacterSpec,
    CharacterValidationError,
    MeshAsset,
    MmdBone,
    MmdCharacterCreator,
    MmdMaterial,
    PmxCharacterDocument,
    RigidBodySpec,
    VertexMorph,
    validate_character,
)


# {
# 責務: [FakeCharacterBackend: deliver fixed candidate docs and provenance]
# フィールド: [documents, license]
# 処理: [exercise route and repair contracts without unavailable 3D models]
# }
class FakeCharacterBackend:
    # {
    # 責務: [__init__: keep test documents and license provenance]
    # 処理: [prepare generated candidate list]
    # 引数: [documents: character candidates, license_id: provenance license]
    # 戻り値: [None: initialized fake backend]
    # }
    def __init__(self, documents, license_id="MIT"):
        self.documents = documents
        self.license_id = license_id

    # {
    # 責務: [generate_candidates: satisfy backend creation protocol]
    # 処理: [return deterministic document candidates]
    # 引数: [spec: requested character]
    # 戻り値: [tuple[PmxCharacterDocument, ...]: candidate documents]
    # }
    def generate_candidates(self, spec):
        return self.documents[: spec.candidate_count]

    # {
    # 責務: [provenance: report fake model and declared license]
    # 処理: [include request reference paths as input sources]
    # 引数: [spec: requested character]
    # 戻り値: [CharacterProvenance: model/license provenance]
    # }
    def provenance(self, spec):
        return CharacterProvenance(
            "fixture-backend", "1.0", self.license_id, tuple(map(str, spec.references)), spec.seed
        )


# {
# 責務: [FakeRepairer: repair broken weights by mapping them to center]
# フィールド: [calls: local repair count]
# 処理: [simulate an auditable localized weight repair]
# }
class FakeRepairer:
    # {
    # 責務: [__init__: initialize local repair counter]
    # 処理: [track repair loop calls]
    # 引数: [None: no inputs]
    # 戻り値: [None: initialized repairer]
    # }
    def __init__(self):
        self.calls = 0

    # {
    # 責務: [repair: replace unknown skinning bone with center]
    # 処理: [rewrite only invalid bone assignments and renormalize vertex weights]
    # 引数: [document: invalid candidate, findings: validation output]
    # 戻り値: [PmxCharacterDocument: locally repaired candidate]
    # }
    def repair(self, document, findings):
        self.calls += 1
        weights = tuple((("センター", 1.0),) for _ in document.mesh.vertices)
        return replace(document, mesh=replace(document.mesh, weights=weights))


# {
# 責務: [FakeExporter: write a small test PMX marker file]
# フィールド: [calls: exporter invocation count]
# 処理: [verify pipeline export gating without asserting fake bytes are real PMX]
# }
class FakeExporter:
    # {
    # 責務: [__init__: initialize export counter]
    # 処理: [track whether invalid input reached the exporter]
    # 引数: [None: no inputs]
    # 戻り値: [None: initialized exporter]
    # }
    def __init__(self):
        self.calls = 0

    # {
    # 責務: [export: create an isolated fake artifact path]
    # 処理: [write fixture marker and return its path]
    # 引数: [document: validated bundle, destination: output folder]
    # 戻り値: [Path: marker artifact]
    # }
    def export(self, document, destination):
        self.calls += 1
        destination.write_bytes(b"fixture-pmx-adapter-output")
        return destination


# {
# 責務: [FakePreviewer: create review artifact from valid character bundle]
# フィールド: [None: stateless]
# 処理: [stand in for Blender/mmd_tools preview integration]
# }
class FakePreviewer:
    # {
    # 責務: [preview: write a simple review marker]
    # 処理: [return one preview path]
    # 引数: [document: character model, destination: output folder]
    # 戻り値: [tuple[Path, ...]: preview artifact paths]
    # }
    def preview(self, document, destination):
        path = destination / "preview.txt"
        path.write_text("test adapter preview", encoding="utf-8")
        return (path,)


# {
# 責務: [MmdCharacterCreatorTests: test structural validation and creator loop]
# フィールド: [fixture documents and temporary export paths]
# 処理: [cover route selection, diagnostic codes, repair, export, and license protection]
# }
class MmdCharacterCreatorTests(unittest.TestCase):
    # {
    # 責務: [make_document: create a minimal complete skeleton/mesh fixture]
    # 処理: [include standard bones, valid weights/morph/material/physics state]
    # 引数: [invalid_weight: optionally reference a missing skinning bone]
    # 戻り値: [PmxCharacterDocument: test candidate]
    # }
    def make_document(self, invalid_weight=False):
        bones = tuple(
            MmdBone(name, None if name == "センター" else "センター", (0, 0, 0), (0, 0.1, 0))
            for name in sorted(MMD_HUMANOID_BONES)
        )
        weights = tuple(
            (("missing_bone", 1.0),) if invalid_weight else (("センター", 1.0),) for _ in range(3)
        )
        mesh = MeshAsset(((0, 0, 0), (1, 0, 0), (0, 1, 0)), ((0, 1, 2),), weights=weights)
        morphs = tuple(
            VertexMorph(name, 0, (0, 0, 0))
            for name in ("まばたき", "笑い", "怒り", "悲しみ", "驚き", "あ", "い", "う", "え", "お")
        )
        materials = (MmdMaterial("body", (0.8, 0.7, 0.6, 1.0)),)
        physics = (RigidBodySpec("hair", "頭", "capsule", (0.1, 0.2, 0.1), 0.2),)
        return PmxCharacterDocument("fixture", mesh, bones, morphs, materials, physics, ())

    # {
    # 責務: [test_validator_reports_geometry_weight_and_morph_failures: check quality diagnostics]
    # 処理: [detect degenerate topology, unweighted vertices, and missing mouth morphs]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_validator_reports_geometry_weight_and_morph_failures(self):
        document = self.make_document()
        mesh = replace(document.mesh, triangles=((0, 0, 1),), weights=((), (), ()))
        broken = replace(document, mesh=mesh, morphs=())
        codes = {finding.code for finding in validate_character(broken)}
        self.assertIn("geometry.triangle.index", codes)
        self.assertIn("rig.weights.unweighted", codes)
        self.assertIn("morph.required.missing", codes)

    # {
    # 責務: [test_validator_handles_malformed_adapter_values: keep untrusted backend output diagnosable]
    # 処理: [feed malformed vectors, face indices, and weights through validation]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_validator_handles_malformed_adapter_values(self):
        document = self.make_document()
        mesh = replace(
            document.mesh,
            vertices=((None, 0, 0), (1, 0, 0), (0, 1, 0)),
            triangles=((0, 1, 9),),
            weights=((("センター", "heavy"),), (), ()),
        )
        findings = validate_character(replace(document, mesh=mesh))
        codes = {finding.code for finding in findings}
        self.assertIn("geometry.vertex.nonfinite", codes)
        self.assertIn("geometry.triangle.index", codes)
        self.assertIn("rig.weights.invalid", codes)
        self.assertIn("rig.weights.unweighted", codes)

    # {
    # 責務: [test_route_and_auto_selection_support_stable_and_free_modes: validate route registry]
    # 処理: [select explicit free route and auto route for anime humanoids]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_route_and_auto_selection_support_stable_and_free_modes(self):
        backend = FakeCharacterBackend((self.make_document(),))
        routes = CharacterRouteRegistry()
        routes.register("stable_humanoid", backend, frozenset())
        routes.register("free_3d", backend, frozenset())
        self.assertEqual(routes.select(CharacterSpec("anime character")).name, "stable_humanoid")
        self.assertEqual(
            routes.select(CharacterSpec("dragon", character_type="monster")).name, "free_3d"
        )

    # {
    # 責務: [test_creator_repairs_bad_skinning_then_exports_provenance_and_preview: exercise retry loop]
    # 処理: [replace invalid influences, revalidate, and export only valid candidates]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_creator_repairs_bad_skinning_then_exports_provenance_and_preview(self):
        backend = FakeCharacterBackend((self.make_document(invalid_weight=True),))
        routes = CharacterRouteRegistry()
        routes.register("stable_humanoid", backend, frozenset())
        repairer, exporter = FakeRepairer(), FakeExporter()
        creator = MmdCharacterCreator(routes, repairer, FakePreviewer(), exporter)
        with tempfile.TemporaryDirectory() as temporary:
            result = creator.create(
                CharacterSpec("anime idol", route="stable_humanoid"), Path(temporary)
            )
            self.assertEqual(repairer.calls, 1)
            self.assertEqual(exporter.calls, 1)
            self.assertTrue(result.pmx_path.is_file())
            self.assertTrue(result.preview_paths[0].is_file())
            report = __import__("json").loads(result.report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["provenance"]["license"], "MIT")
            with self.assertRaises(FileExistsError):
                creator.create(
                    CharacterSpec("anime idol", route="stable_humanoid"), Path(temporary)
                )

    # {
    # 責務: [test_unknown_license_and_remaining_errors_block_export: enforce provenance and validation]
    # 処理: [ensure unknown model license and unrepaired invalid weights never reach PMX exporter]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_unknown_license_and_remaining_errors_block_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            exporter = FakeExporter()
            unknown = FakeCharacterBackend((self.make_document(),), license_id="unknown")
            routes = CharacterRouteRegistry()
            routes.register("stable_humanoid", unknown, frozenset())
            creator = MmdCharacterCreator(routes, exporter=exporter)
            with self.assertRaises(ValueError):
                creator.create(CharacterSpec("model", route="stable_humanoid"), Path(temporary))
            self.assertEqual(exporter.calls, 0)
            invalid_routes = CharacterRouteRegistry()
            invalid_routes.register(
                "stable_humanoid",
                FakeCharacterBackend((self.make_document(invalid_weight=True),)),
                frozenset(),
            )
            invalid_creator = MmdCharacterCreator(invalid_routes, exporter=exporter)
            with self.assertRaises(CharacterValidationError):
                invalid_creator.create(
                    CharacterSpec("model", route="stable_humanoid"), Path(temporary)
                )
            self.assertEqual(exporter.calls, 0)

    # {
    # 責務: [test_request_validation_blocks_missing_prompt_and_unsafe_proportions: guard inputs]
    # 処理: [ensure malformed requests fail before backend selection]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_request_validation_blocks_missing_prompt_and_unsafe_proportions(self):
        with self.assertRaises(ValueError):
            MmdCharacterCreator().create(CharacterSpec("", height=10), Path("unused"))
        with self.assertRaises(ValueError):
            MmdCharacterCreator().create(CharacterSpec("", references=()), Path("unused"))


if __name__ == "__main__":
    unittest.main()
