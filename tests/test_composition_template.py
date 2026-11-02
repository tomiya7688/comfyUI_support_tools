"""Tests for appearance-free layout extraction, adaptation, and persistence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from comfyui_support_tools.applications.composition_template.data.processing.codec import (
    template_from_json,
    template_to_json,
)
from comfyui_support_tools.applications.composition_template.data.processing.library import (
    TemplateLibrary,
)
from comfyui_support_tools.applications.composition_template.process.processing.adaptation import (
    adapt_template,
)
from comfyui_support_tools.applications.composition_template.process.processing.extraction import (
    CompositionExtractionProcessor,
)
from comfyui_support_tools.applications.composition_template.process.processing.guidance import (
    export_guidance,
    export_prompt,
)
from comfyui_support_tools.applications.composition_template.ui.processing.window import (
    CompositionTemplateWindow,
)
from comfyui_support_tools.shared.contracts.composition_template import (
    AspectPolicy,
    CompositionRegion,
    CompositionTemplate,
    DepthLayer,
    DepthStructure,
    ExtractionLevel,
    ExtractionProvenance,
    HorizonLine,
    RegionRole,
    VisualWeightMap,
)


# {
# 責務: [_template: build a small validated test fixture]
# 処理: [create subject and negative-space layout records]
# 戻り値: [CompositionTemplate: reusable test layout]
#   引数: [なし: 宣言の入力値]
# }
def _template() -> CompositionTemplate:
    """Build a small fixture with a subject and empty space."""
    provenance = ExtractionProvenance(
        "a" * 64, 1200, 800, ExtractionLevel.STRUCTURED, ("unit-test",)
    )
    return CompositionTemplate(
        aspect_ratio=1.5,
        shot_type="bust",
        camera_angle="unknown",
        subject_regions=(
            CompositionRegion(
                "main", RegionRole.MAIN_SUBJECT, (0.58, 0.2, 0.22, 0.62), confidence=0.8
            ),
        ),
        negative_space_regions=(
            CompositionRegion(
                "space", RegionRole.EMPTY_SPACE, (0.05, 0.15, 0.38, 0.7), confidence=0.7
            ),
        ),
        visual_weight_map=VisualWeightMap(((0.1, 0.4), (0.7, 1.0))),
        confidence=0.75,
        extraction_provenance=provenance,
    )


# {
# 責務: [CompositionTemplateTests: verify layout extraction and interchange behavior]
# 処理: [test contract validation, adaptation, extraction, export and library persistence]
#   フィールド: [主要状態: CompositionTemplateTestsが管理する状態]
# }
class CompositionTemplateTests(unittest.TestCase):
    """Verify the layout data contract end to end."""

    # {
    # 責務: [test_template_json_round_trip_and_unknown_field_rejection: validate portable JSON schema]
    # 処理: [roundtrip valid data and reject unknown, duplicate and invalid fields]
    #   引数: [なし: 宣言の入力値]
    #   戻り値: [None: 宣言の結果]
    # }
    def test_template_json_round_trip_and_unknown_field_rejection(self) -> None:
        template = _template()
        encoded = template_to_json(template)
        self.assertEqual(template_from_json(encoded), template)
        data = json.loads(encoded)
        data["subject_identity"] = "must never be stored"
        with self.assertRaises(ValueError):
            template_from_json(json.dumps(data))
        with self.assertRaises(ValueError):
            template_from_json('{"schema_version":1,"schema_version":1}')
        data = json.loads(encoded)
        data["depth_structure"]["measured"] = "false"
        with self.assertRaises(ValueError):
            template_from_json(json.dumps(data))

    # {
    # 責務: [test_template_contract_rejects_non_normalized_regions: guard normalized layout invariants]
    # 処理: [verify out-of-bounds boxes and non-finite horizons fail]
    #   引数: [なし: 宣言の入力値]
    #   戻り値: [None: 宣言の結果]
    # }
    def test_template_contract_rejects_non_normalized_regions(self) -> None:
        with self.assertRaises(ValueError):
            CompositionRegion("bad", RegionRole.MAIN_SUBJECT, (0.8, 0.1, 0.3, 0.2))
        with self.assertRaises(ValueError):
            HorizonLine(float("nan"))

    # {
    # 責務: [test_editor_maps_each_region_role_to_its_matching_template_collection: protect manual role edits]
    # 処理: [verify foreground/depth/subject role routing]
    #   引数: [なし: 宣言の入力値]
    #   戻り値: [None: 宣言の結果]
    # }
    def test_editor_maps_each_region_role_to_its_matching_template_collection(self) -> None:
        self.assertEqual(
            CompositionTemplateWindow._category_for_role(RegionRole.BACKGROUND),
            "background_regions",
        )
        self.assertEqual(
            CompositionTemplateWindow._category_for_role(RegionRole.MIDGROUND),
            "midground_regions",
        )
        self.assertEqual(
            CompositionTemplateWindow._category_for_role(RegionRole.MAIN_SUBJECT),
            "subject_regions",
        )

    # {
    # 責務: [test_aspect_adaptation_preserves_geometry_without_stretching: verify crop and fit transforms]
    # 処理: [check unchanged proportions, normalized clipping and attention map adaptation]
    #   引数: [なし: 宣言の入力値]
    #   戻り値: [None: 宣言の結果]
    # }
    def test_aspect_adaptation_preserves_geometry_without_stretching(self) -> None:
        template = _template()
        fit = adapt_template(template, 9 / 16, AspectPolicy.FIT)
        crop = adapt_template(template, 9 / 16, AspectPolicy.CROP)
        self.assertAlmostEqual(fit.subject_regions[0].bbox[2], template.subject_regions[0].bbox[2])
        self.assertNotEqual(crop.subject_regions[0].bbox[0], template.subject_regions[0].bbox[0])
        self.assertLessEqual(crop.subject_regions[0].bbox[0] + crop.subject_regions[0].bbox[2], 1.0)
        self.assertEqual(fit.aspect_ratio, 9 / 16)
        self.assertIsNotNone(fit.visual_weight_map)
        self.assertEqual(len(fit.visual_weight_map.rows), 2)

    # {
    # 責務: [test_smart_reflow_moves_main_region_toward_opposite_empty_space: verify layout reflow]
    # 処理: [check the subject shifts while negative space remains anchored]
    #   引数: [なし: 宣言の入力値]
    #   戻り値: [None: 宣言の結果]
    # }
    def test_smart_reflow_moves_main_region_toward_opposite_empty_space(self) -> None:
        template = _template()
        adapted = adapt_template(template, 1.5, AspectPolicy.SMART_REFLOW)
        self.assertLess(adapted.subject_regions[0].bbox[0], template.subject_regions[0].bbox[0])

    # {
    # 責務: [test_extraction_outputs_only_layout_evidence_and_marks_heuristics: verify the baseline extractor]
    # 処理: [extract one synthetic image and reject appearance-specific output fields]
    #   引数: [なし: 宣言の入力値]
    #   戻り値: [None: 宣言の結果]
    # }
    def test_extraction_outputs_only_layout_evidence_and_marks_heuristics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "synthetic.png"
            image = Image.new("RGB", (320, 240), "white")
            ImageDraw.Draw(image).ellipse((105, 30, 215, 220), fill="black")
            image.save(source)
            template = CompositionExtractionProcessor().extract(source)
        self.assertEqual(template.extraction_provenance.source_width, 320)
        self.assertIn(
            "low-confidence saliency heuristic", " ".join(template.extraction_provenance.warnings)
        )
        self.assertTrue(template.subject_regions)
        serialized = template_to_json(template).lower()
        self.assertNotIn("color", serialized)
        self.assertNotIn("identity", serialized)
        self.assertNotIn("style", serialized)

    # {
    # 責務: [test_injected_subject_pose_depth_and_perspective_adapters_are_retained: verify replaceable CV providers]
    # 処理: [pass injected subject, depth and perspective evidence through extraction]
    #   引数: [なし: 宣言の入力値]
    #   戻り値: [None: 宣言の結果]
    # }
    def test_injected_subject_pose_depth_and_perspective_adapters_are_retained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "synthetic.png"
            Image.new("RGB", (120, 80), "gray").save(source)
            subject = CompositionRegion(
                "adapter-main", RegionRole.MAIN_SUBJECT, (0.2, 0.1, 0.4, 0.8), confidence=0.9
            )
            pose = SimpleNamespace(analyze=lambda _image: ())
            depth = SimpleNamespace(
                analyze=lambda _image, _regions: DepthStructure(
                    (DepthLayer(0, ("adapter-main",), 0.8),),
                    confidence=0.8,
                    measured=True,
                )
            )
            perspective = SimpleNamespace(
                analyze=lambda _image: (HorizonLine(0.55, confidence=0.75), ())
            )
            template = CompositionExtractionProcessor().extract(
                source,
                subject_adapter=SimpleNamespace(analyze=lambda _image: (subject,)),
                pose_adapter=pose,
                depth_adapter=depth,
                perspective_adapter=perspective,
            )
        self.assertEqual(template.subject_regions, (subject,))
        self.assertTrue(template.depth_structure.measured)
        self.assertEqual(template.horizon.y, 0.55)

    # {
    # 責務: [test_library_is_reusable_and_does_not_overwrite: verify safe template library persistence]
    # 処理: [save, list, load, reject overwrite and reject unsafe identifiers]
    #   引数: [なし: 宣言の入力値]
    #   戻り値: [None: 宣言の結果]
    # }
    def test_library_is_reusable_and_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            library = TemplateLibrary(directory)
            library.save("portrait_01", _template())
            self.assertEqual(library.list_names(), ("portrait_01",))
            self.assertEqual(library.load("portrait_01"), _template())
            with self.assertRaises(FileExistsError):
                library.save("portrait_01", _template())
            with self.assertRaises(ValueError):
                library.load("../outside")

    # {
    # 責務: [test_prompt_and_downstream_guidance_contain_spatial_data: verify generic consumer exports]
    # 処理: [assert that prompt and JSON payload carry layout without identity/style claims]
    #   引数: [なし: 宣言の入力値]
    #   戻り値: [None: 宣言の結果]
    # }
    def test_prompt_and_downstream_guidance_contain_spatial_data(self) -> None:
        template = _template()
        prompt = export_prompt(template).lower()
        guidance = json.loads(export_guidance(template))
        self.assertIn("negative space", prompt)
        self.assertEqual(guidance["schema"], "comfyui-support-tools/composition-guidance/v1")
        self.assertNotIn("character", prompt)
        self.assertNotIn("style", export_guidance(template).lower())


if __name__ == "__main__":
    unittest.main()
