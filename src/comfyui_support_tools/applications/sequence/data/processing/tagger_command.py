"""GUI-independent Tagger HTTP command for local sequence steps."""

from __future__ import annotations

import base64
from dataclasses import asdict
from io import BytesIO
import ipaddress
import json
from pathlib import Path
import ssl
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from PIL import Image

from comfyui_support_tools.shared.contracts.tagger_backend import resolve_backend
from comfyui_support_tools.shared.tag_result_normalizer import parse_tag_result

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TIMEOUT = 600


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TaggerCommand:
    """Send one image to a compatible Tagger service running on this machine."""

    def __init__(self, timeout: float = 60.0) -> None:
        self._validate_timeout(timeout)
        self._timeout = timeout
        self._opener = build_opener(
            ProxyHandler({}),
            _NoRedirect(),
            HTTPSHandler(context=ssl.create_default_context()),
        )

    def __call__(self, inputs: Mapping[str, Any], _context: Mapping[str, Any]) -> Mapping[str, Any]:
        image_path = self._required_text(inputs, "image")
        model = self._required_text(inputs, "model")
        backend_id = inputs.get("backend", "auto_http")
        url = self._validate_url(inputs.get("url"), backend_id)
        threshold = self._threshold(inputs.get("threshold", 0.35), "threshold")
        character_threshold = self._threshold(
            inputs.get("character_threshold", 0.85), "character_threshold"
        )
        timeout = inputs.get("timeout", self._timeout)
        self._validate_timeout(timeout)
        image = self._read_image(Path(image_path))
        backend = resolve_backend(backend_id, url)
        payload = {
            "image": base64.b64encode(image).decode("ascii"),
            "model": model,
            "threshold": threshold,
        }
        if backend.supports_character_threshold:
            payload["character_threshold"] = character_threshold
        raw_result = self._post_json(url, payload, timeout)
        result = parse_tag_result(
            raw_result, threshold, character_threshold, backend.id, url, model
        )
        normalized = self._normalized_mapping(result)
        tags = (
            *result.content_tags,
            *result.character_tags,
            *result.copyright_tags,
        )
        tag_text = ", ".join(tags)
        return {
            "backend": result.backend,
            "model": result.model,
            "tags": list(tags),
            "tag_text": tag_text,
            "caption": result.caption,
            "caption_text": result.caption or tag_text,
            "rating": result.rating,
            "metadata": normalized,
            "result": normalized,
        }

    @staticmethod
    def _required_text(inputs: Mapping[str, Any], key: str) -> str:
        value = inputs.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _threshold(value: Any, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
        return float(value)

    @staticmethod
    def _validate_timeout(value: Any) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= MAX_TIMEOUT:
            raise ValueError(f"timeout must be between 0 and {MAX_TIMEOUT} seconds")

    @staticmethod
    def _validate_url(value: Any, backend_id: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("url must be a local HTTP(S) Tagger endpoint URL")
        endpoint = value.strip()
        parsed = urlsplit(endpoint)
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
        ):
            raise ValueError("Tagger URL must target localhost/loopback without credentials, query, or fragment")
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("url contains an invalid port")
        resolve_backend(backend_id, endpoint)
        return endpoint

    @staticmethod
    def _read_image(path: Path) -> bytes:
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError("image must be an existing absolute file, not a symbolic link")
        before = path.stat()
        if not 0 < before.st_size <= MAX_IMAGE_BYTES:
            raise ValueError("image must be between 1 byte and 20 MiB")
        with path.open("rb") as source:
            data = source.read(MAX_IMAGE_BYTES + 1)
        after = path.stat()
        if (
            len(data) != before.st_size
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
        ):
            raise ValueError("image changed while it was being read")
        try:
            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("image exceeds 40 megapixels")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("animated or multi-frame images are not supported")
                image.verify()
        except (ValueError, OSError):
            raise ValueError("image is invalid, too large, or has multiple frames") from None
        return data

    def _post_json(self, url: str, payload: Mapping[str, Any], timeout: float) -> Any:
        request = Request(
            url,
            data=json.dumps(payload, allow_nan=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            code = error.code
            error.close()
            raise RuntimeError(f"Tagger API returned HTTP {code}; redirects are not followed") from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError("Could not reach Tagger API; check the URL and service") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise RuntimeError("Tagger API response exceeds 1 MiB")
        try:
            return json.loads(raw.decode("utf-8"), parse_constant=self._reject_json_constant)
        except (UnicodeError, json.JSONDecodeError, ValueError):
            raise RuntimeError("Tagger API returned invalid JSON") from None

    @staticmethod
    def _reject_json_constant(value: str) -> None:
        raise ValueError(f"Invalid JSON constant: {value}")

    @staticmethod
    def _normalized_mapping(result: Any) -> dict[str, Any]:
        values = asdict(result)
        for key in ("content_tags", "character_tags", "copyright_tags"):
            values[key] = list(values[key])
        for key in ("content_scores", "character_scores", "rating_scores"):
            values[key] = list(values[key])
        return values
