from __future__ import annotations
import ast
from pathlib import Path

# {
# 責務: [DocstringAuditor: Pythonソースのdocstring不足を検出して報告する]
# フィールド: []
# 処理: [1: ファイルまたはディレクトリを走査する, 2: 不足箇所をMarkdownで出力する]
# }
class DocstringAuditor:
    """公開Python APIのdocstring不足を静的に報告する。"""
    # {
    # 責務: [audit_file: 1つのPythonファイル内でdocstringがない宣言を列挙する]
    # 処理: [1: ソースをAST解析する, 2: モジュール・宣言のdocstringを確認する, 3: 不足行と種別を返す]
    # 引数: [source: 検査するPythonファイル]
    # 戻り値: [docstringが不足する行番号と宣言種別の一覧]
    # }
    def audit_file(self, source: Path) -> list[tuple[int, str]]:
        tree=ast.parse(source.read_text(encoding="utf-8"),filename=str(source)); missing=[]
        if not ast.get_docstring(tree): missing.append((1,"module"))
        for node in ast.walk(tree):
            if isinstance(node,ast.ClassDef) and not node.name.startswith("_") and not ast.get_docstring(node): missing.append((node.lineno,f"class {node.name}"))
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and not node.name.startswith("_") and not ast.get_docstring(node): missing.append((node.lineno,f"function {node.name}"))
        return sorted(missing)
    # {
    # 責務: [audit: 対象範囲のPythonファイルを検査する]
    # 処理: [1: 単一ファイルまたは指定深度のファイル一覧を作る, 2: 各ファイルを検査する]
    # 引数: [target: 検査するファイルまたはディレクトリ, recursive: 配下を再帰走査するか]
    # 戻り値: [ファイルごとのdocstring不足箇所]
    # }
    def audit(self,target:Path,recursive:bool)->dict[Path,list[tuple[int,str]]]:
        files=[target] if target.is_file() else sorted((target.rglob("*.py") if recursive else target.glob("*.py")),key=lambda path:path.as_posix().casefold())
        return {source:self.audit_file(source) for source in files}
    # {
    # 責務: [write_report: docstring監査結果をMarkdownレポートへ保存する]
    # 処理: [1: 不足箇所をファイル別に整形する, 2: 出力先へ書き込む]
    # 引数: [results: ファイルごとの監査結果, output: レポート出力先]
    # 戻り値: [docstring不足の総数]
    # }
    def write_report(self,results:dict[Path,list[tuple[int,str]]],output:Path)->int:
        lines=["# Docstring不足レポート",""]; total=0
        for source,items in results.items():
            if not items: continue
            lines.extend([f"## {source}",""])
            lines.extend(f"- {line}行: `{name}`" for line,name in items); lines.append(""); total+=len(items)
        if not total: lines.append("公開APIの不足はありません。")
        output.parent.mkdir(parents=True,exist_ok=True); output.write_text("\n".join(lines)+"\n",encoding="utf-8")
        return total
