import unittest

import numpy as np
from PIL import Image

from image_enhancer import EnhanceSettings, _curve_lut, process_image


# {
#   責務: [ProcessingTests: image enhancement processing behaviorを確認するunit testsをまとめる]
#   処理: [RGBA sample imageを共有fixtureとして使いpixel output contractsを検証する]
#   フィールド: [image: test input image]
# }
class ProcessingTests(unittest.TestCase):
    # {
    #   責務: [setUp: each test用のRGBA fixture imageを作成する]
    #   処理: [base pixels and one semi-transparent accent pixelを初期化する]
    #   引数: [self]
    #   戻り値: [None]
    # }
    def setUp(self):
        self.image = Image.new("RGBA", (12, 10), (80, 100, 120, 173))
        self.image.putpixel((2, 3), (240, 20, 30, 91))

    # {
    #   責務: [test_identity_normal_blend_preserves_image: identity settingsでpixel valuesが保持されることを確認する]
    #   処理: [full opacity, normal blend output and input RGBA arraysを比較する]
    #   引数: [self]
    #   戻り値: [None]
    # }
    def test_identity_normal_blend_preserves_image(self):
        out = process_image(self.image, EnhanceSettings(opacity=100))
        self.assertEqual(np.asarray(out).tolist(), np.asarray(self.image).tolist())

    # {
    #   責務: [test_curves_and_adjustments_keep_shape_alpha: adjustments後もimage dimensions and alpha channelが保持されることを確認する]
    #   処理: [curve, contrast, highlights, shadows, detail, opacityを併用しRGB valuesの変化も確認する]
    #   引数: [self]
    #   戻り値: [None]
    # }
    def test_curves_and_adjustments_keep_shape_alpha(self):
        settings = EnhanceSettings(master_curve=[(0, 0), (.5, .8), (1, 1)], contrast=60,
                                   highlights=-35, shadows=40, detail=50, opacity=75)
        out = process_image(self.image, settings)
        self.assertEqual(out.size, self.image.size)
        self.assertTrue(np.array_equal(np.asarray(out)[..., 3], np.asarray(self.image)[..., 3]))
        self.assertTrue(np.any(np.asarray(out)[..., :3] != np.asarray(self.image)[..., :3]))

    # {
    #   責務: [test_all_blend_modes_and_repeated_passes: supported blend modesがrepeated passesを含めRGBA outputを返すことを確認する]
    #   処理: [six blend mode settingsを順に処理しmode and sizeをassertする]
    #   引数: [self]
    #   戻り値: [None]
    # }
    def test_all_blend_modes_and_repeated_passes(self):
        for mode in ("Normal", "Darken", "Lighten", "Multiply", "Screen", "Overlay"):
            out = process_image(self.image, EnhanceSettings(blend_mode=mode, opacity=55, passes=3))
            self.assertEqual((out.mode, out.size), ("RGBA", self.image.size))

    # {
    #   責務: [test_curve_lut_endpoints: identity curve lookup tableが入力端点を保持することを確認する]
    #   処理: [0..1 identity control pointsからLUTを作成し0 and 255 endpointsを検証する]
    #   引数: [self]
    #   戻り値: [None]
    # }
    def test_curve_lut_endpoints(self):
        lut = _curve_lut([(0, 0), (1, 1)])
        self.assertEqual((int(lut[0]), int(lut[-1])), (0, 255))


if __name__ == "__main__":
    unittest.main()
