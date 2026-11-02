from __future__ import annotations

import unittest

from comfyui_support_tools.shared.face_style.contracts import BangsPolicy, FaceStyleTarget


# {
# 責務: [FaceStyleContractTests: face style targetの整合性を検証する]
# フィールド: [なし]
# 処理: [髪保護と前髪編集の衝突を検出する]
# }
class FaceStyleContractTests(unittest.TestCase):
    # {
    # 責務: [test_target_rejects_conflicting_hair_controls: 相反する髪設定を拒否する]
    # 処理: [1: preserve hairとinclude bangsを同時指定する, 2: ValueErrorを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_target_rejects_conflicting_hair_controls(self) -> None:
        with self.assertRaises(ValueError):
            FaceStyleTarget(preserve_hair=True, bangs_policy=BangsPolicy.INCLUDE)


if __name__ == "__main__":
    unittest.main()
