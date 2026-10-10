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
#   処理: [1: backendを検証する, 2: backend固有のURL・script・flagをまとめる, 3: 不変な設定を返す]
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
    if backend == "comfyui":
        api_root = comfyui_api_url.strip().rstrip("/")
        return BackendLaunchSpec(
            backend=backend,
            display_name="ComfyUI",
            health_url=f"{api_root}/system_stats",
            port=8188,
            launch_script_name="main.py",
            default_flags=("--listen", "127.0.0.1", "--port", "8188", "--lowvram", "--disable-auto-launch"),
        )
    if backend == "a1111":
        api_root = a1111_api_url.strip().rstrip("/")
        if "/sdapi/" in api_root:
            api_root = api_root.split("/sdapi/", 1)[0]
        return BackendLaunchSpec(
            backend=backend,
            display_name="WebUI1111",
            health_url=f"{api_root}/sdapi/v1/progress",
            port=7860,
            launch_script_name="launch.py",
            default_flags=(
                "--lowvram", "--disable-safe-unpickle", "--api",
                "--ckpt-dir", str(checkpoints_dir),
                "--lora-dir", str(models_dir / "Lora"),
                "--vae-dir", str(models_dir / "VAE"),
                "--embeddings-dir", str(models_dir / "embeddings"),
                "--hypernetwork-dir", str(models_dir / "hypernetworks"),
                "--esrgan-models-path", str(models_dir / "RealESRGAN"),
                "--gfpgan-models-path", str(models_dir / "GFPGAN"),
                "--codeformer-models-path", str(models_dir / "Codeformer"),
            ),
        )
    raise ValueError(f"Unsupported launch backend: {backend}")
