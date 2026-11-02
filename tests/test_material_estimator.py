"""Tests for spatial material maps, uncertainty routing, and synthetic map evaluation."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from nuno._touka.material_estimator import (
    ClassicalMaterialEstimator,
    MaterialEstimatorRegistry,
    apply_surface_estimate,
    evaluate_against_ground_truth,
)


# {
#   責務: [MaterialEstimatorTests: local map hypotheses, priors, fallback and GT evaluationを検証する]
#   フィールド: [deterministic synthetic surface/transmission composition]
#   処理: [measure spatial variation and route conservative estimates under uncertainty]
# }
class MaterialEstimatorTests(unittest.TestCase):
    # {
    #   責務: [_synthetic_capture: spatially varying alphaのsmall RGB inputとknown mapsを作る]
    #   処理: [compose a textured hidden layer with known surface color and local alpha]
    #   引数: [self: test case]
    #   戻り値: [tuple: input image, alpha GT, transmission GT, surface RGB GT]
    # }
    def _synthetic_capture(self):
        height, width = 48, 64
        y, x = np.mgrid[:height, :width]
        hidden = np.stack(
            (
                60 + (x * 3) % 150,
                50 + (y * 4) % 170,
                70 + ((x + y) * 2) % 140,
            ),
            axis=2,
        ).astype(np.float32)
        alpha = (0.08 + 0.22 * x / (width - 1)).astype(np.float32)
        surface_color = np.zeros_like(hidden)
        surface_color[:] = (188, 176, 158)
        mixed = alpha[..., None] * surface_color + (1 - alpha[..., None]) * hidden
        return (
            Image.fromarray(np.clip(mixed, 0, 255).astype(np.uint8), "RGB"),
            Image.fromarray(np.round(alpha * 255).astype(np.uint8), "L"),
            Image.fromarray(np.round((1 - alpha) * 255).astype(np.uint8), "L"),
            Image.fromarray(surface_color.astype(np.uint8), "RGB"),
        )

    # {
    #   責務: [test_estimator_returns_spatial_maps_and_multiple_hypotheses: local mapsを検証する]
    #   処理: [assert alpha map varies by region and transmission maps complement alpha]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_estimator_returns_spatial_maps_and_multiple_hypotheses(self) -> None:
        source, _alpha, _transmission, _surface = self._synthetic_capture()
        estimate_set = ClassicalMaterialEstimator().estimate(source)
        self.assertEqual(len(estimate_set.estimates), 3)
        arrays = [
            np.asarray(Image.open(io.BytesIO(item.alpha_map)).convert("L"))
            for item in estimate_set.estimates
        ]
        self.assertGreater(float(arrays[1].std()), 0.1)
        self.assertLess(float(arrays[0].mean()), float(arrays[1].mean()))
        self.assertGreater(float(arrays[2].mean()), float(arrays[1].mean()))
        self.assertTrue(estimate_set.warnings)
        self.assertTrue(estimate_set.estimates[0].uncertainty_map)

    # {
    #   責務: [test_high_uncertainty_routes_to_small_conservative_change: uncertainty boundsを検証する]
    #   処理: [compare candidate difference across conservative and enhanced map hypotheses]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_high_uncertainty_routes_to_small_conservative_change(self) -> None:
        source, _alpha, _transmission, _surface = self._synthetic_capture()
        estimates = ClassicalMaterialEstimator().estimate(source).estimates
        conservative = apply_surface_estimate(source, estimates[0], "conservative")
        enhanced = apply_surface_estimate(source, estimates[2], "shape_strong")
        source_pixels = np.asarray(source, dtype=np.float32)
        conservative_change = np.abs(
            np.asarray(conservative, dtype=np.float32) - source_pixels
        ).mean()
        enhanced_change = np.abs(np.asarray(enhanced, dtype=np.float32) - source_pixels).mean()
        self.assertLess(conservative_change, enhanced_change)

    # {
    #   責務: [test_synthetic_ground_truth_evaluation_reports_separate_map_errors: GT metricを検証する]
    #   処理: [evaluate estimated maps against known alpha/transmission/surface maps]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_synthetic_ground_truth_evaluation_reports_separate_map_errors(self) -> None:
        source, alpha, transmission, surface = self._synthetic_capture()
        estimate = ClassicalMaterialEstimator().estimate(source).estimates[1]
        report = evaluate_against_ground_truth(estimate, alpha, transmission, surface)
        for value in (report.alpha_mae, report.transmittance_mae, report.surface_color_mae):
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 1)

    # {
    #   責務: [test_reference_and_material_prior_change_hypothesis: optional priorsを検証する]
    #   処理: [compare prior-free, named material and reference alpha estimates]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_reference_and_material_prior_change_hypothesis(self) -> None:
        source, _alpha, _transmission, _surface = self._synthetic_capture()
        estimator = ClassicalMaterialEstimator()
        prior_free = estimator.estimate(source).estimates[1]
        material = estimator.estimate(source, "cloth", "thin_cloth").estimates[1]
        referenced = estimator.estimate(
            source, "cloth", "thin_cloth", ((190, 180, 160),), 0.2
        ).estimates[1]
        self.assertNotEqual(prior_free.alpha_map, material.alpha_map)
        self.assertNotEqual(material.alpha_map, referenced.alpha_map)
        self.assertLess(material.confidence, 0.7)

    # {
    #   責務: [test_registry_exposes_pluggable_estimator_collection: multiple estimator comparison seamを検証する]
    #   処理: [default registry provides a usable estimate set without learned model dependencies]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_registry_exposes_pluggable_estimator_collection(self) -> None:
        source, _alpha, _transmission, _surface = self._synthetic_capture()
        results = MaterialEstimatorRegistry().estimate(source)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0].estimates), 3)

    # {
    #   責務: [test_map_application_rejects_dimension_mismatch: source binding safetyを検証する]
    #   処理: [reject maps from a differently sized input]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_map_application_rejects_dimension_mismatch(self) -> None:
        source, _alpha, _transmission, _surface = self._synthetic_capture()
        estimate = ClassicalMaterialEstimator().estimate(source).estimates[0]
        with self.assertRaisesRegex(ValueError, "dimensions"):
            apply_surface_estimate(Image.new("RGB", (5, 5)), estimate)

    # {
    #   責務: [test_image_cli_writes_local_maps_and_hypothesis_manifest: batch integrationを検証する]
    #   処理: [run image CLI and inspect candidate maps plus provenance report]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_image_cli_writes_local_maps_and_hypothesis_manifest(self) -> None:
        source, _alpha, _transmission, _surface = self._synthetic_capture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "source.png"
            output_path = root / "output.png"
            source.save(source_path)
            subprocess.run(
                [
                    sys.executable,
                    "nuno/_touka/touka_batch.py",
                    "--mode",
                    "image",
                    "--input",
                    str(source_path),
                    "--output",
                    str(output_path),
                    "--profile",
                    "conservative",
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
            report = json.loads(output_path.with_name("output.material.json").read_text())
            self.assertEqual(report["schema"], "surface-estimates.v1")
            selected = report["inputs"][0]
            self.assertTrue(selected["selected_estimate"]["estimate_id"].endswith(":conservative"))
            self.assertEqual(len(selected["hypotheses"]), 3)
            self.assertTrue(
                all((output_path.parent / item).is_file() for item in selected["map_files"])
            )


if __name__ == "__main__":
    unittest.main()
