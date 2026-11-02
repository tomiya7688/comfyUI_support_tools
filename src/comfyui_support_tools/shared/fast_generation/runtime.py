"""Best-effort runtime resource probing without requiring a local CUDA install."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event, Lock, Thread
from typing import Any

from .contracts import Quantization, RuntimeResources


# {
#   責務: [probe_comfyui_resources: ComfyUI system_statsからGPU VRAMとhost RAMの容量を読む]
#   処理: [未取得・不正な値をNoneにし, 量子化対応を推測しない]
#   引数: [api_url: ComfyUI root URL, request_get: injectable HTTP GET関数, quantizations: 明示されたruntime対応precision]
#   戻り値: [RuntimeResources: 取得したmemory容量とbackend識別]
# }
def probe_comfyui_resources(
    api_url: str,
    request_get: Callable[..., Any],
    quantizations: frozenset[Quantization] = frozenset(),
) -> RuntimeResources:
    response = request_get(f"{api_url.strip().rstrip('/')}/system_stats", timeout=5)
    response.raise_for_status()
    payload = response.json()
    system = payload.get("system", {}) if isinstance(payload, dict) else {}
    devices = payload.get("devices", []) if isinstance(payload, dict) else []
    device = _select_comfyui_device(devices)
    valid_devices = [item for item in devices if isinstance(item, dict)]
    vram = _bytes_to_gib(device.get("vram_total"))
    ram = _bytes_to_gib(system.get("ram_total"))
    device_type = str(device.get("type", "")).casefold()
    return RuntimeResources(
        gpu_vram_gib=vram,
        system_ram_gib=ram,
        backend="comfyui",
        available_vram_gib=_nonnegative_bytes_to_gib(device.get("vram_free")),
        available_ram_gib=_nonnegative_bytes_to_gib(system.get("ram_free")),
        cuda_available=("cuda" in device_type) if valid_devices else None,
        cuda_version=_optional_text(system.get("cuda_version")),
        device_name=_optional_text(device.get("name")),
        quantizations=quantizations,
    )


# {
#   責務: [_bytes_to_gib: ComfyUI byte countをfinite positive GiBへ変換する]
#   処理: [reject invalid/non-positive values before converting bytes to GiB]
#   引数: [value: ComfyUI system_statsのraw byte field]
#   戻り値: [float | None: 不正値ならunknown]
# }
def _bytes_to_gib(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value) / (1024**3)


# {
#   責務: [_optional_text: nullable runtime metadataを空文字なしで保持する]
#   処理: [trim known text and preserve missing values as None]
#   引数: [value: raw metadata field]
#   戻り値: [str | None: non-empty text or unknown]
# }
def _optional_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


# {
#   責務: [_nonnegative_bytes_to_gib: zero-byte free-memory observationを含むbyte値を変換する]
#   処理: [accept zero and positive byte counts and reject invalid payload values]
#   引数: [value: ComfyUI free memory field]
#   戻り値: [float | None: zero or positive GiB, invalid valueならunknown]
# }
def _nonnegative_bytes_to_gib(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value) / (1024**3)


# {
#   責務: [_select_comfyui_device: system_statsからVRAMを持つCUDA deviceを優先して選択する]
#   処理: [prefer CUDA device and otherwise choose first valid device with memory]
#   引数: [devices: ComfyUI devices payload]
#   戻り値: [dict: first CUDA device, otherwise first device with a VRAM capacity]
# }
def _select_comfyui_device(devices: object) -> dict:
    if not isinstance(devices, list):
        return {}
    valid_devices = [item for item in devices if isinstance(item, dict)]
    return next(
        (item for item in valid_devices if "cuda" in str(item.get("type", "")).casefold()),
        next((item for item in valid_devices if _bytes_to_gib(item.get("vram_total"))), {}),
    )


# {
#   責務: [ComfyUIPeakMemorySampler: generation中にsystem_stats memory usageを周期観測する]
#   フィールド: [api_url, request_get, interval_seconds, sampled_peak_gib]
#   処理: [測定の瞬間値を周期取得し, 欠測時はNoneのまま継続する]
#   注意: [polling peakは瞬間的な最大使用量を見逃す場合がある]
# }
class ComfyUIPeakMemorySampler:
    # {
    #   責務: [__init__: memory polling samplerを設定する]
    #   処理: [create bounded polling state for the ComfyUI stats endpoint]
    #   引数: [api_url: ComfyUI endpoint, request_get: HTTP GET, interval_seconds: polling周期]
    #   戻り値: []
    # }
    def __init__(
        self, api_url: str, request_get: Callable[..., Any], interval_seconds: float = 0.5
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("sampling interval must be positive")
        self._url = f"{api_url.strip().rstrip('/')}/system_stats"
        self._request_get = request_get
        self._interval = interval_seconds
        self._stop = Event()
        self._lock = Lock()
        self._peak_vram_gib: float | None = None
        self._thread: Thread | None = None
        self._last_error: str | None = None

    # {
    #   責務: [start: daemon sampler threadを起動する]
    #   処理: [start one background sampling loop]
    #   引数: [self: memory sampler]
    #   戻り値: []
    # }
    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("memory sampler has already been started")
        self._thread = Thread(target=self._sample_until_stopped, daemon=True)
        self._thread.start()

    # {
    #   責務: [stop: pollingを停止して観測済みpeakを返す]
    #   処理: [signal worker, join briefly, and return the observed peak]
    #   引数: [self: memory sampler]
    #   戻り値: [float | None: sampling interval内に観測したVRAM usage]
    # }
    def stop(self) -> float | None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval * 2))
        with self._lock:
            return self._peak_vram_gib

    # {
    #   責務: [last_error: best-effort samplerで最後に発生した通信問題を公開する]
    #   処理: [return the most recent probe error without masking generation]
    #   引数: [self: memory sampler]
    #   戻り値: [str | None: latest error message or no error]
    # }
    @property
    def last_error(self) -> str | None:
        return self._last_error

    # {
    #   責務: [_sample_until_stopped: memory endpointを周期pollしてVRAM使用量を最大化する]
    #   処理: [poll available VRAM, retain peak used memory, and record request failures]
    #   引数: [self: memory sampler]
    #   戻り値: []
    # }
    def _sample_until_stopped(self) -> None:
        while not self._stop.is_set():
            try:
                response = self._request_get(self._url, timeout=2)
                response.raise_for_status()
                payload = response.json()
                devices = payload.get("devices", []) if isinstance(payload, dict) else []
                device = _select_comfyui_device(devices)
                total = _bytes_to_gib(device.get("vram_total"))
                free = _nonnegative_bytes_to_gib(device.get("vram_free"))
                if total is not None and free is not None and free <= total:
                    used = total - free
                    with self._lock:
                        self._peak_vram_gib = max(self._peak_vram_gib or 0, used)
            except Exception as error:
                self._last_error = str(error)
            self._stop.wait(self._interval)
