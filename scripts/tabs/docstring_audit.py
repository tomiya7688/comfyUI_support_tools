from __future__ import annotations
import threading
from pathlib import Path
from ..context import *
from ..backend.docstring_auditor import DocstringAuditor
from ..services import LogBox, LabeledPathRow
from ..widgets.preset_store import PresetStore

# {
#   "責務": "Python宣言のdocstring不足を検査してMarkdown報告するUI。",
#   "フィールド": ["target: 検査対象", "output: レポート先", "recursive: 子フォルダ検査設定", "preset_name: 選択プリセット名", "preset_store: プリセット保存先", "logbox: 実行結果表示"]
# }
class DocstringAuditTab(ttk.Frame):
    # {
    #   "責務": "監査画面の状態を初期化してウィジェットを構築する。",
    #   "処理": ["対象・出力先・再帰設定とプリセット保存先を初期化する", "入力欄と操作ボタンとログ領域を配置する"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self,master):
        super().__init__(master,padding=10); self.target=tk.StringVar(); self.output=tk.StringVar(value=str(USER_DATA_DIR/"output"/"docstring_audit.md")); self.recursive=tk.BooleanVar(value=True); self.preset_name=tk.StringVar(); self.preset_store=PresetStore("docstring_audit"); self._build()
    # {
    #   "責務": "監査対象・出力先・再帰設定の入力UIを組み立てる。",
    #   "処理": ["ファイル・フォルダ選択欄を配置する", "レポート先、再帰設定、開始操作、ログ領域を配置する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _build(self):
        row=ttk.Frame(self); row.pack(fill="x",pady=3); ttk.Label(row,text="Pythonファイル / フォルダ",width=22).pack(side="left"); ttk.Entry(row,textvariable=self.target).pack(side="left",fill="x",expand=True); ttk.Button(row,text="ファイル",command=lambda:self._choose(False)).pack(side="left",padx=3); ttk.Button(row,text="フォルダ",command=lambda:self._choose(True)).pack(side="left")
        LabeledPathRow(self,"レポートMarkdown",self.output,mode="save",filetypes=[("Markdown","*.md")]).pack(fill="x",pady=3); ttk.Checkbutton(self,text="サブフォルダも検査",variable=self.recursive).pack(anchor="w")
        buttons=ttk.Frame(self); buttons.pack(fill="x",pady=6); ttk.Button(buttons,text="検査開始",command=self.start).pack(side="left"); self.logbox=LogBox(self); self.logbox.pack(fill="both",expand=True)
    # {
    #   "責務": "ファイルまたはフォルダの選択dialogを開き監査対象を更新する。",
    #   "処理": ["folderに応じたdialogを開く", "選択されたパスがある場合だけtargetへ設定する"],
    #   "引数": {"folder": "Trueならフォルダ、FalseならPythonファイルを選択"},
    #   "戻り値": []
    # }
    def _choose(self,folder):
        path=filedialog.askdirectory() if folder else filedialog.askopenfilename(filetypes=[("Python","*.py")])
        if path:self.target.set(path)
    # {
    #   "責務": "docstring監査をdaemon threadで開始する。",
    #   "処理": ["runをworker threadで起動する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def start(self): threading.Thread(target=self.run,daemon=True).start()
    # {
    #   "責務": "選択範囲のdocstringを監査しMarkdownレポートを出力する。",
    #   "処理": ["対象と出力先を検証する", "DocstringAuditorで走査・報告書保存を行い件数をログへ出す", "失敗を例外メッセージとしてログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run(self):
        try:
            target,output=Path(self.target.get().strip()),Path(self.output.get().strip())
            if not(target.is_file() or target.is_dir()): raise ValueError(f"対象がありません: {target}")
            auditor=DocstringAuditor(); results=auditor.audit(target,self.recursive.get()); count=auditor.write_report(results,output); self.logbox.log(f"検査完了: {len(results)}ファイル / 不足 {count}件 / {output}")
        except Exception as error:self.logbox.log(f"検査エラー: {error}")
