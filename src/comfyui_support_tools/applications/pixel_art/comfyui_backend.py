"""ComfyUI API adapter for prompt-driven pixel-art drafts."""

from __future__ import annotations

import copy
import json
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image

from comfyui_support_tools.applications.sequence.data.processing.comfyui_generate_command import (
    ComfyUIGenerateCommand,
)
from comfyui_support_tools.shared.pixel_art.contracts import PixelArtRequest
from comfyui_support_tools.shared.pixel_art.pipeline import validate_settings


# {
# 責務: [ComfyUIPixelTextBackend: adapt local ComfyUI API workflows to pixel draft generation]
# フィールド: [workflow, api_url, timeout, command adapter]
# 処理: [inject pixel intent/dimensions/seed, retrieve candidates, and return copied images]
# }
class ComfyUIPixelTextBackend:
    # {
    # 責務: [__init__: configure an API-format ComfyUI workflow and local endpoint]
    # 処理: [store a reusable workflow and injectable command for deterministic tests]
    # 引数: [workflow: API workflow mapping or file path, api_url: loopback endpoint, timeout: request limit, command: command adapter]
    # 戻り値: [None: initialized ComfyUI pixel backend]
    # }
    def __init__(
        self,
        workflow: Mapping[str, Any] | Path,
        api_url: str = "http://127.0.0.1:8188",
        timeout: float = 1800,
        command=None,
    ):
        if isinstance(workflow, Mapping):
            self.workflow = copy.deepcopy(dict(workflow))
        elif isinstance(workflow, Path):
            if not workflow.is_absolute() or workflow.is_symlink() or not workflow.is_file():
                raise ValueError("workflow path must be an existing absolute regular file")
            if workflow.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("workflow file exceeds 10 MiB")
            try:
                self.workflow = json.loads(workflow.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                raise ValueError("workflow file must contain valid UTF-8 JSON") from None
        else:
            raise ValueError("workflow must be an API-format mapping or Path")
        if not isinstance(self.workflow, dict) or not self.workflow:
            raise ValueError("workflow must be a non-empty API-format mapping")
        if any(
            not isinstance(node, dict)
            or not isinstance(node.get("class_type"), str)
            or not isinstance(node.get("inputs"), dict)
            for node in self.workflow.values()
        ):
            raise ValueError("workflow must contain API-format nodes")
        self.api_url = ComfyUIGenerateCommand._validate_api_url(api_url)
        ComfyUIGenerateCommand._validate_timeout(timeout)
        self.timeout = timeout
        self.command = command or ComfyUIGenerateCommand(timeout=timeout)

    # {
    # 責務: [generate: request ranked pixel-art drafts from ComfyUI]
    # 処理: [submit one configured workflow per candidate with pixel prompt and target dimensions]
    # 引数: [request: prompt, category, palette intent, size, seed, and candidate count]
    # 戻り値: [tuple[Image, ...]: copied generated images ready for strict-grid rendering]
    # }
    def generate(self, request: PixelArtRequest) -> tuple[Image.Image, ...]:
        validate_settings(request.settings)
        if not isinstance(request.prompt, str) or not request.prompt.strip():
            raise ValueError("pixel prompt must not be empty")
        if (
            not isinstance(request.candidate_count, int)
            or isinstance(request.candidate_count, bool)
            or not 1 <= request.candidate_count <= 16
        ):
            raise ValueError("candidate_count must be in 1..16")
        width, height = request.settings.custom_size or (
            request.settings.size,
            request.settings.size,
        )
        with tempfile.TemporaryDirectory(prefix="pixel-art-comfyui-") as temporary:
            temporary_root = Path(temporary).resolve()
            images = []
            generation_scale = self._generation_scale(width, height)
            for index in range(request.candidate_count):
                workflow = self._candidate_workflow(
                    request,
                    width * generation_scale,
                    height * generation_scale,
                    index,
                )
                inputs = {
                    "workflow": workflow,
                    "prompt": self._positive_prompt(request),
                    "negative_prompt": self._negative_prompt(request),
                    "api_url": self.api_url,
                    "timeout": self.timeout,
                    "output_dir": temporary,
                }
                response = self.command(inputs, {})
                if not isinstance(response, Mapping) or not isinstance(response.get("image"), str):
                    raise RuntimeError("ComfyUI pixel backend returned no image path")
                image_path = Path(response["image"])
                if image_path.is_symlink() or image_path.resolve().parent != temporary_root:
                    raise RuntimeError("ComfyUI pixel backend returned an unsafe image path")
                with Image.open(image_path) as image:
                    images.append(image.copy())
        return tuple(images)

    # {
    # 責務: [_generation_scale: select a semantic draft size for target pixel resolution]
    # 処理: [use larger drafts only for tiny targets and keep larger targets near-native]
    # 引数: [width/height: requested final pixel grid dimensions]
    # 戻り値: [int: draft-to-grid scale factor]
    # }
    @staticmethod
    def _generation_scale(width, height):
        target = max(width, height)
        if target <= 16:
            return 8
        if target <= 32:
            return 4
        if target <= 64:
            return 2
        return 1

    # {
    # 責務: [_candidate_workflow: specialize one ComfyUI workflow for target pixel dimensions]
    # 処理: [set latent width/height and sampler seed on copied API graph nodes]
    # 引数: [request: pixel request, width/height: target canvas, index: candidate offset]
    # 戻り値: [dict: independent candidate workflow]
    # }
    def _candidate_workflow(self, request, width, height, index):
        workflow = copy.deepcopy(self.workflow)
        size_nodes = 0
        for node in workflow.values():
            node_type = node["class_type"]
            inputs = node["inputs"]
            if node_type in {"EmptyLatentImage", "EmptySD3LatentImage"}:
                inputs["width"] = width
                inputs["height"] = height
                size_nodes += 1
            if node_type == "KSamplerAdvanced" and "noise_seed" in inputs:
                base_seed = request.seed if request.seed is not None else inputs["noise_seed"]
                if not isinstance(base_seed, int) or isinstance(base_seed, bool) or base_seed < 0:
                    raise ValueError("ComfyUI sampler seed must be a non-negative integer")
                inputs["noise_seed"] = (base_seed + index) % (2**32)
            elif node_type in {"KSampler", "KSamplerAdvanced"} and "seed" in inputs:
                base_seed = request.seed if request.seed is not None else inputs["seed"]
                if not isinstance(base_seed, int) or isinstance(base_seed, bool) or base_seed < 0:
                    raise ValueError("ComfyUI sampler seed must be a non-negative integer")
                inputs["seed"] = (int(base_seed) + index) % (2**32)
        if size_nodes == 0:
            raise ValueError("ComfyUI workflow must contain an EmptyLatentImage size node")
        return workflow

    # {
    # 責務: [_positive_prompt: combine plain prompt with pixel-specific request intent]
    # 処理: [add category/style/grid/palette/anti-alias constraints without mimicking a specific game]
    # 引数: [request: typed pixel generation request]
    # 戻り値: [str: positive ComfyUI conditioning prompt]
    # }
    @staticmethod
    def _positive_prompt(request):
        settings = request.settings
        width, height = settings.custom_size or (settings.size, settings.size)
        category = getattr(settings.category, "value", settings.category)
        palette = ", user-defined palette" if settings.palette_mode == "custom" else ""
        return (
            f"{request.prompt.strip()}, pixel art, {request.style.replace('_', ' ')} style, "
            f"{category} sprite, {width}x{height} pixel canvas, "
            f"crisp pixel clusters, limited palette of {settings.color_count} colors{palette}, "
            f"{request.outline_policy.replace('_', ' ')} outline, {request.shading_level} shading, "
            f"{request.detail_level} detail, clean silhouette, no antialiasing, no blur"
        )

    # {
    # 責務: [_negative_prompt: append pixel-art failure constraints to user negatives]
    # 処理: [combine caller exclusions with anti-alias and fractional-edge suppression]
    # 引数: [request: typed pixel generation request]
    # 戻り値: [str: negative ComfyUI conditioning prompt]
    # }
    @staticmethod
    def _negative_prompt(request):
        constraints = (
            "photorealistic, blurry, antialiased edges, subpixel gradients, noisy dithering"
        )
        return ", ".join(part for part in (request.negative_prompt.strip(), constraints) if part)
