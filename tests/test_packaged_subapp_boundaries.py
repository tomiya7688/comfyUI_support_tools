from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class PackagedSubAppBoundaryTests(unittest.TestCase):
    def test_touka_tab_has_no_python_or_external_layout_dependency(self):
        source = (ROOT / "scripts" / "tabs" / "touka_enhancer.py").read_text(encoding="utf-8")
        for forbidden in ("venv_python", "sys.executable", "NUNO_TOUKA_DIR", "touka_batch.py", "image_enhancer.py"):
            self.assertNotIn(forbidden, source)

    def test_youtube_tab_has_no_python_or_external_layout_dependency(self):
        source = (ROOT / "scripts" / "tabs" / "youtube_downloader.py").read_text(encoding="utf-8")
        for forbidden in ("venv_python", "sys.executable", "YOUTUBE_DOWNLOADER_DIR", "youtube_dl.py"):
            self.assertNotIn(forbidden, source)

    def test_tabs_resolve_packaged_executables(self):
        touka = (ROOT / "scripts" / "tabs" / "touka_enhancer.py").read_text(encoding="utf-8")
        youtube = (ROOT / "scripts" / "tabs" / "youtube_downloader.py").read_text(encoding="utf-8")
        self.assertIn('packaged_executable("Touka")', touka)
        self.assertIn('packaged_executable("ToukaEditor")', touka)
        self.assertIn('packaged_executable("ToukaFashionpediaPresets")', touka)
        self.assertIn('packaged_executable("YouTubeDownloader")', youtube)


if __name__ == "__main__":
    unittest.main()
