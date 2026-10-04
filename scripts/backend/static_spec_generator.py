from __future__ import annotations
import ast
from pathlib import Path

# {
# 責務: [StaticSpecGenerator: Python ASTから静的なMarkdown API仕様を生成する]
# フィールド: []
# 処理: [1: module/class/function概要を抽出する, 2: 1ファイルまたは複数ファイルの文書を出力する]
# }
class StaticSpecGenerator:
    """Pythonソースを実行せずASTからMarkdown仕様書を作る。"""
    # {
    # 責務: [generate: 1つのPythonファイルをMarkdown仕様へ変換する]
    # 処理: [1: ASTを解析する, 2: module・class・function情報を収集する, 3: Markdownを組み立てる]
    # 引数: [source: 解析対象のPythonファイル]
    # 戻り値: [生成したMarkdown本文]
    # }
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
    # {
    # 責務: [_function_line: function AST nodeを仕様表の1行へ整形する]
    # 処理: [1: async区分、引数、戻り値注釈を取得する, 2: Markdown行を返す]
    # 引数: [node: 関数またはメソッドのAST node]
    # 戻り値: [function宣言を表すMarkdown行]
    # }
    def _function_line(self,node):
        prefix="async " if isinstance(node,ast.AsyncFunctionDef) else ""; args=ast.unparse(node.args); result=ast.unparse(node.returns) if node.returns else ""
        doc=ast.get_docstring(node); detail=f" — {doc.splitlines()[0]}" if doc else ""
        return f"- `{prefix}{node.name}({args})`"+(f" -> `{result}`" if result else "")+detail
    # {
    # 責務: [generate_files: 対象Pythonファイルを走査し仕様Markdownを書き出す]
    # 処理: [1: 対象ファイルを収集する, 2: 各ファイル仕様を生成する, 3: 出力へ保存する]
    # 引数: [target: 入力ファイルまたはdirectory, output: Markdown出力先,
    # recursive: directoryを再帰走査するか]
    # 戻り値: [仕様生成したPythonファイル数]
    # }
    def generate_files(self,target:Path,output:Path,recursive:bool)->int:
        files=[target] if target.is_file() else sorted((target.rglob("*.py") if recursive else target.glob("*.py")),key=lambda p:p.as_posix().casefold())
        if not files: raise ValueError("Pythonファイルが見つかりません")
        chunks=[]
        for source in files:
            chunks.append(self.generate(source)); chunks.append("")
        output.parent.mkdir(parents=True,exist_ok=True); output.write_text("\n".join(chunks),encoding="utf-8")
        return len(files)
