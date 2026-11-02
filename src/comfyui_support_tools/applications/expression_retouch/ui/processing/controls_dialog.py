"""Optional per-feature controls for expression retouch requests."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from comfyui_support_tools.shared.contracts.expression_retouch import ExpressionParameters

CONTROL_LABELS = {
    "smile_strength": "Smile strength (0–1)",
    "mouth_open": "Mouth openness (0–1)",
    "eye_openness_left": "Left-eye openness (0–1)",
    "eye_openness_right": "Right-eye openness (0–1)",
    "eyebrow_raise_left": "Left-brow raise (0–1)",
    "eyebrow_raise_right": "Right-brow raise (0–1)",
    "eyebrow_inward": "Brow inward (0–1)",
    "blush_strength": "Blush (0–1)",
    "tear_strength": "Tears (0–1)",
    "gaze_x": "Gaze horizontal (−1 left to +1 right)",
    "gaze_y": "Gaze vertical (−1 up to +1 down)",
}


# {
#   責務: [ExpressionControlsDialog: edit bounded optional facial feature controls]
#   フィールド: [root window, current parameter variables, result]
#   処理: [show one optional control per muscle/gaze parameter and return validated values]
# }
class ExpressionControlsDialog:
    # {
    #   責務: [__init__: initialize an optional expression control dialog]
    #   処理: [create blank-or-existing text fields without changing unspecified defaults]
    #   引数: [root: parent Tk window, initial: current parameter values]
    #   戻り値: []
    # }
    def __init__(self, root: tk.Tk, initial: ExpressionParameters) -> None:
        self.root = root
        self.initial = initial
        self.result: ExpressionParameters | None = None
        self.window = tk.Toplevel(root)
        self.window.title("Fine-tune expression controls")
        self.window.transient(root)
        self.window.grab_set()
        self.variables: dict[str, tk.StringVar] = {}
        body = ttk.Frame(self.window, padding=12)
        body.pack(fill="both", expand=True)
        for row, (name, label) in enumerate(CONTROL_LABELS.items()):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=2)
            value = getattr(initial, name)
            variable = tk.StringVar(value="" if value is None else str(value))
            self.variables[name] = variable
            ttk.Entry(body, textvariable=variable, width=12).grid(
                row=row, column=1, sticky="e", padx=(16, 0), pady=2
            )
        ttk.Label(
            body,
            text="Leave a field blank to let the expression preset choose it.",
            wraplength=360,
        ).grid(row=len(CONTROL_LABELS), column=0, columnspan=2, sticky="w", pady=(8, 4))
        buttons = ttk.Frame(body)
        buttons.grid(row=len(CONTROL_LABELS) + 1, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=self.window.destroy).pack(side="right")
        ttk.Button(buttons, text="Apply", command=self._apply).pack(side="right", padx=6)

    # {
    #   責務: [show: wait until the dialog is applied or canceled]
    #   処理: [block the parent window and return the optional validated parameter set]
    #   引数: [self: expression controls dialog]
    #   戻り値: [ExpressionParameters | None: applied values or cancellation]
    # }
    def show(self) -> ExpressionParameters | None:
        self.root.wait_window(self.window)
        return self.result

    # {
    #   責務: [_apply: parse and validate user-entered facial controls]
    #   処理: [keep blanks unset, parse numeric fields, and show range errors]
    #   引数: [self: expression controls dialog]
    #   戻り値: []
    # }
    def _apply(self) -> None:
        values: dict[str, float | None] = {}
        try:
            for name, variable in self.variables.items():
                text = variable.get().strip()
                values[name] = float(text) if text else None
            self.result = ExpressionParameters(**values)
        except (TypeError, ValueError) as error:
            messagebox.showerror("Invalid facial control", str(error), parent=self.window)
            return
        self.window.destroy()
