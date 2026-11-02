"""Focused processor tests for semantic candidate ranking."""

from __future__ import annotations

import io
import tempfile
import unittest

from PIL import Image

from comfyui_support_tools.applications.expression_retouch.data.messenger.retouch_data_messenger import (
    ExpressionRetouchDataEndpoint,
)
from comfyui_support_tools.applications.expression_retouch.process.messenger.data_messenger import (
    ExpressionRetouchDataMessenger,
)
from comfyui_support_tools.applications.expression_retouch.process.processing.processor import (
    ExpressionRetouchProcessor,
)
from comfyui_support_tools.shared.contracts.expression_retouch import (
    DetectedFace,
    ExpressionBackendCapabilities,
    ExpressionEditRequest,
    ExpressionEvaluation,
    ExpressionMode,
    ExpressionPreset,
    FaceAnalysis,
    FacePart,
    FacePartRegion,
)


# {
# 責務: [ExpressionRetouchProcessorTests: verify semantic evaluator signals determine persisted rank]
# フィールド: [none: use deterministic local image and backend fixtures]
# 処理: [run candidate generation through the processor and assert the highest semantic score ranks first]
# 引数: [None: unittest fixture]
# 戻り値: [None: tests report processor ranking behavior]
# }
class ExpressionRetouchProcessorTests(unittest.TestCase):
    # {
    # 責務: [test_semantic_match_ranks_candidates_ahead_of_lower_match: verify ranked candidate ordering]
    # 処理: [synthesize candidates with distinct measurable pixel cues and return corresponding evaluator scores]
    # 引数: [self: test case]
    # 戻り値: [None: saved candidate order follows semantic ranking]
    # }
    def test_semantic_match_ranks_candidates_ahead_of_lower_match(self):
        output = io.BytesIO()
        Image.new("RGB", (128, 128), "white").save(output, format="PNG")
        source = output.getvalue()
        face = DetectedFace(
            0,
            (0.15, 0.1, 0.7, 0.8),
            0.95,
            (FacePartRegion(FacePart.MOUTH, (0.38, 0.55, 0.24, 0.15), 0.8),),
        )

        # {
        # 責務: [Backend: generate deterministic color-coded expression candidates]
        # フィールド: [backend_id, capabilities]
        # 処理: [edit the selected region using a seed-specific pixel cue]
        # }
        class Backend:
            backend_id = "test_inpaint"
            capabilities = ExpressionBackendCapabilities(
                (ExpressionMode.ANIME,), True, True, True, 1024
            )

            # {
            # 責務: [edit: return one candidate whose blue channel represents its seed]
            # 処理: [create deterministic local test pixels]
            # 引数: [request: edit request, mask: edit mask, seed: generation seed]
            # 戻り値: [bytes: encoded candidate image]
            # }
            def edit(self, request, mask, seed):
                image = Image.open(io.BytesIO(request.source_image)).convert("RGB")
                image.putpixel((64, 80), (0, 0, int(seed or 0)))
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                return buffer.getvalue()

        # {
        # 責務: [Evaluator: provide a deterministic semantic score for each candidate]
        # フィールド: [none: the score derives from candidate pixels]
        # 処理: [translate the fixture's blue-channel cue to measured expression match]
        # }
        class Evaluator:
            # {
            # 責務: [evaluate: derive a deterministic semantic match score from candidate pixels]
            # 処理: [map the candidate seed cue to a normalized expression score]
            # 引数: [request: request, face: selected face, source: source image, candidate: raw result, mask: selected region]
            # 戻り値: [ExpressionEvaluation: measured semantic match and preservation]
            # }
            def evaluate(self, request, face, source, candidate, mask):
                with Image.open(io.BytesIO(candidate)) as image:
                    score = image.convert("RGB").getpixel((64, 80))[2] / 255
                return ExpressionEvaluation(score, 0.9, 0.9, 0.9)

        endpoint = ExpressionRetouchDataEndpoint(
            analyzer=lambda _image: FaceAnalysis((128, 128), (face,))
        )
        processor = ExpressionRetouchProcessor(
            ExpressionRetouchDataMessenger(endpoint), Evaluator()
        )
        processor.register_backend(Backend())
        with tempfile.TemporaryDirectory() as workspace:
            result = processor.retouch(
                ExpressionEditRequest(
                    source,
                    ExpressionPreset.SMILE,
                    edit_regions=(FacePart.MOUTH,),
                    candidate_count=2,
                    seed=30,
                ),
                workspace,
            )
        self.assertEqual(result.candidates[0].seed, 31)
        self.assertGreater(
            result.candidates[0].evaluation.expression_match,
            result.candidates[1].evaluation.expression_match,
        )


if __name__ == "__main__":
    unittest.main()
