from __future__ import annotations
import shutil
from pathlib import Path

# {
# 責務: [DependencyChecker: 実行に必要なパス、コマンド、APIの可用性を確認する]
# フィールド: []
# 処理: [1: 依存種別ごとの検査結果を呼び出し元へ返す]
# }
class DependencyChecker:
    """ローカル依存関係と任意APIの利用可否を検査する。"""
    # {
    # 責務: [check_paths: 指定パスが存在するかを検査する]
    # 処理: [1: 各パスの存在状態を調べる, 2: ラベル別の結果を返す]
    # 引数: [paths: 検査対象名とPathの対応]
    # 戻り値: [各パスの存在状態]
    # }
    def check_paths(self, paths: dict[str, Path]) -> dict[str, bool]:
        return {label: path.exists() for label,path in paths.items()}
    # {
    # 責務: [check_commands: 必須の外部コマンドが実行可能かを調べる]
    # 処理: [1: ffmpegとffprobeをPATHから検索する, 2: コマンド別の結果を返す]
    # 引数: []
    # 戻り値: [各コマンドの利用可否]
    # }
    def check_commands(self) -> dict[str, bool]:
        return {name: shutil.which(name) is not None for name in ("ffmpeg","ffprobe")}
    # {
    # 責務: [check_api: HTTP APIの応答可否と状態を確認する]
    # 処理: [1: requestsが利用可能か確認する, 2: URLへ短いtimeoutでGETし結果を整形する]
    # 引数: [url: 接続確認先URL, requests_module: HTTP GETを提供するモジュール]
    # 戻り値: [接続成功可否とHTTP状態または失敗理由]
    # }
    def check_api(self, url: str, requests_module) -> tuple[bool,str]:
        if requests_module is None: return False,"requests未導入"
        try:
            response=requests_module.get(url,timeout=3); return response.ok,f"HTTP {response.status_code}"
        except Exception as error: return False,type(error).__name__
