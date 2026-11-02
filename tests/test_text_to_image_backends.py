from __future__ import annotations

import base64
from pathlib import Path
import tempfile
import unittest
from threading import Event
from unittest.mock import Mock, patch

from scripts.context import create_configured_image_generation_backend
from scripts.backend.a1111_image_generation_backend import A1111ImageGenerationBackend
from scripts.backend.comfyui_image_generation_backend import ComfyUIImageGenerationBackend
from scripts.backend.comfy_ui_client import ComfyUIClient
from scripts.backend.image_to_image_request import ImageToImageRequest
from scripts.backend.image_generation_backend_factory import create_image_generation_backend
from scripts.backend.backend_launch_spec import create_backend_launch_spec
from scripts.backend.generation_backend_registry import (
    SUPPORTED_GENERATION_BACKENDS,
    SUPPORTED_LAUNCH_BACKENDS,
)
from scripts.backend.generation_backend_catalog_factory import create_generation_backend_catalog
from scripts.backend.text_to_image_request import TextToImageRequest


# {
#   責務: [FakeResponse: controlled HTTP response with configured status, headers, and JSON payload]
#   処理: [1: provide the configured fields and methods used by the surrounding cases]
#   フィールド: [
#     payload: HTTP request/response payload captured by the fixture,
#     status_checked: status checked fixture state used by the test cases,
#   ],
#   引数: []
# }
class FakeResponse:
    # {
    #   責務: [__init__: initializes the fields and controlled behavior of FakeResponse]
    #   処理: [1: store constructor inputs and initialize controlled fixture state]
    #   引数: [payload: JSON request/response payload (unspecified)]
    #   戻り値: [None: initialize instance state without returning a value]
    # }
    def __init__(self, payload):
        self.payload = payload
        self.status_checked = False

    # {
    #   責務: [raise_for_status: records that the fake HTTP response status was checked]
    #   処理: [1: record that the caller checked the fake response status]
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def raise_for_status(self):
        self.status_checked = True

    # {
    #   責務: [json: returns the configured decoded response payload]
    #   処理: [1: return the payload configured for this fake response]
    #   引数: []
    #   戻り値: [result: value returned by the helper's documented test role]
    # }
    def json(self):
        return self.payload


# {
#   責務: [request: builds a TextToImageRequest using the supplied prompt and backend parameters]
#   処理: [1: merge supplied overrides with deterministic default request fields, 2: construct a TextToImageRequest]
#   引数: [**overrides: **overrides passed to this helper (unspecified)]
#   戻り値: [result: TextToImageRequest built or selected by this helper]
# }
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


