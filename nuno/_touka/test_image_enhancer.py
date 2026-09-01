import unittest

import numpy as np
from PIL import Image

from image_enhancer import EnhanceSettings, _curve_lut, process_image


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGBA", (12, 10), (80, 100, 120, 173))
        self.image.putpixel((2, 3), (240, 20, 30, 91))

    def test_identity_normal_blend_preserves_image(self):
        out = process_image(self.image, EnhanceSettings(opacity=100))
        self.assertEqual(np.asarray(out).tolist(), np.asarray(self.image).tolist())

    def test_curves_and_adjustments_keep_shape_alpha(self):
        settings = EnhanceSettings(master_curve=[(0, 0), (.5, .8), (1, 1)], contrast=60,
                                   highlights=-35, shadows=40, detail=50, opacity=75)
        out = process_image(self.image, settings)
        self.assertEqual(out.size, self.image.size)
        self.assertTrue(np.array_equal(np.asarray(out)[..., 3], np.asarray(self.image)[..., 3]))
        self.assertTrue(np.any(np.asarray(out)[..., :3] != np.asarray(self.image)[..., :3]))

    def test_all_blend_modes_and_repeated_passes(self):
        for mode in ("Normal", "Darken", "Lighten", "Multiply", "Screen", "Overlay"):
            out = process_image(self.image, EnhanceSettings(blend_mode=mode, opacity=55, passes=3))
            self.assertEqual((out.mode, out.size), ("RGBA", self.image.size))

    def test_curve_lut_endpoints(self):
        lut = _curve_lut([(0, 0), (1, 1)])
        self.assertEqual((int(lut[0]), int(lut[-1])), (0, 255))


if __name__ == "__main__":
    unittest.main()
