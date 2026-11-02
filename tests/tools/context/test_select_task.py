import unittest
from hashlib import sha256
from io import BytesIO
import ssl
from unittest.mock import patch

from tools.context import select_task
from tools.security.check_python_ca import AFFECTED_CERTIFICATES


# {
#   責務: [SelectTaskTests: related test fixtures and cases for SelectTask behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class SelectTaskTests(unittest.TestCase):
    # {
    #   責務: [issue: builds an issue fixture with the selected number and markdown sections]
    #   処理: [1: build the Issue object with the supplied number/title/body fields]
    #   引数: [number: issue number (int), title: title passed to this helper (str), body: issue markdown body (str)]
    #   戻り値: [result: select_task.Issue built or selected by this helper]
    # }
    def issue(self, number: int, title: str, body: str = ""):
        return select_task.Issue(number, title, body, f"https://example.invalid/{number}")

    # {
    #   責務: [test_p0_wins_over_lower_priority: verifies the behavior described by "p0 wins over lower priority"]
    #   処理: [
    #     1: arrange case data and fixture state for p0 wins over lower priority,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_p0_wins_over_lower_priority(self):
        issues = [
            self.issue(2, "[P1] Later"),
            self.issue(8, "[P0] Important"),
        ]
        self.assertEqual(select_task.select_issue(issues).number, 8)

    # {
    #   責務: [
    #     test_oldest_number_wins_with_same_priority: verifies the behavior described by "oldest number wins with same priority",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for oldest number wins with same priority,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_oldest_number_wins_with_same_priority(self):
        issues = [
            self.issue(9, "[P0] Newer"),
            self.issue(4, "[P0] Older"),
        ]
        self.assertEqual(select_task.select_issue(issues).number, 4)

    # {
    #   責務: [test_roadmap_is_skipped: verifies the behavior described by "roadmap is skipped"]
    #   処理: [
    #     1: arrange case data and fixture state for roadmap is skipped,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_roadmap_is_skipped(self):
        issues = [
            self.issue(1, "[P0] 開発ロードマップ / Issue索引"),
            self.issue(3, "[P1] Implement feature"),
        ]
        self.assertEqual(select_task.select_issue(issues).number, 3)

    # {
    #   責務: [test_acceptance_is_compacted: verifies the behavior described by "acceptance is compacted"]
    #   処理: [
    #     1: arrange case data and fixture state for acceptance is compacted,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_acceptance_is_compacted(self):
        issue = self.issue(
            5,
            "[P1] Task",
            "## 完了条件\n- alpha\n- beta\n\n## Other\n- ignored",
        )
        packet = select_task.compact_packet(issue)
        self.assertEqual(packet["acceptance"], ["alpha", "beta"])

    # {
    #   責務: [test_request_uses_managed_ca_bundle: GitHub API通信で管理対象CA bundleを使う]
    #   処理: [1: API応答を模擬する, 2: urlopenへ渡されたTLS contextを確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: []
    # }
    def test_request_uses_managed_ca_bundle(self):
        with patch(
            "tools.context.select_task.urllib.request.urlopen",
            return_value=BytesIO(b"{}"),
        ) as urlopen:
            select_task._request_json("https://api.github.com/test")

        context = urlopen.call_args.kwargs["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        fingerprints = {
            sha256(certificate).hexdigest()
            for certificate in context.get_ca_certs(binary_form=True)
        }
        self.assertTrue(fingerprints)
        self.assertFalse(fingerprints & set(AFFECTED_CERTIFICATES))


if __name__ == "__main__":
    unittest.main()
