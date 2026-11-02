from __future__ import annotations
import threading
from ..context import *
from ..backend.dependency_checker import DependencyChecker
from ..services import LogBox


# {
#   責務: [DependencyStatusTab: local tool dependencies and optional API reachabilityを表示するtabを提供する]
#   処理: [create API check control, background action, and log view]
#   フィールド: [api_check, logbox]
# }
class DependencyStatusTab(ttk.Frame):
    # {
    #   責務: [__init__: API-check toggleとtab widgetsを初期化する]
    #   処理: [initialize Tk state and build controls]
    #   引数: [master]
    #   戻り値: [処理結果]
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.api_check = tk.BooleanVar(value=False)
        self._build()

    # {
    #   責務: [_build: dependency status controls and log areaを構築する]
    #   処理: [create API option, start button, and output widget]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def _build(self):
        ttk.Label(self, text="依存状態（確認のみ。未導入でも他タブは利用できます）").pack(
            anchor="w"
        )
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=6)
        ttk.Checkbutton(buttons, text="ローカルAPIの疎通も確認", variable=self.api_check).pack(
            side="left"
        )
        ttk.Button(buttons, text="状態を確認", command=self.start).pack(side="left", padx=8)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)

    # {
    #   責務: [start: dependency auditをdaemon worker threadで開始する]
    #   処理: [spawn run callback without blocking Tk event loop]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    # {
    #   責務: [run: 設定済みツール・コマンド・選択APIの疎通状態を記録する]
    #   処理: [1: ローカル依存を確認する, 2: 要求時にgeneration catalogとbackend launch契約からAPI endpointを得て疎通する]
    #   引数: [self: DependencyStatusTab instance]
    #   戻り値: []
    # }
    def run(self):
        checker = DependencyChecker()
        paths = {
            "WebUI1111": A1111_DIR,
            "ComfyUI": COMFYUI_DIR,
            "PixAI Tagger": PIXAI_TAGGER_DIR,
            "共有models": MODELS_DIR,
            "wildcards": WILDCARDS_DIR,
        }
        for label, ok in checker.check_paths(paths).items():
            self.logbox.log(
                ("✅ " if ok else "⚠️ ") + label + (" 利用可能" if ok else " 見つかりません")
            )
        for label, ok in checker.check_commands().items():
            self.logbox.log(
                ("✅ " if ok else "⚠️ ") + label + (" 利用可能" if ok else " PATHにありません")
            )
        if self.api_check.get():
            api_checks = configured_backend_api_health_checks()
            api_checks.append(("PixAI API", PIXAI_TAGGER_API_URL))
            for label, url in api_checks:
                ok, detail = checker.check_api(url, requests)
                self.logbox.log(("✅ " if ok else "⚠️ ") + f"{label}: {detail}")
