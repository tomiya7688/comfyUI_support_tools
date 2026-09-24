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
            self.assertTrue(all(item["distribution_status"] in {"bundled", "bundled-component"} for item in manifest["components"]))
            by_name = {item["name"]: item for item in manifest["components"]}
            bootloader = by_name["PyInstaller bootloader"]
            runtime_hooks = by_name["PyInstaller runtime hooks"]
            self.assertEqual(bootloader["license_metadata"], "GPL-2.0-or-later WITH Bootloader-exception")
            self.assertEqual(runtime_hooks["license_metadata"], "Apache-2.0")
            self.assertEqual(bootloader["version"], runtime_hooks["version"])
            self.assertIn("COPYING.txt", [Path(path).name for path in bootloader["license_files"]])
            self.assertEqual(manifest["schema_version"], 2)
            external = {item["name"]: item for item in manifest["external_components"]}
            expected_external = {"ComfyUI", "WebUI1111", "PixAI Tagger", "TagGUI", "Ollama", "FFmpeg", "7-Zip", "AI model weights"}
            self.assertTrue(expected_external.issubset(external))
            self.assertTrue(all(item["distribution_status"] == "external-only" for item in external.values()))
            self.assertTrue(all(item["version"] is None and item["license_metadata"] is None for item in external.values()))
            self.assertTrue(all(item["audit_status"] == "not-audited-by-this-artifact" for item in external.values()))
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
