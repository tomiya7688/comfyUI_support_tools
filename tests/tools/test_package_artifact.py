"""Tests for final distribution archive creation and integrity verification."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from tools.build.package_artifact import (
    ARCHIVE_NAME,
    CHECKSUM_NAME,
    package_distribution,
    verify_distribution,
)


# {
#   責務: [PackageArtifactTests: final ZIP/checksum generation and rejection pathsを検証する]
#   フィールド: [temporary distribution/output trees]
# }
class PackageArtifactTests(unittest.TestCase):
    # {
    #   責務: [test_package_is_repeatable_and_verifiable: normalized archive produces stable digest and verifies]
    #   処理: [1: fixture distributionを梱包する 2: packageを再生成する 3: checksum/zip membersを検証する]
    #   引数: []
    #   戻り値: []
    # }
    def test_package_is_repeatable_and_verifiable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            distribution = root / "dist" / "KadokaTools"
            (distribution / "nested").mkdir(parents=True)
            (distribution / "KadokaTools.exe").write_bytes(b"MZ\x00signed")
            (distribution / "nested" / "data.bin").write_bytes(b"payload")
            output = root / "release"
            archive, checksum = package_distribution(distribution, output)
            first_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(checksum.name, CHECKSUM_NAME)
            self.assertEqual(verify_distribution(output), (archive, checksum))
            package_distribution(distribution, output)
            second_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(first_digest, second_digest)
            with ZipFile(archive) as bundle:
                self.assertIn("KadokaTools/KadokaTools.exe", bundle.namelist())
                self.assertIn("KadokaTools/nested/data.bin", bundle.namelist())

    # {
    #   責務: [test_corrupt_archive_fails_checksum_verification: corrupted final artifact is rejected]
    #   処理: [1: packageを生成する 2: archive bytesを改変する 3: checksum mismatchを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_corrupt_archive_fails_checksum_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "file.bin").write_bytes(b"payload")
            archive, _checksum = package_distribution(source, root / "release")
            archive.write_bytes(archive.read_bytes() + b"tamper")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                verify_distribution(root / "release")

    # {
    #   責務: [test_unsafe_zip_member_and_checksum_manifest_are_rejected: traversal and malformed checksum manifests fail closed]
    #   処理: [1: traversal ZIPを作る 2: matching digest manifestを書く 3: unsafe member rejectionを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_unsafe_zip_member_and_checksum_manifest_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            archive = output / ARCHIVE_NAME
            with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
                bundle.writestr("../escape.txt", b"bad")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            (output / CHECKSUM_NAME).write_text(f"{digest}  {ARCHIVE_NAME}\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "unsafe member"):
                verify_distribution(output)

    # {
    #   責務: [test_symlink_and_nested_output_are_refused: packaging does not follow symlinks or recurse into its output]
    #   処理: [1: nested output pathを拒否する 2: source symlinkを拒否する]
    #   引数: []
    #   戻り値: []
    # }
    def test_symlink_and_nested_output_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "distribution"
            source.mkdir()
            (source / "file.bin").write_bytes(b"safe")
            with self.assertRaisesRegex(ValueError, "outside"):
                package_distribution(source, source / "release")
            try:
                (source / "link").symlink_to(source / "file.bin")
            except (NotImplementedError, OSError):
                self.skipTest("symlink creation is unavailable on this platform")
            with self.assertRaisesRegex(ValueError, "symlink"):
                package_distribution(source, root / "release")


if __name__ == "__main__":
    unittest.main()
