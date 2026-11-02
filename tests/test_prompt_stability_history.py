from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comfyui_support_tools.shared.prompt_stability.contracts import ContentMode
from comfyui_support_tools.shared.prompt_stability.history import PromptFailureHistory


# {
# 責務: [PromptStabilityHistoryTests: privacy-safe local historyを検証する]
# フィールド: [temporary history file]
# 処理: [failure type照会とprompt本文非保存を確認する]
# }
class PromptStabilityHistoryTests(unittest.TestCase):
    # {
    # 責務: [test_history_stores_prompt_hash_and_returns_model_scoped_failures: prompt privacyとscopeを確認する]
    # 処理: [1: local failureをappendする, 2: JSONL本文とmatching queryを検証する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_history_stores_prompt_hash_and_returns_model_scoped_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.jsonl"
            history = PromptFailureHistory(path)
            record = history.append(
                prompt="private character prompt",
                content_mode=ContentMode.SFW,
                backend="backend-a",
                model="model-a",
                failure_types=("hands", "composition"),
            )
            self.assertEqual(len(record.prompt_features_hash), 64)
            self.assertNotIn("private character prompt", path.read_text(encoding="utf-8"))
            self.assertEqual(
                history.recent_failures(
                    content_mode=ContentMode.SFW, backend="backend-a", model="model-a"
                ),
                ("hands", "composition"),
            )
            self.assertFalse(
                history.recent_failures(
                    content_mode=ContentMode.NSFW, backend="backend-a", model="model-a"
                )
            )


if __name__ == "__main__":
    unittest.main()
