"""Tests for WAV analysis, section planning, backend routing, and VMD output."""

from __future__ import annotations

import json
import math
import struct
import subprocess
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

from comfyui_support_tools.shared.music_to_mmd import (
    AudioAnalysis,
    AudioSection,
    AudioSignal,
    AutoAudioDecoder,
    DanceBackendRegistry,
    FFmpegAudioDecoder,
    MusicToMmdApplication,
    MusicToMmdSession,
    WavAudioDecoder,
    analyze_audio,
    build_choreography_plan,
    replace_section_instruction,
)
from comfyui_support_tools.shared.video_to_mmd.contracts import (
    RecoveredFrame,
    RecoveredMotion,
    RetargetProfile,
    RetargetRule,
    SourceBonePose,
)


# {
# 責務: [FakeDanceBackend: return deterministic short motion for each planned segment]
# フィールド: [requests: section generation calls]
# 処理: [validate section-local generation and template reuse without external models]
# }
class FakeDanceBackend:
    # {
    # 責務: [__init__: initialize generation call history]
    # 処理: [record each section request for test assertions]
    # 引数: [None: no inputs]
    # 戻り値: [None: initialized backend]
    # }
    def __init__(self):
        self.requests = []

    # {
    # 責務: [generate_section: emit simple root/foot animation in local frame coordinates]
    # 処理: [create deterministic motion frames and retain musical request]
    # 引数: [request: section plan, seed, and motif context]
    # 戻り値: [RecoveredMotion: backend motion clip]
    # }
    def generate_section(self, request):
        self.requests.append(request)
        count = request.section.end_frame - request.section.start_frame
        frames = []
        for frame in range(count):
            movement = math.sin(frame / 8) * request.section.intensity
            root = SourceBonePose("root", (movement, 1.0, 0.0), (0, 0, 0, 1), 0.9)
            foot = SourceBonePose("left_foot", (movement, 0.0, 0.0), (0, 0, 0, 1), 0.9, True)
            frames.append(RecoveredFrame(frame, "dancer", (0, 0, 0), 0.0, (root, foot)))
        return RecoveredMotion(request.plan.fps, tuple(frames), camera_compensated=True)


# {
# 責務: [FakeAudioDecoder: supply prebuilt signal independent of file codec]
# フィールド: [signal: decoder output]
# 処理: [exercise application orchestration without optional decode libraries]
# }
class FakeAudioDecoder:
    # {
    # 責務: [__init__: retain deterministic audio signal]
    # 処理: [prepare fixed signal]
    # 引数: [signal: AudioSignal returned by decoder]
    # 戻り値: [None: initialized fake]
    # }
    def __init__(self, signal):
        self.signal = signal

    # {
    # 責務: [decode: satisfy audio decoder adapter protocol]
    # 処理: [return prepared signal]
    # 引数: [path: ignored fixture file]
    # 戻り値: [AudioSignal: mono PCM fixture]
    # }
    def decode(self, path):
        return self.signal


