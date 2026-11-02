from __future__ import annotations
import ast
from pathlib import Path

# {
#   責務: [DocstringAuditor: Python module/class/public function docstring omissionsを静的にauditする]
#   処理: [parse source AST and report missing public docstrings]
#   フィールド: [stateless AST audit and Markdown report operations]
# }
class DocstringAuditor:
    """公開Python APIのdocstring不足を静的に報告する。"""
    # {
    #   責務: [audit_file: one Python source fileのmodule/class/public function docstringsをinspectする]
    #   処理: [read and parse source, collect declaration line/name pairs, and return sorted results]
    #   引数: [source]
    #   戻り値: [list[tuple[int, str]]]
    # }
    def audit_file(self, source: Path) -> list[tuple[int, str]]:
        tree=ast.parse(source.read_text(encoding="utf-8"),filename=str(source)); missing=[]
        if not ast.get_docstring(tree): missing.append((1,"module"))
        for node in ast.walk(tree):
            if isinstance(node,ast.ClassDef) and not node.name.startswith("_") and not ast.get_docstring(node): missing.append((node.lineno,f"class {node.name}"))
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and not node.name.startswith("_") and not ast.get_docstring(node): missing.append((node.lineno,f"function {node.name}"))
        return sorted(missing)
    # {
    #   責務: [audit: file or selected recursive/nonrecursive directoryのPython filesをauditする]
    #   処理: [select source paths and map each path to audit results]
    #   引数: [target, recursive]
    #   戻り値: [dict[Path, list[tuple[int, str]]]]
    # }
    def audit(self,target:Path,recursive:bool)->dict[Path,list[tuple[int,str]]]:
        files=[target] if target.is_file() else sorted((target.rglob("*.py") if recursive else target.glob("*.py")),key=lambda path:path.as_posix().casefold())
        return {source:self.audit_file(source) for source in files}
    # {
    #   責務: [write_report: audit findingsをMarkdown reportへwriteする]
    #   処理: [render grouped omissions, create parent directories, write UTF-8 file, and return total findings]
    #   引数: [results, output]
    #   戻り値: [int]
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
