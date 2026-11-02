"""Tests for declarative anime generation policies, routing, and integration."""

from __future__ import annotations

import unittest
from threading import Event

from comfyui_support_tools.shared.anime_generation import (
    AnimeBenchmarkCase,
    AnimeContentMode,
    AnimeIntent,
    AnimeLoraRequirement,
    AnimeModelFamily,
    AnimeModelProfile,
    AnimeModelRegistry,
    AnimePromptPolicy,
    AnimeRouteRequest,
    AnimeRoutingError,
    apply_anime_prompt_policy,
    build_benchmark_prompts,
    create_default_anime_model_registry,
    route_anime_model,
)
from scripts.backend.anime_generation_backend import AnimeGenerationBackend
from scripts.backend.anime_generation_policy import resolve_anime_generation
from scripts.backend.generation_capabilities import GenerationCapabilities
from scripts.backend.text_to_image_request import TextToImageRequest


# {
#   責務: [AnimeGenerationTests: verify prompt family descriptors and model routing]
#   フィールド: [default profile registry, benchmark examples, fake backend]
#   処理: [check family policies, LoRA compatibility, explicit precedence, and txt2img delegation]
# }
class AnimeGenerationTests(unittest.TestCase):
    # {
    #   責務: [test_default_profiles_apply_model_native_prompt_policies: verify model-specific prompt vocabulary]
    #   処理: [apply the same user prompt to supported families and compare policy ordering and tags]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_default_profiles_apply_model_native_prompt_policies(self) -> None:
        registry = create_default_anime_model_registry()
        animagine = registry.classify("models/checkpoints/animagineXL40.safetensors")
        illustrious = registry.classify("models/checkpoints/Illustrious-XL-v2.safetensors")
        noobai = registry.classify("models/checkpoints/NoobAI-XL-1.0.safetensors")
        self.assertEqual(animagine.family, AnimeModelFamily.ANIMAGINE.value)
        self.assertEqual(illustrious.family, AnimeModelFamily.ILLUSTRIOUS.value)
        self.assertEqual(noobai.family, AnimeModelFamily.NOOBAI.value)

        prompt, negative = apply_anime_prompt_policy(
            animagine,
            "best quality, 1girl, blue hair",
            "blurry",
            intent=AnimeIntent.CHARACTER,
            content_mode=AnimeContentMode.SFW,
        )
        self.assertEqual(
            prompt,
            "masterpiece, best quality, character illustration, safe, 1girl, blue hair",
        )
        self.assertIn("low quality", negative)
        self.assertIn("blurry", negative)
        self.assertEqual(prompt.casefold().count("best quality"), 1)
        self.assertNotIn("safe", apply_anime_prompt_policy(animagine, "1girl")[0])

    # {
    #   責務: [test_registry_accepts_a_new_model_family_without_algorithm_changes: verify descriptor extensibility]
    #   処理: [register a previously unknown family ID and route to it using only profile metadata]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_registry_accepts_a_new_model_family_without_algorithm_changes(self) -> None:
        profile = AnimeModelProfile(
            profile_id="test_anime_family",
            family="test_anime_family",
            aliases=("test anime checkpoint",),
            lineage="test lineage",
            native_resolution=768,
            prompt_policy=AnimePromptPolicy(quality_tags=("test quality",)),
            lora_compatible_families=frozenset({"test_anime_family"}),
            recommended_intents=(AnimeIntent.BACKGROUND,),
        )
        registry = AnimeModelRegistry((*create_default_anime_model_registry().profiles, profile))
        result = route_anime_model(
            registry,
            AnimeRouteRequest(
                (
                    "models/checkpoints/Animagine XL 4.0.safetensors",
                    "test-anime-checkpoint.safetensors",
                ),
                intent=AnimeIntent.BACKGROUND,
            ),
        )
        self.assertEqual(result.profile.profile_id, "test_anime_family")
        self.assertEqual(result.selected_model, "test-anime-checkpoint.safetensors")

    # {
    #   責務: [test_router_respects_intent_lora_constraints_and_explicit_model: verify deterministic routing rules]
    #   処理: [prefer intent profiles, constrain required adapters, and preserve explicit user selection]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_router_respects_intent_lora_constraints_and_explicit_model(self) -> None:
        registry = create_default_anime_model_registry()
        models = (
            "models/checkpoints/sdxl-general.safetensors",
            "models/checkpoints/animagineXL40.safetensors",
            "models/checkpoints/NoobAI-XL-1.0.safetensors",
        )
        routed = route_anime_model(
            registry,
            AnimeRouteRequest(
                models,
                intent=AnimeIntent.CHARACTER,
                required_loras=(AnimeLoraRequirement("noobai_character", frozenset({"noobai"})),),
            ),
        )
        self.assertEqual(routed.profile.family, "noobai")
        self.assertEqual(routed.ranked_models[0], routed.selected_model)

        explicit = route_anime_model(
            registry,
            AnimeRouteRequest(
                models,
                intent=AnimeIntent.CHARACTER,
                explicit_model=models[1],
            ),
        )
        self.assertEqual(explicit.selected_model, models[1])
        with self.assertRaises(AnimeRoutingError):
            route_anime_model(
                registry,
                AnimeRouteRequest(
                    models,
                    explicit_model=models[1],
                    required_loras=(
                        AnimeLoraRequirement("noobai_character", frozenset({"noobai"})),
                    ),
                ),
            )

    # {
    #   責務: [test_benchmark_uses_each_family_prompt_policy: verify fair comparison inputs]
    #   処理: [render one common case for Animagine and Illustrious with family-specific tags]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_benchmark_uses_each_family_prompt_policy(self) -> None:
        registry = create_default_anime_model_registry()
        case = AnimeBenchmarkCase(
            "character_portrait",
            "1girl, blue hair",
            intent=AnimeIntent.CHARACTER,
        )
        animagine = build_benchmark_prompts(registry.classify("animagine xl"), (case,))[0]
        illustrious = build_benchmark_prompts(registry.classify("illustrious xl"), (case,))[0]
        self.assertNotEqual(animagine.prompt, illustrious.prompt)
        self.assertEqual(animagine.case_id, illustrious.case_id)

    # {
    #   責務: [test_generation_adapter_applies_prompt_and_route_before_delegation: verify executable integration]
    #   処理: [wrap a fake image backend and inspect its received model, prompts, and cancellation event]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_generation_adapter_applies_prompt_and_route_before_delegation(self) -> None:
        # {
        #   責務: [FakeBackend: record a request forwarded through the model-policy adapter]
        #   フィールド: [capabilities, request, stop_event]
        #   処理: [return deterministic bytes without contacting an image service]
        # }
        class FakeBackend:
            capabilities = GenerationCapabilities(frozenset({"txt2img", "img2img", "interrupt"}))

            # {
            #   責務: [__init__: initialize request and cancellation capture state]
            #   処理: [start with no forwarded request or cancellation event]
            #   引数: [self: fake backend instance]
            #   戻り値: []
            # }
            def __init__(self) -> None:
                self.request = None
                self.stop_event = None

            # {
            #   責務: [generate: record one wrapped txt2img request]
            #   処理: [capture the policy-expanded request and cancellation event]
            #   引数: [request: text-to-image settings, stop_event: cancellation signal]
            #   戻り値: [bytes: deterministic fake output]
            # }
            def generate(self, request, stop_event=None):
                self.request = request
                self.stop_event = stop_event
                return b"generated"

            # {
            #   責務: [generate_from_image: provide the wrapped backend img2img method]
            #   処理: [return a deterministic result for protocol completeness]
            #   引数: [request: image-to-image settings, stop_event: cancellation signal]
            #   戻り値: [bytes: deterministic fake output]
            # }
            def generate_from_image(self, request, stop_event=None):
                return b"img2img"

            # {
            #   責務: [interrupt: satisfy the image backend protocol]
            #   処理: [perform no network action in this test double]
            #   引数: [self: fake backend]
            #   戻り値: []
            # }
            def interrupt(self):
                return None

        fake = FakeBackend()
        adapter = AnimeGenerationBackend(
            fake,
            model_catalog={
                "checkpoints": ["models/checkpoints/Animagine XL 4.0.safetensors"],
                "unets": [],
                "loras": [],
            },
            intent=AnimeIntent.CHARACTER,
            content_mode=AnimeContentMode.SFW,
            auto_route=True,
            has_explicit_model_overrides=False,
        )
        event = Event()
        request = TextToImageRequest(
            prompt="1girl, blue hair",
            negative="blurry",
            checkpoint="unknown model",
            steps=20,
            cfg=6.0,
            sampler="Euler",
            width=1024,
            height=1024,
        )
        self.assertEqual(adapter.generate(request, event), b"generated")
        self.assertIn("character illustration", fake.request.prompt)
        self.assertIn("low quality", fake.request.negative)
        self.assertEqual(fake.request.checkpoint, "models/checkpoints/Animagine XL 4.0.safetensors")
        self.assertIs(fake.stop_event, event)
        self.assertEqual(adapter.last_resolution.profile_id, "animagine_xl")
        with self.assertRaises(ValueError):
            AnimeGenerationBackend(
                fake,
                model_catalog={},
                intent=AnimeIntent.GENERAL,
                content_mode=AnimeContentMode.UNSPECIFIED,
                auto_route=True,
                has_explicit_model_overrides=True,
            )

    # {
    #   責務: [test_explicit_model_rejects_a_known_incompatible_anime_lora: avoid silent family mismatch]
    #   処理: [select Illustrious explicitly and reject a known NoobAI-only adapter]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_explicit_model_rejects_a_known_incompatible_anime_lora(self) -> None:
        with self.assertRaises(AnimeRoutingError):
            resolve_anime_generation(
                "models/checkpoints/animagineXL40.safetensors",
                "1girl, <lora:noobai_character:0.8>",
                "",
                {
                    "checkpoints": ["models/checkpoints/animagineXL40.safetensors"],
                    "loras": ["models/loras/NoobAI/noobai_character.safetensors"],
                },
            )


if __name__ == "__main__":
    unittest.main()
