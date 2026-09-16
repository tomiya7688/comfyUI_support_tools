from pathlib import Path
import sys
import tempfile
import unittest

MODULE_DIR = Path(__file__).parents[3] / "tools" / "context"
sys.path.insert(0, str(MODULE_DIR))

import repo_map  # noqa: E402


class RepoMapTests(unittest.TestCase):
    def test_collects_symbols_and_imports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "sample.py"
            source.write_text(
                "import os\nfrom pathlib import Path\n\n"
                "class Demo:\n    pass\n\n"
                "def run():\n    return Path('.')\n",
                encoding="utf-8",
            )
            data = repo_map.build_repo_map(root)
            self.assertEqual(data["file_count"], 1)
            entry = data["files"][0]
            self.assertEqual(entry["path"], "sample.py")
            self.assertIn("os", entry["imports"])
            self.assertIn("pathlib", entry["imports"])
            self.assertEqual(
                [(item["name"], item["kind"]) for item in entry["symbols"]],
                [("Demo", "class"), ("run", "function")],
            )

    def test_skips_invalid_python(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
            data = repo_map.build_repo_map(root)
            self.assertEqual(data["file_count"], 0)


if __name__ == "__main__":
    unittest.main()
