from __future__ import annotations

import re
import unittest
from pathlib import Path

from scripts.context import _default_user_paths


# {
#   責務: [
#     ContextPathDefaultsTest: 既定パスが配置先に追従することを検証する
#   ]
#   フィールド: []
# }
class ContextPathDefaultsTest(unittest.TestCase):
    # {
    #   責務: [
    #     test_defaults_follow_the_application_directory: 指定した配置先が各既定パスへ反映されることを検証する
    #   ]
    #   処理: [
    #     1: 仮のアプリ配置先で既定パスを構築する
    #     2: アプリ本体・ComfyUI・Downloaderのパスを比較する
    #   ]
    #   引数: [
    #     self: unittestのテストケース
    #   ]
    #   戻り値: []
    # }
    def test_defaults_follow_the_application_directory(self):
        app_dir = Path("R:/portable/tools")

        paths = _default_user_paths(app_dir)

        self.assertEqual(paths["sd_root"], str(app_dir))
        self.assertEqual(paths["nuno_touka_dir"], str(app_dir / "nuno" / "_touka"))
        self.assertEqual(
            paths["comfyui_dir"],
            str(app_dir / "external" / "ComfyUI"),
        )
        self.assertEqual(
            paths["youtube_downloader_dir"],
            str(app_dir / "external" / "youtubez_downloader"),
        )

    # {
    #   責務: [
    #     test_defaults_contain_no_machine_drive_roots: 固定ドライブに依存しないことを検証する
    #   ]
    #   処理: [
    #     1: 仮のアプリ配置先で既定パスを構築する
    #     2: ドライブ絶対パスが仮配置先以外を参照しないことを確認する
    #   ]
    #   引数: [
    #     self: unittestのテストケース
    #   ]
    #   戻り値: []
    # }
    def test_defaults_contain_no_machine_drive_roots(self):
        paths = _default_user_paths(Path("R:/portable/tools"))

        drive_paths = [value for value in paths.values() if re.match(r"^[A-Za-z]:[\\/]", value)]
        self.assertTrue(all(value.startswith("R:") for value in drive_paths))


if __name__ == "__main__":
    unittest.main()
