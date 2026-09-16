from pathlib import Path
import sys
import tempfile
import unittest

MODULE_DIR = Path(__file__).parents[3] / "tools" / "context"
sys.path.insert(0, str(MODULE_DIR))

import task_packet  # noqa: E402
from select_task import Issue  # noqa: E402


class TaskPacketTests(unittest.TestCase):
    def issue(self, body: str) -> Issue:
        return Issue(44, "[P0] Example task", body, "https://example.invalid/44")

    def test_sections_are_compacted(self):
        issue = self.issue(
            "## 目的\nReduce context.\n\n"
            "## 必須要件\n- create packet\n- keep it small\n\n"
            "## 完了条件\n- packet is written\n"
        )
        packet = task_packet.build_packet(issue, ["tools/context/task_packet.py"])
        self.assertEqual(packet.goal, ["Reduce context."])
        self.assertEqual(packet.required, ["create packet", "keep it small"])
        self.assertEqual(packet.acceptance, ["packet is written"])
        self.assertEqual(packet.changed_files, ["tools/context/task_packet.py"])

    def test_write_packet_creates_issue_directory(self):
        packet = task_packet.build_packet(self.issue("## 目的\nTest."), [])
        with tempfile.TemporaryDirectory() as temp_dir:
            path = task_packet.write_packet(packet, Path(temp_dir))
            self.assertEqual(path.name, "task.json")
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
