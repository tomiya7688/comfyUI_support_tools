import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.comfyui_support_tools.shared.output_artifact import (
    ArtifactState,
    ConflictPolicy,
    atomic_write_bytes,
    resolve_conflict,
    safe_filename,
)


# {
# 責務: [ OutputArtifactTests: conflict/atomic/validation artifact policyを検証する ]
# フィールド: []
# 処理: [ 1: conflict policyを検証する, 2: atomic failure safetyを検証する, 3: filename safetyを検証する ]
# }
class OutputArtifactTests(unittest.TestCase):
    # {
    # 責務: [ test_conflict_policies_do_not_silently_overwrite: conflict policyの意味を確認する ]
    # 処理: [ 1: 既存targetを作る, 2: fail/skip/rename/version/overwriteを確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_conflict_policies_do_not_silently_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.txt"
            target.write_text("old", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                resolve_conflict(target, ConflictPolicy.FAIL)
            self.assertIsNone(resolve_conflict(target, ConflictPolicy.SKIP))
            self.assertEqual(resolve_conflict(target, ConflictPolicy.OVERWRITE), target)
            self.assertEqual(resolve_conflict(target, ConflictPolicy.RENAME).name, "result (1).txt")
            self.assertEqual(
                resolve_conflict(target, ConflictPolicy.VERSIONED).name, "result.v001.txt"
            )
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    # {
    # 責務: [ test_atomic_write_validates_before_commit: validation failureで完成名を壊さない ]
    # 処理: [ 1: 既存artifactを用意する, 2: failing validatorでoverwriteを試す, 3: 旧artifact/tempを確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_atomic_write_validates_before_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.json"
            target.write_bytes(b'{"old": true}')

            # {
            # 責務: [reject: staged JSONがinvalidであることを示すtest validator]
            # 処理: [1: validationを拒否する]
            # 引数: [_path: staged artifact]
            # 戻り値: [raises ValueError]
            # }
            def reject(_path):
                raise ValueError("invalid staged artifact")

            with self.assertRaisesRegex(ValueError, "invalid staged"):
                atomic_write_bytes(
                    target, b"invalid", policy=ConflictPolicy.OVERWRITE, validator=reject
                )
            self.assertEqual(target.read_bytes(), b'{"old": true}')
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    # {
    # 責務: [ test_atomic_write_commits_validated_bytes: valid outputをatomic commitする ]
    # 処理: [ 1: bytesを書き込む, 2: state/group/pathを確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_atomic_write_commits_validated_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.txt"
            result = atomic_write_bytes(target, b"complete", group_id="group-1")
            self.assertEqual(target.read_bytes(), b"complete")
            self.assertEqual(result.state, ArtifactState.COMPLETE)
            self.assertEqual(result.group_id, "group-1")

    # {
    # 責務: [ test_atomic_policies_preserve_existing_target: rename/version/skipで既存出力を保持する ]
    # 処理: [ 1: 既存fileを作る, 2: 各policyで出力する, 3: 旧fileが維持されることを確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_atomic_policies_preserve_existing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.txt"
            target.write_bytes(b"old")
            self.assertIsNone(atomic_write_bytes(target, b"skip", policy=ConflictPolicy.SKIP))
            renamed = atomic_write_bytes(target, b"renamed", policy=ConflictPolicy.RENAME)
            versioned = atomic_write_bytes(target, b"versioned", policy=ConflictPolicy.VERSIONED)
            self.assertEqual(target.read_bytes(), b"old")
            self.assertEqual(renamed.target.name, "result (1).txt")
            self.assertEqual(versioned.target.name, "result.v001.txt")
            self.assertEqual(renamed.target.read_bytes(), b"renamed")
            self.assertEqual(versioned.target.read_bytes(), b"versioned")

    # {
    # 責務: [test_skip_policy_handles_target_race: resolve後にtargetが作られてもskipする]
    # 処理: [1: link commitでcollisionを起こす 2: skip結果とtemp cleanupを確認する]
    # 引数: [self: test instance]
    # 戻り値: []
    # }
    def test_skip_policy_handles_target_race(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.txt"
            with patch(
                "src.comfyui_support_tools.shared.output_artifact.os.link",
                side_effect=FileExistsError,
            ):
                result = atomic_write_bytes(target, b"skip", policy=ConflictPolicy.SKIP)
            self.assertIsNone(result)
            self.assertEqual(list(Path(directory).glob(".*.tmp")), [])

    # {
    # 責務: [ test_rejects_input_collision_and_sanitizes_names: source破壊とWindows予約名を防止する ]
    # 処理: [ 1: source collisionを拒否する, 2: unsafe/reserved filenameを変換する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_rejects_input_collision_and_sanitizes_names(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            with self.assertRaisesRegex(ValueError, "collides"):
                resolve_conflict(source, ConflictPolicy.OVERWRITE, [source])
        self.assertEqual(safe_filename("CON"), "_CON")
        self.assertEqual(safe_filename("日本語:画像?"), "日本語_画像_")


if __name__ == "__main__":
    unittest.main()
