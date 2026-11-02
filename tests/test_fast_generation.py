"""Resource-aware fast-generation contracts, routing and telemetry tests."""

from __future__ import annotations

import json
import tempfile
from threading import Event
import unittest
from pathlib import Path
from scripts.backend.fast_generation_policy import resolve_fast_generation

from comfyui_support_tools.shared.fast_generation import (
    FastGenerationRouter,
    ComfyUIPeakMemorySampler,
    FastRouteRequest,
    GenerationHistory,
    GenerationIntent,
    GenerationMeasurement,
    GenerationMode,
    ModelCapability,
    Quantization,
    RuntimeResources,
    create_default_fast_model_profiles,
    probe_comfyui_resources,
    quality_per_gib,
    quality_per_second,
    run_draft_to_final,
    summarize_generation_history,
)


# {
#   責務: [FastGenerationTests: fast model resource routing and measurement persistenceを検証する]
#   フィールド: [default router]
#   処理: [実GPUやComfyUIなしでresource gates, variant choice, unknown metricsを確認する]
# }
class FastGenerationTests(unittest.TestCase):
    # {
    #   責務: [setUp: built-in variant descriptorでrouterを作る]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def setUp(self) -> None:
        self.router = FastGenerationRouter(create_default_fast_model_profiles())

    # {
    #   責務: [test_routes_flux2_klein_when_resource_and_precision_are_declared: eligible model選択を検証する]
    #   処理: [8-16 GB帯のresource snapshotとinstalled Klein modelをrouteしdeclared step countを確認する]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_routes_flux2_klein_when_resource_and_precision_are_declared(self) -> None:
        resources = RuntimeResources(
            gpu_vram_gib=12,
            system_ram_gib=32,
            backend="comfyui",
            quantizations=frozenset({Quantization.FP8}),
        )
        result = self.router.route(FastRouteRequest(("flux2-klein-4b-fp8.safetensors",), resources))
        self.assertEqual(result.profile.profile_id, "flux2_klein_4b_distilled")
        self.assertEqual(result.quantization, Quantization.FP8)
        self.assertEqual(result.profile.steps, 4)

    # {
    #   責務: [test_quantized_variant_can_fit_eight_gib_gpu: per-precision memory profileを検証する]
    #   処理: [select a declared int4 variant within the issue's 8-GiB device target]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_quantized_variant_can_fit_eight_gib_gpu(self) -> None:
        resources = RuntimeResources(
            8,
            18,
            "comfyui",
            quantizations=frozenset({Quantization.INT4}),
        )
        result = self.router.route(
            FastRouteRequest(("flux2-klein-4b-int4.safetensors",), resources)
        )
        self.assertEqual(result.quantization, Quantization.INT4)

    # {
    #   責務: [test_rejects_unknown_resources_and_quality_mode: fail-closed behaviorを検証する]
    #   処理: [unknown resource, no headroom, and quality preference do not auto-select a fast variant]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_rejects_unknown_resources_and_quality_mode(self) -> None:
        unknown = RuntimeResources(
            None, None, "comfyui", quantizations=frozenset({Quantization.FP8})
        )
        with self.assertRaisesRegex(LookupError, "requires known"):
            self.router.route(FastRouteRequest(("flux2 klein 4b fp8",), unknown))
        insufficient = RuntimeResources(
            8, 16, "comfyui", quantizations=frozenset({Quantization.FP8})
        )
        with self.assertRaisesRegex(LookupError, "no installed"):
            self.router.route(FastRouteRequest(("flux2 klein 4b fp8",), insufficient))
        adequate = RuntimeResources(12, 32, "comfyui", quantizations=frozenset({Quantization.FP8}))
        with self.assertRaisesRegex(LookupError, "disabled"):
            self.router.route(
                FastRouteRequest(("flux2 klein 4b fp8",), adequate, mode=GenerationMode.QUALITY)
            )

    # {
    #   責務: [test_sana_sprint_is_more_specific_than_sana_alias: family boundaryを検証する]
    #   処理: [longest alias matching keeps Sana Sprint from being classified as generic Sana]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_sana_sprint_is_more_specific_than_sana_alias(self) -> None:
        resources = RuntimeResources(
            12, 32, "comfyui", quantizations=frozenset({Quantization.INT4})
        )
        result = self.router.route(FastRouteRequest(("Sana-Sprint-int4",), resources))
        self.assertEqual(result.profile.profile_id, "sana_sprint")

    # {
    #   責務: [test_flux_base_variant_exposes_finetune_capability_without_fast_autoroute: base profileの分離を検証する]
    #   処理: [base checkpoint advertises LoRA fine-tuning but automatic draft routing skips it]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_flux_base_variant_exposes_finetune_capability_without_fast_autoroute(self) -> None:
        profile = next(
            item
            for item in create_default_fast_model_profiles()
            if item.profile_id == "flux2_klein_4b_base"
        )
        self.assertIn(ModelCapability.LORA_FINETUNE, profile.capabilities)
        resources = RuntimeResources(24, 48, "comfyui")
        with self.assertRaisesRegex(LookupError, "no installed"):
            self.router.route(FastRouteRequest(("flux2 klein 4b base",), resources))

    # {
    #   責務: [test_explicit_model_is_preserved_and_backend_must_match: explicit model selectionを検証する]
    #   処理: [explicit compatible variant is honored and incompatible backend is rejected]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_explicit_model_is_preserved_and_backend_must_match(self) -> None:
        resources = RuntimeResources(12, 32, "comfyui", quantizations=frozenset({Quantization.FP8}))
        result = self.router.route(
            FastRouteRequest(
                ("flux2 klein 4b fp8",),
                resources,
                explicit_model="flux2 klein 4b fp8",
            )
        )
        self.assertEqual(result.model, "flux2 klein 4b fp8")
        other_backend = RuntimeResources(
            12, 32, "a1111", quantizations=frozenset({Quantization.FP8})
        )
        with self.assertRaisesRegex(LookupError, "does not fit"):
            self.router.route(
                FastRouteRequest(
                    ("flux2 klein 4b fp8",),
                    other_backend,
                    explicit_model="flux2 klein 4b fp8",
                )
            )

    # {
    #   責務: [test_comfyui_resource_probe_keeps_missing_quantization_unknown: probe parseを検証する]
    #   処理: [system_stats bytes become GiB and quantization is not inferred]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_comfyui_resource_probe_keeps_missing_quantization_unknown(self) -> None:
        class Response:
            # {
            #   責務: [raise_for_status: fake successful HTTP response]
            #   引数: [self: response]
            #   戻り値: []
            # }
            def raise_for_status(self) -> None:
                return None

            # {
            #   責務: [json: return a ComfyUI system_stats fixture]
            #   引数: [self: response]
            #   戻り値: [dict: GPU and system capacities]
            # }
            def json(self) -> dict:
                return {
                    "system": {
                        "ram_total": 32 * 1024**3,
                        "ram_free": 28 * 1024**3,
                    },
                    "devices": [
                        {
                            "vram_total": 12 * 1024**3,
                            "vram_free": 10 * 1024**3,
                            "type": "cuda",
                        }
                    ],
                }

        calls = []

        def request_get(url, timeout):
            calls.append((url, timeout))
            return Response()

        resources = probe_comfyui_resources("http://localhost:8188/", request_get)
        self.assertEqual(resources.gpu_vram_gib, 12)
        self.assertEqual(resources.system_ram_gib, 32)
        self.assertEqual(resources.available_vram_gib, 10)
        self.assertEqual(resources.available_ram_gib, 28)
        self.assertEqual(resources.quantizations, frozenset())
        self.assertEqual(calls, [("http://localhost:8188/system_stats", 5)])

    # {
    #   責務: [test_peak_memory_sampler_tracks_observed_busy_memory: poll-based VRAM peak測定を検証する]
    #   処理: [sample two free-memory values and retain only the observed peak]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_peak_memory_sampler_tracks_observed_busy_memory(self) -> None:
        observed = Event()
        samples = iter((8, 2))
        sampler = None

        class Response:
            # {
            #   責務: [__init__: one VRAM free-memory observationを設定する]
            #   引数: [self: response, free_gib: available GPU memory]
            #   戻り値: []
            # }
            def __init__(self, free_gib: int) -> None:
                self._free_gib = free_gib

            # {
            #   責務: [raise_for_status: fake HTTP request successを表す]
            #   引数: [self: response]
            #   戻り値: []
            # }
            def raise_for_status(self) -> None:
                return None

            # {
            #   責務: [json: current free memory valueをComfyUI payloadとして返す]
            #   引数: [self: response]
            #   戻り値: [dict: one device memory payload]
            # }
            def json(self) -> dict:
                return {
                    "devices": [
                        {
                            "type": "cuda",
                            "vram_total": 12 * 1024**3,
                            "vram_free": self._free_gib * 1024**3,
                        }
                    ]
                }

        def request_get(_url, timeout):
            self.assertEqual(timeout, 2)
            free_gib = next(samples)
            if free_gib == 2:
                observed.set()
            return Response(free_gib)

        sampler = ComfyUIPeakMemorySampler("http://localhost:8188", request_get, 0.01)
        sampler.start()
        self.assertTrue(observed.wait(timeout=1))
        self.assertEqual(sampler.stop(), 10)

    # {
    #   責務: [test_fast_policy_routes_only_installed_profiles_and_guards_workflow_overrides: backend adapterを検証する]
    #   処理: [query ComfyUI resource metadata, choose an installed native Klein variant, and reject workflow ambiguity]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_fast_policy_routes_only_installed_profiles_and_guards_workflow_overrides(self) -> None:
        class Response:
            # {
            #   責務: [raise_for_status: fake resource response is successful]
            #   引数: [self: response]
            #   戻り値: []
            # }
            def raise_for_status(self) -> None:
                return None

            # {
            #   責務: [json: provide a representative 12-GiB runtime]
            #   引数: [self: response]
            #   戻り値: [dict: ComfyUI system resource payload]
            # }
            def json(self) -> dict:
                return {
                    "system": {
                        "ram_total": 32 * 1024**3,
                        "ram_free": 30 * 1024**3,
                    },
                    "devices": [
                        {
                            "vram_total": 12 * 1024**3,
                            "vram_free": 11 * 1024**3,
                            "type": "cuda",
                        }
                    ],
                }

        resolution = resolve_fast_generation(
            "large quality checkpoint",
            30,
            {"checkpoints": ["FLUX.2 Klein 4B.safetensors"]},
            "http://localhost:8188",
            auto_route=True,
            request_get=lambda *_args, **_kwargs: Response(),
        )
        self.assertEqual(resolution.checkpoint, "FLUX.2 Klein 4B.safetensors")
        self.assertEqual(resolution.steps, 4)
        self.assertEqual(resolution.gpu_vram_gib, 12)
        self.assertEqual(resolution.available_vram_gib, 11)
        balanced = resolve_fast_generation(
            "large quality checkpoint",
            20,
            {"checkpoints": ["FLUX.2 Klein 4B.safetensors"]},
            "http://localhost:8188",
            mode=GenerationMode.BALANCED,
            auto_route=True,
            request_get=lambda *_args, **_kwargs: Response(),
        )
        self.assertEqual(balanced.steps, 20)
        with self.assertRaisesRegex(ValueError, "explicit ComfyUI"):
            resolve_fast_generation(
                "large quality checkpoint",
                30,
                {"checkpoints": ["FLUX.2 Klein 4B.safetensors"]},
                "http://localhost:8188",
                auto_route=True,
                has_explicit_model_overrides=True,
                request_get=lambda *_args, **_kwargs: Response(),
            )

    # {
    #   責務: [test_generation_history_persists_measurements_and_efficiency: measurement storageを検証する]
    #   処理: [append stable JSONL, keep missing peak VRAM unknown, and compute score per second]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_generation_history_persists_measurements_and_efficiency(self) -> None:
        measurement = GenerationMeasurement(
            "flux2_klein", "flux2-klein-fp8", 2, None, prompt_alignment=0.8
        )
        self.assertEqual(quality_per_second(measurement), 0.4)
        self.assertIsNone(quality_per_gib(measurement))
        with tempfile.TemporaryDirectory() as directory:
            path = GenerationHistory(Path(directory) / "history.jsonl").append(measurement)
            record = json.loads(path.read_text(encoding="utf-8"))
            summary = summarize_generation_history(path)[0]
        self.assertIsNone(record["peak_vram_gib"])
        self.assertEqual(record["model"], "flux2-klein-fp8")
        self.assertEqual(summary.images_per_minute, 30)
        self.assertIsNone(summary.average_peak_vram_gib)

    # {
    #   責務: [test_draft_pipeline_ranks_candidates_and_rerenders_selected_image: Draft-to-HQ flowを検証する]
    #   処理: [generate four deterministic drafts, retain top two, and render only the best as final]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_draft_pipeline_ranks_candidates_and_rerenders_selected_image(self) -> None:
        final_inputs = []
        result = run_draft_to_final(
            4,
            lambda candidate_id: f"draft-{candidate_id}".encode(),
            lambda image: int(image.rsplit(b"-", 1)[-1]) / 3,
            top_k=2,
            render_final=lambda image: final_inputs.append(image) or b"final",
        )
        self.assertEqual([item.candidate_id for item in result.candidates], [3, 2])
        self.assertEqual(final_inputs, [b"draft-3"])
        self.assertEqual(result.final_image, b"final")

    # {
    #   責務: [test_draft_pipeline_rejects_invalid_candidate_counts: batch boundsを検証する]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_draft_pipeline_rejects_invalid_candidate_counts(self) -> None:
        with self.assertRaises(ValueError):
            run_draft_to_final(0, lambda _candidate_id: b"draft", lambda _image: 0.5)


if __name__ == "__main__":
    unittest.main()
