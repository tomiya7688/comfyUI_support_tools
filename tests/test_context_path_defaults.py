from __future__ import annotations

import re
import unittest
from pathlib import Path

from scripts.context import _default_user_paths


class ContextPathDefaultsTest(unittest.TestCase):
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

    def test_defaults_contain_no_machine_drive_roots(self):
        paths = _default_user_paths(Path("R:/portable/tools"))

        drive_paths = [
            value
            for value in paths.values()
            if re.match(r"^[A-Za-z]:[\\/]", value)
        ]
        self.assertTrue(all(value.startswith("R:") for value in drive_paths))


if __name__ == "__main__":
    unittest.main()
