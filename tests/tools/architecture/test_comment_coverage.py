from pathlib import Path
import sys
import unittest
from unittest import mock

MODULE_DIR = Path(__file__).parents[3] / "tools" / "architecture"
sys.path.insert(0, str(MODULE_DIR))

import comment_coverage  # noqa: E402


# {
# 責務: [CommentCoverageTests: コメント検査器の判定と対象範囲を検証する]
# フィールド: []
# }
class CommentCoverageTests(unittest.TestCase):
    # {
    # 責務: [test_covered_class_function_and_method_include_decorators: decorator付き宣言のコメントを認識する]
    # 処理: [1: クラスとdecorator付きメソッドの例を走査する,
    # 2: 3宣言すべてがcoveredになることを確認する]
    # 引数: [self: unittestのテストインスタンス]
    # 戻り値: []
    # }
    def test_covered_class_function_and_method_include_decorators(self):
        source = """# {
# 責務: [Item: 1件を表す]
# フィールド: [name: 表示名]
# }
class Item:
    # {
    # 責務: [build: Itemを作る]
    # 処理: [1: 値を返す]
    # 引数: []
    # 戻り値: [item: Item]
    # }
    @staticmethod
    def build():
        return Item()

    # {
    # 責務: [label: 表示用ラベルを返す]
    # 処理: [1: nameを返す]
    # 引数: []
    # 戻り値: [label: 文字列]
    # }
    @property
    def label(self):
        return "item"
"""
        declarations, errors = comment_coverage.scan_source("sample.py", source)
        self.assertEqual(errors, ())
        self.assertEqual([item[4] for item in declarations], ["covered"] * 3)
        self.assertEqual([item[1] for item in declarations], [5, 12, 22])

    # {
    # 責務: [test_no_argument_no_return_and_abstract_declarations_are_applicable: 抽象宣言も引数有無によらず対象となることを検証する]
    # 処理: [1: 無引数の抽象関数を解析する, 2: クラスと関数が対象として数えられることを確認する]
    # 引数: [self: unittestのテストインスタンス]
    # 戻り値: []
    # }
    def test_no_argument_no_return_and_abstract_declarations_are_applicable(self):
        source = """from abc import ABC, abstractmethod

class Base(ABC):
    @abstractmethod
    def run(self):
        ...
"""
        declarations, errors = comment_coverage.scan_source("sample.py", source)
        self.assertEqual(errors, ())
        self.assertEqual([item[4] for item in declarations], ["uncovered", "uncovered"])

    # {
    # 責務: [test_async_and_nested_declarations_are_scanned: 非同期関数とネスト関数を個別の宣言として数える]
    # 処理: [1: 2階層の宣言を解析する, 2: 両方がcoverage対象であることを確認する]
    # 引数: [self: unittestのテストインスタンス]
    # 戻り値: []
    # }
    def test_async_and_nested_declarations_are_scanned(self):
        source = """# {
# 責務: [outer: 外側処理]
# 処理: [1: 内部関数を定義する]
# 引数: []
# 戻り値: []
# }
async def outer():
    # {
    # 責務: [inner: 内部処理]
    # 処理: [1: 値を返す]
    # 引数: []
    # 戻り値: [値]
    # }
    def inner():
        return 1
    return inner()
"""
        declarations, errors = comment_coverage.scan_source("sample.py", source)
        self.assertEqual(errors, ())
        self.assertEqual([item[2] for item in declarations], ["outer", "inner"])
        self.assertEqual([item[4] for item in declarations], ["covered", "covered"])

    # {
    # 責務: [test_comments_inside_body_do_not_cover_declaration: 関数内部コメントを宣言コメントと誤認しない]
    # 処理: [1: 関数本体のJSON-likeコメントを解析する,
    # 2: 宣言は未記載と判定されることを確認する]
    # 引数: [self: unittestのテストインスタンス]
    # 戻り値: []
    # }
    def test_comments_inside_body_do_not_cover_declaration(self):
        source = """def run():
    # {
    # 責務: [run: 実行する]
    # }
    return None
"""
        declarations, errors = comment_coverage.scan_source("sample.py", source)
        self.assertEqual(errors, ())
        self.assertEqual(declarations[0][4], "uncovered")

    # {
    # 責務: [test_malformed_json_like_candidate_is_unrecognized_not_covered: 壊れた構造をcovered扱いしない]
    # 処理: [1: 括弧不整合の候補を解析する,
    # 2: unrecognized判定を確認する]
    # 引数: [self: unittestのテストインスタンス]
    # 戻り値: []
    # }
    def test_malformed_json_like_candidate_is_unrecognized_not_covered(self):
        source = """# {
# 責務: [broken
# }
def run():
    return None
"""
        declarations, errors = comment_coverage.scan_source("sample.py", source)
        self.assertEqual(errors, ())
        self.assertEqual(declarations[0][4], "unrecognized")

    # {
    # 責務: [test_ordinary_comments_do_not_count_as_structured_coverage: 通常コメントを構造化コメントと区別する]
    # 処理: [1: 通常コメント付き関数を解析する,
    # 2: 未記載判定を確認する]
    # 引数: [self: unittestのテストインスタンス]
    # 戻り値: []
    # }
    def test_ordinary_comments_do_not_count_as_structured_coverage(self):
        source = """# run the action
def run():
    return None
"""
        declarations, errors = comment_coverage.scan_source("sample.py", source)
        self.assertEqual(errors, ())
        self.assertEqual(declarations[0][4], "uncovered")

    # {
    # 責務: [test_syntax_errors_are_reported_as_unrecognized_source: Python構文エラーを未認識ソースとして検出する]
    # 処理: [1: 不正ソースを解析する,
    # 2: エラーパスが記録されることを確認する]
    # 引数: [self: unittestのテストインスタンス]
    # 戻り値: []
    # }
    # {
    # 責務: [test_natural_language_apostrophe_is_not_treated_as_quote: 自然言語のアポストロフィを構文引用符と誤認しない]
    # 処理: [1: 所有格を含む有効ブロックを解析する, 2: covered判定を確認する]
    # 引数: [self: unittestのテストインスタンス]
    # 戻り値: []
    # }
    def test_natural_language_apostrophe_is_not_treated_as_quote(self):
        source = """# {
# Responsibility: [run: user's dataを処理する]
# Action: [1: 値を確認する]
# Param: []
# Return: []
# }
def run():
    return None
"""
        declarations, errors = comment_coverage.scan_source("sample.py", source)
        self.assertEqual(errors, ())
        self.assertEqual(declarations[0][4], "covered")

    # {
    # 責務: [test_syntax_errors_are_reported_as_unrecognized_source: Python構文エラーを未認識ソースとして検出する]
    # 処理: [1: 不正ソースを解析する, 2: エラーパスが記録されることを確認する]
    # 引数: [self: unittestのテストインスタンス]
    # 戻り値: []
    # }
    def test_syntax_errors_are_reported_as_unrecognized_source(self):
        declarations, errors = comment_coverage.scan_source("bad.py", "def broken(:\n")
        self.assertEqual(declarations, ())
        self.assertEqual(errors[0][0], "bad.py")

    # {
    # 責務: [test_scope_excludes_external_generated_and_user_data: 外部・生成物・利用者データを除外する]
    # 処理: [1: first-party Pythonを対象として確認する,
    # 2: 除外パスが対象外であることを確認する]
    # 引数: [self: unittestのテストインスタンス]
    # 戻り値: []
    # }
    def test_scope_excludes_external_generated_and_user_data(self):
        self.assertTrue(comment_coverage.is_in_scope("scripts/tabs/tool.py"))
        self.assertTrue(comment_coverage.is_in_scope("tests/test_tool.py"))
        self.assertTrue(comment_coverage.is_in_scope("tools/build/build_one_dir.py"))
        for path in (
            "external/vendor/tool.py",
            "user_data/input/tool.py",
            "models/checkpoints/tool.py",
            "doc/generated/tool.py",
            "build/temp.py",
            "dist/generated.py",
            "generated/schema_pb2.py",
            "../scripts/outside.py",
            ".cache/generated.py",
        ):
            with self.subTest(path=path):
                self.assertFalse(comment_coverage.is_in_scope(path))

    # {
    # 責務: [test_baseline_rejects_new_uncovered_declarations_per_file: ファイル単位で新しい未記載を拒否する]
    # 処理: [1: 未記載関数を解析する, 2: 許容0で違反になることを確認する,
    # 3: 許容1で通ることを確認する]
    # 引数: [self: unittestのテストインスタンス]
    # 戻り値: []
    # }
    def test_baseline_rejects_new_uncovered_declarations_per_file(self):
        declarations, errors = comment_coverage.scan_source(
            "scripts/example.py", "def one():\n    pass\n"
        )
        result = (declarations, errors)
        self.assertEqual(
            comment_coverage.find_budget_violations(result, {"scripts/example.py": 0})[0][1],
            1,
        )
        self.assertEqual(
            comment_coverage.find_budget_violations(result, {"scripts/example.py": 1}), ()
        )
        removed = ((), ())
        self.assertEqual(
            comment_coverage.find_budget_violations(removed, {"scripts/example.py": 1}),
            (("scripts/example.py", 0, 1),),
        )

    # {
    # 責務: [test_baseline_rejects_non_object_json: 配列などJSON object以外のbaselineを明瞭に拒否する]
    # 処理: [1: JSON読み込みを配列で差し替える, 2: 設定エラーがValueErrorになることを確認する]
    # 引数: [self: unittestのテストインスタンス]
    # 戻り値: []
    # }
    def test_baseline_rejects_non_object_json(self):
        with mock.patch.object(Path, "read_text", return_value="[]"):
            with self.assertRaisesRegex(ValueError, "JSON object"):
                comment_coverage.load_baseline(Path("invalid.json"))


if __name__ == "__main__":
    unittest.main()
