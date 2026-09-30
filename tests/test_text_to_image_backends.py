from __future__ import annotations

import base64
from pathlib import Path
import tempfile
import unittest
from threading import Event

from scripts.backend.a1111_image_generation_backend import A1111ImageGenerationBackend
from scripts.backend.comfyui_image_generation_backend import ComfyUIImageGenerationBackend
from scripts.backend.image_to_image_request import ImageToImageRequest
from scripts.backend.image_generation_backend_factory import create_image_generation_backend
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

        backend = A1111ImageGenerationBackend("http://localhost:7860/sdapi/v1/txt2img", 30, post)

        result = backend.generate(request(enable_hr=True, hr_upscaler="4x-ultrasharp"))

        self.assertEqual(result, image)
        self.assertTrue(response.status_checked)
        self.assertEqual(calls[0][0], "http://localhost:7860/sdapi/v1/txt2img")
        self.assertEqual(calls[0][1]["timeout"], 30)
        self.assertEqual(calls[0][1]["json"]["cfg_scale"], 6.5)
        self.assertTrue(calls[0][1]["json"]["save_images"])
        self.assertEqual(calls[0][1]["json"]["override_settings"], {
            "sd_model_checkpoint": "model.safetensors",
            "sd_vae": "Automatic",
        })
        self.assertTrue(calls[0][1]["json"]["enable_hr"])

    def test_a1111_does_not_send_request_when_already_cancelled(self):
        called = []
        stopped = Event()
        stopped.set()
        backend = A1111ImageGenerationBackend("url", 30, lambda *args, **kwargs: called.append(True))

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

        backend = ComfyUIImageGenerationBackend("http://localhost:8188", 40, FakeClient)
        stop_event = Event()
        generation_request = request(enable_hr=True, workflow_path="flow.json", model_overrides={"4:ckpt_name": "other.safetensors"})

        result = backend.generate(generation_request, stop_event)

        self.assertEqual(result, b"comfy-image")
        self.assertEqual(instances, [("http://localhost:8188", 40)])
        self.assertEqual(backend.client.arguments["prompt"], "portrait")
        self.assertEqual(backend.client.arguments["workflow_path"], "flow.json")
        self.assertIs(backend.client.arguments["stop_event"], stop_event)
        self.assertEqual(backend.client.arguments["model_overrides"], {"4:ckpt_name": "other.safetensors"})

    def test_a1111_img2img_encodes_source_image_and_maps_settings(self):
        source_image = b"source-image"
        response = FakeResponse({"images": [base64.b64encode(b"result-image").decode("ascii")]})
        calls = []

        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "source.png"
            image_path.write_bytes(source_image)
            backend = A1111ImageGenerationBackend(
                "http://localhost:7860/sdapi/v1/img2img",
                25,
                lambda url, **kwargs: (calls.append((url, kwargs)) or response),
            )
            img_request = ImageToImageRequest(
                image_path=image_path,
                prompt="portrait",
                negative="low quality",
                checkpoint="model.safetensors",
                steps=20,
                cfg=5.5,
                sampler="Euler a",
                denoise=0.6,
                width=640,
                height=832,
            )

            result = backend.generate_from_image(img_request)

        self.assertEqual(result, b"result-image")
        self.assertEqual(calls[0][1]["json"]["init_images"], [base64.b64encode(source_image).decode("ascii")])
        self.assertEqual(calls[0][1]["json"]["denoising_strength"], 0.6)
        self.assertEqual(calls[0][1]["timeout"], 25)

    def test_comfyui_img2img_passes_image_path_and_stop_event(self):
        class FakeClient:
            def __init__(self, _url, _timeout):
                self.arguments = None

            def img2img(self, **kwargs):
                self.arguments = kwargs
                return b"comfy-img2img"

        backend = ComfyUIImageGenerationBackend("http://localhost:8188", 60, FakeClient)
        image_path = Path("input.png")
        stop_event = Event()
        img_request = ImageToImageRequest(
            image_path=image_path,
            prompt="portrait",
            negative="",
            checkpoint="model.safetensors",
            steps=20,
            cfg=5.5,
            sampler="euler",
            denoise=0.65,
            width=640,
            height=832,
        )

        self.assertEqual(backend.generate_from_image(img_request, stop_event), b"comfy-img2img")
        self.assertEqual(backend.client.arguments["image_path"], image_path)
        self.assertIs(backend.client.arguments["stop_event"], stop_event)
        self.assertEqual(backend.client.arguments["denoise"], 0.65)

    def test_a1111_interrupt_uses_service_root_and_declares_capabilities(self):
        calls = []
        response = FakeResponse({})
        backend = A1111ImageGenerationBackend(
            "http://localhost:7860/sdapi/v1/img2img",
            30,
            lambda url, **kwargs: (calls.append((url, kwargs)) or response),
        )

        backend.interrupt()

        self.assertEqual(calls[0][0], "http://localhost:7860/sdapi/v1/interrupt")
        self.assertEqual(calls[0][1]["timeout"], 10)
        self.assertTrue(backend.capabilities.supports("img2img"))
        self.assertFalse(backend.capabilities.supports("workflow"))

    def test_comfyui_interrupt_delegates_and_declares_workflow_support(self):
        class FakeClient:
            def __init__(self, _url, _timeout):
                self.interrupted = False

            def interrupt(self):
                self.interrupted = True

        backend = ComfyUIImageGenerationBackend("http://localhost:8188", 60, FakeClient)

        backend.interrupt()

        self.assertTrue(backend.client.interrupted)
        self.assertTrue(backend.capabilities.supports("workflow"))
        self.assertTrue(backend.capabilities.supports("interrupt"))

    def test_factory_selects_supported_backend_and_rejects_unknown(self):
        post = lambda *args, **kwargs: FakeResponse({"images": []})
        self.assertIsInstance(
            create_image_generation_backend("a1111", "url", 1, request_post=post),
            A1111ImageGenerationBackend,
        )
        with self.assertRaises(ValueError):
            create_image_generation_backend("unknown", "url", 1, request_post=post)


if __name__ == "__main__":
    unittest.main()
