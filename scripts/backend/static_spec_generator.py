from __future__ import annotations
import ast
from pathlib import Path

class StaticSpecGenerator:
    """Pythonソースを実行せずASTからMarkdown仕様書を作る。"""
    def generate(self, source: Path) -> str:
        tree=ast.parse(source.read_text(encoding="utf-8"),filename=str(source)); lines=[f"# {source.name}",""]
        module_doc=ast.get_docstring(tree)
        if module_doc: lines.extend([module_doc.splitlines()[0],""])
        functions=[node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))]
        classes=[node for node in tree.body if isinstance(node,ast.ClassDef)]
        if functions: lines.extend(["## モジュール関数",""]+[self._function_line(node) for node in functions]+[""])
        for cls in classes:
            bases=", ".join(ast.unparse(base) for base in cls.bases)
            lines.extend([f"## class {cls.name}"+(f"({bases})" if bases else ""),""])
            doc=ast.get_docstring(cls)
            if doc: lines.extend([doc.splitlines()[0],""])
            methods=[node for node in cls.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))]
            if methods: lines.extend(["### メソッド",""]+[self._function_line(node) for node in methods]+[""])
        return "\n".join(lines).rstrip()+"\n"
    def _function_line(self,node):
        prefix="async " if isinstance(node,ast.AsyncFunctionDef) else ""; args=ast.unparse(node.args); result=ast.unparse(node.returns) if node.returns else ""
        doc=ast.get_docstring(node); detail=f" — {doc.splitlines()[0]}" if doc else ""
        return f"- `{prefix}{node.name}({args})`"+(f" -> `{result}`" if result else "")+detail
    def generate_files(self,target:Path,output:Path,recursive:bool)->int:
        files=[target] if target.is_file() else sorted((target.rglob("*.py") if recursive else target.glob("*.py")),key=lambda p:p.as_posix().casefold())
        if not files: raise ValueError("Pythonファイルが見つかりません")
        chunks=[]
        for source in files:
            chunks.append(self.generate(source)); chunks.append("")
        output.parent.mkdir(parents=True,exist_ok=True); output.write_text("\n".join(chunks),encoding="utf-8")
        return len(files)
