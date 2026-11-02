from __future__ import annotations

from pathlib import Path


# {
#   責務: [ToukaDatasetPresetBuilder: validated reference image dataset向けTouka preset valuesを作る]
#   処理: [supported image filesをcountし、generation form defaultsをreturnする]
#   フィールド: [IMAGE_SUFFIXES]
# }
class ToukaDatasetPresetBuilder:
    """Create a named Touka preset from a validated reference-image dataset."""

    IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

    # {
    #   責務: [image_count: reference directory内のsupported image filesを再帰的にcountする]
    #   処理: [directoryをvalidateし、suffix allowlistに合うfilesを集計する]
    #   引数: [reference_dir]
    #   戻り値: [int]
    # }
    def image_count(self, reference_dir: str) -> int:
        directory = Path(reference_dir)
        if not directory.is_dir():
            raise ValueError(f"参考画像フォルダが見つかりません: {directory}")
        return sum(1 for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in self.IMAGE_SUFFIXES)

    # {
    #   責務: [values: non-empty reference dataset用のTouka configuration valuesをbuildする]
    #   処理: [image countをvalidateし、object preset and reference pathをdefaultsへ設定する]
    #   引数: [reference_dir, object_preset]
    #   戻り値: [dict[str, str]]
    # }
    def values(self, reference_dir: str, object_preset: str) -> dict[str, str]:
        if self.image_count(reference_dir) < 1:
            raise ValueError("参考画像フォルダに対応画像がありません")
        return {
            "mode": "video", "profile": "balanced", "object_preset": object_preset,
            "surface_preset": "自動推定", "cpu_cores": "", "preview_seconds": "5",
            "preview_start_seconds": "0", "roi": "", "input_path": "", "output_path": "",
            "reference_path": str(Path(reference_dir)), "surface_reference_path": "",
        }
