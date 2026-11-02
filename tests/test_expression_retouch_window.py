"""Focused UI tests for honest expression score presentation."""

from __future__ import annotations

import unittest

from comfyui_support_tools.applications.expression_retouch.ui.processing.window import (
    ExpressionRetouchWindow,
)
from comfyui_support_tools.shared.contracts.expression_retouch import (
    ExpressionCandidate,
    ExpressionEvaluation,
    ExpressionPreset,
    ExpressionRetouchResult,
)


# {
# 責務: [ExpressionRetouchUiTests: verify candidate review communicates measured and unavailable scores]
# フィールド: [fake Tk widgets and one persisted candidate result]
# 処理: [exercise success and selection handlers without creating a display server]
# 引数: [None: unittest fixture]
# 戻り値: [None: tests report UI score presentation]
# }
class ExpressionRetouchUiTests(unittest.TestCase):
    # {
    # 責務: [test_candidate_review_does_not_claim_unmeasured_expression_accuracy: preserve evidence boundaries]
    # 処理: [show a proxy-ranked candidate with no semantic evaluator and inspect review text]
    # 引数: [self: test case]
    # 戻り値: [None: UI identifies expression match as unavailable]
    # }
    def test_candidate_review_does_not_claim_unmeasured_expression_accuracy(self):
        # {
        # 責務: [Widget: emulate the small Tk widget surface used by review callbacks]
        # フィールド: [values, items, selection, value]
        # 処理: [record changes for assertions without requiring a display server]
        # }
        class Widget:
            # {
            # 責務: [configure: record display properties]
            # 処理: [store keyword values]
            # 引数: [self: fake widget, values: display options]
            # 戻り値: [None]
            # }
            def configure(self, **values):
                self.values = values

            # {
            # 責務: [set: record a variable's displayed value]
            # 処理: [store the value for test inspection]
            # 引数: [self: fake widget, value: display text]
            # 戻り値: [None]
            # }
            def set(self, value):
                self.value = value

            # {
            # 責務: [delete: clear recorded list rows]
            # 処理: [reset items]
            # 引数: [self: fake widget, args: listbox bounds]
            # 戻り値: [None]
            # }
            def delete(self, *_args):
                self.items = []

            # {
            # 責務: [insert: append one displayed candidate row]
            # 処理: [record list text]
            # 引数: [self: fake widget, where: insertion index, value: row text]
            # 戻り値: [None]
            # }
            def insert(self, _where, value):
                self.items.append(value)

            # {
            # 責務: [selection_set: retain the selected list row]
            # 処理: [store the selected index]
            # 引数: [self: fake widget, index: candidate position]
            # 戻り値: [None]
            # }
            def selection_set(self, index):
                self.selection = index

            # {
            # 責務: [curselection: return the current candidate selection]
            # 処理: [return one Tk-compatible index tuple]
            # 引数: [self: fake widget]
            # 戻り値: [tuple[int, ...]: selected index]
            # }
            def curselection(self):
                return (getattr(self, "selection", 0),)

        window = ExpressionRetouchWindow.__new__(ExpressionRetouchWindow)
        window._busy = True
        window.generate_button = Widget()
        window.candidate_list = Widget()
        window.score_label = Widget()
        window.status_value = Widget()
        window._draw_preview = lambda: None
        candidate = ExpressionCandidate(
            "candidate.png",
            "mask.png",
            "manifest.json",
            "test_backend",
            12,
            ExpressionEvaluation(None, 0.9, 0.8, 0.95),
        )
        window._generation_succeeded(
            ExpressionRetouchResult("sha256", ExpressionPreset.SMILE, (), (candidate,), 0)
        )
        self.assertIn("preservation", window.candidate_list.items[0])
        self.assertIn("unavailable", window.score_label.values["text"])
        window._select_candidate(None)
        self.assertIn("not evaluated", window.score_label.values["text"])


if __name__ == "__main__":
    unittest.main()
