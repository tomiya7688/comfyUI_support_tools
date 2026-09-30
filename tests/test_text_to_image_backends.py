from __future__ import annotations

import base64
import unittest
from threading import Event

from scripts.backend.a1111_text_to_image_backend import A1111TextToImageBackend
from scripts.backend.comfyui_text_to_image_backend import ComfyUITextToImageBackend
from scripts.backend.text_to_image_backend_factory import create_text_to_image_backend
from scripts.backend.text_to_image_request import TextToImageRequest


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_checked = False

    def raise_for_status(self):
        self.status_checked = True

    def json(self):
        return self.payload


def request(**overrides):
    values = {
        "prompt": "portrait",
        "negative": "low quality",
        "checkpoint": "model.safetensors",
        "steps": 24,
        "cfg": 6.5,
        "sampler": "Euler a",
        "width": 768,
        "height": 1024,
    }
    values.update(overrides)
    return TextToImageRequest(**values)


class TextToImageBackendTests(unittest.TestCase):
    def test_a1111_maps_common_request_and_decodes_first_image(self):
        image = b"image-bytes"
        response = FakeResponse({"images": [base64.b64encode(image).decode("ascii"), "ignored"]})
        calls = []

        def post(url, **kwargs):
            calls.append((url, kwargs))
            return response

        backend = A1111TextToImageBackend("http://localhost:7860/sdapi/v1/txt2img", 30, post)

        result = backend.generate(request(enable_hr=True, hr_upscaler="4x-ultrasharp"))

        self.assertEqual(result, image)
        self.assertTrue(response.status_checked)
        self.assertEqual(calls[0][0], "http://localhost:7860/sdapi/v1/txt2img")
        self.assertEqual(calls[0][1]["timeout"], 30)
        self.assertEqual(calls[0][1]["json"]["cfg_scale"], 6.5)
        self.assertEqual(calls[0][1]["json"]["override_settings"], {
            "sd_model_checkpoint": "model.safetensors",
            "sd_vae": "Automatic",
        })
        self.assertTrue(calls[0][1]["json"]["enable_hr"])

    def test_a1111_does_not_send_request_when_already_cancelled(self):
        called = []
        stopped = Event()
        stopped.set()
        backend = A1111TextToImageBackend("url", 30, lambda *args, **kwargs: called.append(True))

        self.assertIsNone(backend.generate(request(), stopped))
        self.assertEqual(called, [])

    def test_comfyui_maps_request_to_existing_client(self):
        instances = []

        class FakeClient:
            def __init__(self, api_url, timeout):
                instances.append((api_url, timeout))

            def txt2img(self, **kwargs):
                self.arguments = kwargs
                return b"comfy-image"

        backend = ComfyUITextToImageBackend("http://localhost:8188", 40, FakeClient)
        stop_event = Event()
        generation_request = request(enable_hr=True, workflow_path="flow.json", model_overrides={"4:ckpt_name": "other.safetensors"})

        result = backend.generate(generation_request, stop_event)

        self.assertEqual(result, b"comfy-image")
        self.assertEqual(instances, [("http://localhost:8188", 40)])
        self.assertEqual(backend.client.arguments["prompt"], "portrait")
        self.assertEqual(backend.client.arguments["workflow_path"], "flow.json")
        self.assertIs(backend.client.arguments["stop_event"], stop_event)
        self.assertEqual(backend.client.arguments["model_overrides"], {"4:ckpt_name": "other.safetensors"})

    def test_factory_selects_supported_backend_and_rejects_unknown(self):
        post = lambda *args, **kwargs: FakeResponse({"images": []})
        self.assertIsInstance(
            create_text_to_image_backend("a1111", "url", 1, request_post=post),
            A1111TextToImageBackend,
        )
        with self.assertRaises(ValueError):
            create_text_to_image_backend("unknown", "url", 1, request_post=post)


if __name__ == "__main__":
    unittest.main()
