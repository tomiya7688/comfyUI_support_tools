from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from comfyui_support_tools.entrypoints.main_gui import create_shell_commander  # noqa: E402


# {
#   責務: [MainGuiUpdFlowTests: related test fixtures and cases for MainGuiUpdFlow behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class MainGuiUpdFlowTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_ui_process_data_flow_bootstraps_status: verifies the behavior described by "ui process data flow bootstraps status",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for ui process data flow bootstraps status,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_ui_process_data_flow_bootstraps_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "app.json"
            config.write_text(
                json.dumps({"name": "Kadoka Tools", "version": "1.2.3"}),
                encoding="utf-8",
            )
            commander = create_shell_commander()
            self.assertEqual(
                commander.initialize(config),
                "Kadoka Tools 1.2.3: ready",
            )


if __name__ == "__main__":
    unittest.main()
