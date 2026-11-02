import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts.backend.embedded_random_image import EmbeddedRandomImage
from scripts.backend.generation_capabilities import GenerationCapabilities


# {
#   責務: [_Backend: deterministic image-generation backend that records capability use and returns a tiny PNG]
#   処理: [1: provide the configured fields and methods used by the surrounding cases]
#   フィールド: [
#     request: fake request passed through the backend fixture,
#     capabilities: capabilities fixture state used by the test cases,
#   ],
#   引数: []
# }
class _Backend:
    # {
    #   責務: [_Backend: 生成テストでrequestを記録し, テスト画像を返すadapter]
    # }

    # {
    #   責務: [__init__: テスト用capabilityとrequest記録状態を初期化する]
    #   引数: [self: backend stub]
    #   戻り値: []
    # }
    # {
    #   責務: [__init__: initializes the fields and controlled behavior of _Backend]
    #   処理: [1: store constructor inputs and initialize controlled fixture state]
    #   引数: []
    #   戻り値: [None: initialize instance state without returning a value]
    # }
    def __init__(self):
        self.request = None
        self.capabilities = GenerationCapabilities(frozenset({"txt2img"}))

    # {
    #   責務: [generate: returns a deterministic image payload for the supplied generation request]
    #   処理: [
    #     1: record or derive the generation output from the supplied sequence inputs,
    #     2: return the deterministic output payload,
    #   ],
    #   引数: [
    #     request: request data under test (unspecified),
    #     stop_event: cooperative cancellation signal (unspecified),
    #   ],
    #   戻り値: [result: buffer.getvalue built or selected by this helper]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def generate(self, request, stop_event=None):
        self.request = request
        from io import BytesIO

        buffer = BytesIO()
        Image.new("RGB", (1, 1), "red").save(buffer, format="PNG")
        return buffer.getvalue()


# {
#   責務: [
#     EmbeddedRandomImageGenerationParameterTests: related test fixtures and cases for EmbeddedRandomImageGenerationParameter behavior,
#   ],
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class EmbeddedRandomImageGenerationParameterTests(unittest.TestCase):
    # {
    #   責務: [EmbeddedRandomImageGenerationParameterTests: generation parameterとbackend capability routingを検証する]
    # }

    # {
    #   責務: [test_generation_capabilities_require_declared_features: 必須機能が未宣言なら共通エラーになることを確認する]
    #   処理: [対応機能は通し, 未対応機能をrequireするとValueErrorになることを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_generation_capabilities_require_declared_features(self):
        capabilities = GenerationCapabilities(frozenset({"txt2img"}))

        self.assertIsNone(capabilities.require("txt2img"))
        with self.assertRaisesRegex(ValueError, "img2img"):
            capabilities.require("img2img")

    # {
    #   責務: [test_incompatible_lora_stops_before_backend_request: 非互換LoRAで生成APIを呼ばずに中止する]
    # }
    # {
    #   責務: [
    #     test_incompatible_lora_stops_before_backend_request: verifies the behavior described by "incompatible lora stops before backend request",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for incompatible lora stops before backend request,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
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
            "scripts.backend.embedded_random_image.create_configured_image_generation_backend"
        ) as create_backend:
            with self.assertRaisesRegex(ValueError, "生成を中止"):
                generator._generate(prompt="<lora:flux/detail:1>", negative="")

        create_backend.assert_called_once()
        self.assertTrue(any("[incompatible]" in message for message in messages))

    # {
    #   責務: [test_model_override_ambiguity_uses_backend_capability: model override判定をadapter capabilityから行う]
    #   処理: [異なるcapabilityで生成し, LoRA検証へ渡るbase model情報を確認する]
    #   戻り値: []
    # }
    # {
    #   責務: [
    #     test_model_override_ambiguity_uses_backend_capability: verifies the behavior described by "model override ambiguity uses backend capability",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for model override ambiguity uses backend capability,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_model_override_ambiguity_uses_backend_capability(self):
        cases = (({"txt2img", "model_overrides"}, None), ({"txt2img"}, "sdxl/base.safetensors"))
        with tempfile.TemporaryDirectory() as temporary_directory:
            for features, expected_checkpoint in cases:
                with self.subTest(features=features):
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
                        patch(
                            "scripts.backend.embedded_random_image.create_configured_image_generation_backend",
                            return_value=backend,
                        ),
                        patch("scripts.backend.embedded_random_image.validate_prompt_loras") as validate_loras,
                    ):
                        generator._generate(prompt="a simple test prompt", negative="")

                    self.assertEqual(validate_loras.call_args.args[1], expected_checkpoint)
                    reason = validate_loras.call_args.kwargs["base_model_reason"]
                    self.assertEqual(reason is not None, expected_checkpoint is None)

    # {
    #   責務: [
    #     test_resolved_values_are_sent_to_backend_and_saved_as_metadata: verifies the behavior described by "resolved values are sent to backend and saved as metadata",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for resolved values are sent to backend and saved as metadata,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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
                "scripts.backend.embedded_random_image.create_configured_image_generation_backend",
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
            self.assertEqual(metadata["backend"], generator.generation_profile.backend)
            self.assertEqual(metadata["steps"], 18)
            self.assertEqual(metadata["resolution"], {"width": 512, "height": 768})
            self.assertEqual(metadata["sampler"], "DPM++ 2M Karras")
            self.assertTrue(any("CFG=5.5" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
