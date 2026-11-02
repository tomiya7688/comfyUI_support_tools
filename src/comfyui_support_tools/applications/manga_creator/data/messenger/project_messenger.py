"""Data endpoint for manga project documents and rendered assets."""

from pathlib import Path

from comfyui_support_tools.applications.manga_creator.data.processing.media_store import (
    compose_page_image,
    inspect_panel_image,
    read_project_asset,
    store_page_image,
    store_panel_candidate,
)
from comfyui_support_tools.applications.manga_creator.data.processing.project_store import (
    MangaProjectStore,
)
from comfyui_support_tools.shared.contracts.manga_creator import MangaPage, MangaProject


# {
# 責務: [MangaProjectMessenger: route manga document and asset operations to Data processing]
# フィールド: [project store]
# 処理: [serve bounded project persistence, image validation, panel revision and page composition]
# }
class MangaProjectMessenger:
    # {
    # 責務: [__init__: bind the project storage endpoint]
    # 処理: [retain an injectable project store]
    # 引数: [self: Data messenger, store: optional project persistence]
    # 戻り値: [None: endpoint initialized]
    # }
    def __init__(self, store: MangaProjectStore | None = None) -> None:
        self._store = store or MangaProjectStore()

    # {
    # 責務: [load: read one validated project document]
    # 処理: [forward the path to Data persistence]
    # 引数: [path: project JSON path]
    # 戻り値: [MangaProject: restored project]
    # }
    def load(self, path: str | Path) -> MangaProject:
        return self._store.load(path)

    # {
    # 責務: [save: persist the current project state]
    # 処理: [forward the project and destination path]
    # 引数: [project: editable manga state, path: project JSON path]
    # 戻り値: [Path: saved document]
    # }
    def save(self, project: MangaProject, path: str | Path) -> Path:
        return self._store.save(project, path)

    # {
    # 責務: [store_panel: persist one generated panel candidate]
    # 処理: [validate and write a new immutable panel revision]
    # 引数: [project_dir: project asset directory, panel_id: stable panel identifier, image_bytes: candidate image]
    # 戻り値: [Path: stored panel artifact]
    # }
    def store_panel(self, project_dir: str | Path, panel_id: str, image_bytes: bytes) -> Path:
        return store_panel_candidate(project_dir, panel_id, image_bytes)

    # {
    # 責務: [inspect_panel: validate candidate image data]
    # 処理: [forward bounded image decoding]
    # 引数: [image_bytes: encoded panel image]
    # 戻り値: [tuple[int, int]: image dimensions]
    # }
    def inspect_panel(self, image_bytes: bytes) -> tuple[int, int]:
        return inspect_panel_image(image_bytes)

    # {
    # 責務: [read_asset: retrieve one project-relative preview asset]
    # 処理: [forward bounded path validation and image loading to Data processing]
    # 引数: [project_dir: project root, relative_path: panel/page image path]
    # 戻り値: [bytes: encoded preview image]
    # }
    def read_asset(self, project_dir: str | Path, relative_path: str) -> bytes:
        return read_project_asset(project_dir, relative_path)

    # {
    # 責務: [compose_page: assemble panel renders and lettering]
    # 処理: [call Data image composition and persist the composed page]
    # 引数: [project: manga project, page: selected page, project_dir: asset root, page_size: optional output size]
    # 戻り値: [tuple[Path, tuple[str, ...]]: page artifact path and rendering warnings]
    # }
    def compose_page(
        self,
        project: MangaProject,
        page: MangaPage,
        project_dir: str | Path,
        page_size: tuple[int, int] = (1600, 2200),
    ) -> tuple[Path, tuple[str, ...]]:
        image_bytes, warnings = compose_page_image(project, page, project_dir, page_size)
        path = store_page_image(project_dir, page.id, image_bytes)
        return path, warnings
