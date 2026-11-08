import hashlib
import tempfile
import unittest
from pathlib import Path

from src.comfyui_support_tools.applications.character_registry.data.processing.character_reference_image_loader import (
    load_character_reference_image,
)


# {
#   責務: [CharacterReferenceImageLoaderTest: local image reference ID/hash and validationを検証する]
#   フィールド: [unittest assertion機能]
#   処理: [一時画像fileを使って参照path, content digest, duplicate identityを確認する]
# }
class CharacterReferenceImageLoaderTest(unittest.TestCase):
    # {
    #   責務: [test_loads_image_reference_without_copying: 元fileを保持したままreference metadataを作る]
    #   処理: [選択画像のpathとSHA-256由来IDを検証する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_loads_image_reference_without_copying(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "reference.png"
            content = b"small image fixture"
            path.write_bytes(content)

            image = load_character_reference_image(path)

            digest = hashlib.sha256(content).hexdigest()
            self.assertEqual(image.image_id, f"sha256-{digest}")
            self.assertEqual(image.content_sha256, digest)
            self.assertEqual(image.source_path, str(path.resolve()))
            self.assertTrue(path.is_file())

    # {
    #   責務: [test_identical_content_has_same_stable_id: 同一内容の別pathを同じIDへまとめる]
    #   処理: [内容hashがファイル名や配置pathに依存しないことを確認する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_identical_content_has_same_stable_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / "first.png"
            second = root / "second.jpg"
            first.write_bytes(b"same image content")
            second.write_bytes(first.read_bytes())

            self.assertEqual(
                load_character_reference_image(first).image_id,
                load_character_reference_image(second).image_id,
            )

    # {
    #   責務: [test_rejects_unsupported_or_missing_image: 読み込み対象でないpathを拒否する]
    #   処理: [unsupported suffixと不存在fileをValueErrorで拒否する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_rejects_unsupported_or_missing_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            unsupported = root / "caption.txt"
            missing = root / "missing.png"
            unsupported.write_text("caption", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "未対応"):
                load_character_reference_image(unsupported)
            with self.assertRaisesRegex(ValueError, "読み込めません"):
                load_character_reference_image(missing)


if __name__ == "__main__":
    unittest.main()
