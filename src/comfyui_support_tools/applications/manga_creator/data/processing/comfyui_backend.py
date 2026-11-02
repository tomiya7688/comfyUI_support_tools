"""ComfyUI-backed manga panel rendering adapter."""

from __future__ import annotations

import copy
import json
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from PIL import Image

from comfyui_support_tools.shared.comfyui_generate_command import (
    ComfyUIGenerateCommand,
)
from comfyui_support_tools.shared.contracts.manga_creator import (
    MangaStyleMode,
    PanelRenderRequest,
    PanelRenderResult,
)

MAX_WORKFLOW_BYTES = 10 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_PIXELS = 80_000_000


# {
#   責務: [_unique_object: workflow JSONの重複keyを拒否する]
#   処理: [1: key/value pairをdict化, 2: duplicate keyを検出して失敗]
#   引数: [pairs: JSON parserが返すpair sequence]
#   戻り値: [dict[str, object]: keyが一意なJSON object]
# }
def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate workflow field: {key}")
        result[key] = value
    return result


# {
#   責務: [ComfyUIPanelBackend: ComfyUI API workflowを漫画panel画像生成に接続する]
#   フィールド: [workflow, API URL, prompt/seed node IDs, command, timeout]
#   処理: [1: workflowを検証, 2: panel意図をpromptへ変換, 3: ComfyUIで生成して画像を返す]
# }
class ComfyUIPanelBackend:
    # {
    #   責務: [__init__: ComfyUI panel backendを設定する]
    #   処理: [1: API workflowとnode指定を検証, 2: injectable commandを保持]
    #   引数: [workflow: API workflow JSONまたは絶対Path, api_url: local ComfyUI URL, prompt_node_ids: positive text nodes, negative_prompt_node_ids: negative text nodes, seed_node_ids: seed-bearing sampler nodes, timeout: generation timeout, command: injectable API command]
    #   戻り値: []
    # }
    def __init__(
        self,
        workflow: Mapping[str, Any] | Path,
        *,
        api_url: str = "http://127.0.0.1:8188",
        prompt_node_ids: tuple[str, ...] | None = None,
        negative_prompt_node_ids: tuple[str, ...] | None = None,
        seed_node_ids: tuple[str, ...] = (),
        timeout: float = 1800,
        command: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        if isinstance(workflow, Path):
            if not workflow.is_absolute() or workflow.is_symlink() or not workflow.is_file():
                raise ValueError("workflow path must be an existing absolute regular file")
            if workflow.stat().st_size > MAX_WORKFLOW_BYTES:
                raise ValueError("workflow file exceeds 10 MiB")
            raw = workflow.read_bytes()
            try:
                workflow = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
            except (UnicodeError, json.JSONDecodeError):
                raise ValueError("workflow file must contain valid UTF-8 JSON") from None
        if not isinstance(workflow, Mapping) or not workflow:
            raise ValueError("workflow must be a non-empty API-format object")
        try:
            self._workflow = copy.deepcopy(dict(workflow))
            encoded = json.dumps(self._workflow, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError):
            raise ValueError("workflow must contain JSON-compatible values") from None
        if len(encoded) > MAX_WORKFLOW_BYTES:
            raise ValueError("workflow must not exceed 10 MiB")
        for node_id, node in self._workflow.items():
            if (
                not isinstance(node_id, str)
                or not isinstance(node, dict)
                or not isinstance(node.get("class_type"), str)
                or not isinstance(node.get("inputs"), dict)
            ):
                raise ValueError("workflow must contain API nodes with class_type and inputs")
        self._prompt_node_ids = prompt_node_ids
        self._negative_prompt_node_ids = negative_prompt_node_ids
        self._seed_node_ids = seed_node_ids or tuple(
            node_id
            for node_id, node in self._workflow.items()
            if {"seed", "noise_seed"} & set(node["inputs"])
        )
        self._api_url = ComfyUIGenerateCommand._validate_api_url(api_url)
        ComfyUIGenerateCommand._validate_timeout(timeout)
        self._timeout = timeout
        self._command = command or ComfyUIGenerateCommand(timeout=timeout)
        self._validate_seed_nodes()

    # {
    #   責務: [render_panel: 構造化されたpanel意図をComfyUIで画像化する]
    #   処理: [1: project bibleとpanel計画からpromptを作成, 2: sampler seedを設定, 3: 生成画像を検証してbytesで返す]
    #   引数: [request: project/page/panel/bible/continuityを含む生成要求]
    #   戻り値: [PanelRenderResult: PNGまたはJPEG画像とbackend provenance]
    # }
    def render_panel(self, request: PanelRenderRequest) -> PanelRenderResult:
        if request.seed is not None and not self._seed_node_ids:
            raise ValueError(
                "workflow has no seed input; reproducible panel generation is unavailable"
            )
        prompt = self._positive_prompt(request)
        negative_prompt = self._negative_prompt(request)
        overrides = self._seed_overrides(request.seed)
        with tempfile.TemporaryDirectory(prefix="manga-comfyui-") as temporary:
            response = self._command(
                {
                    "workflow": self._workflow,
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "prompt_node_ids": list(self._prompt_node_ids)
                    if self._prompt_node_ids is not None
                    else None,
                    "negative_prompt_node_ids": list(self._negative_prompt_node_ids)
                    if self._negative_prompt_node_ids is not None
                    else None,
                    "overrides": overrides,
                    "api_url": self._api_url,
                    "timeout": self._timeout,
                    "output_dir": temporary,
                },
                {},
            )
            if not isinstance(response, Mapping) or not isinstance(response.get("image"), str):
                raise RuntimeError("ComfyUI manga backend returned no image path")
            image_path = Path(response["image"])
            root = Path(temporary).resolve()
            if (
                not image_path.is_absolute()
                or image_path.is_symlink()
                or image_path.resolve().parent != root
            ):
                raise RuntimeError("ComfyUI returned an image outside its temporary output")
            if image_path.stat().st_size > MAX_OUTPUT_BYTES:
                raise ValueError("ComfyUI panel image exceeds 64 MiB")
            with Image.open(image_path) as image:
                if image.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("ComfyUI panel image must be PNG, JPEG, or WEBP")
                if (
                    image.width < 1
                    or image.height < 1
                    or image.width * image.height > MAX_OUTPUT_PIXELS
                ):
                    raise ValueError("ComfyUI panel image dimensions exceed safe limits")
                image.verify()
            image_bytes = image_path.read_bytes()
        return PanelRenderResult(
            image_bytes,
            "comfyui",
            request.seed,
            ("Reference image paths are recorded but not injected into this generic workflow.",),
        )

    # {
    #   責務: [_positive_prompt: bibleとpanel intentを可読promptに変換する]
    #   処理: [1: location/character/prop groundingを組み立て, 2: action/camera/style制約を追加, 3: lettering分離を明記]
    #   引数: [request: panel generation context]
    #   戻り値: [str: positive text prompt]
    # }
    @staticmethod
    def _positive_prompt(request: PanelRenderRequest) -> str:
        project = request.project
        panel = request.panel
        characters = {item.id: item for item in project.characters}
        locations = {item.id: item for item in project.locations}
        props = {item.id: item for item in project.props}
        parts = [
            f"Create one manga panel illustration for {project.genre or 'a manga story'}.",
            f"Panel purpose: {panel.narrative_purpose}. Beat: {panel.beat}.",
            f"Action: {panel.action}. Emotion: {panel.emotion}. Pose: {', '.join(panel.poses)}.",
            f"Expression: {', '.join(panel.expressions)}. Gaze: {panel.gaze}.",
            f"Camera: {panel.camera}. Shot: {panel.shot}.",
        ]
        location = locations.get(panel.background_location_id)
        if location:
            parts.append(
                "Location: "
                + ", ".join(
                    value
                    for value in (
                        location.name,
                        location.description,
                        location.layout,
                        location.lighting,
                        location.time_of_day,
                        location.style,
                    )
                    if value
                )
            )
        for character_id in panel.character_ids:
            character = characters.get(character_id)
            if character:
                parts.append(
                    f"Character {character.name}: "
                    + ", ".join(
                        value
                        for value in (
                            *character.fixed_visual_attributes,
                            character.default_costume,
                            *character.accessories,
                            *character.variable_state,
                        )
                        if value
                    )
                )
        for prop_id in panel.prop_ids:
            prop = props.get(prop_id)
            if prop:
                parts.append(
                    f"Prop {prop.name}: {prop.description} {prop.continuity_state}".strip()
                )
        constraints = [*panel.preserve_constraints]
        constraints.extend(
            f"Story continuity: {event.entity_id} {event.field} remains {event.value}."
            for event in request.continuity_context
        )
        parts.extend(constraints)
        parts.append(
            "Do not draw speech text, captions, watermarks, or panel borders; lettering is composited separately."
        )
        if project.style == MangaStyleMode.BLACK_AND_WHITE:
            parts.append("Black-and-white manga ink, clear line art, readable screentone shading.")
        elif project.style == MangaStyleMode.COLOR:
            parts.append("Full-color manga illustration with clear silhouette separation.")
        else:
            parts.append("Readable manga storyboard illustration with a clear focal point.")
        return "\n".join(parts)[:12000]

    # {
    #   責務: [_negative_prompt: 漫画panelで避ける生成内容を指定する]
    #   処理: [1: letteringやwatermarkなどの除外語を返す]
    #   引数: [request: panel request]
    #   戻り値: [str: negative text prompt]
    # }
    @staticmethod
    def _negative_prompt(request: PanelRenderRequest) -> str:
        return (
            "text, letters, speech bubbles, watermark, signature, extra panels, page collage, "
            "duplicate character, inconsistent costume, malformed anatomy, cropped focal subject"
        )

    # {
    #   責務: [_validate_seed_nodes: sampler node指定がworkflowと合うことを検証する]
    #   処理: [1: node IDを解決, 2: seed/noise_seed入力の有無を確認]
    #   引数: [self: backend]
    #   戻り値: []
    # }
    def _validate_seed_nodes(self) -> None:
        if len(set(self._seed_node_ids)) != len(self._seed_node_ids):
            raise ValueError("seed_node_ids must be unique")
        for node_id in self._seed_node_ids:
            node = self._workflow.get(node_id)
            if not node or not ({"seed", "noise_seed"} & set(node["inputs"])):
                raise ValueError(f"sampler node {node_id} has no seed input")

    # {
    #   責務: [_seed_overrides: 指定samplerへ再現可能seedを適用する]
    #   処理: [1: seedなしなら空overrideを返す, 2: seed fieldをworkflowから選んで値を設定]
    #   引数: [self: backend, seed: optional generation seed]
    #   戻り値: [dict[str, dict[str, int]]: ComfyUI workflow overrides]
    # }
    def _seed_overrides(self, seed: int | None) -> dict[str, dict[str, int]]:
        if seed is None:
            return {}
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ValueError("panel seed must be a nonnegative integer")
        if seed > 2**63 - 1:
            raise ValueError("panel seed exceeds ComfyUI's supported integer range")
        return {
            node_id: {
                "noise_seed" if "noise_seed" in self._workflow[node_id]["inputs"] else "seed": seed
            }
            for node_id in self._seed_node_ids
        }
