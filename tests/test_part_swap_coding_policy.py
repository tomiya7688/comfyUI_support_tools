import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


# {
# 責務: [PartSwapCodingPolicyTests: Part Swap Designが正本規約とAgent導線から消えないことを検証する]
# フィールド: [ROOT: repository root]
# }
class PartSwapCodingPolicyTests(unittest.TestCase):
    # {
    # 責務: [test_part_swap_design_remains_canonical_coding_policy: 日英規約とAGENTSのPart Swap Design要件を検証する]
    # 処理: [1: 日英コーディング規約とAGENTSを読む, 2: 参照元と閉じた呼び出し関係・swap test要件を確認する]
    # 引数: [self: test instance]
    # 戻り値: []
    # }
    def test_part_swap_design_remains_canonical_coding_policy(self):
        english = (ROOT / "doc" / "coding-standards.md").read_text(encoding="utf-8")
        japanese = (ROOT / "doc" / "コーディング規約.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        architecture_en = (ROOT / "doc" / "architecture" / "upd_standard.en.md").read_text(
            encoding="utf-8"
        )
        architecture_ja = (ROOT / "doc" / "architecture" / "upd_standard.md").read_text(
            encoding="utf-8"
        )

        reference = "https://github.com/tomiya7688/part-swap-design"
        message_reference = "https://github.com/tomiya7688/Message-Orientated-Design"
        self.assertIn(reference, english)
        self.assertIn(reference, japanese)
        self.assertIn(message_reference, english)
        self.assertIn(message_reference, japanese)
        self.assertIn("closed call relationship", english)
        self.assertIn("閉じた呼び出し関係", japanese)
        self.assertIn("fake/minimal replacement implementation", english)
        self.assertIn("fake / minimal implementation", japanese)
        self.assertIn("Part Swap Design", agents)
        self.assertIn("Message Orientated Design selectively", agents)
        self.assertIn("Plain UPD is valid for simple flows", agents)
        self.assertIn("Commander / Orchestrator is **optional**", architecture_en)
        self.assertIn("Commander / Orchestratorは**標準必須ではない**", architecture_ja)
        self.assertIn("selectively applied between independent state-owning subjects", architecture_en)
        self.assertIn("独立した状態主体間で選択適用", architecture_ja)
        self.assertIn("Message Manager performs delivery only", architecture_en)
        self.assertIn("Message Managerは配送だけ", architecture_ja)
        self.assertIn("Message\n├ from\n├ to\n├ type\n└ content", architecture_en)
        self.assertIn("Process Orchestrator is not a fourth UPD role", architecture_en)
        self.assertIn("Process Orchestratorは新しい第4roleではなく", architecture_ja)
        self.assertIn("pass-through Commander/Messenger", english)
        self.assertIn("形式だけのCommander", japanese)


if __name__ == "__main__":
    unittest.main()
