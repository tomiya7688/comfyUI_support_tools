"""GUI-independent command adapter for Ollama prompt correction."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from scripts.backend.ollama_prompt_corrector import OllamaPromptCorrector
from comfyui_support_tools.shared.python_tls import create_certifi_context


# {
# 責務: [OllamaPromptCommand: Ollama生成APIへprompt correction requestを送り結果を返す]
# フィールド: [_timeout: HTTP timeout, _corrector: Ollama request payload builder]
# }
class OllamaPromptCommand:
    """Call Ollama and return both the original and corrected prompt."""

    # {
    #   責務: [__init__: timeoutを検証してprompt correctorを初期化する]
    #   処理: [正のtimeoutを保存しOllamaPromptCorrectorを生成する]
    #   引数: [self: command instance, timeout: HTTP timeout seconds]
    #   戻り値: [なし]
    #   エラー: [ValueError: timeoutが0以下]
    # }
    def __init__(self, timeout: float = 180.0) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self._timeout = timeout
        self._corrector = OllamaPromptCorrector()

    # {
    #   責務: [__call__: Ollamaへprompt correctionを要求しbefore/afterとbackend情報を返す]
    #   処理: [prompt/model/API URLを検証し、non-streaming requestを送りresponse promptを検証する]
    #   引数: [inputs: prompt/model/API URL mapping, _context: runner context（未使用）]
    #   戻り値: [prompt_before, prompt_after, model, backend=ollama]
    #   エラー: [ValueError: input/URL不正, RuntimeError: responseに有効なpromptがない]
    #   副作用: [Ollama /api/generate endpointへHTTPS対応JSON requestを送る]
    # }
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

    # {
    #   責務: [_required_text: Ollama command inputの必須文字列をtrimして返す]
    #   処理: [keyを読み、non-empty stringであることを確認する]
    #   引数: [inputs: input mapping, name: field key]
    #   戻り値: [trimmed text]
    #   エラー: [ValueError: 値が空またはstring以外]
    # }
    @staticmethod
    def _required_text(inputs: Mapping[str, Any], name: str) -> str:
        value = inputs.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

    # {
    #   責務: [_validate_api_url: Ollama serverのHTTP(S) base URLを検証して正規化する]
    #   処理: [host/pathを要求しcredential/query/fragmentやserver subpathを拒否する]
    #   引数: [value: api_url候補]
    #   戻り値: [schemeとauthorityからなるbase URL]
    #   エラー: [ValueError: URLがHTTP(S) server base URLとして不正]
    # }
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

    # {
    #   責務: [_post_json: 管理対象CA bundleで検証しながらOllamaへ生成要求を送信する]
    #   処理: [1: 要求をencodeする, 2: certifi bundleでHTTPSを検証する, 3: サイズ制限内のJSON応答を解析する]
    #   引数: [url: Ollama endpoint, payload: JSON request mapping]
    #   戻り値: [data: 解析したJSON object]
    #   エラー: [RuntimeError: 接続失敗、応答サイズ超過、またはJSON不正]
    # }
    def _post_json(self, url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(
                request,
                timeout=self._timeout,
                context=create_certifi_context(),
            ) as response:
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
