import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts.backend.embedded_random_image import EmbeddedRandomImage


class _Backend:
    def __init__(self):
        self.request = None

    def generate(self, request, stop_event=None):
        self.request = request
        from io import BytesIO

        buffer = BytesIO()
        Image.new("RGB", (1, 1), "red").save(buffer, format="PNG")
        return buffer.getvalue()


class EmbeddedRandomImageGenerationParameterTests(unittest.TestCase):
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

        create_backend.assert_not_called()
        self.assertTrue(any("[incompatible]" in message for message in messages))

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
