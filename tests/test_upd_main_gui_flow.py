from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from comfyui_support_tools.entrypoints.main_gui import create_shell_commander  # noqa: E402


class MainGuiUpdFlowTests(unittest.TestCase):
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
