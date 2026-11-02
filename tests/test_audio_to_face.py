from __future__ import annotations

import json
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from comfyui_support_tools.shared.audio_to_face import (
    AudioFaceService,
    MorphCalibration,
    MorphKey,
    SpeechAnalysis,
    read_vmd,
    read_vmd_bytes,
    write_facial_vmd,
    write_vmd,
)


# {
# 責務: [empty_vmd: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [なし: 処理入力]
# 戻り値: [bytes: 処理結果]
# }
# {
# 責務: [empty_vmd: compact VMD fixtureを作成する]
# 処理: [optional bone recordとempty remaining sectionsをencodeする]
# 引数: [with_bone: bone record inclusion]
# 戻り値: [bytes: valid VMD fixture]
# }
def empty_vmd(with_bone: bool = False) -> bytes:
    data = bytearray(b"Vocaloid Motion Data 0002".ljust(30, b"\0"))
    data.extend(b"fixture".ljust(20, b"\0"))
    data.extend(struct.pack("<I", int(with_bone)))
    if with_bone:
        data.extend(b"center".ljust(15, b"\0"))
        data.extend(struct.pack("<I3f4f", 0, 0, 0, 0, 0, 0, 0, 1))
        data.extend(bytes(64))
    data.extend(struct.pack("<I", 0))  # morph records
    data.extend(struct.pack("<I", 0))  # camera records
    data.extend(struct.pack("<I", 0))  # light records
    data.extend(struct.pack("<I", 0))  # shadow records
    data.extend(struct.pack("<I", 0))  # model display / IK records
    return bytes(data)


# {
# 責務: [AudioToFaceTests: transcript mapping, VMD merge and export behaviorを検証する]
# フィールド: [temporary WAV and VMD fixtures]
# 処理: [mora alignment, morph calibration, preserve-body merge, report and previewを確認する]
# }
class AudioToFaceTests(unittest.TestCase):
    # {
    # 責務: [test_japanese_transcript_generates_vowels_and_merges_body_vmd: VMD facial/body mergeを確認する]
    # 処理: [1: PCM WAVとbody VMDを作る, 2: vowel morph/merge/report/GIFを検証する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_japanese_transcript_generates_vowels_and_merges_body_vmd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "voice.wav"
            with wave.open(str(audio), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(1000)
                stream.writeframes(struct.pack("<1000h", *([200] * 1000)))
            body = root / "body.vmd"
            body_document = read_vmd_bytes(empty_vmd(with_bone=True))
            body.write_bytes(write_vmd(body_document, (MorphKey("笑い", 0, 0.3),)))
            output = root / "face.vmd"
            calibration = MorphCalibration(
                ("あ", "い", "う", "え", "お", "まばたき", "笑い"),
                (("あ", 0.8),),
                (("あ", 0.0),),
            )
            report = AudioFaceService().run(
                audio,
                output,
                transcript="あいうえお",
                emotion="happy",
                body_vmd=body,
                calibration=calibration,
                seed=4,
            )
            names = {key.name for key in report.morph_keys}
            self.assertTrue({"あ", "い", "う", "え", "お"}.issubset(names))
            self.assertTrue(report.merged_vmd_path and report.merged_vmd_path.is_file())
            merged = read_vmd(report.merged_vmd_path)
            self.assertIn("笑い", {key.name for key in merged.morphs})
            self.assertEqual(merged.prefix, body_document.prefix)
            self.assertTrue(report.preview_path.read_bytes().startswith(b"GIF89a"))
            payload = json.loads(report.report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["analysis_provenance"], "transcript-uniform-estimate")
            self.assertEqual(payload["evaluation"]["vowel_mapping_accuracy"], 1.0)
            alias_report = AudioFaceService().run(
                audio,
                root / "face-aliases.vmd",
                transcript="あいうえお",
                calibration=MorphCalibration(("口あ", "口い", "口う", "口え", "口お")),
                seed=4,
            )
            self.assertEqual(alias_report.evaluation.vowel_mapping_accuracy, 1.0)
            with self.assertRaises(ValueError):
                write_facial_vmd(report.morph_keys, "日本語の長いモデル名は切り詰めずに拒否する")

    # {
    # 責務: [test_speech_analyzer_adapter_supports_non_wav_inputs: optional model adapter経路を確認する]
    # 処理: [1: fake AnyTalk engineを構成, 2: MP3 facade requestのphoneme結果を検証する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_speech_analyzer_adapter_supports_non_wav_inputs(self) -> None:
        from comfyui_support_tools.shared.audio_to_face import AnyTalkAdapter

        # {
        # 責務: [Engine: facial motionの型または処理単位を表す]
        # フィールド: [audio timelineまたはVMD処理の必要状態]
        # 処理: [検証可能なfacial VMD生成に利用する]
        # }
        class Engine:
            # {
            # 責務: [analyze_audio: audio-to-face処理を実行する]
            # 処理: [入力を検証し、再現可能なfacial motion結果を返す]
            # 引数: [audio_path, transcript, language: 処理入力]
            # 戻り値: [処理結果: 処理結果]
            # }
            def analyze_audio(self, audio_path, transcript, language):
                return SpeechAnalysis((), "neutral", language, "fixture", 1.0)

        adapter = AnyTalkAdapter(Engine())
        self.assertEqual(adapter.analyze(Path("voice.mp3"), "hello", "en").duration_seconds, 1.0)

    # {
    # 責務: [test_vmd_parser_refuses_truncated_sections: truncationをfail-safe拒否する]
    # 処理: [1: valid body fixtureを切り詰める, 2: explicit format errorを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_vmd_parser_refuses_truncated_sections(self) -> None:
        with self.assertRaisesRegex(ValueError, "truncated"):
            read_vmd_bytes(empty_vmd()[:-2])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "body.vmd"
            path.write_bytes(empty_vmd())
            self.assertEqual(read_vmd(path).morphs, ())


if __name__ == "__main__":
    unittest.main()
