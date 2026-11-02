from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from scripts import context
from scripts.backend.a1111_backend_catalog import A1111BackendCatalog
from scripts.backend.comfyui_backend_catalog import ComfyUIBackendCatalog
from scripts.backend.generation_backend_catalog_factory import create_generation_backend_catalog


# {
#   責務: [FakeResponse: controlled HTTP response with configured status, headers, and JSON payload]
#   処理: [1: provide the configured fields and methods used by the surrounding cases]
#   フィールド: [payload: HTTP request/response payload captured by the fixture]
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

    # {
    #   責務: [raise_for_status: records that the fake HTTP response status was checked]
    #   処理: [1: record that the caller checked the fake response status]
    #   引数: []
    #   戻り値: [result: NoneType value built or selected by this helper]
    # }
    def raise_for_status(self):
        return None

    # {
    #   責務: [json: returns the configured decoded response payload]
    #   処理: [1: return the payload configured for this fake response]
    #   引数: []
    #   戻り値: [result: value returned by the helper's documented test role]
    # }
    def json(self):
        return self.payload


# {
#   責務: [GenerationBackendCatalogTests: related test fixtures and cases for GenerationBackendCatalog behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class GenerationBackendCatalogTests(unittest.TestCase):
    # {
    #   責務: [GenerationBackendCatalogTests: backend catalog候補とcapabilityの共通契約を検証する]
    # }

    # {
    #   責務: [test_capabilities_are_shared_with_generation_adapters: UI catalogと生成adapterが同じ機能宣言を公開することを検証する]
    #   処理: [A1111とComfyUIのworkflow対応を各catalogのcapabilityから確認する]
    #   戻り値: []
    # }
    # {
    #   責務: [
    #     test_capabilities_are_shared_with_generation_adapters: verifies the behavior described by "capabilities are shared with generation adapters",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for capabilities are shared with generation adapters,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_capabilities_are_shared_with_generation_adapters(self):
        a1111 = create_generation_backend_catalog("a1111")
        comfyui = create_generation_backend_catalog("comfyui")

        self.assertFalse(a1111.capabilities.supports("workflow"))
        self.assertTrue(comfyui.capabilities.supports("workflow"))
        self.assertFalse(a1111.capabilities.supports("model_overrides"))
        self.assertTrue(comfyui.capabilities.supports("model_overrides"))

    # {
    #   責務: [test_runtime_checkpoint_folders_are_backend_specific: 各catalogが従来のruntime checkpoint配置先を公開することを検証する]
    #   処理: [A1111とComfyUIのcatalogが異なるcheckpoint folder名を返すことを確認する]
    #   戻り値: []
    # }
    # {
    #   責務: [
    #     test_runtime_checkpoint_folders_are_backend_specific: verifies the behavior described by "runtime checkpoint folders are backend specific",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for runtime checkpoint folders are backend specific,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_runtime_checkpoint_folders_are_backend_specific(self):
        self.assertEqual(A1111BackendCatalog().runtime_checkpoint_folders, ("Stable-diffusion",))
        self.assertEqual(ComfyUIBackendCatalog().runtime_checkpoint_folders, ("checkpoints",))

    # {
    #   責務: [test_configured_catalog_is_selected_at_context_boundary: context境界が実行時設定に対応するcatalogを返すことを検証する]
    #   処理: [A1111とComfyUIの設定を順に適用し, 対応catalogのcapabilityを確認する]
    #   戻り値: []
    # }
    # {
    #   責務: [
    #     test_configured_catalog_is_selected_at_context_boundary: verifies the behavior described by "configured catalog is selected at context boundary",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for configured catalog is selected at context boundary,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_configured_catalog_is_selected_at_context_boundary(self):
        with patch.object(context, "RUNTIME_BACKEND", "a1111"):
            a1111 = context.create_configured_generation_backend_catalog()
        with patch.object(context, "RUNTIME_BACKEND", "comfyui"):
            comfyui = context.create_configured_generation_backend_catalog()

        self.assertFalse(a1111.capabilities.supports("workflow"))
        self.assertTrue(comfyui.capabilities.supports("workflow"))

    # {
    #   責務: [test_prompt_generate_workflow_value_uses_capability: Prompt Generateがworkflow値をcapabilityに応じて保持または除外することを検証する]
    #   処理: [同じworkflow入力に対しA1111では空値, ComfyUIでは選択値を返すことを確認する]
    #   戻り値: []
    # }
    # {
    #   責務: [
    #     test_prompt_generate_workflow_value_uses_capability: verifies the behavior described by "prompt generate workflow value uses capability",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for prompt generate workflow value uses capability,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_prompt_generate_workflow_value_uses_capability(self):
        from scripts.tabs.prompt_generate import PromptGenerateTab

        tab = PromptGenerateTab.__new__(PromptGenerateTab)
        tab.comfy_flow = Mock()
        tab.comfy_flow.get.return_value = " default.json "

        tab.backend_capabilities = create_generation_backend_catalog("a1111").capabilities
        self.assertEqual(tab._workflow_value(), "")

        tab.backend_capabilities = create_generation_backend_catalog("comfyui").capabilities
        self.assertEqual(tab._workflow_value(), "default.json")

    # {
    #   責務: [test_primary_model_choices_are_backend_specific: 主モデル候補がbackend catalogごとに選ばれることを検証する]
    #   処理: [同じcheckpoint/UNet候補mappingを各catalogへ渡し, A1111とComfyUIの結果を比較する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_primary_model_choices_are_backend_specific(self):
        choices = {
            "checkpoints": ["checkpoint.safetensors", "checkpoint.safetensors"],
            "unets": ["unet.safetensors", "checkpoint.safetensors"],
        }

        self.assertEqual(
            A1111BackendCatalog().primary_model_choices(choices),
            ["checkpoint.safetensors"],
        )
        self.assertEqual(
            ComfyUIBackendCatalog().primary_model_choices(choices),
            ["checkpoint.safetensors", "unet.safetensors"],
        )

    # {
    #   責務: [
    #     test_a1111_queries_all_catalogs_and_normalizes_api_url: verifies the behavior described by "a1111 queries all catalogs and normalizes api url",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for a1111 queries all catalogs and normalizes api url,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: FakeResponse built or selected by this helper]
    # }
    def test_a1111_queries_all_catalogs_and_normalizes_api_url(self):
        payloads = {
            "sd-models": [{"title": "checkpoint.safetensors"}],
            "loras": [{"name": "character/style"}],
            "sd-vae": [{"model_name": "vae.safetensors"}],
            "upscalers": [{"name": "4x-UltraSharp"}],
            "samplers": [{"name": "Euler a"}],
        }
        calls = []

        # {
        #   責務: [get: records or returns a deterministic HTTP response for the requested endpoint]
        #   処理: [1: record the requested endpoint, 2: select the matching configured payload or error response]
        #   引数: [url: fake endpoint URL (unspecified), timeout: maximum wait duration (unspecified)]
        #   戻り値: [result: FakeResponse built or selected by this helper]
        # }
        def get(url, timeout):
            calls.append((url, timeout))
            endpoint = url.rsplit("/", 1)[-1]
            return FakeResponse(payloads[endpoint])

        choices, warnings = A1111BackendCatalog().query_choices(
            "http://localhost:7860/sdapi/v1/txt2img", get
        )

        self.assertEqual(choices, {
            "checkpoints": ["checkpoint.safetensors"],
            "unets": [],
            "loras": ["character/style"],
            "vaes": ["vae.safetensors"],
            "upscalers": ["4x-UltraSharp"],
            "samplers": ["Euler a"],
        })
        self.assertEqual(warnings, [])
        self.assertEqual(calls[0], ("http://localhost:7860/sdapi/v1/sd-models", 5))

    # {
    #   責務: [
    #     test_comfyui_reads_choices_from_object_info: verifies the behavior described by "comfyui reads choices from object info",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for comfyui reads choices from object info,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: FakeResponse built or selected by this helper]
    # }
    def test_comfyui_reads_choices_from_object_info(self):
        values = {
            "CheckpointLoaderSimple": ("ckpt_name", ["model.safetensors"]),
            "UNETLoader": ("unet_name", ["diffusion_models/flux-dev.safetensors"]),
            "LoraLoader": ("lora_name", ["style.safetensors"]),
            "VAELoader": ("vae_name", ["vae.safetensors"]),
            "UpscaleModelLoader": ("model_name", ["upscale.pth"]),
            "KSampler": ("sampler_name", ["euler"]),
        }

        # {
        #   責務: [get: records or returns a deterministic HTTP response for the requested endpoint]
        #   処理: [1: record the requested endpoint, 2: select the matching configured payload or error response]
        #   引数: [url: fake endpoint URL (unspecified), timeout: maximum wait duration (unspecified)]
        #   戻り値: [result: FakeResponse built or selected by this helper]
        # }
        def get(url, timeout):
            node_name = url.rsplit("/", 1)[-1]
            field, choices = values[node_name]
            return FakeResponse({node_name: {"input": {"required": {field: [choices, {}]}}}})

        choices, warnings = ComfyUIBackendCatalog().query_choices("http://localhost:8188/", get)

        self.assertEqual(choices, {
            "checkpoints": ["model.safetensors"],
            "unets": ["diffusion_models/flux-dev.safetensors"],
            "loras": ["style.safetensors"],
            "vaes": ["vae.safetensors"],
            "upscalers": ["upscale.pth"],
            "samplers": ["euler"],
        })
        self.assertEqual(warnings, [])

    # {
    #   責務: [
    #     test_endpoint_failure_is_reported_without_losing_other_results: verifies the behavior described by "endpoint failure is reported without losing other results",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for endpoint failure is reported without losing other results,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: FakeResponse built or selected by this helper]
    # }
    def test_endpoint_failure_is_reported_without_losing_other_results(self):
        # {
        #   責務: [get: records or returns a deterministic HTTP response for the requested endpoint]
        #   処理: [1: record the requested endpoint, 2: select the matching configured payload or error response]
        #   引数: [url: fake endpoint URL (unspecified), timeout: maximum wait duration (unspecified)]
        #   戻り値: [result: FakeResponse built or selected by this helper]
        # }
        def get(url, timeout):
            if url.endswith("/samplers"):
                raise RuntimeError("offline")
            if url.endswith("/loras"):
                return FakeResponse([{"name": "style"}])
            if url.endswith("/sd-models"):
                return FakeResponse([{"model_name": "checkpoint"}])
            if url.endswith("/sd-vae"):
                return FakeResponse([{"model_name": "vae"}])
            return FakeResponse([{"name": "upscaler"}])

        choices, warnings = A1111BackendCatalog().query_choices("http://localhost:7860", get)

        self.assertEqual(choices["checkpoints"], ["checkpoint"])
        self.assertEqual(choices["loras"], ["style"])
        self.assertEqual(choices["upscalers"], ["upscaler"])
        self.assertEqual(choices["samplers"], [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("samplers", warnings[0])

    # {
    #   責務: [
    #     test_factory_rejects_unknown_backend: verifies the behavior described by "factory rejects unknown backend",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for factory rejects unknown backend,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_factory_rejects_unknown_backend(self):
        with self.assertRaises(ValueError):
            create_generation_backend_catalog("unknown")


if __name__ == "__main__":
    unittest.main()
