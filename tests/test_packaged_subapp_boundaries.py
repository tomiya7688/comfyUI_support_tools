from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


# {
#   責務: [PackagedSubAppBoundaryTests: related test fixtures and cases for PackagedSubAppBoundary behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class PackagedSubAppBoundaryTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_touka_tab_has_no_python_or_external_layout_dependency: verifies the behavior described by "touka tab has no python or external layout dependency",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for touka tab has no python or external layout dependency,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_touka_tab_has_no_python_or_external_layout_dependency(self):
        source = (ROOT / "scripts" / "tabs" / "touka_enhancer.py").read_text(encoding="utf-8")
        for forbidden in ("venv_python", "sys.executable", "NUNO_TOUKA_DIR", "touka_batch.py", "image_enhancer.py"):
            self.assertNotIn(forbidden, source)

    # {
    #   責務: [
    #     test_youtube_tab_has_no_python_or_external_layout_dependency: verifies the behavior described by "youtube tab has no python or external layout dependency",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for youtube tab has no python or external layout dependency,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_youtube_tab_has_no_python_or_external_layout_dependency(self):
        source = (ROOT / "scripts" / "tabs" / "youtube_downloader.py").read_text(encoding="utf-8")
        for forbidden in ("venv_python", "sys.executable", "YOUTUBE_DOWNLOADER_DIR", "youtube_dl.py"):
            self.assertNotIn(forbidden, source)

    # {
    #   責務: [
    #     test_tabs_resolve_packaged_executables: verifies the behavior described by "tabs resolve packaged executables",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for tabs resolve packaged executables,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_tabs_resolve_packaged_executables(self):
        touka = (ROOT / "scripts" / "tabs" / "touka_enhancer.py").read_text(encoding="utf-8")
        youtube = (ROOT / "scripts" / "tabs" / "youtube_downloader.py").read_text(encoding="utf-8")
        self.assertIn('packaged_executable("Touka")', touka)
        self.assertIn('packaged_executable("ToukaEditor")', touka)
        self.assertIn('packaged_executable("ToukaFashionpediaPresets")', touka)
        self.assertIn('packaged_executable("YouTubeDownloader")', youtube)


if __name__ == "__main__":
    unittest.main()
