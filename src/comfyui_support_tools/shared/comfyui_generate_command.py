"""GUI-independent txt2img command for a local ComfyUI API."""

from __future__ import annotations

import copy
import ipaddress
import json
import re
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from comfyui_support_tools.shared.c2pa_adapter import SignerProvider
from comfyui_support_tools.shared.python_tls import create_certifi_context
from comfyui_support_tools.shared.transparency_preferences import TransparencyPreferenceStore
from comfyui_support_tools.shared.transparency_processing import apply_generation_transparency

MAX_WORKFLOW_BYTES = 10 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 100 * 1024 * 1024
MAX_TIMEOUT = 3600
# {
#   責務: [_NoRedirect: ComfyUI workflow command responsibility]
#   フィールド: [validated workflow execution state]
#   処理: [configure and run one bounded ComfyUI request]
# }


class _NoRedirect(HTTPRedirectHandler):
    # {
    #   責務: [redirect_request: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [self, req, fp, code, msg, headers, newurl: declared operation inputs]
    #   戻り値: [None: operation result]
    # }
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# {
#   責務: [ComfyUIGenerateCommand: ComfyUI workflow command responsibility]
#   フィールド: [validated workflow execution state]
#   処理: [configure and run one bounded ComfyUI request]
# }


class ComfyUIGenerateCommand:
    """Submit an API-format workflow, save its first image, and expose its path."""

    # {
    #   責務: [__init__: proxyなしでComfyUI通信を行うopenerを初期化する]
    #   処理: [1: timeoutとpoll intervalを検証する, 2: certifi CA bundleを使うHTTPS openerを作成する]
    #   引数: [self: command instance, timeout: 実行timeout秒, poll_interval: polling間隔秒]
    #   戻り値: []
    # }
    def __init__(
        self,
        timeout: float = 1800.0,
        poll_interval: float = 0.5,
        *,
        transparency_preferences: TransparencyPreferenceStore | None = None,
        transparency_signer_provider: SignerProvider | None = None,
    ) -> None:
        self._validate_timeout(timeout)
        if (
            isinstance(poll_interval, bool)
            or not isinstance(poll_interval, (int, float))
            or poll_interval <= 0
        ):
            raise ValueError("poll_interval must be greater than zero")
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._transparency_preferences = transparency_preferences
        self._transparency_signer_provider = transparency_signer_provider
        self._opener = build_opener(
            ProxyHandler({}), _NoRedirect(), HTTPSHandler(context=create_certifi_context())
        )

    # {
    #   責務: [__call__: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [self, inputs, _context: declared operation inputs]
    #   戻り値: [Mapping[str, Any]: operation result]
    # }

    def __call__(self, inputs: Mapping[str, Any], _context: Mapping[str, Any]) -> Mapping[str, Any]:
        workflow = self._workflow(inputs)
        prompt = self._required_text(inputs, "prompt")
        negative_prompt = inputs.get("negative_prompt", "")
        if not isinstance(negative_prompt, str):
            raise ValueError("negative_prompt must be text")
        self._apply_prompts(workflow, prompt, negative_prompt, inputs)
        self._apply_overrides(workflow, inputs.get("overrides", {}))
        api_url = self._validate_api_url(inputs.get("api_url", "http://127.0.0.1:8188"))
        timeout = inputs.get("timeout", self._timeout)
        self._validate_timeout(timeout)
        self._upload_images(api_url, workflow, inputs.get("image_uploads", {}), timeout)
        output_dir = self._output_directory(inputs.get("output_dir"))

        prompt_id = self._submit(api_url, workflow, timeout)
        image_info = self._wait_for_image(api_url, prompt_id, timeout)
        image_data = self._download_image(api_url, image_info, timeout)
        image_path = self._save_image(output_dir, image_info["filename"], prompt_id, image_data)
        result = {"image": str(image_path), "prompt_id": prompt_id, "backend": "comfyui"}
        transparency_options = inputs.get("transparency")
        transparency = apply_generation_transparency(
            image_path,
            application_id="sequence.comfyui",
            backend="comfyui",
            prompt=prompt,
            model_id=(
                transparency_options.get("model_id")
                if isinstance(transparency_options, Mapping)
                else None
            ),
            model_family=(
                transparency_options.get("model_family")
                if isinstance(transparency_options, Mapping)
                else None
            ),
            model_version=(
                transparency_options.get("model_version")
                if isinstance(transparency_options, Mapping)
                else None
            ),
            workflow=workflow,
            transparency_options=transparency_options,
            preferences=self._transparency_preferences,
            signer_provider=self._transparency_signer_provider,
        )
        if transparency["transparency_enabled"]:
            result.update(transparency)
        return result

    # {
    #   責務: [_upload_images: upload local source images and bind them to workflow loader nodes]
    #   処理: [1: validate loader node and bounded image bytes, 2: POST multipart to ComfyUI, 3: assign returned input names]
    #   引数: [self: command, base_url: validated local endpoint, workflow: API graph, image_uploads: node-to-filename-and-bytes mapping, timeout: request limit]
    #   戻り値: []
    # }
    def _upload_images(
        self,
        base_url: str,
        workflow: dict[str, Any],
        image_uploads: Any,
        timeout: float,
    ) -> None:
        if not isinstance(image_uploads, Mapping):
            raise ValueError("image_uploads must map loader node IDs to filename and image bytes")
        for node_id, upload in image_uploads.items():
            if (
                not isinstance(node_id, str)
                or node_id not in workflow
                or workflow[node_id]["class_type"] not in {"LoadImage", "LoadImageMask"}
                or "image" not in workflow[node_id]["inputs"]
            ):
                raise ValueError(f"image upload node {node_id!r} must be a ComfyUI image loader")
            if (
                not isinstance(upload, tuple)
                or len(upload) != 2
                or not isinstance(upload[0], str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}\.(?:png|jpe?g|webp)", upload[0], re.I)
                or not isinstance(upload[1], bytes)
                or not 1 <= len(upload[1]) <= MAX_IMAGE_BYTES
            ):
                raise ValueError(
                    "image upload must be a safe filename and 1..100 MiB of image bytes"
                )
            uploaded = self._upload_image(base_url, upload[0], upload[1], timeout)
            workflow[node_id]["inputs"]["image"] = uploaded

    # {
    #   責務: [_upload_image: send one image to the local ComfyUI input directory]
    #   処理: [1: construct bounded multipart request, 2: parse server image name, 3: reject unsafe returned paths]
    #   引数: [self: command, base_url: validated local endpoint, filename: safe image filename, content: image bytes, timeout: request limit]
    #   戻り値: [str: ComfyUI input filename]
    # }
    def _upload_image(self, base_url: str, filename: str, content: bytes, timeout: float) -> str:
        boundary = f"CodexImage{uuid.uuid4().hex}"
        header = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("ascii")
        type_field = (
            f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\ninput'
        ).encode("ascii")
        body = b"".join((header, content, type_field, f"\r\n--{boundary}--\r\n".encode("ascii")))
        request = Request(
            f"{base_url}/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=min(timeout, 60)) as response:
                raw = response.read(MAX_JSON_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise RuntimeError(f"ComfyUI image upload failed: {error}") from error
        if len(raw) > MAX_JSON_BYTES:
            raise RuntimeError("ComfyUI image upload response exceeds 4 MiB")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError("ComfyUI image upload response is invalid JSON") from error
        if not isinstance(payload, Mapping):
            raise RuntimeError("ComfyUI image upload returned an invalid response")
        name = payload.get("name")
        subfolder = payload.get("subfolder", "")
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", name)
            or not isinstance(subfolder, str)
            or (subfolder and any(part in {"", ".", ".."} for part in Path(subfolder).parts))
            or Path(subfolder).is_absolute()
            or "\\" in subfolder
        ):
            raise RuntimeError("ComfyUI returned an unsafe uploaded image path")
        return f"{subfolder}/{name}" if subfolder else name

    # {
    #   責務: [_required_text: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [inputs, key: declared operation inputs]
    #   戻り値: [str: operation result]
    # }

    @staticmethod
    def _required_text(inputs: Mapping[str, Any], key: str) -> str:
        value = inputs.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string")
        return value.strip()

    # {
    #   責務: [_workflow: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [cls, inputs: declared operation inputs]
    #   戻り値: [dict[str, Any]: operation result]
    # }

    @classmethod
    def _workflow(cls, inputs: Mapping[str, Any]) -> dict[str, Any]:
        value = inputs.get("workflow")
        if value is None:
            path_value = cls._required_text(inputs, "workflow_path")
            path = Path(path_value)
            if not path.is_absolute() or path.is_symlink() or not path.is_file():
                raise ValueError(
                    "workflow_path must be an existing absolute file, not a symbolic link"
                )
            raw = path.read_bytes()
            if len(raw) > MAX_WORKFLOW_BYTES:
                raise ValueError("workflow file exceeds 10 MiB")
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                raise ValueError("workflow file is not valid UTF-8 JSON") from None
        if not isinstance(value, Mapping) or not value:
            raise ValueError("workflow must be a non-empty ComfyUI API-format object")
        workflow = copy.deepcopy(dict(value))
        for node_id, node in workflow.items():
            if (
                not isinstance(node_id, str)
                or not isinstance(node, dict)
                or not isinstance(node.get("class_type"), str)
                or not isinstance(node.get("inputs"), dict)
            ):
                raise ValueError(
                    "workflow must contain API-format nodes with class_type and inputs"
                )
        return workflow

    # {
    #   責務: [_apply_prompts: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [workflow, prompt, negative_prompt, inputs: declared operation inputs]
    #   戻り値: [None: operation result]
    # }

    @staticmethod
    def _apply_prompts(
        workflow: dict[str, Any],
        prompt: str,
        negative_prompt: str,
        inputs: Mapping[str, Any],
    ) -> None:
        clip_nodes = {
            node_id: node
            for node_id, node in workflow.items()
            if node["class_type"] == "CLIPTextEncode" and "text" in node["inputs"]
        }
        positive_ids = inputs.get("prompt_node_ids")
        negative_ids = inputs.get("negative_prompt_node_ids")
        if positive_ids is None:
            positive_ids = [
                node_id
                for node_id, node in clip_nodes.items()
                if "negative" not in str(node.get("_meta", {}).get("title", "")).lower()
            ]
        if negative_ids is None:
            negative_ids = [
                node_id
                for node_id, node in clip_nodes.items()
                if "negative" in str(node.get("_meta", {}).get("title", "")).lower()
            ]
            if not negative_ids:
                negative_ids = [node_id for node_id in clip_nodes if node_id not in positive_ids][
                    0:1
                ]
        ComfyUIGenerateCommand._assign_prompt_nodes(clip_nodes, positive_ids, prompt)
        if negative_prompt and negative_ids:
            ComfyUIGenerateCommand._assign_prompt_nodes(clip_nodes, negative_ids, negative_prompt)

    # {
    #   責務: [_assign_prompt_nodes: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [clip_nodes, node_ids, value: declared operation inputs]
    #   戻り値: [None: operation result]
    # }

    @staticmethod
    def _assign_prompt_nodes(clip_nodes: Mapping[str, Any], node_ids: Any, value: str) -> None:
        if not isinstance(node_ids, list) or not all(isinstance(item, str) for item in node_ids):
            raise ValueError(
                "prompt_node_ids and negative_prompt_node_ids must be arrays of node IDs"
            )
        if not node_ids:
            if value:
                raise ValueError("workflow has no matching CLIPTextEncode text input")
            return
        for node_id in node_ids:
            if node_id not in clip_nodes:
                raise ValueError(f"prompt node {node_id} is not a CLIPTextEncode text input")
            clip_nodes[node_id]["inputs"]["text"] = value

    # {
    #   責務: [_apply_overrides: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [workflow, overrides: declared operation inputs]
    #   戻り値: [None: operation result]
    # }

    @staticmethod
    def _apply_overrides(workflow: dict[str, Any], overrides: Any) -> None:
        if not isinstance(overrides, Mapping):
            raise ValueError("overrides must map node IDs to input mappings")
        for node_id, values in overrides.items():
            if node_id not in workflow or not isinstance(values, Mapping):
                raise ValueError(f"invalid workflow override for node {node_id}")
            for field, value in values.items():
                if field not in workflow[node_id]["inputs"]:
                    raise ValueError(f"workflow override input not found: {node_id}.{field}")
                workflow[node_id]["inputs"][field] = value

    # {
    #   責務: [_output_directory: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [value: declared operation inputs]
    #   戻り値: [Path: operation result]
    # }

    @staticmethod
    def _output_directory(value: Any) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("output_dir must be an absolute directory")
        path = Path(value)
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("output_dir must be an absolute directory, not a symbolic link")
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            raise ValueError("output_dir must be a directory")
        return path

    # {
    #   責務: [_validate_timeout: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [value: declared operation inputs]
    #   戻り値: [None: operation result]
    # }

    @staticmethod
    def _validate_timeout(value: Any) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 < value <= MAX_TIMEOUT
        ):
            raise ValueError(f"timeout must be between 0 and {MAX_TIMEOUT} seconds")

    # {
    #   責務: [_validate_api_url: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [value: declared operation inputs]
    #   戻り値: [str: operation result]
    # }

    @staticmethod
    def _validate_api_url(value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("api_url must be a local ComfyUI HTTP(S) base URL")
        parsed = urlsplit(value.strip())
        try:
            port = parsed.port
            host = parsed.hostname or ""
            local_host = host.lower() == "localhost" or (
                bool(host) and ipaddress.ip_address(host).is_loopback
            )
        except ValueError:
            local_host = False
            port = None
        if (
            parsed.scheme not in {"http", "https"}
            or not local_host
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(
                "ComfyUI api_url must be a localhost/loopback base URL without credentials or path"
            )
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("api_url contains an invalid port")
        return f"{parsed.scheme}://{parsed.netloc}"

    # {
    #   責務: [_submit: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [self, base_url, workflow, timeout: declared operation inputs]
    #   戻り値: [str: operation result]
    # }

    def _submit(self, base_url: str, workflow: Mapping[str, Any], timeout: float) -> str:
        data = self._request_json(
            f"{base_url}/prompt", {"prompt": workflow}, timeout, method="POST"
        )
        prompt_id = data.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id.strip():
            raise RuntimeError("ComfyUI did not return a prompt_id")
        return prompt_id

    # {
    #   責務: [_wait_for_image: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [self, base_url, prompt_id, timeout: declared operation inputs]
    #   戻り値: [Mapping[str, str]: operation result]
    # }

    def _wait_for_image(self, base_url: str, prompt_id: str, timeout: float) -> Mapping[str, str]:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            history = self._request_json(f"{base_url}/history/{prompt_id}", None, min(timeout, 30))
            record = history.get(prompt_id)
            if isinstance(record, Mapping):
                status = record.get("status", {})
                if isinstance(status, Mapping) and status.get("status_str") == "error":
                    raise RuntimeError("ComfyUI reported a generation error")
                outputs = record.get("outputs", {})
                if isinstance(outputs, Mapping):
                    for output in outputs.values():
                        images = output.get("images", []) if isinstance(output, Mapping) else []
                        if images:
                            image = images[0]
                            if not isinstance(image, Mapping):
                                raise RuntimeError("ComfyUI returned invalid image metadata")
                            filename = image.get("filename")
                            subfolder = image.get("subfolder", "")
                            image_type = image.get("type", "output")
                            if not isinstance(filename, str) or Path(filename).name != filename:
                                raise RuntimeError("ComfyUI returned an unsafe image filename")
                            if not isinstance(subfolder, str) or not isinstance(image_type, str):
                                raise RuntimeError("ComfyUI returned invalid image metadata")
                            return {
                                "filename": filename,
                                "subfolder": subfolder,
                                "type": image_type,
                            }
            time.sleep(min(self._poll_interval, max(0, deadline - time.monotonic())))
        raise TimeoutError(f"ComfyUI generation did not finish within {timeout} seconds")

    # {
    #   責務: [_download_image: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [self, base_url, image, timeout: declared operation inputs]
    #   戻り値: [bytes: operation result]
    # }

    def _download_image(self, base_url: str, image: Mapping[str, str], timeout: float) -> bytes:
        query = urlencode(image)
        request = Request(f"{base_url}/view?{query}", headers={"Accept": "image/*"})
        try:
            with self._opener.open(request, timeout=min(timeout, 60)) as response:
                data = response.read(MAX_IMAGE_BYTES + 1)
        except HTTPError as error:
            code = error.code
            error.close()
            raise RuntimeError(
                f"ComfyUI image endpoint returned HTTP {code}; redirects are not followed"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError("Could not retrieve generated image from ComfyUI") from None
        if not 0 < len(data) <= MAX_IMAGE_BYTES:
            raise RuntimeError("ComfyUI image response is empty or exceeds 100 MiB")
        return data

    # {
    #   責務: [_request_json: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [self, url, payload, timeout, method: declared operation inputs]
    #   戻り値: [Mapping[str, Any]: operation result]
    # }

    def _request_json(
        self, url: str, payload: Mapping[str, Any] | None, timeout: float, method: str = "GET"
    ) -> Mapping[str, Any]:
        body = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with self._opener.open(request, timeout=min(timeout, 60)) as response:
                raw = response.read(MAX_JSON_BYTES + 1)
        except HTTPError as error:
            code = error.code
            error.close()
            raise RuntimeError(
                f"ComfyUI API returned HTTP {code}; redirects are not followed"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError("Could not reach ComfyUI API; check that it is running") from None
        if len(raw) > MAX_JSON_BYTES:
            raise RuntimeError("ComfyUI JSON response exceeds 4 MiB")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise RuntimeError("ComfyUI returned invalid JSON") from None
        if not isinstance(data, dict):
            raise RuntimeError("ComfyUI response must be a JSON object")
        return data

    # {
    #   責務: [_save_image: ComfyUI workflow command operation]
    #   処理: [1: validate inputs, 2: perform the operation, 3: return a bounded result]
    #   引数: [directory, filename, prompt_id, data: declared operation inputs]
    #   戻り値: [Path: operation result]
    # }

    @staticmethod
    def _save_image(directory: Path, filename: str, prompt_id: str, data: bytes) -> Path:
        suffix = Path(filename).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            raise RuntimeError("ComfyUI returned an unsupported image extension")
        safe_id = "".join(char for char in prompt_id if char.isalnum() or char in "-_")[:80]
        destination = directory / f"{Path(filename).stem}_{safe_id or uuid.uuid4().hex}{suffix}"
        try:
            with destination.open("xb") as target:
                target.write(data)
        except FileExistsError:
            destination = directory / f"{Path(filename).stem}_{uuid.uuid4().hex}{suffix}"
            with destination.open("xb") as target:
                target.write(data)
        return destination
