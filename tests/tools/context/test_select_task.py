import unittest

from tools.context import select_task


class SelectTaskTests(unittest.TestCase):
    def issue(self, number: int, title: str, body: str = ""):
        return select_task.Issue(number, title, body, f"https://example.invalid/{number}")

    def test_p0_wins_over_lower_priority(self):
        issues = [
            self.issue(2, "[P1] Later"),
            self.issue(8, "[P0] Important"),
        ]
        self.assertEqual(select_task.select_issue(issues).number, 8)

    def test_oldest_number_wins_with_same_priority(self):
        issues = [
            self.issue(9, "[P0] Newer"),
            self.issue(4, "[P0] Older"),
        ]
        self.assertEqual(select_task.select_issue(issues).number, 4)

    def test_roadmap_is_skipped(self):
        issues = [
            self.issue(1, "[P0] 開発ロードマップ / Issue索引"),
            self.issue(3, "[P1] Implement feature"),
        ]
        self.assertEqual(select_task.select_issue(issues).number, 3)

    def test_acceptance_is_compacted(self):
        issue = self.issue(
            5,
            "[P1] Task",
            "## 完了条件\n- alpha\n- beta\n\n## Other\n- ignored",
        )
        packet = select_task.compact_packet(issue)
        self.assertEqual(packet["acceptance"], ["alpha", "beta"])


if __name__ == "__main__":
    unittest.main()
