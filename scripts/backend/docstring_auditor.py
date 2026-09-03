from __future__ import annotations
import ast
from pathlib import Path

class DocstringAuditor:
    """公開Python APIのdocstring不足を静的に報告する。"""
    def audit_file(self, source: Path) -> list[tuple[int, str]]:
        tree=ast.parse(source.read_text(encoding="utf-8"),filename=str(source)); missing=[]
        if not ast.get_docstring(tree): missing.append((1,"module"))
        for node in ast.walk(tree):
            if isinstance(node,ast.ClassDef) and not node.name.startswith("_") and not ast.get_docstring(node): missing.append((node.lineno,f"class {node.name}"))
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and not node.name.startswith("_") and not ast.get_docstring(node): missing.append((node.lineno,f"function {node.name}"))
        return sorted(missing)
    def audit(self,target:Path,recursive:bool)->dict[Path,list[tuple[int,str]]]:
        files=[target] if target.is_file() else sorted((target.rglob("*.py") if recursive else target.glob("*.py")),key=lambda path:path.as_posix().casefold())
        return {source:self.audit_file(source) for source in files}
    def write_report(self,results:dict[Path,list[tuple[int,str]]],output:Path)->int:
        lines=["# Docstring不足レポート",""]; total=0
        for source,items in results.items():
            if not items: continue
            lines.extend([f"## {source}",""])
            lines.extend(f"- {line}行: `{name}`" for line,name in items); lines.append(""); total+=len(items)
        if not total: lines.append("公開APIの不足はありません。")
        output.parent.mkdir(parents=True,exist_ok=True); output.write_text("\n".join(lines)+"\n",encoding="utf-8")
        return total