# {
# 責務: [MusicToMmdTests: verify analysis, planning, section editing, and serialization]
# フィールド: [temporary audio source and fake adapter fixtures]
# 処理: [exercise deterministic shared workflow and bounded input handling]
# }
class MusicToMmdTests(unittest.TestCase):
    # {
    # 責務: [make_signal: create pulse-like beat fixture]
    # 処理: [emit 120 BPM impulses at 8kHz]
    # 引数: [seconds: signal duration]
    # 戻り値: [AudioSignal: compact analysis signal]
    # }
    def make_signal(self, seconds=8):
        signal = array("f", [0.0]) * (seconds * 8000)
        for onset in range(0, seconds * 2, 1):
            start = onset * 4000
            for index in range(start, min(start + 120, len(signal))):
                signal[index] = 0.9 * math.sin(index / 3)
        return AudioSignal(signal, 8000)

    # {
    # 責務: [make_analysis: create three sections with a repeated chorus motif]
    # 処理: [build direct timeline fixture for rerolling and motif reuse tests]
    # 引数: [None: no inputs]
    # 戻り値: [AudioAnalysis: three section test plan]
    # }
    def make_analysis(self, source):
        sections = (
            AudioSection("chorus", 0, 2, 1.0, "section-000"),
            AudioSection("verse", 2, 4, 0.55, "section-001"),
            AudioSection("chorus", 4, 6, 0.95, "section-002"),
        )
        return AudioAnalysis(
            6, 120, tuple(index * 0.5 for index in range(12)), (), (), sections, source, "fixture"
        )

    # {
    # 責務: [test_wav_pcm_decoder_and_tempo_analysis: exercise default supported audio path]
    # 処理: [write 16-bit PCM WAV pulses, decode to compact mono, and estimate tempo]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_wav_pcm_decoder_and_tempo_analysis(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "beat.wav"
            with wave.open(str(path), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(8000)
                values = []
                for index in range(8 * 8000):
                    if index % 4000 < 120:
                        values.append(int(20000 * math.sin(index / 3)))
                    else:
                        values.append(0)
                stream.writeframes(struct.pack(f"<{len(values)}h", *values))
            signal = WavAudioDecoder().decode(path)
            analysis = analyze_audio(signal, path)
            self.assertGreaterEqual(analysis.bpm, 90)
            self.assertLessEqual(analysis.bpm, 150)
            self.assertTrue(analysis.beats)
            self.assertTrue(analysis.sections)
            self.assertEqual(len(signal.samples), 8 * 8000)

    # {
    # 責務: [test_ffmpeg_decoder_handles_compressed_audio_when_available: validate optional codec]
    # 処理: [decode a short WAV through FFmpeg raw-float adapter when installed]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or skip]
    # }
    def test_ffmpeg_decoder_handles_audio_when_available(self):
        decoder = FFmpegAudioDecoder()
        if decoder.executable is None:
            self.skipTest("FFmpeg is optional")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "short.wav"
            with wave.open(str(path), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(8000)
                frames = [int(10000 * math.sin(index / 10)) for index in range(8000)]
                stream.writeframes(struct.pack(f"<{len(frames)}h", *frames))
            signal = decoder.decode(path)
            self.assertEqual(signal.sample_rate, 8000)
            self.assertEqual(len(signal.samples), 8000)
            self.assertEqual(AutoAudioDecoder().decode(path).sample_rate, 8000)
            mp3 = Path(temporary) / "short.mp3"
            subprocess.run(
                [
                    decoder.executable,
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(path),
                    "-codec:a",
                    "libmp3lame",
                    str(mp3),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            decoded_mp3 = AutoAudioDecoder().decode(mp3)
            self.assertEqual(decoded_mp3.sample_rate, 8000)
            self.assertGreaterEqual(len(decoded_mp3.samples), 8000)

    # {
    # 責務: [test_plan_reuses_chorus_motifs_and_updates_one_instruction: verify editable planning]
    # 処理: [map coarse sections to frame ranges and motif references]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_plan_reuses_chorus_motifs_and_updates_one_instruction(self):
        analysis = self.make_analysis(Path("song.wav"))
        plan = build_choreography_plan(analysis, style="idol", instruction="bright", fps=30)
        self.assertEqual(plan.repeated_motifs, (("section-000", "section-002"),))
        self.assertEqual(plan.sections[2].motif_id, plan.sections[0].motif_id)
        revised = replace_section_instruction(plan, "section-001", "calmer verse")
        self.assertEqual(revised.sections[1].instruction, "calmer verse")
        self.assertEqual(plan.sections[1].instruction, "bright")
        with self.assertRaises(KeyError):
            replace_section_instruction(plan, "missing", "instruction")

    # {
    # 責務: [test_backend_registry_routes_capability_sets: confirm modular model selection]
    # 処理: [select matching capability tags and reject unsatisfied requirements]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_backend_registry_routes_capability_sets(self):
        registry = DanceBackendRegistry()
        backend = FakeDanceBackend()
        registry.register(
            "atomic", backend, frozenset({"editable_sections", "long_form", "genre_control"})
        )
        self.assertEqual(registry.select(frozenset({"genre_control"})).name, "atomic")
        with self.assertRaises(LookupError):
            registry.select(frozenset({"reference_motion"}))

    # {
    # 責務: [test_generate_reroll_evaluate_and_export_full_song: verify complete VMD workflow]
    # 処理: [generate sections, reroll a single section, export plan/report/VMD]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_generate_reroll_evaluate_and_export_full_song(self):
        backend = FakeDanceBackend()
        analysis = self.make_analysis(Path("song.wav"))
        plan = build_choreography_plan(analysis, "pop", "", 30)
        profile = RetargetProfile(
            "fixture",
            (RetargetRule("root", "センター"), RetargetRule("left_foot", "左足")),
            smoothing=0,
            maximum_speed=1000,
        )
        session = MusicToMmdSession(analysis, plan, profile, "fake", backend)
        self.assertEqual(len(session.generate(seed=12)), 3)
        self.assertIsNotNone(backend.requests[2].motif_template)
        before = len(backend.requests)
        session.regenerate_section("section-001", instruction="turn slowly", seed=22)
        self.assertEqual(len(backend.requests), before + 1)
        self.assertEqual(session.plan.sections[1].instruction, "turn slowly")
        self.assertEqual(len(session.generated_sections), 3)
        motion, keys, evaluation = session.evaluate()
        self.assertEqual(motion.fps, 30)
        self.assertTrue(keys)
        self.assertIn("beat_alignment_proxy", dict(evaluation.scores))
        ranked = session.generate_best_of_n(2, seed=100)
        self.assertEqual(len(ranked), 2)
        self.assertGreaterEqual(ranked[0][0], ranked[1][0])
        self.assertEqual(len(session.generated_sections), 3)
        with tempfile.TemporaryDirectory() as temporary:
            result = session.export(Path(temporary))
            self.assertTrue(result.vmd_path.read_bytes().startswith(b"Vocaloid Motion Data 0002"))
            self.assertEqual(json.loads(result.report_path.read_text())["backend"], "fake")
            self.assertTrue((Path(temporary) / "music-dance.choreography.json").exists())
            with self.assertRaises(FileExistsError):
                session.export(Path(temporary))

    # {
    # 責務: [test_application_has_procedural_baseline_and_wav_decoder_rejects_mp3: expose default backend]
    # 処理: [create-session uses the built-in baseline; default codec is PCM WAV]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_application_has_procedural_baseline_and_wav_decoder_rejects_mp3(self):
        registry = MusicToMmdApplication(FakeAudioDecoder(self.make_signal()))
        with tempfile.TemporaryDirectory() as temporary:
            audio = Path(temporary) / "song.mp3"
            audio.write_bytes(b"not wav")
            profile = RetargetProfile("fixture", (RetargetRule("root", "センター"),))
            session = registry.create_session(audio, profile)
            self.assertEqual(session.backend_name, "procedural_baseline")
            self.assertEqual(len(session.generate(seed=4)), len(session.plan.sections))
            self.assertTrue(session.evaluate()[1])
            with self.assertRaises(ValueError):
                WavAudioDecoder().decode(audio)


if __name__ == "__main__":
    unittest.main()
