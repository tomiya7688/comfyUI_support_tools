"""Tests for the single-command local PR check selection and safety rules."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.completion import check as check_local


# {
#   責務: [LocalCheckTests: change discovery、test targeting、syntax and zero-test guardsを検証する]
#   フィールド: [temporary repositories]
# }
class LocalCheckTests(unittest.TestCase):
    # {
    #   責務: [test_changed_python_without_explicit_test_falls_back_to_full_suite: source change時にtest対象0件のままPASSしない]
    #   処理: [1: source/test-only changeを選択する 2: related test pathがない場合full discoveryを要求する]
    #   引数: []
    #   戻り値: []
    # }
    def test_changed_python_without_explicit_test_falls_back_to_full_suite(self):
        command = check_local.target_test_command(("src/example.py",), True)
        self.assertIn("discover", command)
        self.assertFalse(check_local.test_count_is_nonzero("Ran 0 tests in 0.0s"))
        self.assertTrue(check_local.test_count_is_nonzero("Ran 2 tests in 0.1s"))

    # {
    #   責務: [test_changed_test_module_is_targeted_and_docs_only_is_skipped: test sourceはmodule単位で実行し非Python変更は理由付きskipにする]
    #   処理: [1: unittest target moduleを選ぶ 2: docs-only caseはNoneを返すことを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_changed_test_module_is_targeted_and_docs_only_is_skipped(self):
        command = check_local.target_test_command(("tests/test_example.py",), True)
        self.assertEqual(command[-1], "tests.test_example")
        self.assertIsNone(check_local.target_test_command(("doc/guide.md",), False))

    # {
    #   責務: [test_discovery_includes_staged_and_untracked_files: change selectionがindexとuntracked fileを含む]
    #   処理: [1: temp git repoを作る 2: staged/untrackedを用意する 3: changed path unionを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_discovery_includes_staged_and_untracked_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True
            )
            subprocess.run(["git", "config", "user.name", "Local Check Test"], cwd=root, check=True)
            (root / "baseline.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "baseline.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "baseline"], cwd=root, check=True)
            (root / "staged.py").write_text("value = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "staged.py"], cwd=root, check=True)
            (root / "untracked.py").write_text("value = 2\n", encoding="utf-8")
            changed = check_local.changed_paths(root, "HEAD")
            self.assertEqual(set(changed), {"staged.py", "untracked.py"})

    # {
    #   責務: [test_python_compile_checks_in_memory_and_reports_syntax_failure: syntax checkがfileを書かず構文異常を検出する]
    #   処理: [1: malformed Pythonを作る 2: compile resultをfailureとすることを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_python_compile_checks_in_memory_and_reports_syntax_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "bad.py").write_text("def broken(:\n", encoding="utf-8")
            result = check_local.compile_changed_python(root, ("bad.py",))
            self.assertEqual(result.status, "FAIL")
            self.assertFalse((root / "__pycache__").exists())

    # {
    #   責務: [test_untracked_trailing_whitespace_is_checked: untracked docs/source trailing whitespaceを検出する]
    #   処理: [1: temporary untracked text fileを作る 2: whitespace resultがfailureになることを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_untracked_trailing_whitespace_is_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
            path = root / "new.md"
            path.write_text("line with space \n", encoding="utf-8")
            result = check_local.check_untracked_whitespace(root, ("new.md",))
            self.assertEqual(result.status, "FAIL")
            self.assertIn("trailing whitespace", result.detail)


if __name__ == "__main__":
    unittest.main()
