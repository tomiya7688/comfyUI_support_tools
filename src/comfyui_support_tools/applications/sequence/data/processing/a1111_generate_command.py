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


# {
# 責務: [A1111GenerateCommand: loopback WebUI txt2img requestを実行し生成画像pathを返す]
# フィールド: [_timeout: request timeout, _request_post: optional injected HTTP POST function]
# }
class A1111GenerateCommand:
    """Generate one image with the existing backend adapter and expose its path."""

    # {
    #   責務: [__init__: timeoutを検証し、任意のHTTP POST transportを保持する]
    #   処理: [timeout range確認後、backendへ使うtimeoutとtransportを保存する]
    #   引数: [self: command instance, timeout: seconds, request_post: optional POST callable]
    #   戻り値: [なし]
    #   エラー: [ValueError: timeoutが数値範囲外]
    # }
    def __init__(
        self,
        timeout: float = 1800.0,
        request_post: Callable[..., Any] | None = None,
    ) -> None:
        self._validate_timeout(timeout)
        self._timeout = timeout
        self._request_post = request_post

    # {
    #   責務: [__call__: WebUI 1111で一枚生成し、検証済み出力pathとbackend情報を返す]
    #   処理: [入力検証、request生成、backend呼出し、bytes上限/画像形式検査、排他的保存を行う]
    #   引数: [inputs: prompt/model/settings/output_dir mapping, _context: runner context（未使用）]
    #   戻り値: [image: file path, prompt: prompt text, backend: a1111]
    #   エラー: [ValueError: request/path設定不正, RuntimeError: backend失敗または画像が不正/大きすぎる]
    #   副作用: [local loopback WebUIへHTTP requestし、出力directoryへ新規画像を書く]
    # }
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

    # {
    #   責務: [_post_function: injected transportかrequests.postを選ぶ]
    #   処理: [test用callbackを優先し、未指定時だけrequestsを遅延importする]
    #   引数: [self: command instance]
    #   戻り値: [callable: backendへ渡すHTTP POST function]
    #   副作用: [callback未指定ならrequests moduleをimportする]
    # }
    def _post_function(self) -> Callable[..., Any]:
        if self._request_post is not None:
            return self._request_post
        import requests

        return requests.post

    # {
    #   責務: [_generation_request: mapping値を検証しA1111向けgeneration requestへ変換する]
    #   処理: [prompt/checkpoint必須、型/数値範囲/寸法multipleを確認し、保存無効のrequestを作る]
    #   引数: [inputs: command inputs, prompt: 検証済みpositive prompt]
    #   戻り値: [TextToImageRequest: backendへ渡すgeneration parameters]
    #   エラー: [ValueError: 欠落または制約違反のparameter]
    # }
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
            hr_second_pass_steps=A1111GenerateCommand._integer(
                inputs, "hr_second_pass_steps", 20, 0, 150
            ),
            denoising_strength=A1111GenerateCommand._number(
                inputs, "denoising_strength", 0.7, 0, 1
            ),
        )

    # {
    #   責務: [_required_text: mapping内の必須文字列をtrimして取得する]
    #   処理: [存在、string型、空でないことを検証する]
    #   引数: [inputs: 入力mapping, name: field key]
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
    #   責務: [_integer: inclusive min/max範囲の整数inputを取得する]
    #   処理: [未指定時defaultを使い、boolを除くint型と上下限を検証する]
    #   引数: [inputs: 入力mapping, name: field key, default: fallback, minimum/maximum: 許容範囲]
    #   戻り値: [validated integer]
    #   エラー: [ValueError: 型または範囲が不正]
    # }
    @staticmethod
    def _integer(
        inputs: Mapping[str, Any], name: str, default: int, minimum: int, maximum: int
    ) -> int:
        value = inputs.get(name, default)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
        return value

    # {
    #   責務: [_number: finite number inputをfloatとして範囲検証する]
    #   処理: [defaultを適用しbool/non-number/non-finiteと境界外値を拒否する]
    #   引数: [inputs: 入力mapping, name: field key, default: fallback, minimum/maximum: 許容範囲]
    #   戻り値: [validated float]
    #   エラー: [ValueError: 型、有限性、範囲が不正]
    # }
    @staticmethod
    def _number(
        inputs: Mapping[str, Any], name: str, default: float, minimum: float, maximum: float
    ) -> float:
        value = inputs.get(name, default)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{name} must be a finite number between {minimum} and {maximum}")
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be a finite number between {minimum} and {maximum}")
        return float(value)

    # {
    #   責務: [_multiple_of_eight: 64から4096内で8の倍数となる寸法を検証する]
    #   処理: [_integerで基本範囲を確認し、8で割り切れない値を拒否する]
    #   引数: [cls: command class, inputs: 入力mapping, name: field key, default: fallback寸法]
    #   戻り値: [validated dimension]
    #   エラー: [ValueError: 整数範囲外または8の倍数でない]
    # }
    @classmethod
    def _multiple_of_eight(cls, inputs: Mapping[str, Any], name: str, default: int) -> int:
        value = cls._integer(inputs, name, default, 64, 4096)
        if value % 8:
            raise ValueError(f"{name} must be a multiple of 8")
        return value

    # {
    #   責務: [_validate_timeout: timeoutを正のfinite数かつMAX_TIMEOUT以下に制限する]
    #   処理: [boolを含む不正型、非finite、0以下、上限超過を拒否する]
    #   引数: [value: timeout候補]
    #   戻り値: [なし]
    #   エラー: [ValueError: timeoutが許容範囲外]
    # }
    @staticmethod
    def _validate_timeout(value: Any) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"timeout must be between 0 and {MAX_TIMEOUT} seconds")
        if not 0 < value <= MAX_TIMEOUT:
            raise ValueError(f"timeout must be between 0 and {MAX_TIMEOUT} seconds")

    # {
    #   責務: [_validate_api_url: A1111 API base URLをHTTP(S) loopback endpointに制限する]
    #   処理: [credential/query/fragmentと想定外pathを拒否し、path無しのbase URLへ正規化する]
    #   引数: [value: api_url候補]
    #   戻り値: [base URL: schemeとauthorityのみ]
    #   エラー: [ValueError: URLがloopback base URL条件を満たさない]
    # }
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

    # {
    #   責務: [_output_directory: 絶対非symlink出力directoryを準備する]
    #   処理: [親directoryを作成し、symlinkでないdirectoryであることを確認する]
    #   引数: [value: output directory path string]
    #   戻り値: [Path: 検証済みdirectory]
    #   エラー: [ValueError: pathが空/相対/symlink/directory以外]
    #   副作用: [directoryが存在しなければ作成する]
    # }
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

    # {
    #   責務: [_image_extension: 生成image bytesから対応する拡張子を判定する]
    #   処理: [PNG/JPEG/WebP signatureを確認し、それ以外を拒否する]
    #   引数: [data: backendから返されたimage bytes]
    #   戻り値: [.png/.jpg/.webp]
    #   エラー: [RuntimeError: 空、非bytes、未対応format]
    # }
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

    # {
    #   責務: [_save_image: UUID名の新規fileとして生成画像を保存する]
    #   処理: [exclusive create modeで既存fileを上書きせずdataを書き込む]
    #   引数: [directory: 検証済みoutput directory, extension: 判定済みsuffix, data: image bytes]
    #   戻り値: [Path: 作成した画像file]
    #   副作用: [directory内へ新しいimage fileを作成する]
    #   エラー: [OSError: fileを作成または書込できない]
    # }
    @staticmethod
    def _save_image(directory: Path, extension: str, data: bytes) -> Path:
        destination = directory / f"a1111_{uuid.uuid4().hex}{extension}"
        with destination.open("xb") as output:
            output.write(data)
        return destination
