"""Tests for evidence-preserving weak-signal candidate workflows."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from comfyui_support_tools.shared.weak_signal import (
    EvidenceKind,
    EvidenceProvenance,
    ObservationInput,
    WeakSignalApplication,
    WeakSignalBackendRegistry,
    WeakSignalMode,
    WeakSignalRequest,
)
from comfyui_support_tools.shared.weak_signal.backend import PillowWeakSignalBackend


# {
#   責務: [WeakSignalTests: image/burst candidate processing and evidence outputを検証する]
#   フィールド: [small deterministic RGB fixtures]
#   処理: [exercise mode routing, safety validation, candidate alternatives and manifest export]
# }
class WeakSignalTests(unittest.TestCase):
    # {
    #   責務: [encode: deterministic RGB imageをPNG bytesへ変換する]
    #   処理: [create test observation payloads]
    #   引数: [image: source image]
    #   戻り値: [bytes: PNG payload]
    # }
    @staticmethod
    def encode(image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    # {
    #   責務: [test_registry_excludes_unimplemented_translucent_mode: fake built-in routingを防ぐ]
    #   処理: [verify registry exposes only implemented Pillow priors]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_registry_excludes_unimplemented_translucent_mode(self) -> None:
        registry = WeakSignalBackendRegistry()
        self.assertNotIn(WeakSignalMode.TRANSLUCENT_SURFACE, registry.modes)
        with self.assertRaises(LookupError):
            registry.get(WeakSignalMode.TRANSLUCENT_SURFACE)

    # {
    #   責務: [test_manual_weak_detail_returns_ranked_evidence: manual modeの複数候補を検証する]
    #   処理: [run the actual Pillow backend and check observed/inferred evidence separation]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_manual_weak_detail_returns_ranked_evidence(self) -> None:
        image = Image.new("RGB", (32, 24), "#777777")
        ImageDraw.Draw(image).rectangle((10, 7, 20, 18), fill="#888888")
        observation = ObservationInput("detail-1", (self.encode(image),))
        result = WeakSignalApplication().process(
            observation,
            WeakSignalRequest(mode=WeakSignalMode.WEAK_DETAIL, candidate_count=3),
        )
        self.assertEqual(result.selected_mode, WeakSignalMode.WEAK_DETAIL)
        self.assertEqual(len(result.candidates), 3)
        for candidate in result.candidates:
            kinds = {item.kind for item in candidate.provenance}
            self.assertIn(EvidenceKind.OBSERVED, kinds)
            self.assertIn(EvidenceKind.ENHANCED, kinds)
            self.assertTrue(dict(candidate.scores))

    # {
    #   責務: [test_aligned_burst_exports_observed_and_inferred_components: reflection burstのlayer manifestsを検証する]
    #   処理: [fuse an aligned synthetic burst and ensure temporal residual is explicitly inferred]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_aligned_burst_exports_observed_and_inferred_components(self) -> None:
        images = []
        for x in (5, 12, 19):
            image = Image.new("RGB", (32, 24), "#505050")
            ImageDraw.Draw(image).rectangle((x, 8, x + 4, 14), fill="#ffffff")
            images.append(self.encode(image))
        observation = ObservationInput("burst-1", tuple(images), media_kind="burst")
        request = WeakSignalRequest(
            mode=WeakSignalMode.REFLECTION,
            aligned_frames_assumed=True,
        )
        result = WeakSignalApplication().process(observation, request)
        self.assertIn("transient_reflection_residual", dict(result.candidates[0].components))
        self.assertIn(
            EvidenceKind.INFERRED,
            {item.kind for item in result.candidates[0].provenance},
        )
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = WeakSignalApplication().export(result, Path(temporary))
            manifest_path = next(path for path in artifacts if path.suffix == ".json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(manifest["ocr_input_candidates"])
            self.assertEqual(manifest["schema"], "weak-signal-evidence.v1")
            self.assertTrue(
                any(path.name.startswith("reflection_conservative") for path in artifacts)
            )

    # {
    #   責務: [test_reflection_burst_requires_alignment_declaration: alignment前提を検証する]
    #   処理: [reject temporal fusion when registration is not declared]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_reflection_burst_requires_alignment_declaration(self) -> None:
        payload = self.encode(Image.new("RGB", (8, 8), "black"))
        observation = ObservationInput("burst-2", (payload,) * 3, media_kind="burst")
        with self.assertRaisesRegex(ValueError, "alignment declaration"):
            PillowWeakSignalBackend().generate(
                observation,
                WeakSignalRequest(mode=WeakSignalMode.REFLECTION),
                WeakSignalMode.REFLECTION,
            )

    # {
    #   責務: [test_contracts_reject_non_numeric_scores: malformed plugin dataを拒否する]
    #   処理: [ensure bad confidence values fail as documented validation errors]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_contracts_reject_non_numeric_scores(self) -> None:
        with self.assertRaises((TypeError, ValueError)):
            EvidenceProvenance("region", EvidenceKind.OBSERVED, "unknown", "test")


if __name__ == "__main__":
    unittest.main()
