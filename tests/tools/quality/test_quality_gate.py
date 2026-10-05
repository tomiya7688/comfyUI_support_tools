from __future__ import annotations

import unittest

from tools.quality import quality_gate


# {
# 責務: [ QualityGateTests: incremental quality gateの主要ruleを検証する ]
# フィールド: []
# 処理: [ 1: comment ruleを検証する, 2: 例外ruleを検証する, 3: 1000行監査を検証する ]
# }
class QualityGateTests(unittest.TestCase):
    # {
    # 責務: [ test_accepts_json_like_comment_for_new_function: 必須comment付き新規functionを受理する ]
    # 処理: [ 1: sourceを作る, 2: scanする, 3: QUA200がないことを確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_accepts_json_like_comment_for_new_function(self) -> None:
        source = """# {
# 責務: [ work: 値を返す ]
# 処理: [ 1: 値を返す ]
# 引数: []
# 戻り値: [ value: 値 ]
# }
def work():
    return 1
"""
        findings = quality_gate.scan_source("sample.py", source, ((1, 8),))
        self.assertFalse(any(item.rule == "QUA200" for item in findings))

    # {
    # 責務: [ test_rejects_new_bare_except: 新規bare exceptをerrorにする ]
    # 処理: [ 1: bare except sourceを作る, 2: scanする, 3: QUA210を確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_rejects_new_bare_except(self) -> None:
        source = """# {
# 責務: [ work: 例外を処理する ]
# 処理: [ 1: 処理を実行する ]
# 引数: []
# 戻り値: []
# }
def work():
    try:
        return 1
    except:
        return 0
"""
        findings = quality_gate.scan_source("sample.py", source, ((1, 11),))
        self.assertTrue(any(item.rule == "QUA210" and item.severity == "E" for item in findings))

    # {
    # 責務: [ test_over_1000_lines_is_audit_not_error: 1000行超を禁止ではなく監査通知にする ]
    # 処理: [ 1: 1001行sourceを作る, 2: scanする, 3: QUA100の重大度を確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_over_1000_lines_is_audit_not_error(self) -> None:
        source = "\n".join(["value = 1"] * 1001)
        findings = quality_gate.scan_source("large.py", source, ())
        audit = [item for item in findings if item.rule == "QUA100"]
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0].severity, "A")


if __name__ == "__main__":
    unittest.main()
