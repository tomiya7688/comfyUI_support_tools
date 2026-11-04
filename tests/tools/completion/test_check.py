import sys
import unittest
from pathlib import Path
from unittest import mock

MODULE_DIR = Path(__file__).parents[3] / "tools" / "completion"
sys.path.insert(0, str(MODULE_DIR))

import check  # noqa: E402


# {
# 責務: [ LocalCheckTests: 標準ローカル検査入口の回帰を確認する ]
# フィールド: []
# 処理: [ 1: 共有gateの起動を確認する, 2: 失敗statusの伝播を確認する ]
# }
class LocalCheckTests(unittest.TestCase):
    # {
    # 責務: [ test_runs_shared_gate_and_reports_no_tests_for_docs_only_change: docs-only時も共有gateを実行する ]
    # 処理: [ 1: gateを成功にmockする, 2: skip-tests指定を確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_runs_shared_gate_and_reports_no_tests_for_docs_only_change(self):
        with (
            mock.patch.object(check, "_changed_paths", return_value=()),
            mock.patch.object(check, "_test_modules", return_value=()),
            mock.patch.object(check.completion_gate, "main", return_value=0) as gate,
        ):
            self.assertEqual(check.main(), 0)
        gate.assert_called_once_with(["--skip-tests"])

    # {
    # 責務: [ test_propagates_shared_gate_failure: 共有gate失敗を呼び出し元へ返す ]
    # 処理: [ 1: gateを失敗にmockする, 2: failure statusを確認する ]
    # 引数: []
    # 戻り値: []
    # }
    def test_propagates_shared_gate_failure(self):
        with (
            mock.patch.object(check, "_changed_paths", return_value=()),
            mock.patch.object(check.completion_gate, "main", return_value=1),
        ):
            self.assertEqual(check.main(), 1)


if __name__ == "__main__":
    unittest.main()
