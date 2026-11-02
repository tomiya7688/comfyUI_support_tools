"""Contract, detection, mask, backend, and persistence checks for Expression Retouch."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from comfyui_support_tools.applications.expression_retouch.data.messenger.retouch_data_messenger import (
    ExpressionRetouchDataEndpoint,
)
from comfyui_support_tools.applications.expression_retouch.data.processing.comfyui_backend import (
    ComfyUIExpressionBackend,
)
from comfyui_support_tools.applications.expression_retouch.data.processing.face_analysis import (
    analyze_faces,
)
from comfyui_support_tools.applications.expression_retouch.data.processing.face_mask import (
    composite_local_edit,
    create_edit_mask,
    measure_candidate_preservation,
)
from comfyui_support_tools.applications.expression_retouch.process.messenger.data_messenger import (
    ExpressionRetouchDataMessenger,
)
from comfyui_support_tools.applications.expression_retouch.process.processing.presets import (
    resolve_expression_target,
)
from comfyui_support_tools.applications.expression_retouch.process.processing.processor import (
    ExpressionRetouchProcessor,
)
from comfyui_support_tools.shared.contracts.expression_retouch import (
    DetectedFace,
    ExpressionBackendCapabilities,
    ExpressionEditRequest,
    ExpressionMode,
    ExpressionParameters,
    ExpressionPreset,
    FaceAnalysis,
    FacePart,
    FacePartRegion,
)


# {
# 責務: [_png: encode a Pillow image as PNG bytes for test inputs]
# 処理: [write to an in-memory buffer and return the encoded bytes]
# 引数: [image: source raster]
# 戻り値: [bytes: PNG data]
# }
def _png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


# {
# 責務: [_face: construct a deterministic face and part fixture]
# 処理: [create stable normalized face and part boxes]
# 引数: [index: stable face ordinal]
# 戻り値: [DetectedFace: test detector output]
# }
def _face(index: int = 0) -> DetectedFace:
    box = (0.2, 0.15, 0.6, 0.7)
    parts = (
        FacePartRegion(FacePart.FULL_FACE, (0.25, 0.18, 0.5, 0.62), 0.8),
        FacePartRegion(FacePart.LEFT_EYE, (0.32, 0.35, 0.14, 0.1), 0.7),
        FacePartRegion(FacePart.RIGHT_EYE, (0.54, 0.35, 0.14, 0.1), 0.7),
        FacePartRegion(FacePart.EYEBROWS, (0.3, 0.25, 0.4, 0.08), 0.5),
        FacePartRegion(FacePart.MOUTH, (0.4, 0.58, 0.2, 0.12), 0.6),
        FacePartRegion(FacePart.CHEEKS, (0.3, 0.5, 0.4, 0.16), 0.5),
        FacePartRegion(FacePart.TEAR_REGION, (0.3, 0.38, 0.4, 0.24), 0.4),
    )
    return DetectedFace(index, box, 0.92, parts)


# {
# 責務: [ExpressionRetouchTests: verify local editing contracts and candidate flow]
# フィールド: [unittest assertions and temporary image artifacts]
# 処理: [test face analysis, region masks, immutable compositing, routing and ComfyUI inputs]
# }
class ExpressionRetouchTests(unittest.TestCase):
    """Exercise the highest-risk expression-retouch boundaries."""

    # {
    # 責務: [test_request_rejects_unsafe_ranges_and_preset_is_stable: validate request contracts]
    # 処理: [accept known expression targets and reject invalid intensity/candidate controls]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_request_rejects_unsafe_ranges_and_preset_is_stable(self) -> None:
        source = _png(Image.new("RGB", (32, 32), "white"))
        request = ExpressionEditRequest(source, ExpressionPreset.WINK_LEFT)
        self.assertEqual(request.target.value, "wink_left")
        self.assertEqual(
            resolve_expression_target("angry but cute", ExpressionPreset.SMILE),
            ExpressionPreset.ANGRY,
        )
        self.assertEqual(
            resolve_expression_target("custom editor text", ExpressionPreset.SMILE),
            ExpressionPreset.SMILE,
        )
        with self.assertRaises(ValueError):
            ExpressionEditRequest(source, ExpressionPreset.SMILE, intensity=1.2)
        with self.assertRaises(ValueError):
            ExpressionEditRequest(source, ExpressionPreset.SMILE, candidate_count=0)
        with self.assertRaises(ValueError):
            ExpressionEditRequest(source, ExpressionPreset.SMILE, candidate_count=True)
        with self.assertRaises(ValueError):
            ExpressionEditRequest(source, ExpressionPreset.SMILE, intensity=True)
        with self.assertRaises(ValueError):
            FacePartRegion(FacePart.MOUTH, (0.1, 0.2, float("nan"), 0.2), 0.5)
        self.assertEqual(ExpressionParameters(gaze_x=-0.5).gaze_x, -0.5)
        with self.assertRaises(ValueError):
            ExpressionParameters(gaze_y=1.1)

    # {
    # 責務: [test_face_analyzer_reports_no_face_without_claiming_landmarks: validate default detector limits]
    # 処理: [run Haar cascade on a blank image and check the landmark limitation]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_face_analyzer_reports_no_face_without_claiming_landmarks(self) -> None:
        source = _png(Image.new("RGB", (128, 128), "white"))
        result = analyze_faces(source)
        self.assertEqual(result.image_size, (128, 128))
        self.assertEqual(result.faces, ())
        self.assertIn("no landmark model", result.warnings[0])

    # {
    # 責務: [test_selected_region_mask_and_composite_preserve_non_target_pixels: enforce local editing]
    # 処理: [create one mouth mask, composite a changed candidate, and compare pixels outside the mask]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_selected_region_mask_and_composite_preserve_non_target_pixels(self) -> None:
        source = _png(Image.new("RGB", (128, 128), "red"))
        face = _face()
        mask = create_edit_mask((128, 128), face, (FacePart.MOUTH,))
        with Image.open(io.BytesIO(mask)) as mask_image:
            mask_array = np.asarray(mask_image.convert("L"))
        self.assertGreater(int(mask_array.max()), 0)
        self.assertLess(int(mask_array.sum()), 128 * 128 * 255 / 3)
        candidate = _png(Image.new("RGB", (128, 128), "blue"))
        result = composite_local_edit(source, candidate, mask)
        with Image.open(io.BytesIO(result)) as edited, Image.open(io.BytesIO(source)) as original:
            edited_pixels = np.asarray(edited)
            original_pixels = np.asarray(original)
        self.assertTrue(
            np.array_equal(edited_pixels[mask_array == 0], original_pixels[mask_array == 0])
        )
        identity_proxy, locality, _limitations = measure_candidate_preservation(
            source, candidate, mask
        )
        self.assertLess(identity_proxy, 1.0)
        self.assertLess(locality, 1.0)

    # {
    # 責務: [test_processor_generates_ranked_immutable_candidates_and_history: verify full local pipeline]
    # 処理: [route two candidates through a fake masked backend and verify composite, ranking and manifest]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_processor_generates_ranked_immutable_candidates_and_history(self) -> None:
        source = _png(Image.new("RGB", (128, 128), "white"))
        face = _face()

        # {
        #   責務: [FakeBackend: provide deterministic masked image candidates]
        #   フィールド: [backend_id, capabilities]
        #   処理: [return a stable test editor without external inference]
        # }
        class FakeBackend:
            backend_id = "test_inpaint"
            capabilities = ExpressionBackendCapabilities(
                (ExpressionMode.ANIME,), True, True, True, 2048
            )

            # {
            #   責務: [edit: make one deterministic test candidate]
            #   処理: [change pixels in a mouth-adjacent rectangle and encode PNG]
            #   引数: [request: candidate settings, mask: local edit mask, seed: candidate seed]
            #   戻り値: [bytes: test candidate PNG]
            # }
            def edit(self, request, mask, seed):
                image = Image.open(io.BytesIO(request.source_image)).convert("RGB")
                pixels = ImageDraw.Draw(image)
                pixels.rectangle((50, 72, 78, 88), fill=(0, 0, int(seed or 1) % 255))
                return _png(image)

        endpoint = ExpressionRetouchDataEndpoint(
            analyzer=lambda _source: FaceAnalysis((128, 128), (face,))
        )
        processor = ExpressionRetouchProcessor(ExpressionRetouchDataMessenger(endpoint))
        processor.register_backend(FakeBackend())
        with tempfile.TemporaryDirectory() as directory:
            result = processor.retouch(
                ExpressionEditRequest(
                    source,
                    ExpressionPreset.SMILE,
                    edit_regions=(FacePart.MOUTH,),
                    candidate_count=2,
                    seed=12,
                ),
                directory,
            )
            self.assertEqual(len(result.candidates), 2)
            self.assertEqual(result.selected_candidate, 0)
            self.assertEqual(result.candidates[0].seed, 12)
            self.assertTrue((Path(directory) / result.candidates[0].image_path).is_file())
            manifest = json.loads(
                (Path(directory) / result.candidates[0].manifest_path).read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["metadata"]["target"], "smile")
            self.assertEqual(manifest["candidates"][0]["backend_id"], "test_inpaint")
            self.assertTrue(
                any("No semantic expression evaluator" in item for item in result.warnings)
            )

    # {
    # 責務: [test_comfyui_backend_uploads_source_and_mask_and_sets_controls: verify inpaint mapping]
    # 処理: [capture one fake ComfyUI request and verify prompt, two image uploads and sampler overrides]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_comfyui_backend_uploads_source_and_mask_and_sets_controls(self) -> None:
        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": "source.png"}},
            "2": {"class_type": "LoadImageMask", "inputs": {"image": "mask.png", "channel": "red"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "4": {"class_type": "KSampler", "inputs": {"seed": 1, "denoise": 0.4}},
        }
        observed = {}

        # {
        #   責務: [command: capture ComfyUI inputs and create a fake output image]
        #   処理: [record backend inputs and return a bounded temporary image path]
        #   引数: [inputs: backend payload, _context: command context]
        #   戻り値: [dict[str, str]: generated image path]
        # }
        def command(inputs, _context):
            observed.update(inputs)
            output = Path(inputs["output_dir"]) / "retouched.png"
            Image.new("RGB", (32, 32), "green").save(output)
            return {"image": str(output)}

        backend = ComfyUIExpressionBackend(
            workflow,
            image_node_id="1",
            mask_node_id="2",
            prompt_node_ids=("3",),
            seed_node_ids=("4",),
            sampler_node_id="4",
            command=command,
        )
        source = _png(Image.new("RGB", (32, 32), "white"))
        mask = _png(Image.new("L", (32, 32), 255))
        candidate = backend.edit(
            ExpressionEditRequest(
                source,
                ExpressionPreset.WINK_RIGHT,
                edit_regions=(FacePart.RIGHT_EYE, FacePart.MOUTH),
                parameters=ExpressionParameters(
                    eye_openness_right=0.15,
                    mouth_open=0.7,
                    gaze_x=-0.4,
                ),
            ),
            mask,
            88,
        )
        self.assertGreater(len(candidate), 0)
        self.assertEqual(len(observed["image_uploads"]), 2)
        self.assertEqual(observed["overrides"], {"4": {"seed": 88, "denoise": 0.35}})
        self.assertIn("wink right", observed["prompt"])
        self.assertIn("right eye, mouth", observed["prompt"])
        self.assertIn("gaze_x=-0.40", observed["prompt"])


if __name__ == "__main__":
    unittest.main()
