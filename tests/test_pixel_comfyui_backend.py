"""Tests for prompt-driven ComfyUI pixel-art workflow adaptation."""

from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image

from comfyui_support_tools.applications.pixel_art.comfyui_backend import ComfyUIPixelTextBackend
from comfyui_support_tools.shared.pixel_art import PixelArtRequest, PixelArtSettings


# {
# 責務: [FakeComfyUICommand: record requests and write deterministic image candidates]
# フィールド: [calls, temporary response paths]
# 処理: [exercise adapter prompt/dimension/seed mapping without a live ComfyUI service]
# }
class FakeComfyUICommand:
    # {
    # 責務: [__init__: initialize recorded fake ComfyUI calls]
    # 処理: [keep request data for adapter assertions]
    # 引数: [None: no inputs]
    # 戻り値: [None: initialized fake command]
    # }
    def __init__(self):
        self.calls = []
        self.paths = []

    # {
    # 責務: [__call__: emulate a successful local ComfyUI image response]
    # 処理: [record input mapping and write one RGBA image into requested output folder]
    # 引数: [inputs: request data, context: command context]
    # 戻り値: [dict: saved image path]
    # }
    def __call__(self, inputs, context):
        self.calls.append(inputs)
        path = Path(inputs["output_dir"]) / f"candidate-{len(self.calls)}.png"
        Image.new("RGBA", (4, 4), (20, 100, 220, 255)).save(path)
        self.paths.append(path)
        return {"image": str(path)}


# {
# 責務: [ComfyUIPixelTextBackendTests: verify workflow specialization and prompt safety]
# フィールド: [minimal API workflow fixtures and fake command]
# 処理: [check candidate count, seed/dimension injection, negative constraints, and local URL gate]
# }
class ComfyUIPixelTextBackendTests(unittest.TestCase):
    # {
    # 責務: [workflow: provide a small valid latent/sampler API graph]
    # 処理: [return fresh ComfyUI API-format node mappings]
    # 引数: [None: no inputs]
    # 戻り値: [dict: API workflow]
    # }
    def workflow(self):
        return {
            "1": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512}},
            "2": {"class_type": "KSampler", "inputs": {"seed": 0}},
        }

    # {
    # 責務: [test_generates_isolated_size_aware_candidates: verify request translation]
    # 処理: [check candidates receive dimensions, distinct seeds, and pixel-specific prompt rules]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_generates_isolated_size_aware_candidates(self):
        command = FakeComfyUICommand()
        backend = ComfyUIPixelTextBackend(self.workflow(), command=command)
        request = PixelArtRequest(
            "blue potion",
            PixelArtSettings(size=16),
            negative_prompt="text",
            style="jrpg",
            seed=400,
            candidate_count=3,
        )
        images = backend.generate(request)
        self.assertEqual(len(images), 3)
        self.assertEqual(
            [call["workflow"]["1"]["inputs"]["width"] for call in command.calls],
            [128] * 3,
        )
        self.assertEqual(
            [call["workflow"]["1"]["inputs"]["height"] for call in command.calls],
            [128] * 3,
        )
        self.assertEqual(
            [call["workflow"]["2"]["inputs"]["seed"] for call in command.calls], [400, 401, 402]
        )
        self.assertIn("pixel art", command.calls[0]["prompt"])
        self.assertIn("no antialiasing", command.calls[0]["prompt"])
        self.assertIn("text,", command.calls[0]["negative_prompt"])
        self.assertTrue(all(not path.exists() for path in command.paths))

    # {
    # 責務: [test_rejects_remote_endpoint_and_missing_latent_dimension_nodes: fail before generation]
    # 処理: [ensure API remains loopback-only and dimensions have an explicit workflow target]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_rejects_remote_endpoint_and_missing_latent_dimension_nodes(self):
        with self.assertRaises(ValueError):
            ComfyUIPixelTextBackend(self.workflow(), api_url="https://example.com")
        command = FakeComfyUICommand()
        backend = ComfyUIPixelTextBackend(
            {"1": {"class_type": "KSampler", "inputs": {"seed": 2}}}, command=command
        )
        with self.assertRaises(ValueError):
            backend.generate(PixelArtRequest("sprite", candidate_count=1))
        self.assertEqual(command.calls, [])


if __name__ == "__main__":
    unittest.main()
