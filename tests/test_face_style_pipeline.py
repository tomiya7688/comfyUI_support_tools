from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from comfyui_support_tools.shared.face_style.contracts import (
    FaceRegion,
    FaceSelection,
    FaceStyleMetrics,
    FaceStyleRequest,
    FaceStyleTarget,
)
from comfyui_support_tools.shared.face_style.pipeline import (
    CallableFaceStyleBackend,
    CallableFaceStyleEvaluator,
    FaceStyleService,
)


# {
# 責務: [mask_at: face style retouchの処理または検証を行う]
# 処理: [1: 入力を検証する, 2: 結果を返す]
# 引数: [box, size]
# 戻り値: [処理結果]
# }
def mask_at(box: tuple[int, int, int, int], size: tuple[int, int] = (16, 12)) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rectangle(box, fill=255)
    return mask


# {
# 責務: [FaceStylePipelineTests: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
class FaceStylePipelineTests(unittest.TestCase):
    # {
    # 責務: [setUp: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def setUp(self) -> None:
        self.source = Image.new("RGB", (16, 12), "white")
        self.faces = (
            FaceRegion("left", mask_at((1, 2, 4, 6)), mask_at((1, 2, 2, 3)), 0.98),
            FaceRegion("right", mask_at((10, 2, 13, 6)), confidence=0.99),
        )
        self.target = FaceStyleTarget(era="retro anime")

    # {
    # 責務: [test_no_backend_does_not_invent_a_result: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_no_backend_does_not_invent_a_result(self) -> None:
        result = FaceStyleService().run(FaceStyleRequest(self.source, self.target, self.faces))
        self.assertEqual(result.candidates, ())
        self.assertIsNone(result.selected_index)
        self.assertIn("No face-style editing backend", result.warnings[0])

    # {
    # 責務: [test_default_main_face_selection_preserves_hair_and_outside_pixels: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_default_main_face_selection_preserves_hair_and_outside_pixels(self) -> None:
        # {
        # 責務: [edit: face style retouchの処理または検証を行う]
        # 処理: [1: 入力を検証する, 2: 結果を返す]
        # 引数: [image, mask, target, prompt]
        # 戻り値: [処理結果]
        # }
        def edit(image: Image.Image, mask: Image.Image, target: object, prompt: str) -> Image.Image:
            image.paste("red", (0, 0, *image.size))
            return image

        metrics = FaceStyleMetrics(0.9, 0.95, 0.96, 0.97, 0.95, 1.0)
        service = FaceStyleService(
            [CallableFaceStyleBackend("test", edit)],
            evaluator=CallableFaceStyleEvaluator(lambda *args: metrics),
        )
        result = service.run(FaceStyleRequest(self.source, self.target, self.faces))
        self.assertEqual(result.candidates[0].face_ids, ("left",))
        candidate = result.candidates[0].image
        self.assertEqual(candidate.getpixel((0, 0)), self.source.getpixel((0, 0)))
        self.assertEqual(candidate.getpixel((3, 5)), (255, 0, 0))
        self.assertEqual(candidate.getpixel((2, 3)), self.source.getpixel((2, 3)))
        self.assertEqual(result.selected_index, 0)

    # {
    # 責務: [test_all_faces_share_one_target_and_low_confidence_fails_closed: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_all_faces_share_one_target_and_low_confidence_fails_closed(self) -> None:
        backend = CallableFaceStyleBackend("test", lambda image, mask, target, prompt: image)
        evaluator = CallableFaceStyleEvaluator(
            lambda *args: FaceStyleMetrics(0.9, 0.9, 0.9, 0.9, 0.9, 1.0)
        )
        service = FaceStyleService([backend], evaluator=evaluator)
        all_faces = FaceStyleRequest(
            self.source, self.target, self.faces, selection=FaceSelection.ALL
        )
        self.assertEqual(service.run(all_faces).candidates[0].face_ids, ("left", "right"))
        uncertain = FaceRegion("uncertain", mask_at((1, 2, 4, 6)), confidence=0.2)
        result = service.run(FaceStyleRequest(self.source, self.target, (uncertain,)))
        self.assertFalse(result.candidates)
        self.assertIn("below", result.warnings[0])

    # {
    # 責務: [test_style_and_gaze_must_both_pass_before_candidate_acceptance: styleとgaze評価を独立して検証する]
    # 処理: [1: style未達candidateを評価, 2: gaze未計測candidateを評価, 3: いずれも未承認を確認]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_style_and_gaze_must_both_pass_before_candidate_acceptance(self) -> None:
        backend = CallableFaceStyleBackend("test", lambda image, mask, target, prompt: image)
        for metrics in (
            FaceStyleMetrics(0.2, 0.95, 0.96, 0.97, 0.95, 1.0),
            FaceStyleMetrics(0.95, 0.95, 0.96, 0.97, None, 1.0),
        ):
            service = FaceStyleService(
                [backend],
                evaluator=CallableFaceStyleEvaluator(lambda *args, metrics=metrics: metrics),
            )
            result = service.run(FaceStyleRequest(self.source, self.target, self.faces))
            self.assertIsNone(result.selected_index)
            self.assertFalse(result.candidates[0].accepted)

    # {
    # 責務: [test_target_rejects_conflicting_hair_controls: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }


if __name__ == "__main__":
    unittest.main()
