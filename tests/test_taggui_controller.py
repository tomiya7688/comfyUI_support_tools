from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.backend import taggui_controller


# {
#   責務: [TagGUIControllerTest: TagGUI起動コマンドの引数と初期化順を検証する]
#   フィールド: []
# }
class TagGUIControllerTest(unittest.TestCase):
    # {
    #   責務: [test_start_preloads_torch_before_running_tag_gui: 起動bootstrapがPyTorchを先に読むことを確認する]
    #   処理: [1: 一時TagGUI環境と画像フォルダを作る, 2: 子プロセスを模擬する, 3: 起動引数とimport順を検証する]
    #   引数: [self: unittestのテストケース]
    #   戻り値: []
    #   エラー: []
    # }
    def test_start_preloads_torch_before_running_tag_gui(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            taggui_root = root / "taggui"
            run_gui = taggui_root / "taggui" / "run_gui.py"
            pythonw = taggui_root / "venv" / "Scripts" / "pythonw.exe"
            image_directory = root / "images"
            run_gui.parent.mkdir(parents=True)
            run_gui.touch()
            pythonw.parent.mkdir(parents=True)
            pythonw.touch()
            image_directory.mkdir()
            process = Mock()
            process.poll.return_value = None

            with (
                patch.object(taggui_controller, "TAGGUI_DIR", taggui_root),
                patch.object(
                    taggui_controller,
                    "TAGGUI_PACKAGED_EXE",
                    root / "missing-taggui.exe",
                ),
                patch.object(
                    taggui_controller,
                    "venv_python",
                    side_effect=(pythonw, taggui_root / "venv" / "Scripts" / "python.exe"),
                ),
                patch.object(taggui_controller.subprocess, "Popen", return_value=process) as popen,
            ):
                controller = taggui_controller.TagGUIController()
                controller.start(image_directory)

            command = popen.call_args.args[0]
            self.assertEqual(command[0], str(pythonw))
            self.assertEqual(command[1], "-c")
            self.assertEqual(command[3], str(run_gui))
            self.assertEqual(command[4], str(image_directory.resolve()))
            self.assertLess(
                command[2].index('import_module("torch")'),
                command[2].index('run_path(str(run_gui), run_name="__main__")'),
            )


if __name__ == "__main__":
    unittest.main()
