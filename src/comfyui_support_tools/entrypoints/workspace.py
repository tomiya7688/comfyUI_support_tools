"""Composition root for the opt-in Main GUI shell; no backend is loaded here."""
from comfyui_support_tools.applications.main_gui.process.commander.navigation_commander import NavigationCommander
from comfyui_support_tools.applications.main_gui.process.messenger.navigation_messenger import ProcessNavigationMessenger
from comfyui_support_tools.applications.main_gui.process.processing.navigation_processing import NavigationProcessing
from comfyui_support_tools.applications.main_gui.ui.commander.navigation_commander import NavigationUiCommander
from comfyui_support_tools.applications.main_gui.ui.messenger.navigation_messenger import UiNavigationMessenger
from comfyui_support_tools.applications.main_gui.ui.processing.shell_window import ShellWindow
from comfyui_support_tools.shared.contracts.tool_entry import ToolEntry
from comfyui_support_tools.entrypoints.media_browser import create_media_browser


def create_navigation(tools: tuple[ToolEntry, ...]) -> NavigationUiCommander:
    processing = NavigationProcessing(tools)
    process = NavigationCommander(processing)
    process_messenger = ProcessNavigationMessenger(process)
    ui_messenger = UiNavigationMessenger(process_messenger)
    return NavigationUiCommander(ui_messenger)


def run_shell(commander: NavigationUiCommander) -> str | None:
    requested: list[str] = []

    def open_legacy(tool_id: str) -> None:
        requested.append(tool_id)
        window.destroy()

    # Reset filters on reopening; the same Process instance retains recent tools.
    commander.filter_tools("", "")
    commander.select_section("all")
    window = ShellWindow(commander, open_legacy, create_media_browser())
    window.mainloop()
    return requested[0] if requested else None


def smoke_test(tools: tuple[ToolEntry, ...]) -> None:
    requested: list[str] = []
    window = ShellWindow(create_navigation(tools), requested.append, create_media_browser())
    errors: list[str] = []
    window.report_callback_exception = lambda *args: errors.append(str(args))
    try:
        window.update()
        if not all(getattr(window, name).winfo_ismapped()
                   for name in ("toolbar", "library", "workspace", "inspector", "jobs")):
            raise RuntimeError("One or more shell regions did not display")
        for section in ("all", "images", "videos", "dataset", "generated", "favorites", "recent"):
            window.select_section(section)
            window.update()
        for name in ("library", "inspector", "jobs"):
            window.set_pane_visible(name, False)
            window.update()
            window.set_pane_visible(name, True)
            window.update()
        window.geometry("900x600")
        window.update()
        from comfyui_support_tools.entrypoints.media_smoke import exercise_media
        exercise_media(window)
        if errors:
            raise RuntimeError("Tk callback failed: " + "; ".join(errors))
    finally:
        window.destroy()
    print("KadokaTools workspace GUI smoke test: OK")
