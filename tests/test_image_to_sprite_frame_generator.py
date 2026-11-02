from __future__ import annotations

import io
import unittest

from PIL import Image

from comfyui_support_tools.shared.pixel_sprite.contracts import SpriteDirection, SpriteFrameSpec
from scripts.backend.generation_capabilities import GenerationCapabilities
from scripts.backend.image_to_sprite_frame_generator import ImageToSpriteFrameGenerator


# {
# 責務: [ImageToSpriteFrameGeneratorTests: img2img host adapterのrequest/responseを検証する]
# フィールド: [backend stub]
# 処理: [canonical input、direction/action conditioning、decoded outputを確認する]
# }
class ImageToSpriteFrameGeneratorTests(unittest.TestCase):
    # {
    # 責務: [test_adapter_conditions_on_canonical_and_pose_then_decodes_output: backend requestを確認する]
    # 処理: [1: fake img2img adapterを呼ぶ, 2: temporary canonicalとcondition/outputを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_adapter_conditions_on_canonical_and_pose_then_decodes_output(self) -> None:
        # {
        # 責務: [Backend: img2img adapter integration fixtureを提供する]
        # フィールド: [img2img capability, captured request]
        # 処理: [temporary image pathを検証してPNG candidateを返す]
        # }
        class Backend:
            # {
            # 責務: [__init__: img2img test capabilityとrequest stateを初期化する]
            # 処理: [backend requestの保存領域を作る]
            # 引数: [self: backend stub]
            # 戻り値: []
            # }
            def __init__(self) -> None:
                self.capabilities = GenerationCapabilities(frozenset({"img2img"}))
                self.request = None

            # {
            # 責務: [generate_from_image: test image bytesを返す]
            # 処理: [temporary input存在確認とrequest captureを行う]
            # 引数: [self: backend stub, request: img2img input]
            # 戻り値: [PNG bytes]
            # }
            def generate_from_image(self, request):
                self.request = request
                self.assert_input_exists = request.image_path.is_file()
                stream = io.BytesIO()
                Image.new("RGBA", (12, 12), (200, 20, 20, 255)).save(stream, format="PNG")
                return stream.getvalue()

        backend = Backend()
        adapter = ImageToSpriteFrameGenerator(
            "http://localhost", 30, checkpoint="test", backend=backend
        )
        spec = SpriteFrameSpec(
            "walk", SpriteDirection.FRONT_RIGHT, 1, 4, 0.25, "right foot forward"
        )
        output = adapter.generate(Image.new("RGBA", (16, 16), "red"), spec, "tiny knight")
        self.assertTrue(backend.assert_input_exists)
        self.assertEqual(output.size, (12, 12))
        self.assertIn("front right direction", backend.request.prompt)
        self.assertIn("right foot forward", backend.request.prompt)
        self.assertEqual(backend.request.denoise, 0.45)


if __name__ == "__main__":
    unittest.main()
