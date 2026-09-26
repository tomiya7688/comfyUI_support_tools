"""Runtime dependency license inventory checks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.build.license_inventory import _python_native_components, collect_license_inventory


ROOT = Path(__file__).resolve().parents[1]


class LicenseInventoryTests(unittest.TestCase):
    def test_classifies_python_bundled_native_libraries_separately(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            distribution = Path(temporary_directory)
            for filename in ("libcrypto-1_1.dll", "libssl-1_1.dll", "libffi-7.dll", "_bz2.pyd", "_lzma.pyd", "_decimal.pyd", "pyexpat.pyd", "VCRUNTIME140.dll"):
                (distribution / filename).touch()

            with patch("ssl.OPENSSL_VERSION", "OpenSSL 1.1.1t 7 Feb 2023"):
                components = _python_native_components(distribution, "licenses/Python/LICENSE.txt", "3.10.11")

        by_name = {item["name"]: item for item in components}
        self.assertEqual(set(by_name), {"OpenSSL", "libffi", "bzip2", "XZ Utils liblzma", "libmpdec", "Expat", "Microsoft Visual C++ Runtime"})
        self.assertEqual(by_name["OpenSSL"]["version"], "1.1.1t")
        self.assertEqual(by_name["OpenSSL"]["license_files"], ["licenses/Python/LICENSE.txt"])
        self.assertEqual(by_name["libffi"]["version"], "3.3.0")
        self.assertEqual(by_name["libffi"]["version_source_urls"], [
            "https://github.com/python/cpython/blob/v3.10.11/PCbuild/python.props",
            "https://github.com/python/cpython/blob/v3.10.11/PCbuild/get_externals.bat",
        ])
        self.assertEqual(by_name["libffi"]["license_files"], ["licenses/Python/LICENSE.txt"])
        self.assertEqual(by_name["bzip2"]["version"], "1.0.8")
        self.assertEqual(by_name["bzip2"]["license_files"], ["licenses/Python/LICENSE.txt"])
        self.assertEqual(by_name["bzip2"]["version_source_urls"], [
            "https://github.com/python/cpython/blob/v3.10.11/PCbuild/readme.txt",
            "https://github.com/python/cpython/blob/v3.10.11/PCbuild/python.props",
        ])
        self.assertEqual(by_name["XZ Utils liblzma"]["version"], "5.2.5")
        self.assertEqual(by_name["XZ Utils liblzma"]["license_files"], [])
        self.assertEqual(by_name["XZ Utils liblzma"]["license_reference_urls"], [
            "https://raw.githubusercontent.com/tukaani-project/xz/v5.2.5/COPYING",
        ])
        self.assertEqual(by_name["XZ Utils liblzma"]["audit_status"], "compiled-binary-toolchain-scope-review-required")
        self.assertEqual(by_name["libmpdec"]["version"], "2.5.1")
        self.assertEqual(by_name["libmpdec"]["license_files"], ["licenses/Python/LICENSE.txt", "licenses/libmpdec/LICENSE.txt"])
        self.assertEqual(by_name["libmpdec"]["version_source_urls"], [
            "https://github.com/python/cpython/issues/85541",
            "https://github.com/python/cpython/tree/v3.10.11/Modules/_decimal/libmpdec",
        ])
        self.assertEqual(by_name["Expat"]["version"], "2.5.0")
        self.assertEqual(by_name["Expat"]["license_files"], ["licenses/Python/LICENSE.txt", "licenses/expat/LICENSE.txt"])
        self.assertEqual(by_name["Expat"]["version_source_urls"], [
            "https://raw.githubusercontent.com/python/cpython/v3.10.11/Modules/expat/expat.h",
        ])
        self.assertEqual(by_name["Microsoft Visual C++ Runtime"]["audit_status"], "redistribution-terms-review-required")
        self.assertEqual(by_name["Microsoft Visual C++ Runtime"]["license_files"], [])

    def test_keeps_libffi_version_unresolved_for_unverified_python_builds(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            distribution = Path(temporary_directory)
            (distribution / "libffi-7.dll").touch()
            components = _python_native_components(distribution, "licenses/Python/LICENSE.txt", "3.14.0")

        self.assertIsNone(components[0]["version"])
        self.assertEqual(components[0]["audit_status"], "upstream-version-unresolved")

    def test_keeps_liblzma_version_unresolved_for_unverified_python_builds(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            distribution = Path(temporary_directory)
            (distribution / "_lzma.pyd").touch()
            components = _python_native_components(distribution, "licenses/Python/LICENSE.txt", "3.14.0")

        self.assertIsNone(components[0]["version"])
        self.assertIsNone(components[0]["license_metadata"])
        self.assertEqual(components[0]["audit_status"], "upstream-version-unresolved")

    def test_keeps_libmpdec_version_unresolved_for_unverified_python_builds(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            distribution = Path(temporary_directory)
            (distribution / "_decimal.pyd").touch()
            components = _python_native_components(distribution, "licenses/Python/LICENSE.txt", "3.14.0")

        self.assertIsNone(components[0]["version"])
        self.assertIsNone(components[0]["license_metadata"])
        self.assertEqual(components[0]["license_files"], [])
        self.assertEqual(components[0]["audit_status"], "upstream-version-unresolved")

    def test_keeps_expat_version_unresolved_for_unverified_python_builds(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            distribution = Path(temporary_directory)
            (distribution / "pyexpat.pyd").touch()
            components = _python_native_components(distribution, "licenses/Python/LICENSE.txt", "3.14.0")

        self.assertIsNone(components[0]["version"])
        self.assertIsNone(components[0]["license_metadata"])
        self.assertEqual(components[0]["license_files"], [])
        self.assertEqual(components[0]["audit_status"], "upstream-version-unresolved")

    def test_copies_runtime_license_files_and_records_resolved_versions(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory)
            executable = target / "KadokaTools.exe"
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_bytes(b"test executable")
            extension = target / "cv2" / "native.pyd"
            extension.parent.mkdir(parents=True)
            extension.write_bytes(b"test native extension")
            (target / "_decimal.pyd").write_bytes(b"test decimal extension")
            (target / "pyexpat.pyd").write_bytes(b"test expat extension")
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
            libmpdec = by_name["libmpdec"]
            self.assertEqual(libmpdec["version"], "2.5.1")
            self.assertEqual(libmpdec["license_files"], ["licenses/Python/LICENSE.txt", "licenses/libmpdec/LICENSE.txt"])
            self.assertTrue((target / "licenses" / "libmpdec" / "LICENSE.txt").is_file())
            expat = by_name["Expat"]
            self.assertEqual(expat["version"], "2.5.0")
            self.assertEqual(expat["license_files"], ["licenses/Python/LICENSE.txt", "licenses/expat/LICENSE.txt"])
            self.assertTrue((target / "licenses" / "expat" / "LICENSE.txt").is_file())
            self.assertIn("COPYING.txt", [Path(path).name for path in bootloader["license_files"]])
            native = {item["path"]: item for item in manifest["native_artifacts"]}
            self.assertEqual(native["KadokaTools.exe"]["size_bytes"], len(b"test executable"))
            self.assertEqual(native["cv2/native.pyd"]["audit_status"], "build-source-unavailable")
            self.assertEqual(len(native["KadokaTools.exe"]["sha256"]), 64)
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
