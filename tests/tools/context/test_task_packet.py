from pathlib import Path
import sys
import tempfile
import unittest

MODULE_DIR = Path(__file__).parents[3] / "tools" / "context"
sys.path.insert(0, str(MODULE_DIR))

from diff_context import DiffContext  # noqa: E402
import task_packet  # noqa: E402
from select_task import Issue  # noqa: E402


# {
#   責務: [TaskPacketTests: related test fixtures and cases for TaskPacket behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class TaskPacketTests(unittest.TestCase):
    # {
    #   責務: [issue: builds an issue fixture with the selected number and markdown sections]
    #   処理: [1: build the Issue object with the supplied number/title/body fields]
    #   引数: [body: issue markdown body (str)]
    #   戻り値: [result: Issue produced for the supplied fixture/input]
    # }
    def issue(self, body: str) -> Issue:
        return Issue(44, "[P0] Example task", body, "https://example.invalid/44")

    # {
    #   責務: [
    #     test_sections_and_diff_are_compacted: verifies the behavior described by "sections and diff are compacted",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for sections and diff are compacted,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_sections_and_diff_are_compacted(self):
        issue = self.issue(
            "## 目的\nReduce context.\n\n"
            "## 必須要件\n- create packet\n- keep it small\n\n"
            "## 完了条件\n- packet is written\n"
        )
        diff = DiffContext(
            ["tools/context/task_packet.py"],
            ["build_packet"],
            ["@@ def build_packet", "+    compact_patch: list[str]"],
        )
        packet = task_packet.build_packet(issue, diff)
        self.assertEqual(packet.goal, ["Reduce context."])
        self.assertEqual(packet.required, ["create packet", "keep it small"])
        self.assertEqual(packet.acceptance, ["packet is written"])
        self.assertEqual(packet.changed_files, ["tools/context/task_packet.py"])
        self.assertEqual(packet.changed_symbols, ["build_packet"])
        self.assertEqual(len(packet.compact_patch), 2)

    # {
    #   責務: [
    #     test_write_packet_creates_issue_directory: verifies the behavior described by "write packet creates issue directory",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for write packet creates issue directory,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_write_packet_creates_issue_directory(self):
        packet = task_packet.build_packet(self.issue("## 目的\nTest."))
        with tempfile.TemporaryDirectory() as temp_dir:
            path = task_packet.write_packet(packet, Path(temp_dir))
            self.assertEqual(path.name, "task.json")
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
