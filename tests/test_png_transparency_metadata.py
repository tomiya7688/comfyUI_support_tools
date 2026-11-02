import struct
import tempfile
import unittest
import zlib
from io import BytesIO
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from comfyui_support_tools.shared.png_transparency_metadata import (
    create_png_transparency_copy,
    verify_png_transparency,
)


# {
# 責務: [ PngTransparencyMetadataTests: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class PngTransparencyMetadataTests(unittest.TestCase):
    # {
    # 責務: [ test_metadata_is_added_to_copy_and_existing_pixels_text_are_preserved: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_metadata_is_added_to_copy_and_existing_pixels_text_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "original.png"
            info = PngInfo()
            info.add_text("existing", "preserve me")
            Image.new("RGBA", (4, 3), (30, 80, 120, 128)).save(source, pnginfo=info)
            before = source.read_bytes()
            payload = {"schema_version": 1, "generated_or_modified": "generated"}

            copied = create_png_transparency_copy(source, payload)

            self.assertEqual(source.read_bytes(), before)
            self.assertTrue(verify_png_transparency(copied, payload))
            with Image.open(BytesIO(copied)) as result, Image.open(source) as original:
                self.assertEqual(result.info["existing"], "preserve me")
                self.assertEqual(list(result.getdata()), list(original.getdata()))

    # {
    # 責務: [ test_existing_c2pa_chunk_is_not_stripped_by_png_reencoding: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_existing_c2pa_chunk_is_not_stripped_by_png_reencoding(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "credentialed.png"
            Image.new("RGB", (2, 2), "white").save(source)
            data = source.read_bytes()
            chunk_type = b"caBX"
            chunk_payload = b"existing C2PA JUMBF"
            chunk = (
                struct.pack(">I", len(chunk_payload))
                + chunk_type
                + chunk_payload
                + struct.pack(">I", zlib.crc32(chunk_type + chunk_payload) & 0xFFFFFFFF)
            )
            source.write_bytes(data[:-12] + chunk + data[-12:])

            with self.assertRaisesRegex(ValueError, "C2PA credentials"):
                create_png_transparency_copy(source, {"schema_version": 1})

    # {
    # 責務: [ test_invalid_or_animated_inputs_are_rejected: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_invalid_or_animated_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "not-png.jpg"
            Image.new("RGB", (2, 2), "white").save(source, format="JPEG")
            with self.assertRaisesRegex(ValueError, "signature"):
                create_png_transparency_copy(source, {})

    # {
    # 責務: [ test_visible_disclosure_is_applied_only_to_requested_copy: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_visible_disclosure_is_applied_only_to_requested_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "original.png"
            Image.new("RGB", (240, 120), "blue").save(source)
            before = source.read_bytes()
            payload = {"schema_version": 1}
            result = create_png_transparency_copy(
                source, payload, visible_disclosure_label="AI-generated"
            )
            with Image.open(BytesIO(before)) as original, Image.open(BytesIO(result)) as copy:
                self.assertNotEqual(list(original.getdata()), list(copy.getdata()))
                self.assertEqual(copy.size, original.size)
            self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
