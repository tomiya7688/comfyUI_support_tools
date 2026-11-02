"""Launch the LoRA dataset curation review UI."""

from .ui.processing.window import DatasetCuratorWindow


# {
# 責務: [main: launch the dataset curation UI]
# 処理: [create the window and run Tk's event loop]
# 引数: [none]
# 戻り値: [None: process exits when the window closes]
# }
def main() -> None:
    window = DatasetCuratorWindow()
    window.mainloop()


if __name__ == "__main__":
    main()
