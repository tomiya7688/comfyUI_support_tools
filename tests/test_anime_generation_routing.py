"""Focused compatibility and ranking tests for anime model routing."""

from __future__ import annotations

import unittest

from comfyui_support_tools.shared.anime_generation import (
    AnimeIntent,
    AnimeLoraRequirement,
    AnimeRouteRequest,
    AnimeRoutingError,
    create_default_anime_model_registry,
    route_anime_model,
)


# {
# 責務: [AnimeGenerationRoutingTests: verify compatibility-first family selection]
# フィールド: [default model registry and deterministic available-model fixtures]
# 処理: [ensure required LoRA families filter candidates before intent ranking]
# 引数: [None: unittest fixture]
# 戻り値: [None: tests report routing behavior]
# }
class AnimeGenerationRoutingTests(unittest.TestCase):
    # {
    # 責務: [test_required_lora_family_filters_incompatible_models: prevent known adapter mismatch]
    # 処理: [rank several installed families under one required LoRA family]
    # 引数: [self: test case]
    # 戻り値: [None: selected model supports the required family]
    # }
    def test_required_lora_family_filters_incompatible_models(self):
        models = (
            "models/checkpoints/sdxl-general.safetensors",
            "models/checkpoints/animagineXL40.safetensors",
            "models/checkpoints/NoobAI-XL-1.0.safetensors",
        )
        result = route_anime_model(
            create_default_anime_model_registry(),
            AnimeRouteRequest(
                models,
                intent=AnimeIntent.CHARACTER,
                required_loras=(AnimeLoraRequirement("noobai_character", frozenset({"noobai"})),),
            ),
        )
        self.assertEqual(result.selected_model, models[2])
        self.assertEqual(result.ranked_models, (models[2],))

    # {
    # 責務: [test_empty_compatible_family_set_is_reported: stop rather than use a known mismatch]
    # 処理: [request one required family with no matching installed checkpoint]
    # 引数: [self: test case]
    # 戻り値: [None: routing explains that no compatible model exists]
    # }
    def test_empty_compatible_family_set_is_reported(self):
        with self.assertRaisesRegex(AnimeRoutingError, "no installed anime model profile"):
            route_anime_model(
                create_default_anime_model_registry(),
                AnimeRouteRequest(
                    ("models/checkpoints/AnimagineXL40.safetensors",),
                    required_loras=(
                        AnimeLoraRequirement("noobai_character", frozenset({"noobai"})),
                    ),
                ),
            )


if __name__ == "__main__":
    unittest.main()
