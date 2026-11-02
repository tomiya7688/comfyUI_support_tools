from __future__ import annotations

import unittest

from tools.quality.comment_coverage import (
    analyze_source,
    is_first_party_python,
    select_paths,
)


# {
#   責務: [CommentCoverageTests: declaration coverage scannerの境界と集計を検証する]
#   フィールド: []
#   処理: [source snippetで適用/未適用/判定不能を確認し、path filterと除外規則を検証する]
# }
class CommentCoverageTests(unittest.TestCase):
    # {
    #   責務: [test_counts_decorated_nested_and_async_declarations: decorator付き/async/nested宣言を数える]
    #   処理: [全てにcommentがあるsourceを解析し、total/appliedが一致することを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_counts_decorated_nested_and_async_declarations(self) -> None:
        source = """# {
# 責務: [Outer: stateを保持する]
# フィールド: []
# }
class Outer:
    # {
    # 責務: [__init__: instanceを初期化する]
    # 処理: [1: valueを保存する]
    # 引数: [value: 初期値]
    # 戻り値: []
    # }
    def __init__(self, value):
        self.value = value

    # {
    # 責務: [build: nested helperを返す]
    # 処理: [1: inner functionを定義する, 2: inner functionを返す]
    # 引数: []
    # 戻り値: [function: inner callable]
    # }
    def build(self):
        # {
        # 責務: [inner: 保存値を返す]
        # 処理: [1: outer stateから値を読む]
        # 引数: []
        # 戻り値: [value: 保存値]
        # }
        def inner():
            return self.value
        return inner

    # {
    # 責務: [asynchronous: async operationを表す]
    # 処理: [1: await可能な値を返す]
    # 引数: []
    # 戻り値: [value: 非同期結果]
    # }
    @staticmethod
    async def asynchronous():
        return None
"""

        result = analyze_source(source, "sample.py")

        self.assertEqual((result.total, result.applied, result.missing, result.undecidable), (5, 5, 0, 0))

    # {
    #   責務: [test_reports_missing_comments: comment未適用宣言をmissingとして報告する]
    #   処理: [commentなしfunction sourceを解析し、適用/未適用数を確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_reports_missing_comments(self) -> None:
        result = analyze_source("def undocumented():\n    return 1\n")

        self.assertEqual((result.total, result.applied, result.missing), (1, 0, 1))

    # {
    #   責務: [test_reports_syntax_errors_as_undecidable: parse不能sourceを判定不能として数える]
    #   処理: [invalid Python sourceを解析し、missingと混同しないことを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_reports_syntax_errors_as_undecidable(self) -> None:
        result = analyze_source("def invalid(:\n")

        self.assertEqual((result.total, result.applied, result.missing, result.undecidable), (0, 0, 0, 1))

    # {
    #   責務: [test_filters_only_selected_paths_and_excludes_generated_data:対象path filterと除外境界を検証する]
    #   処理: [prefix filterを適用し、tool sourceとgenerated/vendor/data pathの扱いを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_filters_only_selected_paths_and_excludes_generated_data(self) -> None:
        paths = ["tools/quality/a.py", "tests/a.py", "doc/generated/a.py"]

        self.assertEqual(select_paths(paths, ["tools/quality"]), ["tools/quality/a.py"])
        self.assertTrue(is_first_party_python("tools/build/build_one_dir.py"))
        self.assertFalse(is_first_party_python("external/app/module.py"))
        self.assertFalse(is_first_party_python("src/project/vendor/module.py"))
        self.assertFalse(is_first_party_python("doc/generated/module.py"))


if __name__ == "__main__":
    unittest.main()
