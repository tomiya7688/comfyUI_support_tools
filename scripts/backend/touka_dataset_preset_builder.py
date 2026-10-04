from __future__ import annotations

from pathlib import Path


# {
# 責務: [ToukaDatasetPresetBuilder: 検証済み参考画像folderをTouka設定値へ変換する]
# フィールド: []
# 処理: [1: 対応画像の有無を検査する, 2: 対象preset用の既定設定辞書を作る]
# }
class ToukaDatasetPresetBuilder:
    """Create a named Touka preset from a validated reference-image dataset."""

    IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

    # {
    # 責務: [image_count: 参考画像directory内の対応画像数を数える]
    # 処理: [1: directoryの存在を検証する, 2: 対応拡張子を再帰列挙する]
    # 引数: [reference_dir: 参考画像directory]
    # 戻り値: [対応画像のfile数]
    # }
    def image_count(self, reference_dir: str) -> int:
        directory = Path(reference_dir)
        if not directory.is_dir():
            raise ValueError(f"参考画像フォルダが見つかりません: {directory}")
        return sum(1 for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in self.IMAGE_SUFFIXES)

    # {
    # 責務: [values: 参考画像datasetからTouka向け初期設定を構成する]
    # 処理: [1: 対応画像が存在するか検証する, 2: 動画・profile・対象・path既定値を返す]
    # 引数: [reference_dir: 参考画像directory, object_preset: 強調対象preset名]
    # 戻り値: [UIへ渡すTouka設定値]
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
