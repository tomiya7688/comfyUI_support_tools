"""Backend-specific local launch settings behind one immutable value."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# {
#   責務: [BackendLaunchSpec: ローカルbackendの起動に必要な差分設定を保持する]
#   フィールド: [backend: backend識別子, display_name: UI表示名, health_url: 接続確認URL, port: 使用ポート, launch_script_name: 起動スクリプト名, default_flags: 既定起動引数]
# }
@dataclass(frozen=True)
class BackendLaunchSpec:
    backend: str
    display_name: str
    health_url: str
    port: int
    launch_script_name: str
    default_flags: tuple[str, ...]


# {
#   責務: [create_backend_launch_spec: 選択backend用のローカル起動設定を作る]
#   処理: [1: 共通registryからbackend固有factoryを解決する, 2: 設定値を渡して起動specを返す]
#   引数: [backend: 選択中backend, a1111_api_url: A1111 APIのbase URL, comfyui_api_url: ComfyUI APIのbase URL, checkpoints_dir: checkpoint共有ディレクトリ, models_dir: 共有モデルディレクトリ]
#   戻り値: [BackendLaunchSpec: 起動に必要なbackend固有設定]
#   エラー: [ValueError: 未対応backendが渡された場合]
# }
def create_backend_launch_spec(
    backend: str,
    a1111_api_url: str,
    comfyui_api_url: str,
    checkpoints_dir: Path,
    models_dir: Path,
) -> BackendLaunchSpec:
    from .generation_backend_registry import generation_backend_launch_spec_factory

    factory = generation_backend_launch_spec_factory(backend)
    return factory(a1111_api_url, comfyui_api_url, checkpoints_dir, models_dir)


# {
#   責務: [_create_comfyui_launch_spec: ComfyUIの起動と疎通設定を作る]
#   処理: [ComfyUIのhealth URL・port・script・low-VRAM flagsをspecへまとめる]
#   引数: [a1111_api_url: 未使用の共通互換引数, comfyui_api_url: ComfyUI API base URL, checkpoints_dir: 未使用の共通互換引数, models_dir: 未使用の共通互換引数]
#   戻り値: [BackendLaunchSpec: ComfyUIの起動設定]
# }
def _create_comfyui_launch_spec(
    a1111_api_url: str,
    comfyui_api_url: str,
    checkpoints_dir: Path,
    models_dir: Path,
) -> BackendLaunchSpec:
    del a1111_api_url, checkpoints_dir, models_dir
    api_root = comfyui_api_url.strip().rstrip("/")
    return BackendLaunchSpec(
        backend="comfyui",
        display_name="ComfyUI",
        health_url=f"{api_root}/system_stats",
        port=8188,
        launch_script_name="main.py",
        default_flags=(
            "--listen",
            "127.0.0.1",
            "--port",
            "8188",
            "--lowvram",
            "--disable-auto-launch",
        ),
    )


# {
#   責務: [_create_a1111_launch_spec: A1111の起動と疎通設定を作る]
#   処理: [A1111のhealth URL・共有model path・port・script・flagsをspecへまとめる]
#   引数: [a1111_api_url: A1111 API base URL, comfyui_api_url: 未使用の共通互換引数, checkpoints_dir: checkpoint共有ディレクトリ, models_dir: 共有model directory]
#   戻り値: [BackendLaunchSpec: A1111の起動設定]
# }
def _create_a1111_launch_spec(
    a1111_api_url: str,
    comfyui_api_url: str,
    checkpoints_dir: Path,
    models_dir: Path,
) -> BackendLaunchSpec:
    del comfyui_api_url
    api_root = a1111_api_url.strip().rstrip("/")
    if "/sdapi/" in api_root:
        api_root = api_root.split("/sdapi/", 1)[0]
    return BackendLaunchSpec(
        backend="a1111",
        display_name="WebUI1111",
        health_url=f"{api_root}/sdapi/v1/progress",
        port=7860,
        launch_script_name="launch.py",
        default_flags=(
            "--lowvram",
            "--disable-safe-unpickle",
            "--api",
            "--ckpt-dir",
            str(checkpoints_dir),
            "--lora-dir",
            str(models_dir / "Lora"),
            "--vae-dir",
            str(models_dir / "VAE"),
            "--embeddings-dir",
            str(models_dir / "embeddings"),
            "--hypernetwork-dir",
            str(models_dir / "hypernetworks"),
            "--esrgan-models-path",
            str(models_dir / "RealESRGAN"),
            "--gfpgan-models-path",
            str(models_dir / "GFPGAN"),
            "--codeformer-models-path",
            str(models_dir / "Codeformer"),
        ),
    )


# {
#   責務: [create_backend_api_health_checks: 全launch backendの接続確認名とURLを作る]
#   処理: [1: 対応backend IDを列挙する, 2: 各backendの共通launch specから表示名とhealth URLを返す]
#   引数: [a1111_api_url: A1111 API URL, comfyui_api_url: ComfyUI API URL, checkpoints_dir: checkpoint共有ディレクトリ, models_dir: 共有モデルディレクトリ]
#   戻り値: [list[tuple[str, str]]: API表示名と疎通確認URLの組]
# }
def create_backend_api_health_checks(
    a1111_api_url: str,
    comfyui_api_url: str,
    checkpoints_dir: Path,
    models_dir: Path,
) -> list[tuple[str, str]]:
    from .generation_backend_registry import SUPPORTED_LAUNCH_BACKENDS

    checks = []
    for backend in SUPPORTED_LAUNCH_BACKENDS:
        spec = create_backend_launch_spec(
            backend,
            a1111_api_url,
            comfyui_api_url,
            checkpoints_dir,
            models_dir,
        )
        checks.append((f"{spec.display_name} API", spec.health_url))
    return checks
