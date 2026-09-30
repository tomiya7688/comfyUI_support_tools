"""GUI-independent txt2img command for the local WebUI 1111 API."""

from __future__ import annotations

import ipaddress
import math
from collections.abc import Callable, Mapping
from pathlib import Path
import uuid
from typing import Any
from urllib.parse import urlsplit

from scripts.backend.image_generation_backend_factory import create_image_generation_backend
from scripts.backend.text_to_image_request import TextToImageRequest

MAX_IMAGE_BYTES = 100 * 1024 * 1024
MAX_TIMEOUT = 3600


class A1111GenerateCommand:
    """Generate one image with the existing backend adapter and expose its path."""

    def __init__(
        self,
        timeout: float = 1800.0,
        request_post: Callable[..., Any] | None = None,
    ) -> None:
        self._validate_timeout(timeout)
        self._timeout = timeout
        self._request_post = request_post

    def __call__(self, inputs: Mapping[str, Any], _context: Mapping[str, Any]) -> Mapping[str, Any]:
        prompt = self._required_text(inputs, "prompt")
        api_url = self._validate_api_url(inputs.get("api_url", "http://127.0.0.1:7860"))
        timeout = inputs.get("timeout", self._timeout)
        self._validate_timeout(timeout)
        request = self._generation_request(inputs, prompt)
        output_dir = self._output_directory(inputs.get("output_dir"))
        backend = create_image_generation_backend(
            "a1111",
            f"{api_url}/sdapi/v1/txt2img",
            math.ceil(timeout),
            request_post=self._post_function(),
        )
        image_data = backend.generate(request)
        if image_data is None:
            raise RuntimeError("WebUI 1111 did not return a generated image")
        if len(image_data) > MAX_IMAGE_BYTES:
            raise RuntimeError("WebUI 1111 image response exceeds 100 MiB")
        extension = self._image_extension(image_data)
        image_path = self._save_image(output_dir, extension, image_data)
        return {"image": str(image_path), "prompt": prompt, "backend": "a1111"}

    def _post_function(self) -> Callable[..., Any]:
        if self._request_post is not None:
            return self._request_post
        import requests

        return requests.post

    @staticmethod
    def _generation_request(inputs: Mapping[str, Any], prompt: str) -> TextToImageRequest:
        negative = inputs.get("negative_prompt", "")
        if not isinstance(negative, str):
            raise ValueError("negative_prompt must be text")
        checkpoint = A1111GenerateCommand._required_text(inputs, "checkpoint")
        sampler = inputs.get("sampler", "Euler a")
        if not isinstance(sampler, str) or not sampler.strip():
            raise ValueError("sampler must be a non-empty string")
        use_model_vae = inputs.get("use_model_vae", True)
        if not isinstance(use_model_vae, bool):
            raise ValueError("use_model_vae must be a boolean")
        enable_hr = inputs.get("enable_hr", False)
        if not isinstance(enable_hr, bool):
            raise ValueError("enable_hr must be a boolean")
        hr_upscaler = inputs.get("hr_upscaler", "")
        if not isinstance(hr_upscaler, str):
            raise ValueError("hr_upscaler must be text")
        return TextToImageRequest(
            prompt=prompt,
            negative=negative,
            checkpoint=checkpoint,
            steps=A1111GenerateCommand._integer(inputs, "steps", 24, 1, 150),
            cfg=A1111GenerateCommand._number(inputs, "cfg", 6.5, 0, 50),
            sampler=sampler.strip(),
            width=A1111GenerateCommand._multiple_of_eight(inputs, "width", 512),
            height=A1111GenerateCommand._multiple_of_eight(inputs, "height", 512),
            use_model_vae=use_model_vae,
            save_images=False,
            enable_hr=enable_hr,
            hr_scale=A1111GenerateCommand._number(inputs, "hr_scale", 1.5, 1, 4),
            hr_upscaler=hr_upscaler.strip(),
            hr_second_pass_steps=A1111GenerateCommand._integer(inputs, "hr_second_pass_steps", 20, 0, 150),
            denoising_strength=A1111GenerateCommand._number(inputs, "denoising_strength", 0.7, 0, 1),
        )

    @staticmethod
    def _required_text(inputs: Mapping[str, Any], name: str) -> str:
        value = inputs.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _integer(inputs: Mapping[str, Any], name: str, default: int, minimum: int, maximum: int) -> int:
        value = inputs.get(name, default)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
        return value

    @staticmethod
    def _number(inputs: Mapping[str, Any], name: str, default: float, minimum: float, maximum: float) -> float:
        value = inputs.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number between {minimum} and {maximum}")
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be a finite number between {minimum} and {maximum}")
        return float(value)

    @classmethod
    def _multiple_of_eight(cls, inputs: Mapping[str, Any], name: str, default: int) -> int:
        value = cls._integer(inputs, name, default, 64, 4096)
        if value % 8:
            raise ValueError(f"{name} must be a multiple of 8")
        return value

    @staticmethod
    def _validate_timeout(value: Any) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"timeout must be between 0 and {MAX_TIMEOUT} seconds")
        if not 0 < value <= MAX_TIMEOUT:
            raise ValueError(f"timeout must be between 0 and {MAX_TIMEOUT} seconds")

    @staticmethod
    def _validate_api_url(value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("WebUI 1111 api_url must be a localhost/loopback base URL")
        parsed = urlsplit(value.strip())
        try:
            host = parsed.hostname or ""
            local_host = host.lower() == "localhost" or (
                bool(host) and ipaddress.ip_address(host).is_loopback
            )
            port = parsed.port
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
            or parsed.path not in {"", "/", "/sdapi/v1/txt2img"}
        ):
            raise ValueError("WebUI 1111 api_url must be a localhost/loopback base URL")
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("api_url contains an invalid port")
        return f"{parsed.scheme}://{parsed.netloc}"

    @staticmethod
    def _output_directory(value: Any) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("output_dir must be an absolute directory")
        directory = Path(value)
        if not directory.is_absolute() or directory.is_symlink():
            raise ValueError("output_dir must be an absolute directory, not a symbolic link")
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.is_dir():
            raise ValueError("output_dir must be a directory")
        return directory

    @staticmethod
    def _image_extension(data: bytes) -> str:
        if not isinstance(data, bytes) or not data:
            raise RuntimeError("WebUI 1111 returned an empty or invalid image")
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if data.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return ".webp"
        raise RuntimeError("WebUI 1111 returned an unsupported image format")

    @staticmethod
    def _save_image(directory: Path, extension: str, data: bytes) -> Path:
        destination = directory / f"a1111_{uuid.uuid4().hex}{extension}"
        with destination.open("xb") as output:
            output.write(data)
        return destination