# {
#   責務: [TextToImageBackendTests: related test fixtures and cases for TextToImageBackend behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: [
#     arguments: arguments fixture state used by the test cases,
#     interrupted: interrupted fixture state used by the test cases,
#   ],
#   引数: []
# }
class TextToImageBackendTests(unittest.TestCase):
    # {
    #   責務: [test_registered_backend_apis_create_matching_catalogs_and_adapters: 共通registry APIがbackendごとの生成機能一式を対応づけることを検証する]
    #   処理: [1: catalogと生成adapterを作りcapability一致を確認する, 2: 起動対応backendのlaunch specを確認する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_registered_backend_apis_create_matching_catalogs_and_adapters(self):
        post = lambda *args, **kwargs: FakeResponse({"images": []})

        for backend_id in SUPPORTED_GENERATION_BACKENDS:
            with self.subTest(backend=backend_id):
                catalog = create_generation_backend_catalog(backend_id)
                adapter = create_image_generation_backend(
                    backend_id,
                    "http://localhost:8188",
                    1,
                    request_post=post,
                    comfy_client_factory=Mock(),
                )

                self.assertEqual(catalog.capabilities, adapter.capabilities)
                adapter.capabilities.require("txt2img")
                adapter.capabilities.require("img2img")

                if backend_id in SUPPORTED_LAUNCH_BACKENDS:
                    launch_spec = create_backend_launch_spec(
                        backend_id,
                        "http://127.0.0.1:7860",
                        "http://127.0.0.1:8188",
                        Path("models/checkpoints"),
                        Path("models"),
                    )
                    self.assertEqual(launch_spec.backend, backend_id)

    # {
    #   責務: [test_configured_backend_provider_hides_backend_selection: 設定境界が選択backendをadapterへ解決することを検証する]
    #   処理: [選択backend名とHTTP関数がadapter factoryへ渡り, adapterが返されることを確認する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_configured_backend_provider_hides_backend_selection(self):
        adapter = object()
        request_module = Mock()
        with (
            patch("scripts.context.RUNTIME_BACKEND", "comfyui"),
            patch("scripts.context.requests", request_module),
            patch(
                "scripts.backend.image_generation_backend_factory.create_image_generation_backend",
                return_value=adapter,
            ) as factory,
        ):
            result = create_configured_image_generation_backend("http://localhost:8188", 45)

        self.assertIs(result, adapter)
        factory.assert_called_once_with(
            "comfyui",
            "http://localhost:8188",
            45,
            request_post=request_module.post,
        )

    # {
    #   責務: [test_configured_backend_provider_reports_missing_requests: HTTP client依存がない場合のエラーを検証する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    # {
    #   責務: [
    #     test_configured_backend_provider_reports_missing_requests: verifies the behavior described by "configured backend provider reports missing requests",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for configured backend provider reports missing requests,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_configured_backend_provider_reports_missing_requests(self):
        with patch("scripts.context.requests", None):
            with self.assertRaisesRegex(RuntimeError, "requests"):
                create_configured_image_generation_backend("http://localhost:8188", 45)

    # {
    #   責務: [
    #     test_a1111_maps_common_request_and_decodes_first_image: verifies the behavior described by "a1111 maps common request and decodes first image",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for a1111 maps common request and decodes first image,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: response value built or selected by this helper]
    # }
    def test_a1111_maps_common_request_and_decodes_first_image(self):
        image = b"image-bytes"
        response = FakeResponse({"images": [base64.b64encode(image).decode("ascii"), "ignored"]})
        calls = []

        # {
        #   責務: [post: records the request sent to the fake A1111 backend and returns a generated-image response]
        #   処理: [1: capture the URL and request options, 2: return the configured fake HTTP response]
        #   引数: [
        #     url: fake endpoint URL (unspecified),
        #     **kwargs: keyword request options captured by the fake client (unspecified),
        #   ],
        #   戻り値: [result: response value built or selected by this helper]
        # }
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

    # {
    #   責務: [
    #     test_comfyui_selected_vae_loader_is_connected_to_all_vae_consumers: verifies the behavior described by "comfyui selected vae loader is connected to all vae consumers",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for comfyui selected vae loader is connected to all vae consumers,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_comfyui_selected_vae_loader_is_connected_to_all_vae_consumers(self):
        workflow = {
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "11": {"class_type": "VAEEncode", "inputs": {"pixels": ["12", 0], "vae": ["4", 2]}},
        }

        ComfyUIClient._apply_vae_selection(workflow, "vae.safetensors")

        self.assertEqual(workflow["12"], {
            "class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"},
        })
        self.assertEqual(workflow["8"]["inputs"]["vae"], ["12", 0])
        self.assertEqual(workflow["11"]["inputs"]["vae"], ["12", 0])

    # {
    #   責務: [
    #     test_comfyui_selection_updates_existing_vae_loader: verifies the behavior described by "comfyui selection updates existing vae loader",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for comfyui selection updates existing vae loader,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_comfyui_selection_updates_existing_vae_loader(self):
        workflow = {
            "61": {"class_type": "VAELoader", "inputs": {"vae_name": "old.safetensors"}},
            "62": {"class_type": "VAEDecode", "inputs": {"samples": ["1", 0], "vae": ["61", 0]}},
        }

        ComfyUIClient._apply_vae_selection(workflow, "chosen.safetensors")

        self.assertEqual(workflow["61"]["inputs"]["vae_name"], "chosen.safetensors")
        self.assertEqual(workflow["62"]["inputs"]["vae"], ["61", 0])
    # {
    #   責務: [
    #     test_a1111_uses_explicit_vae_when_selected: verifies the behavior described by "a1111 uses explicit vae when selected",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for a1111 uses explicit vae when selected,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_a1111_uses_explicit_vae_when_selected(self):
        response = FakeResponse({"images": []})
        calls = []
        backend = A1111ImageGenerationBackend(
            "http://localhost:7860/sdapi/v1/txt2img", 30,
            lambda url, **kwargs: (calls.append((url, kwargs)) or response),
        )

        backend.generate(request(vae_name="vae.safetensors"))

        self.assertEqual(calls[0][1]["json"]["override_settings"]["sd_vae"], "vae.safetensors")
    # {
    #   責務: [
    #     test_a1111_does_not_send_request_when_already_cancelled: verifies the behavior described by "a1111 does not send request when already cancelled",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for a1111 does not send request when already cancelled,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_a1111_does_not_send_request_when_already_cancelled(self):
        called = []
        stopped = Event()
        stopped.set()
        backend = A1111ImageGenerationBackend("url", 30, lambda *args, **kwargs: called.append(True))

        self.assertIsNone(backend.generate(request(), stopped))
        self.assertEqual(called, [])

    # {
    #   責務: [
    #     test_comfyui_maps_request_to_existing_client: verifies the behavior described by "comfyui maps request to existing client",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for comfyui maps request to existing client,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: bytes value built or selected by this helper]
    # }
    def test_comfyui_maps_request_to_existing_client(self):
        instances = []

        # {
        #   責務: [FakeClient: reusable fixture or controlled test double for FakeClient behavior]
        #   処理: [1: provide the configured fields and methods used by the surrounding cases]
        #   フィールド: [arguments: arguments fixture state used by the test cases]
        #   引数: []
        # }
        class FakeClient:
            # {
            #   責務: [__init__: initializes the fields and controlled behavior of FakeClient]
            #   処理: [1: store constructor inputs and initialize controlled fixture state]
            #   引数: [
            #     api_url: API base URL supplied to the fake client (unspecified),
            #     timeout: maximum wait duration (unspecified),
            #   ],
            #   戻り値: [None: initialize instance state without returning a value]
            # }
            def __init__(self, api_url, timeout):
                instances.append((api_url, timeout))

            # {
            #   責務: [txt2img: returns a deterministic image for the text-to-image test double]
            #   処理: [1: store the generation arguments, 2: return the configured image bytes]
            #   引数: [**kwargs: keyword request options captured by the fake client (unspecified)]
            #   戻り値: [result: bytes value built or selected by this helper]
            # }
            def txt2img(self, **kwargs):
                self.arguments = kwargs
                return b"comfy-image"

        backend = ComfyUIImageGenerationBackend("http://localhost:8188", 40, FakeClient)
        stop_event = Event()
        generation_request = request(enable_hr=True, workflow_path="flow.json", model_overrides={"4:ckpt_name": "other.safetensors"}, vae_name="vae.safetensors")

        result = backend.generate(generation_request, stop_event)

        self.assertEqual(result, b"comfy-image")
        self.assertEqual(instances, [("http://localhost:8188", 40)])
        self.assertEqual(backend.client.arguments["prompt"], "portrait")
        self.assertEqual(backend.client.arguments["workflow_path"], "flow.json")
        self.assertIs(backend.client.arguments["stop_event"], stop_event)
        self.assertEqual(backend.client.arguments["model_overrides"], {"4:ckpt_name": "other.safetensors"})
        self.assertEqual(backend.client.arguments["vae_name"], "vae.safetensors")

    # {
    #   責務: [
    #     test_a1111_img2img_encodes_source_image_and_maps_settings: verifies the behavior described by "a1111 img2img encodes source image and maps settings",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for a1111 img2img encodes source image and maps settings,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
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

    # {
    #   責務: [
    #     test_comfyui_img2img_passes_image_path_and_stop_event: verifies the behavior described by "comfyui img2img passes image path and stop event",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for comfyui img2img passes image path and stop event,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: bytes value built or selected by this helper]
    # }
    def test_comfyui_img2img_passes_image_path_and_stop_event(self):
        # {
        #   責務: [FakeClient: reusable fixture or controlled test double for FakeClient behavior]
        #   処理: [1: provide the configured fields and methods used by the surrounding cases]
        #   フィールド: [arguments: arguments fixture state used by the test cases]
        #   引数: []
        # }
        class FakeClient:
            # {
            #   責務: [__init__: initializes the fields and controlled behavior of FakeClient]
            #   処理: [1: store constructor inputs and initialize controlled fixture state]
            #   引数: [
            #     _url:  url passed to this helper (unspecified),
            #     _timeout:  timeout passed to this helper (unspecified),
            #   ],
            #   戻り値: [None: initialize instance state without returning a value]
            # }
            def __init__(self, _url, _timeout):
                self.arguments = None

            # {
            #   責務: [img2img: returns the canned image-to-image result from the fake client]
            #   処理: [1: store the generation arguments, 2: return the configured image-to-image bytes]
            #   引数: [**kwargs: keyword request options captured by the fake client (unspecified)]
            #   戻り値: [result: bytes value built or selected by this helper]
            # }
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
        self.assertEqual(backend.client.arguments["vae_name"], "")

    # {
    #   責務: [
    #     test_a1111_interrupt_uses_service_root_and_declares_capabilities: verifies the behavior described by "a1111 interrupt uses service root and declares capabilities",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for a1111 interrupt uses service root and declares capabilities,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [
    #     test_comfyui_interrupt_delegates_and_declares_workflow_support: verifies the behavior described by "comfyui interrupt delegates and declares workflow support",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for comfyui interrupt delegates and declares workflow support,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_comfyui_interrupt_delegates_and_declares_workflow_support(self):
        # {
        #   責務: [FakeClient: reusable fixture or controlled test double for FakeClient behavior]
        #   処理: [1: provide the configured fields and methods used by the surrounding cases]
        #   フィールド: [interrupted: interrupted fixture state used by the test cases]
        #   引数: []
        # }
        class FakeClient:
            # {
            #   責務: [__init__: initializes the fields and controlled behavior of FakeClient]
            #   処理: [1: store constructor inputs and initialize controlled fixture state]
            #   引数: [
            #     _url:  url passed to this helper (unspecified),
            #     _timeout:  timeout passed to this helper (unspecified),
            #   ],
            #   戻り値: [None: initialize instance state without returning a value]
            # }
            def __init__(self, _url, _timeout):
                self.interrupted = False

            # {
            #   責務: [interrupt: returns the interruption response configured for the fake client]
            #   処理: [1: store the interruption request, 2: return the configured interrupted result]
            #   引数: []
            #   戻り値: [None: test helper returns no value]
            # }
            def interrupt(self):
                self.interrupted = True

        backend = ComfyUIImageGenerationBackend("http://localhost:8188", 60, FakeClient)

        backend.interrupt()

        self.assertTrue(backend.client.interrupted)
        self.assertTrue(backend.capabilities.supports("workflow"))
        self.assertTrue(backend.capabilities.supports("interrupt"))

    # {
    #   責務: [
    #     test_factory_selects_supported_backend_and_rejects_unknown: verifies the behavior described by "factory selects supported backend and rejects unknown",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for factory selects supported backend and rejects unknown,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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
