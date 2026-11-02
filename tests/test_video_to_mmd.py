"""Tests for video motion retargeting, VMD encoding, and artifact safety."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from comfyui_support_tools.shared.video_to_mmd import (
    RecoveredFrame,
    RecoveredMotion,
    RetargetProfile,
    RetargetRule,
    SourceBonePose,
    VmdBoneKey,
    convert_video_to_vmd,
    process_recovered_motion,
    write_motion_vmd,
)


# {
# 責務: [FakeRecoveryBackend: 固定姿勢列を返すtest backend]
# フィールド: [motion: test向けpose recovery result]
# 処理: [external GVHMR runtimeなしでserviceを検証する]
# }
class FakeRecoveryBackend:
    # {
    # 責務: [__init__: test motionを登録する]
    # 引数: [motion: fake backendから返すrecovered motion]
    # 処理: [validate test behavior and expected output]
    # 戻り値: [None: unittest assertion result]
    # }
    def __init__(self, motion):
        self.motion = motion

    # {
    # 責務: [recover: backend protocolに沿って固定motionを返す]
    # 処理: [video pathとframe範囲を記録しmotionを返す]
    # 引数: [test fixture values: scenario inputs]
    # 戻り値: [None: unittest assertion result]
    # }
    def recover(self, video_path, person_id=None, start_frame=None, end_frame=None):
        self.request = (video_path, person_id, start_frame, end_frame)
        return self.motion


# {
# 責務: [VideoToMmdTests: retargetとVMD artifactの回帰を検証する]
# フィールド: [TemporaryDirectory: isolated test files]
# 処理: [camera correction/contact/validation/no-clobberを検証する]
# }
class VideoToMmdTests(unittest.TestCase):
    # {
    # 責務: [make_motion: predictable tracked pose fixtureを生成する]
    # 戻り値: [RecoveredMotion: three frame test motion]
    # 処理: [validate test behavior and expected output]
    # 引数: [test fixture values: scenario inputs]
    # }
    def make_motion(self):
        frames = []
        for frame_number, x in enumerate((2.0, 2.2, 4.0)):
            foot = SourceBonePose("left_foot", (x, 0.5, 0.0), (0, 0, 0, 1), 0.9, True)
            root = SourceBonePose("root", (x, 1.0, 0.0), (0, 0, 0, 1), 0.9)
            frames.append(RecoveredFrame(frame_number, "person-1", (1.0, 0, 0), 0.0, (root, foot)))
        return RecoveredMotion(30, tuple(frames))

    # {
    # 責務: [test_camera_compensation_contact_repair_and_key_reduction: cleanup処理の組み合わせを検証]
    # 処理: [rootのcamera translation除去とfoot anchorを確認する]
    # 引数: [test fixture values: scenario inputs]
    # 戻り値: [None: unittest assertion result]
    # }
    def test_camera_compensation_contact_repair_and_key_reduction(self):
        profile = RetargetProfile(
            "fixture",
            (
                RetargetRule("root", "センター"),
                RetargetRule("left_foot", "左足"),
            ),
            smoothing=0,
            key_error_tolerance=0.01,
            maximum_speed=1000,
        )
        keys, confidence, findings = process_recovered_motion(self.make_motion(), profile)
        root_keys = [key for key in keys if key.bone == "センター"]
        foot_keys = [key for key in keys if key.bone == "左足"]
        self.assertEqual(root_keys[0].translation[0], 1.0)
        self.assertTrue(all(key.translation[1] == 0.0 for key in foot_keys))
        self.assertEqual(len(confidence), 6)
        self.assertIn("camera.compensated", {item.code for item in findings})
        self.assertLessEqual(len(root_keys), 3)

    # {
    # 責務: [test_vmd_serialization_has_bone_record_and_empty_sections: VMD layoutを確認]
    # 処理: [binary record count/bone name/zero optional sectionをparseする]
    # 引数: [test fixture values: scenario inputs]
    # 戻り値: [None: unittest assertion result]
    # }
    def test_vmd_serialization_has_bone_record_and_empty_sections(self):
        payload = write_motion_vmd((VmdBoneKey("センター", 12, (1, 2, 3), (0, 0, 0, 1)),))
        self.assertTrue(payload.startswith(b"Vocaloid Motion Data 0002"))
        self.assertEqual(struct.unpack_from("<I", payload, 50)[0], 1)
        self.assertEqual(payload[54:69].decode("shift_jis").rstrip("\0"), "センター")
        self.assertEqual(len(payload), 189)
        self.assertEqual(struct.unpack_from("<I", payload, len(payload) - 4)[0], 0)
        long_name = write_motion_vmd(
            (VmdBoneKey("センター", 0, (0, 0, 0), (0, 0, 0, 1)),), "モデル名が長いモデル名"
        )
        self.assertEqual(len(long_name), 189)

    # {
    # 責務: [test_service_writes_vmd_report_and_gif_and_refuses_overwrite: artifact outputを検証]
    # 処理: [3成果物の生成と既存fileを保護する動作を確認する]
    # 引数: [test fixture values: scenario inputs]
    # 戻り値: [None: unittest assertion result]
    # }
    def test_service_writes_vmd_report_and_gif_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "dance.mp4"
            video.write_bytes(b"fixture")
            backend = FakeRecoveryBackend(self.make_motion())
            profile = RetargetProfile("fixture", (RetargetRule("root", "センター"),), smoothing=0)
            result = convert_video_to_vmd(video, root / "out", backend, profile)
            self.assertTrue(result.vmd_path.read_bytes().startswith(b"Vocaloid Motion Data 0002"))
            report = json.loads(result.report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["fps"], 30)
            self.assertEqual(report["key_count"], len(result.keys))
            with Image.open(result.preview_path) as preview:
                self.assertEqual(preview.format, "GIF")
            self.assertEqual(backend.request, (video, None, None, None))
            result.vmd_path.write_bytes(b"keep")
            with self.assertRaises(FileExistsError):
                convert_video_to_vmd(video, root / "out", backend, profile)
            self.assertEqual(result.vmd_path.read_bytes(), b"keep")

    # {
    # 責務: [test_invalid_retarget_profile_and_video_range_are_rejected: invalid inputsを拒否]
    # 処理: [profile mappingとrange boundaryのvalidationを確認する]
    # 引数: [test fixture values: scenario inputs]
    # 戻り値: [None: unittest assertion result]
    # }
    def test_invalid_retarget_profile_and_video_range_are_rejected(self):
        motion = self.make_motion()
        with self.assertRaises(ValueError):
            process_recovered_motion(
                motion,
                RetargetProfile(
                    "fixture", (RetargetRule("root", "センター"), RetargetRule("other", "センター"))
                ),
            )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "dance.mp4"
            video.touch()
            with self.assertRaises(ValueError):
                convert_video_to_vmd(
                    video,
                    root / "out",
                    FakeRecoveryBackend(motion),
                    RetargetProfile("fixture", (RetargetRule("root", "センター"),)),
                    start_frame=3,
                    end_frame=2,
                )


if __name__ == "__main__":
    unittest.main()
