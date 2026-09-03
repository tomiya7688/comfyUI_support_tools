from __future__ import annotations

from pathlib import Path


class ToukaDatasetPresetBuilder:
    """Create a named Touka preset from a validated reference-image dataset."""

    IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

    def image_count(self, reference_dir: str) -> int:
        directory = Path(reference_dir)
        if not directory.is_dir():
            raise ValueError(f"参考画像フォルダが見つかりません: {directory}")
        return sum(1 for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in self.IMAGE_SUFFIXES)

    def values(self, reference_dir: str, object_preset: str) -> dict[str, str]:
        if self.image_count(reference_dir) < 1:
            raise ValueError("参考画像フォルダに対応画像がありません")
        return {
            "mode": "video", "profile": "balanced", "object_preset": object_preset,
            "surface_preset": "自動推定", "cpu_cores": "", "preview_seconds": "5",
            "preview_start_seconds": "0", "roi": "", "input_path": "", "output_path": "",
            "reference_path": str(Path(reference_dir)), "surface_reference_path": "",
        }
