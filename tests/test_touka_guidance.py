"""Tests for soft sparse hints, rasterized region priors, and contradiction diagnostics."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from nuno._touka.guidance import (
    GuidanceHints,
    GuidancePoint,
    GuidanceScribble,
    apply_guidance_prior,
    detect_guidance_conflicts,
    load_guidance,
    save_guidance,
)
from scripts.backend.guidance_document import (
    GuidanceHints as UiGuidanceHints,
)
from scripts.backend.guidance_document import (
    GuidancePoint as UiGuidancePoint,
)
from scripts.backend.guidance_document import (
    GuidanceScribble as UiGuidanceScribble,
)
from scripts.backend.guidance_document import (
    load_guidance as load_ui_guidance,
)
from scripts.backend.guidance_document import (
    save_guidance as save_ui_guidance,
)


# {
#   責務: [ToukaGuidanceTests: hints schema, regional image changes and warning flowを検証する]
#   フィールド: [small synthetic images and normalized hint fixtures]
#   処理: [prove hints remain optional, confidence-weighted, reversible and serializable]
# }
class ToukaGuidanceTests(unittest.TestCase):
    # {
    #   責務: [test_sparse_hidden_point_changes_only_guided_region: point priorの局所性を検証する]
    #   処理: [blend enhanced pixels under a low-confidence point mask]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_sparse_hidden_point_changes_only_guided_region(self) -> None:
        source = Image.new("RGB", (32, 32), "black")
        enhanced = Image.new("RGB", (32, 32), "white")
        hints = GuidanceHints(points=(GuidancePoint(0.5, 0.5, "hidden_object", 0.6),))
        guided, warnings = apply_guidance_prior(source, enhanced, hints)
        self.assertGreater(guided.getpixel((16, 16))[0], 100)
        self.assertEqual(guided.getpixel((0, 0)), (0, 0, 0))
        self.assertEqual(warnings, ())

    # {
    #   責務: [test_exclude_scribble_preserves_observation: exclude mask behaviorを検証する]
    #   処理: [keep excluded source pixels while allowing enhanced candidate outside the stroke]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_exclude_scribble_preserves_observation(self) -> None:
        source = Image.new("RGB", (40, 40), "black")
        enhanced = Image.new("RGB", (40, 40), "white")
        hints = GuidanceHints(
            scribbles=(GuidanceScribble(((0.1, 0.5), (0.9, 0.5)), "exclude", 0.1, 0.9),)
        )
        guided, _warnings = apply_guidance_prior(source, enhanced, hints)
        self.assertEqual(guided.getpixel((20, 20)), (0, 0, 0))
        self.assertEqual(guided.getpixel((20, 3)), (0, 0, 0))

    # {
    #   責務: [test_color_sample_and_overlap_conflicts_are_reported: contradiction detectorを検証する]
    #   処理: [compare expected sample color and opposite-class scribble overlap]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_color_sample_and_overlap_conflicts_are_reported(self) -> None:
        source = Image.new("RGB", (32, 32), "black")
        hints = GuidanceHints(
            points=(GuidancePoint(0.5, 0.5, "color_sample", 0.9, (255, 255, 255)),),
            scribbles=(
                GuidanceScribble(((0.2, 0.5), (0.8, 0.5)), "surface", 0.15, 0.9),
                GuidanceScribble(((0.5, 0.2), (0.5, 0.8)), "hidden_object", 0.15, 0.9),
            ),
        )
        warnings = detect_guidance_conflicts(source, hints)
        self.assertIn("color_sample_conflict:0", warnings)
        self.assertIn("overlapping_surface_hidden_scribbles", warnings)

    # {
    #   責務: [test_no_hints_preserves_existing_automatic_candidate: optionalityを検証する]
    #   処理: [return candidate pixels unchanged when the guidance document contains no annotations]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_no_hints_preserves_existing_automatic_candidate(self) -> None:
        source = Image.new("RGB", (4, 4), "black")
        candidate = Image.new("RGB", (4, 4), "gray")
        result, _warnings = apply_guidance_prior(source, candidate, GuidanceHints())
        self.assertEqual(result.tobytes(), candidate.tobytes())

    # {
    #   責務: [test_guidance_json_round_trip: local schema serializationを検証する]
    #   処理: [save and reload normalized point/scribble annotations]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_guidance_json_round_trip(self) -> None:
        hints = GuidanceHints(
            points=(GuidancePoint(0.25, 0.75, "edge", 0.8),),
            scribbles=(GuidanceScribble(((0.1, 0.1), (0.4, 0.4)), "surface"),),
            category="cloth",
            material="thin_cloth",
            source_sha256="a" * 64,
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = save_guidance(Path(temporary) / "hints.json", hints)
            self.assertEqual(load_guidance(path), hints)

    # {
    #   責務: [test_touka_cli_applies_guidance_and_keeps_hint_free_path: external CLI integrationを検証する]
    #   処理: [run image processing with and without hints and compare saved candidates]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_touka_cli_applies_guidance_and_keeps_hint_free_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.png"
            automatic = root / "automatic.png"
            guided = root / "guided.png"
            hints_path = root / "guidance.json"
            image = Image.new("RGB", (64, 64), "#777777")
            pixels = image.load()
            for y in range(16, 48):
                for x in range(16, 48):
                    pixels[x, y] = (150, 150, 150)
            image.save(source)
            save_guidance(
                hints_path,
                GuidanceHints(
                    points=(GuidancePoint(0.5, 0.5, "hidden_object", 0.9),),
                    category="cloth",
                    material="thin_cloth",
                    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                ),
            )
            base_command = [
                sys.executable,
                "nuno/_touka/touka_batch.py",
                "--mode",
                "image",
                "--input",
                str(source),
                "--profile",
                "balanced",
            ]
            subprocess.run(
                [*base_command, "--output", str(automatic)],
                check=True,
                capture_output=True,
                timeout=60,
            )
            subprocess.run(
                [*base_command, "--output", str(guided), "--guidance", str(hints_path)],
                check=True,
                capture_output=True,
                timeout=60,
            )
            with Image.open(automatic) as automatic_image, Image.open(guided) as guided_image:
                self.assertNotEqual(
                    automatic_image.convert("RGB").tobytes(), guided_image.convert("RGB").tobytes()
                )

    # {
    #   責務: [test_gui_and_touka_cli_share_file_contract: process boundary schema compatibilityを検証する]
    #   処理: [round trip guidance-hints.v1 between main UI DTO and packaged Touka DTO]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_gui_and_touka_cli_share_file_contract(self) -> None:
        ui_hints = UiGuidanceHints(
            points=(UiGuidancePoint(0.4, 0.6, "color_sample", 0.8, (12, 34, 56)),),
            scribbles=(UiGuidanceScribble(((0.1, 0.2), (0.8, 0.9)), "hidden_object"),),
            category="cloth",
            material="thin_cloth",
            source_sha256="b" * 64,
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = save_ui_guidance(Path(temporary) / "hints.json", ui_hints)
            cli_hints = load_guidance(path)
            self.assertEqual(cli_hints.to_dict(), ui_hints.to_dict())
            save_guidance(path, cli_hints)
            self.assertEqual(load_ui_guidance(path).to_dict(), ui_hints.to_dict())

    # {
    #   責務: [test_invalid_coordinates_and_schema_are_rejected: malformed hint inputを拒否する]
    #   処理: [validate coordinates before using annotations as pixel masks]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_invalid_coordinates_and_schema_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GuidancePoint(1.2, 0.5, "edge")
        with self.assertRaises(ValueError):
            GuidanceHints.from_dict({"schema": "other"})


if __name__ == "__main__":
    unittest.main()
