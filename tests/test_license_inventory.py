"""Runtime dependency license inventory checks."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.build.license_inventory import collect_license_inventory


ROOT = Path(__file__).resolve().parents[1]


class LicenseInventoryTests(unittest.TestCase):
    def test_copies_runtime_license_files_and_records_resolved_versions(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory)
            manifest = collect_license_inventory(ROOT, target)

            names = {item["name"].lower().replace("_", "-") for item in manifest["components"]}
            self.assertTrue({"python", "tcl/tk", "numpy", "pillow", "opencv-python-headless", "requests", "psutil"}.issubset(names))
            for component in manifest["components"]:
                self.assertTrue(component["version"])
                self.assertTrue(component["license_files"])
                for relative_path in component["license_files"]:
                    self.assertTrue((target / relative_path).is_file(), relative_path)

            resolved_file = target / "third_party_components.resolved.json"
            self.assertEqual(json.loads(resolved_file.read_text(encoding="utf-8")), manifest)
            copied_names = [Path(path).name for entry in manifest["components"] for path in entry["license_files"]]
            self.assertIn("LICENSE-3RD-PARTY.txt", copied_names)
            self.assertIn("license.terms", copied_names)


if __name__ == "__main__":
    unittest.main()
