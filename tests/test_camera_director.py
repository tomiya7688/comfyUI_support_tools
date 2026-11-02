from __future__ import annotations

import json
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from comfyui_support_tools.shared.camera_director import (
    CameraKey,
    CameraStyle,
    DanceMotion,
    MotionKey,
    StageBounds,
    analyze_wav_sections,
    build_camera_plan,
    export_camera_plan,
    read_dance_vmd,
    reroll_camera_section,
    write_camera_vmd,
)


# {
# 責務: [dance_vmd: compact dance VMD fixtureを作成する]
# 処理: [bone keysとempty remaining sectionsをbinaryへencodeする]
# 引数: []
# 戻り値: [bytes: valid VMD fixture]
# }
def dance_vmd() -> bytes:
    data = bytearray(b"Vocaloid Motion Data 0002".ljust(30, b"\0"))
    data.extend(b"fixture".ljust(20, b"\0"))
    data.extend(struct.pack("<I", 2))
    for frame, x in ((0, 0.0), (30, 2.0)):
        data.extend("センター".encode("shift_jis").ljust(15, b"\0"))
        data.extend(struct.pack("<I3f4f", frame, x, 10.0, 0.0, 0.0, 0.0, 0.0, 1.0))
        data.extend(bytes(64))
    data.extend(struct.pack("<I", 0))  # morphs
    data.extend(struct.pack("<I", 0))  # cameras
    data.extend(struct.pack("<I", 0))  # lights
    data.extend(struct.pack("<I", 0))  # shadows
    data.extend(struct.pack("<I", 0))  # model display/IK frames
    return bytes(data)


# {
# 責務: [CameraDirectorTests: VMD parse/export/planning/audio integrationを検証する]
# フィールド: [temporary fixtures]
# 処理: [parser bounds, reroll, music section and atomic artifactsを確認する]
# }
class CameraDirectorTests(unittest.TestCase):
    # {
    # 責務: [test_vmd_reader_and_camera_writer_round_trip_sections: VMD section offsetsを確認する]
    # 処理: [1: dance VMDをparse, 2: camera VMDを書き出しheader/countを確認]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_vmd_reader_and_camera_writer_round_trip_sections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "dance.vmd"
            source.write_bytes(dance_vmd())
            motion = read_dance_vmd(source)
            self.assertEqual(motion.duration_frames, 30)
            self.assertEqual(motion.keys[1].position, (2.0, 10.0, 0.0))
        key = CameraKey(30, 10.0, (1.0, 2.0, 3.0), (0.0, 0.1, 0.0))
        camera_bytes = write_camera_vmd((key,))
        self.assertEqual(camera_bytes[:25], b"Vocaloid Motion Data 0002")
        self.assertEqual(struct.unpack_from("<I", camera_bytes, 58)[0], 1)
        self.assertEqual(struct.unpack_from("<I", camera_bytes, 62)[0], 30)
        with self.assertRaises(ValueError):
            write_camera_vmd((key,), "日本語の名前が20バイトを超える名前")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "dance.vmd"
            source.write_bytes(dance_vmd())
            with self.assertRaises(ValueError):
                read_dance_vmd(source, fps=0)

    # {
    # 責務: [test_planner_clamps_targets_and_exports_non_overwriting_artifacts: planner/export policyを確認する]
    # 処理: [1: camera planを生成, 2: VMD/JSON/SVG保存とoverwrite拒否を確認]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_planner_clamps_targets_and_exports_non_overwriting_artifacts(self) -> None:
        motion = DanceMotion(
            Path("dance.vmd"),
            (
                MotionKey("センター", 0, (100.0, 10.0, 0.0)),
                MotionKey("センター", 30, (2.0, 10.0, 0.0)),
            ),
            30,
        )
        plan = build_camera_plan(motion, CameraStyle.CINEMATIC, StageBounds())
        self.assertTrue(any(item.code == "visibility.target_clamped" for item in plan.findings))
        with tempfile.TemporaryDirectory() as directory:
            artifacts = export_camera_plan(plan, Path(directory) / "camera.vmd")
            self.assertTrue(artifacts.vmd_path.is_file())
            self.assertTrue(artifacts.preview_path.is_file())
            self.assertTrue(artifacts.storyboard_path.is_file())
            self.assertTrue(artifacts.preview_path.read_bytes().startswith(b"GIF89a"))
            payload = json.loads(artifacts.plan_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["style"], "cinematic")
            with self.assertRaises(FileExistsError):
                export_camera_plan(plan, artifacts.vmd_path)

    # {
    # 責務: [test_wav_section_analysis_and_seeded_reroll: music sectionと部分再生成を検証する]
    # 処理: [1: WAV energyを解析, 2: 指定区間だけseeded rerollする]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_wav_section_analysis_and_seeded_reroll(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            wav_path = Path(directory) / "music.wav"
            with wave.open(str(wav_path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(30)
                audio.writeframes(struct.pack("<60h", *([1000] * 60)))
            sections = analyze_wav_sections(wav_path, fps=30, window_seconds=1.0)
            self.assertEqual(len(sections), 2)
            self.assertTrue(all(section.intensity > 0.99 for section in sections))
            with self.assertRaises(ValueError):
                analyze_wav_sections(wav_path, window_seconds=float("nan"))
        motion = DanceMotion(
            Path("dance.vmd"),
            (MotionKey("センター", 0, (0, 10, 0)), MotionKey("センター", 30, (1, 10, 0))),
            30,
        )
        prior = tuple(CameraKey(frame, 10, (0, 10, 0), (0, 0, 0)) for frame in (0, 10, 20, 30))
        rerolled = reroll_camera_section(
            motion, CameraStyle.CINEMATIC, StageBounds(), prior, 10, 20, 7
        )
        self.assertEqual(
            [key.frame for key in rerolled if key.frame < 10 or key.frame > 20], [0, 30]
        )
        self.assertTrue(any(key.rotation[1] != 0 for key in rerolled if 10 <= key.frame <= 20))


if __name__ == "__main__":
    unittest.main()
