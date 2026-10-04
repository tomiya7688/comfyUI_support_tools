#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kadoka Tools entrypoint. Existing UI remains the default; --new-ui is opt-in."""
from pathlib import Path
import sys

SD_ROOT = Path(__file__).resolve().parent
if str(SD_ROOT) not in sys.path:
    sys.path.insert(0, str(SD_ROOT))
# Only this application's own source tree, never another app's Python environment.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(SD_ROOT / "src"))


# {
#   "責務": "従来のタブGUIを選択ツールで開き、Workspaceへ戻る操作を提供する。",
#   "処理": ["tool_idからタブindexを取得する", "TabbedToolsAppを構築してmainloopを実行する", "戻る操作の有無を返す"],
#   "引数": {"tool_id": "起動するツールID"}, "戻り値": "Workspaceへ戻る操作が行われたか"
# }
def _legacy_window(tool_id: str) -> bool:
    """Sequential roots in the SAME Main GUI app; no Python/sub-app subprocess."""
    from tkinter import ttk
    from scripts.app import TabbedToolsApp
    from scripts.tab_catalog import tab_index

    index = tab_index(tool_id) if tool_id else 0
    app = TabbedToolsApp()
    return_to_shell = False

    # {
    #   "責務": "従来GUIを閉じてWorkspaceへ戻る状態を設定する。",
    #   "処理": ["戻り先フラグを設定する", "TabbedToolsAppを閉じる"],
    #   "引数": [], "戻り値": "なし"
    # }
    def go_back() -> None:
        nonlocal return_to_shell
        return_to_shell = True
        app._close()

    button = ttk.Button(app, text="Workspace (新GUI)へ戻る", command=go_back)
    button.pack(side="bottom", fill="x", before=app.winfo_children()[0])
    app.show_tab(index)
    app.mainloop()
    return return_to_shell


# {
#   "責務": "起動引数に応じたGUIまたはsmoke testを実行する。",
#   "処理": ["新旧UIの起動経路を選ぶ", "要求されたimport/shell smoke testを実行する"],
#   "引数": [], "戻り値": "なし"
# }
def _run() -> None:
    if "--shell-smoke-test" in sys.argv or "--new-ui" in sys.argv:
        from comfyui_support_tools.entrypoints.workspace import create_navigation, run_shell, smoke_test
        from comfyui_support_tools.shared.contracts.tool_entry import ToolEntry
        from scripts.tab_catalog import TAB_CATALOG

        tools = tuple(ToolEntry(*entry) for entry in TAB_CATALOG)
        if "--smoke-test" in sys.argv:
            print("KadokaTools workspace import smoke test: OK")
            return
        if "--shell-smoke-test" in sys.argv:
            smoke_test(tools)
            return
        commander = create_navigation(tools)
        while True:
            tool_id = run_shell(commander)
            if tool_id is None or not _legacy_window(tool_id):
                return
    else:
        from scripts.app import main
        if "--smoke-test" in sys.argv:
            print("KadokaTools import smoke test: OK")
            return
        main()


if __name__ == "__main__":
    _run()
