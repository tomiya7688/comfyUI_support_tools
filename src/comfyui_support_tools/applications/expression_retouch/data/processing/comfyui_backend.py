"""ComfyUI image-to-image/inpaint backend for expression retouch."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from PIL import Image

from comfyui_support_tools.shared.comfyui_generate_command import ComfyUIGenerateCommand
from comfyui_support_tools.shared.contracts.expression_retouch import (
    ExpressionBackendCapabilities,
    ExpressionEditRequest,
    ExpressionMode,
)

MAX_WORKFLOW_BYTES = 10 * 1024 * 1024


# {
#   責務: [ComfyUIExpressionBackend: upload source and local mask to a ComfyUI inpaint workflow]
#   フィールド: [workflow, image/mask loader nodes, prompt/seed/sampler nodes, API endpoint, command]
#   処理: [validate supported nodes, upload target image and mask, apply expression prompt/strength/seed, return generated image]
# }
class ComfyUIExpressionBackend:
    # {
    #   責務: [__init__: configure a ComfyUI local inpaint workflow]
    #   処理: [1: load and validate workflow, 2: confirm source and mask loader nodes, 3: bind API settings]
    #   引数: [workflow: workflow mapping or JSON file, image_node_id: source LoadImage node, mask_node_id: mask LoadImage/LoadImageMask node, prompt_node_ids: optional text node IDs, negative_prompt_node_ids: optional negative text node IDs, seed_node_ids: optional sampler seed nodes, sampler_node_id: optional denoise input node, api_url: local ComfyUI endpoint, timeout: request limit, command: injected ComfyUI runner]
    #   戻り値: []
    # }
    def __init__(
        self,
        workflow: Mapping[str, Any] | Path,
        *,
        image_node_id: str,
        mask_node_id: str,
        prompt_node_ids: tuple[str, ...] | None = None,
        negative_prompt_node_ids: tuple[str, ...] | None = None,
        seed_node_ids: tuple[str, ...] = (),
        sampler_node_id: str | None = None,
        api_url: str = "http://127.0.0.1:8188",
        timeout: float = 1800,
        command: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        if isinstance(workflow, Path):
            if not workflow.is_absolute() or workflow.is_symlink() or not workflow.is_file():
                raise ValueError("workflow must be an absolute regular JSON file")
            if workflow.stat().st_size > MAX_WORKFLOW_BYTES:
                raise ValueError("workflow file exceeds 10 MiB")
            try:
                graph = json.loads(workflow.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                raise ValueError("workflow file must contain valid UTF-8 JSON") from None
        elif isinstance(workflow, Mapping):
            graph = dict(workflow)
        else:
            raise ValueError("workflow must be an API-format mapping or JSON file")
        self._workflow = ComfyUIGenerateCommand._workflow({"workflow": graph})
        self._image_node_id = image_node_id
        self._mask_node_id = mask_node_id
        self._prompt_node_ids = prompt_node_ids
        self._negative_prompt_node_ids = negative_prompt_node_ids
        self._seed_node_ids = seed_node_ids or tuple(
            node_id
            for node_id, node in self._workflow.items()
            if {"seed", "noise_seed"} & set(node["inputs"])
        )
        self._sampler_node_id = sampler_node_id
        for node_id in (image_node_id, mask_node_id):
            node = self._workflow.get(node_id)
            if (
                node is None
                or node["class_type"] not in {"LoadImage", "LoadImageMask"}
                or "image" not in node["inputs"]
            ):
                raise ValueError(f"node {node_id} must load an image or mask")
        if image_node_id == mask_node_id:
            raise ValueError("source image and edit mask must use separate loader nodes")
        if sampler_node_id is not None:
            sampler = self._workflow.get(sampler_node_id)
            if sampler is None or "denoise" not in sampler["inputs"]:
                raise ValueError("sampler_node_id must refer to a node with a denoise input")
        self._api_url = ComfyUIGenerateCommand._validate_api_url(api_url)
        ComfyUIGenerateCommand._validate_timeout(timeout)
        self._timeout = timeout
        self._command = command or ComfyUIGenerateCommand(timeout=timeout)

    # {
    #   責務: [backend_id: expose the stable ComfyUI expression backend name]
    #   処理: [return the registry identifier]
    #   引数: [self: backend]
    #   戻り値: [str: comfyui_inpaint]
    # }
    @property
    def backend_id(self) -> str:
        return "comfyui_inpaint"

    # {
    #   責務: [capabilities: describe the backend's supported local edit behavior]
    #   処理: [advertise mode, mask, source-image conditioning and bounded resolution]
    #   引数: [self: backend]
    #   戻り値: [ExpressionBackendCapabilities: adapter capability contract]
    # }
    @property
    def capabilities(self) -> ExpressionBackendCapabilities:
        return ExpressionBackendCapabilities(
            (ExpressionMode.ANIME, ExpressionMode.PHOTOREAL),
            local_mask=True,
            identity_reference=True,
            instruction_edit=True,
            max_resolution=8192,
        )

    # {
    #   責務: [edit: generate one image-conditioned, masked expression candidate]
    #   処理: [1: build target/preservation prompt, 2: upload source and mask into workflow, 3: apply seed and denoise, 4: read a bounded candidate]
    #   引数: [request: target expression and preservation settings, mask: grayscale PNG, seed: candidate seed]
    #   戻り値: [bytes: generated image candidate]
    # }
    def edit(self, request: ExpressionEditRequest, mask: bytes, seed: int | None) -> bytes:
        if seed is not None and not self._seed_node_ids:
            raise ValueError("workflow has no sampler seed input")
        overrides: dict[str, dict[str, float | int]] = {}
        if seed is not None:
            for node_id in self._seed_node_ids:
                node_inputs = self._workflow[node_id]["inputs"]
                seed_key = "noise_seed" if "noise_seed" in node_inputs else "seed"
                overrides.setdefault(node_id, {})[seed_key] = seed
        if self._sampler_node_id:
            overrides.setdefault(self._sampler_node_id, {})["denoise"] = request.denoise
        prompt = self._prompt(request)
        with tempfile.TemporaryDirectory(prefix="expression-retouch-") as output_dir:
            response = self._command(
                {
                    "workflow": self._workflow,
                    "prompt": prompt,
                    "negative_prompt": self._negative_prompt(request),
                    "prompt_node_ids": list(self._prompt_node_ids)
                    if self._prompt_node_ids is not None
                    else None,
                    "negative_prompt_node_ids": list(self._negative_prompt_node_ids)
                    if self._negative_prompt_node_ids is not None
                    else None,
                    "image_uploads": {
                        self._image_node_id: ("expression-source.png", request.source_image),
                        self._mask_node_id: ("expression-mask.png", mask),
                    },
                    "overrides": overrides,
                    "api_url": self._api_url,
                    "timeout": self._timeout,
                    "output_dir": output_dir,
                },
                {},
            )
            if not isinstance(response, Mapping) or not isinstance(response.get("image"), str):
                raise RuntimeError("ComfyUI expression backend returned no image path")
            path = Path(response["image"])
            root = Path(output_dir).resolve()
            if not path.is_absolute() or path.is_symlink() or path.resolve().parent != root:
                raise RuntimeError("ComfyUI returned an image outside the temporary output")
            if path.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("ComfyUI expression image exceeds 64 MiB")
            with Image.open(path) as image:
                if image.width * image.height > 80_000_000:
                    raise ValueError("ComfyUI expression image exceeds 80 megapixels")
                image.verify()
            return path.read_bytes()

    # {
    #   責務: [_prompt: translate expression target and controls to an editing instruction]
    #   処理: [1: state edit intent and mode, 2: emphasize identity/background locks, 3: include explicit muscle controls]
    #   引数: [request: expression edit request]
    #   戻り値: [str: bounded positive prompt]
    # }
    @staticmethod
    def _prompt(request: ExpressionEditRequest) -> str:
        parts = [
            f"Edit only the facial expression to {request.target.value.replace('_', ' ')}.",
            f"Expression intensity {request.intensity:.2f}; appearance mode {request.mode.value}.",
            f"Identity preservation strength {request.preserve_identity:.2f}.",
            "Preserve the same person's identity, face outline, hair, eye color, skin tone, costume, accessories, camera, and composition.",
            "Change only these selected facial parts inside the supplied mask: "
            + ", ".join(part.value.replace("_", " ") for part in request.edit_regions)
            + ".",
        ]
        if request.preserve_background:
            parts.append(
                "Keep every pixel outside the facial edit mask unchanged, especially the background."
            )
        if request.natural_language.strip():
            parts.append(f"User instruction: {request.natural_language.strip()}")
        controls = [
            f"{name}={value:.2f}"
            for name, value in request.parameters.__dict__.items()
            if value is not None
        ]
        if controls:
            parts.append("Facial controls: " + ", ".join(controls))
        if request.mode == ExpressionMode.ANIME:
            parts.append(
                "Preserve original anime line art, eye design, flat colors, and facial proportions."
            )
        else:
            parts.append(
                "Preserve skin texture and natural facial asymmetry; avoid malformed teeth or mouth interior."
            )
        return "\n".join(parts)[:8000]

    # {
    #   責務: [_negative_prompt: prevent unwanted global edits in face retouch]
    #   処理: [return stable exclusions for identity and non-target preservation]
    #   引数: [request: expression edit request]
    #   戻り値: [str: negative prompt]
    # }
    @staticmethod
    def _negative_prompt(request: ExpressionEditRequest) -> str:
        return (
            "different person, changed hair, changed clothing, changed background, changed camera, "
            "extra face, warped skull, asymmetrical pupils, duplicate eyes, malformed teeth, text, watermark"
        )
