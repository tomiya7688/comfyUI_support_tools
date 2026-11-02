"""Behavioral checks for explainable task and constraint routing."""

from __future__ import annotations

import unittest
from dataclasses import replace

from comfyui_support_tools.shared.capability_router import (
    CapabilityRegistry,
    CapabilityRouter,
    EvaluatorRegistry,
    GenerationIntent,
    GenerationUseCase,
    create_default_benchmark_matrix,
    create_default_capabilities,
    run_cross_family_best_of_n,
)
from scripts.backend.capability_routing_policy import resolve_generation_capability


# {
#   責務: [CapabilityRouterTests: use-case routing, hard constraints, benchmark and evaluator adaptersを検証する]
#   フィールド: [test fixtures and observable state]
#   処理: [deterministic registry fixturesでGUI/device/serviceなしにrouter behaviorを確認する]
# }
class CapabilityRouterTests(unittest.TestCase):
    # {
    #   責務: [setUp: conservative built-in profilesとworkflow IDsを準備する]
    #   処理: [execute the declared behavioral assertion for this route/evaluator fixture]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def setUp(self) -> None:
        self.registry = CapabilityRegistry(create_default_capabilities())
        self.router = CapabilityRouter(self.registry)
        self.workflows = (
            "flux2_klein_4b.json",
            "flux2_dev.json",
            "qwen_image_2_1.json",
            "sana_sprint.json",
            "sdxl_anime.json",
        )

    # {
    #   責務: [test_use_case_changes_selected_family: same installed setでもanime intentがanime profileを選ぶことを確認する]
    #   処理: [execute the declared behavioral assertion for this route/evaluator fixture]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_use_case_changes_selected_family(self) -> None:
        models = ("flux2-klein-4b-int4.safetensors", "Animagine XL 4.0.safetensors")
        common = dict(
            backend="comfyui",
            installed_models=models,
            available_workflows=self.workflows,
            available_vram_gib=12,
            available_ram_gib=32,
        )
        self.assertEqual(
            self.router.route(
                GenerationIntent(GenerationUseCase.GENERAL, **common)
            ).capability.family,
            "flux2_klein",
        )
        self.assertEqual(
            self.router.route(
                GenerationIntent(GenerationUseCase.ANIME, **common)
            ).capability.family,
            "sdxl_anime",
        )

    # {
    #   責務: [test_low_vram_filters_large_or_unknown_profiles: resource evidence is applied before ranking]
    #   処理: [execute the declared behavioral assertion for this route/evaluator fixture]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_low_vram_filters_large_or_unknown_profiles(self) -> None:
        route = self.router.route(
            GenerationIntent(
                GenerationUseCase.LOW_VRAM,
                backend="comfyui",
                installed_models=("flux2-klein-4b-int4.safetensors", "Sana-Sprint.safetensors"),
                available_workflows=self.workflows,
                available_vram_gib=5,
                available_ram_gib=24,
                candidate_count=2,
            )
        )
        self.assertEqual(route.capability.family, "flux2_klein")
        self.assertEqual({profile.family for _, profile in route.candidates}, {"flux2_klein"})
        self.assertIn(("Sana-Sprint.safetensors", "requires 8 GiB VRAM"), route.excluded)

    # {
    #   責務: [test_typography_requires_capability_and_installed_workflow: specialized intent never falls back silently]
    #   処理: [execute the declared behavioral assertion for this route/evaluator fixture]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_typography_requires_capability_and_installed_workflow(self) -> None:
        route = self.router.route(
            GenerationIntent(
                GenerationUseCase.TYPOGRAPHY,
                backend="comfyui",
                installed_models=("Qwen-Image-2.1.safetensors", "flux2-klein-4b.safetensors"),
                available_workflows=self.workflows,
                allow_unverified_resource=True,
                text_rendering_required=True,
            )
        )
        self.assertEqual(route.capability.profile_id, "qwen_image_2_1")
        with self.assertRaisesRegex(LookupError, "no installed model"):
            self.router.route(
                GenerationIntent(
                    GenerationUseCase.TYPOGRAPHY,
                    backend="comfyui",
                    installed_models=("Qwen-Image-2.1.safetensors",),
                    available_workflows=(),
                    allow_unverified_resource=True,
                    text_rendering_required=True,
                )
            )

    # {
    #   責務: [test_commercial_routing_fails_closed_on_unverified_licenses: permissive labels are insufficient without verified evidence]
    #   処理: [execute the declared behavioral assertion for this route/evaluator fixture]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_commercial_routing_fails_closed_on_unverified_licenses(self) -> None:
        with self.assertRaisesRegex(LookupError, "no installed model"):
            self.router.route(
                GenerationIntent(
                    GenerationUseCase.GENERAL,
                    backend="comfyui",
                    installed_models=("flux2-klein-4b.safetensors",),
                    available_workflows=self.workflows,
                    available_vram_gib=12,
                    available_ram_gib=32,
                    commercial_required=True,
                )
            )

    # {
    #   責務: [test_manual_model_is_preserved_only_after_constraints: manual override stays inside hard gates]
    #   処理: [execute the declared behavioral assertion for this route/evaluator fixture]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_manual_model_is_preserved_only_after_constraints(self) -> None:
        intent = GenerationIntent(
            GenerationUseCase.GENERAL,
            backend="comfyui",
            installed_models=("flux2-klein-4b-int4.safetensors",),
            available_workflows=self.workflows,
            available_vram_gib=8,
            available_ram_gib=24,
            manual_model="flux2-klein-4b-int4.safetensors",
        )
        self.assertEqual(self.router.route(intent).selected_model, intent.manual_model)
        with self.assertRaisesRegex(LookupError, "manual model"):
            self.router.route(replace(intent, available_vram_gib=3))

    # {
    #   責務: [test_evaluator_registry_and_fixed_matrix_are_task_specific: evaluator API does not invent a universal score]
    #   処理: [execute the declared behavioral assertion for this route/evaluator fixture]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_evaluator_registry_and_fixed_matrix_are_task_specific(self) -> None:
        # {
        #   責務: [FakeEvaluator: deterministic task scoreを返すtest double]
        #   フィールド: [prompt alignment score]
        # }
        class FakeEvaluator:
            # {
            #   責務: [evaluate: deterministic prompt alignment fixtureを返す]
            #   処理: [execute the declared behavioral assertion for this route/evaluator fixture]
            #   引数: [self: evaluator, prompt/image/model values]
            #   戻り値: [dict[str, float]: task-specific score]
            # }
            def evaluate(self, prompt: str, image_bytes: bytes, model_id: str):
                return {"prompt_alignment": 0.8}

        evaluators = EvaluatorRegistry({GenerationUseCase.GENERAL: FakeEvaluator()})
        scores = evaluators.evaluate(GenerationUseCase.GENERAL, "same prompt", b"png", "profile")
        self.assertEqual(scores, {"prompt_alignment": 0.8})
        matrix = create_default_benchmark_matrix()
        self.assertEqual(len(matrix), 5)
        self.assertEqual(matrix[3].selection_metric, "ocr_exactness")

    # {
    #   責務: [test_cross_family_best_of_n_ranks_only_declared_task_metric: same-prompt candidates are ranked transparently]
    #   処理: [execute the declared behavioral assertion for this route/evaluator fixture]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_cross_family_best_of_n_ranks_only_declared_task_metric(self) -> None:
        route = self.router.route(
            GenerationIntent(
                GenerationUseCase.FAST_DRAFT,
                backend="comfyui",
                installed_models=("flux2-klein-4b-int4.safetensors", "Sana-Sprint.safetensors"),
                available_workflows=self.workflows,
                available_vram_gib=12,
                available_ram_gib=32,
                allow_unverified_resource=True,
                candidate_count=2,
            )
        )
        plan = run_cross_family_best_of_n(
            route,
            "same prompt",
            lambda model, _profile: model.encode(),
            lambda _prompt, image, _profile: {"prompt_alignment": 0.9 if b"Sana" in image else 0.7},
            selection_metric="prompt_alignment",
            top_k=1,
        )
        self.assertEqual(len(plan.candidates), 1)
        self.assertIn("Sana", plan.candidates[0].model)

    # {
    #   責務: [test_comfyui_adapter_routes_workflow_from_live_catalog_and_memory: UI adapterがinstalled namesとfree memoryを使うことを確認する]
    #   処理: [execute the declared behavioral assertion for this route/evaluator fixture]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_comfyui_adapter_routes_workflow_from_live_catalog_and_memory(self) -> None:
        # {
        #   責務: [FakeResponse: ComfyUI memory probe用HTTP test response]
        #   フィールド: [host RAM and GPU VRAM fixture values]
        # }
        class FakeResponse:
            # {
            #   責務: [raise_for_status: fake resource responseをsuccessfulとして扱う]
            #   処理: [execute the declared behavioral assertion for this route/evaluator fixture]
            #   引数: [self: response fixture]
            #   戻り値: []
            # }
            def raise_for_status(self):
                return None

            # {
            #   責務: [json: resource probe用ComfyUI payloadを返す]
            #   処理: [execute the declared behavioral assertion for this route/evaluator fixture]
            #   引数: [self: response fixture]
            #   戻り値: [dict: host RAM and CUDA VRAM fields]
            # }
            def json(self):
                gib = 1024**3
                return {
                    "system": {"ram_total": 32 * gib, "ram_free": 24 * gib},
                    "devices": [
                        {
                            "type": "cuda",
                            "name": "test GPU",
                            "vram_total": 12 * gib,
                            "vram_free": 10 * gib,
                        }
                    ],
                }

        result = resolve_generation_capability(
            GenerationUseCase.ANIME,
            {
                "checkpoints": ["flux2-klein-4b-int4.safetensors", "Animagine XL 4.0.safetensors"],
                "flows": list(self.workflows),
            },
            "http://127.0.0.1:8188",
            request_get=lambda _url, timeout: FakeResponse(),
            resolution=(768, 1024),
        )
        self.assertEqual(result.route.capability.family, "sdxl_anime")
        self.assertEqual(result.workflow, "sdxl_anime.json")
        self.assertEqual(result.device_name, "test GPU")


if __name__ == "__main__":
    unittest.main()
