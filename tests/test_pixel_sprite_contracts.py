from __future__ import annotations

import unittest

from PIL import Image

from comfyui_support_tools.shared.pixel_sprite.contracts import (
    SpriteAction,
    SpriteDirection,
    SpriteSequenceRequest,
)
from comfyui_support_tools.shared.pixel_sprite.pipeline import make_frame_specs


# {
# 責務: [PixelSpriteContractTests: direction/frame budget contractsを検証する]
# フィールド: [canonical image fixture]
# 処理: [1/4/8方向、pose instruction、frame/pixel safety boundaryを確認する]
# }
class PixelSpriteContractTests(unittest.TestCase):
    # {
    # 責務: [test_eight_direction_custom_pose_specs_and_bounds: 8方向pose scheduleと入力上限を検証する]
    # 処理: [1: 8方向2 action scheduleを解決する, 2: invalid direction/frame budgetを拒否する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_eight_direction_custom_pose_specs_and_bounds(self) -> None:
        canonical = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        request = SpriteSequenceRequest(
            canonical=canonical,
            prompt="sprite character",
            directions=tuple(SpriteDirection),
            actions=(SpriteAction.WALK, SpriteAction.ATTACK),
            frames_per_action=4,
            pose_instructions=(("walk", "front", 1, "left foot forward"),),
            cell_width=16,
            cell_height=16,
            output_directory="unused",
        )
        specs = make_frame_specs(request)
        self.assertEqual(len(specs), 64)
        self.assertEqual(specs[0].phase, 0.0)
        front_walk = next(
            spec
            for spec in specs
            if spec.action == "walk" and spec.direction is SpriteDirection.FRONT and spec.index == 1
        )
        self.assertEqual(front_walk.pose_instruction, "left foot forward")
        with self.assertRaisesRegex(ValueError, "1, 4, or 8"):
            SpriteSequenceRequest(
                canonical,
                "sprite",
                directions=(SpriteDirection.FRONT, SpriteDirection.RIGHT),
            )
        with self.assertRaisesRegex(ValueError, "256 frames"):
            SpriteSequenceRequest(
                canonical,
                "sprite",
                directions=tuple(SpriteDirection),
                actions=("walk", "run", "attack", "hurt"),
                frames_per_action=9,
            )
        with self.assertRaisesRegex(ValueError, "action identifiers"):
            SpriteSequenceRequest(canonical, "sprite", actions=("../../unsafe",))

    # {
    # 責務: [test_rejects_non_integer_layout_and_invalid_background: image/layoutのruntime typeを検証する]
    # 処理: [1: 型不正frame/layout値を指定, 2: contract境界で拒否することを確認]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_rejects_non_integer_layout_and_invalid_background(self) -> None:
        canonical = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        for options, message in (
            ({"frames_per_action": 1.5}, "frames_per_action"),
            ({"fps": True}, "fps"),
            ({"columns": -1}, "columns"),
            ({"background": (0, 0, 0)}, "background"),
            ({"background": (0, 0, 0, 256)}, "background"),
        ):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, message):
                SpriteSequenceRequest(canonical, "sprite", **options)


if __name__ == "__main__":
    unittest.main()
