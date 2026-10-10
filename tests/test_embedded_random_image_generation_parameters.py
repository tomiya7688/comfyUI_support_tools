import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts.backend.embedded_random_image import EmbeddedRandomImage
from scripts.backend.generation_capabilities import GenerationCapabilities


class _Backend:
    # {
    #   責務: [_Backend: 生成テストでrequestを記録し, テスト画像を返すadapter]
    # }

    # {
    #   責務: [__init__: テスト用capabilityとrequest記録状態を初期化する]
    #   引数: [self: backend stub]
    #   戻り値: []
    # }
    def __init__(self):
        self.request = None
        self.capabilities = GenerationCapabilities(frozenset())

    def generate(self, request, stop_event=None):
        self.request = request
        from io import BytesIO

        buffer = BytesIO()
        Image.new("RGB", (1, 1), "red").save(buffer, format="PNG")
        return buffer.getvalue()


class EmbeddedRandomImageGenerationParameterTests(unittest.TestCase):
    # {
    #   責務: [EmbeddedRandomImageGenerationParameterTests: generation parameterとbackend capability routingを検証する]
    # }

    # {
    #   責務: [test_incompatible_lora_stops_before_backend_request: 非互換LoRAで生成APIを呼ばずに中止する]
    # }
    def test_incompatible_lora_stops_before_backend_request(self):
        generator = EmbeddedRandomImage()
        generator.sd_model_checkpoint = "sdxl/base.safetensors"
        generator.model_catalog = {
            "checkpoints": ["sdxl/base.safetensors"],
            "unets": [],
            "loras": ["flux/detail.safetensors"],
        }
        messages = []
        generator._log = messages.append

        with patch(
            "scripts.backend.embedded_random_image.create_image_generation_backend"
        ) as create_backend:
            with self.assertRaisesRegex(ValueError, "生成を中止"):
                generator._generate(prompt="<lora:flux/detail:1>", negative="")

        create_backend.assert_called_once()
        self.assertTrue(any("[incompatible]" in message for message in messages))

    # {
    #   責務: [test_model_override_ambiguity_uses_backend_capability: model override判定をruntime名でなくadapter capabilityから行う]
    #   処理: [矛盾するruntime名とcapabilityで生成し, LoRA検証へ渡るbase model情報を確認する]
    #   戻り値: []
    # }
    def test_model_override_ambiguity_uses_backend_capability(self):
        cases = (
            ("a1111", {"model_overrides"}, None),
            ("comfyui", set(), "sdxl/base.safetensors"),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            for runtime_backend, features, expected_checkpoint in cases:
                with self.subTest(runtime_backend=runtime_backend, features=features):
                    backend = _Backend()
                    backend.capabilities = GenerationCapabilities(frozenset(features))
                    generator = EmbeddedRandomImage()
                    generator.api_url = "http://127.0.0.1:8188"
                    generator.output_dir = temporary_directory
                    generator.comfy_flow = ""
                    generator.enable_hr = False
                    generator.enable_failure_isolation = False
                    generator.enable_nsfw_mosaic = False
                    generator.enable_prompt_correction = False
                    generator.save_prompts = False
                    generator.additional_inputs = []
                    generator.additional_input_files = []
                    generator.action_wildcards = []
                    generator.comfy_model_overrides = {"4:ckpt_name": "override.safetensors"}
                    generator.sd_model_checkpoint = "sdxl/base.safetensors"
                    generator._log = lambda _message: None

                    with (
                        patch("scripts.backend.embedded_random_image.RUNTIME_BACKEND", runtime_backend),
                        patch(
                            "scripts.backend.embedded_random_image.create_image_generation_backend",
                            return_value=backend,
                        ),
                        patch("scripts.backend.embedded_random_image.validate_prompt_loras") as validate_loras,
                    ):
                        generator._generate(prompt="a simple test prompt", negative="")

                    self.assertEqual(validate_loras.call_args.args[1], expected_checkpoint)
                    reason = validate_loras.call_args.kwargs["base_model_reason"]
                    self.assertEqual(reason is not None, expected_checkpoint is None)

    def test_resolved_values_are_sent_to_backend_and_saved_as_metadata(self):
        backend = _Backend()
        messages = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            generator = EmbeddedRandomImage()
            generator.api_url = "http://127.0.0.1:8188"
            generator.output_dir = temporary_directory
            generator.comfy_flow = ""
            generator.enable_hr = False
            generator.enable_failure_isolation = False
            generator.enable_nsfw_mosaic = False
            generator.enable_prompt_correction = False
            generator.save_prompts = False
            generator.additional_inputs = []
            generator.additional_input_files = []
            generator.action_wildcards = []
            generator.generation_parameter_config = {
                "cfg": {"mode": "fixed", "value": 5.5},
                "steps": {"mode": "fixed", "value": 18},
                "resolution": {"mode": "fixed", "value": {"width": 512, "height": 768}},
                "sampler": {"mode": "fixed", "value": "DPM++ 2M Karras"},
            }
            generator._log = messages.append

            with patch(
                "scripts.backend.embedded_random_image.create_image_generation_backend",
                return_value=backend,
            ):
                generator._generate(prompt="a simple test prompt", negative="")

            self.assertEqual(backend.request.cfg, 5.5)
            self.assertEqual(backend.request.steps, 18)
            self.assertEqual((backend.request.width, backend.request.height), (512, 768))
            self.assertEqual(backend.request.sampler, "DPM++ 2M Karras")
            images = list(Path(temporary_directory).glob("*.png"))
            self.assertEqual(len(images), 1)
            metadata = json.loads(images[0].with_suffix(".generation.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["cfg"], 5.5)
            self.assertEqual(metadata["steps"], 18)
            self.assertEqual(metadata["resolution"], {"width": 512, "height": 768})
            self.assertEqual(metadata["sampler"], "DPM++ 2M Karras")
            self.assertTrue(any("CFG=5.5" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
