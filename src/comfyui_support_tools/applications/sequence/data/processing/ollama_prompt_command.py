"""GUI-independent command adapter for Ollama prompt correction."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from scripts.backend.ollama_prompt_corrector import OllamaPromptCorrector


class OllamaPromptCommand:
    """Call Ollama and return both the original and corrected prompt."""

    def __init__(self, timeout: float = 180.0) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self._timeout = timeout
        self._corrector = OllamaPromptCorrector()

    def __call__(self, inputs: Mapping[str, Any], _context: Mapping[str, Any]) -> Mapping[str, Any]:
        prompt = self._required_text(inputs, "prompt")
        model = self._required_text(inputs, "model")
        api_url = self._validate_api_url(inputs.get("api_url", "http://127.0.0.1:11434"))
        payload = self._corrector.payload(model, prompt)
        payload["stream"] = False
        response_data = self._post_json(f"{api_url}/api/generate", payload)
        corrected = response_data.get("response")
        if not isinstance(corrected, str) or not corrected.strip():
            raise RuntimeError("Ollama response did not include a non-empty prompt")
        return {
            "prompt_before": prompt,
            "prompt_after": corrected.strip(),
            "model": model,
            "backend": "ollama",
        }

    @staticmethod
    def _required_text(inputs: Mapping[str, Any], name: str) -> str:
        value = inputs.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _validate_api_url(value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("api_url must be an HTTP(S) base URL")
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("api_url must be an HTTP(S) base URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("api_url must not contain credentials, query, or fragment")
        if parsed.path not in {"", "/"}:
            raise ValueError("api_url must be the Ollama server base URL")
        return f"{parsed.scheme}://{parsed.netloc}"

    def _post_json(self, url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                body = response.read(4 * 1024 * 1024 + 1)
        except HTTPError as error:
            raise RuntimeError(f"Ollama returned HTTP {error.code}") from None
        except (URLError, TimeoutError, OSError) as error:
            raise RuntimeError(f"Could not reach Ollama: {error}") from None
        if len(body) > 4 * 1024 * 1024:
            raise RuntimeError("Ollama response exceeds 4 MiB")
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("Ollama returned invalid JSON") from None
        if not isinstance(data, dict):
            raise RuntimeError("Ollama response must be a JSON object")
        return data
