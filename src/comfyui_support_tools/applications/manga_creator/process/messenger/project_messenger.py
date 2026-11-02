"""Process messenger for project persistence and rendered asset services."""

from pathlib import Path

from comfyui_support_tools.applications.manga_creator.data.messenger.project_messenger import (
    MangaProjectMessenger as DataProjectEndpoint,
)
from comfyui_support_tools.shared.contracts.manga_creator import MangaPage, MangaProject


# {
# 責務: [MangaProjectMessenger: route Process data requests to the Data layer]
# フィールド: [Data-side project and media endpoint]
# 処理: [forward project and artifact payloads without interpreting story business rules]
# }
class MangaProjectMessenger:
    # {
    # 責務: [__init__: bind the Data-layer endpoint]
    # 処理: [store an injectable Data messenger target]
    # 引数: [self: Process messenger, target: Data endpoint]
    # 戻り値: [None: endpoint bound]
    # }
    def __init__(self, target: DataProjectEndpoint) -> None:
        self._target = target

    # {
    # 責務: [load: transport a project load request]
    # 処理: [forward the source path]
    # 引数: [path: project JSON path]
    # 戻り値: [MangaProject: restored project]
    # }
    def load(self, path: str | Path) -> MangaProject:
        return self._target.load(path)

    # {
    # 責務: [save: transport a project save request]
    # 処理: [forward project data and destination path]
    # 引数: [project: project state, path: JSON path]
    # 戻り値: [Path: saved project]
    # }
    def save(self, project: MangaProject, path: str | Path) -> Path:
        return self._target.save(project, path)

    # {
    # 責務: [store_panel: transport one rendered panel candidate]
    # 処理: [forward project directory, panel ID, and image bytes]
    # 引数: [project_dir: artifact root, panel_id: panel identifier, image_bytes: generated image]
    # 戻り値: [Path: stored candidate path]
    # }
    def store_panel(self, project_dir: str | Path, panel_id: str, image_bytes: bytes) -> Path:
        return self._target.store_panel(project_dir, panel_id, image_bytes)

    # {
    # 責務: [inspect_panel: transport candidate image validation]
    # 処理: [forward image bytes to Data validation]
    # 引数: [image_bytes: encoded image]
    # 戻り値: [tuple[int, int]: image dimensions]
    # }
    def inspect_panel(self, image_bytes: bytes) -> tuple[int, int]:
        return self._target.inspect_panel(image_bytes)

    # {
    # 責務: [read_asset: transport a project-relative preview read]
    # 処理: [forward root and relative path to Data messenger]
    # 引数: [project_dir: project root, relative_path: image path]
    # 戻り値: [bytes: encoded image]
    # }
    def read_asset(self, project_dir: str | Path, relative_path: str) -> bytes:
        return self._target.read_asset(project_dir, relative_path)

    # {
    # 責務: [compose_page: transport a page composition request]
    # 処理: [forward project, page, artifact root and page size]
    # 引数: [project: project, page: selected page, project_dir: artifact root, page_size: image size]
    # 戻り値: [tuple[Path, tuple[str, ...]]: page path and warnings]
    # }
    def compose_page(
        self,
        project: MangaProject,
        page: MangaPage,
        project_dir: str | Path,
        page_size: tuple[int, int] = (1600, 2200),
    ) -> tuple[Path, tuple[str, ...]]:
        return self._target.compose_page(project, page, project_dir, page_size)
