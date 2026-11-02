"""Process-level Manga Creator command boundary."""

from pathlib import Path

from comfyui_support_tools.applications.manga_creator.process.processing.production import (
    MangaProductionProcessor,
)
from comfyui_support_tools.shared.contracts.manga_creator import (
    CharacterSpec,
    DialogueLine,
    LocationSpec,
    MangaLayoutMode,
    MangaProject,
    MangaStyleMode,
    PanelEvaluation,
    PanelGenerationBackend,
    PanelSpec,
    PropSpec,
    ReadingDirection,
)


# {
# 責務: [MangaCreatorApplication: expose manga project operations to UI messengers]
# フィールド: [MangaProductionProcessor]
# 処理: [route project edits, planning, rendering, candidate selection and page composition]
# }
class MangaCreatorApplication:
    # {
    # 責務: [__init__: bind the production processor]
    # 処理: [store an injectable manga production pipeline]
    # 引数: [self: Process Commander, processor: production implementation]
    # 戻り値: [None: application initialized]
    # }
    def __init__(self, processor: MangaProductionProcessor) -> None:
        self._processor = processor

    # {
    # 責務: [project: return active project state]
    # 処理: [delegate current-state lookup]
    # 引数: [self: Process Commander]
    # 戻り値: [MangaProject: active project]
    # }
    @property
    def project(self) -> MangaProject:
        return self._processor.project

    # {
    # 責務: [create_project: create a project and initial project file]
    # 処理: [forward title, script, output format and optional bibles]
    # 引数: [path: JSON path, title: project title, story_script: narrative, page_count: target pages, genre: category, layout_mode: layout, reading_direction: page direction, style: rendering mode, characters/locations/props: optional entity bibles]
    # 戻り値: [MangaProject: initialized project]
    # }
    def create_project(
        self,
        path: str | Path,
        title: str,
        story_script: str,
        *,
        page_count: int = 1,
        genre: str = "",
        layout_mode: MangaLayoutMode = MangaLayoutMode.MANGA_PAGE,
        reading_direction: ReadingDirection = ReadingDirection.RIGHT_TO_LEFT,
        style: MangaStyleMode = MangaStyleMode.STORYBOARD,
        characters: tuple[CharacterSpec, ...] = (),
        locations: tuple[LocationSpec, ...] = (),
        props: tuple[PropSpec, ...] = (),
        backend_policy: str = "storyboard",
    ) -> MangaProject:
        return self._processor.create_project(
            path,
            title,
            story_script,
            page_count=page_count,
            genre=genre,
            layout_mode=layout_mode,
            reading_direction=reading_direction,
            style=style,
            characters=characters,
            locations=locations,
            props=props,
            backend_policy=backend_policy,
        )

    # {
    # 責務: [open_project: restore a saved project]
    # 処理: [forward project path to Data-backed production processing]
    # 引数: [path: project JSON path]
    # 戻り値: [MangaProject: restored project]
    # }
    def open_project(self, path: str | Path) -> MangaProject:
        return self._processor.open_project(path)

    # {
    # 責務: [register_backend: expose an external image backend to this application]
    # 処理: [delegate named adapter registration to Process processing]
    # 引数: [name: backend ID, backend: generation implementation]
    # 戻り値: [None: backend registered]
    # }
    def register_backend(self, name: str, backend: PanelGenerationBackend) -> None:
        self._processor.register_backend(name, backend)

    # {
    # 責務: [available_backends: list configured model backends]
    # 処理: [delegate backend catalog access]
    # 引数: [self: Process Commander]
    # 戻り値: [tuple[str, ...]: registered adapter IDs]
    # }
    @property
    def available_backends(self) -> tuple[str, ...]:
        return self._processor.available_backends

    # {
    # 責務: [save_project: save current project]
    # 処理: [forward current state and optional path]
    # 引数: [path: optional project JSON path]
    # 戻り値: [Path: saved project path]
    # }
    def save_project(self, path: str | Path | None = None) -> Path:
        return self._processor.save_project(path)

    # {
    # 責務: [plan: generate editable pages and panels from story text]
    # 処理: [delegate decomposition to Process processing]
    # 引数: [page_count: optional page count]
    # 戻り値: [MangaProject: storyboard plan]
    # }
    def plan(self, page_count: int | None = None) -> MangaProject:
        return self._processor.plan(page_count)

    # {
    # 責務: [edit_project: update user-level story or rendering metadata]
    # 処理: [forward approved project fields]
    # 引数: [updates: project metadata changes]
    # 戻り値: [MangaProject: updated project]
    # }
    def edit_project(self, **updates: object) -> MangaProject:
        return self._processor.edit_project(**updates)

    # {
    # 責務: [upsert_character: add or revise a reusable character bible entry]
    # 処理: [forward the immutable character definition]
    # 引数: [character: character bible entry]
    # 戻り値: [MangaProject: updated project]
    # }
    def upsert_character(self, character: CharacterSpec) -> MangaProject:
        return self._processor.upsert_character(character)

    # {
    # 責務: [upsert_location: add or revise a location bible entry]
    # 処理: [forward the immutable location definition]
    # 引数: [location: location bible entry]
    # 戻り値: [MangaProject: updated project]
    # }
    def upsert_location(self, location: LocationSpec) -> MangaProject:
        return self._processor.upsert_location(location)

    # {
    # 責務: [upsert_prop: add or revise one prop bible entry]
    # 処理: [forward the immutable prop definition]
    # 引数: [prop: prop bible entry]
    # 戻り値: [MangaProject: updated project]
    # }
    def upsert_prop(self, prop: PropSpec) -> MangaProject:
        return self._processor.upsert_prop(prop)

    # {
    # 責務: [edit_panel: update one panel's planned story and composition]
    # 処理: [forward the edited immutable panel]
    # 引数: [panel: panel specification]
    # 戻り値: [MangaProject: updated project]
    # }
    def edit_panel(self, panel: PanelSpec) -> MangaProject:
        return self._processor.edit_panel(panel)

    # {
    # 責務: [edit_dialogue: update text independently of panel art]
    # 処理: [forward panel ID and editable dialogue lines]
    # 引数: [panel_id: target panel, dialogue: replacement lines]
    # 戻り値: [MangaProject: updated project]
    # }
    def edit_dialogue(self, panel_id: str, dialogue: tuple[DialogueLine, ...]) -> MangaProject:
        return self._processor.edit_dialogue(panel_id, dialogue)

    # {
    # 責務: [record_continuity_event: update long-term character/prop/location memory]
    # 処理: [forward the accepted state transition]
    # 引数: [entity_id: entity, field: state field, value: state value, panel_id: source panel]
    # 戻り値: [MangaProject: updated project]
    # }
    def record_continuity_event(
        self, entity_id: str, field: str, value: str, panel_id: str
    ) -> MangaProject:
        return self._processor.record_continuity_event(entity_id, field, value, panel_id)

    # {
    # 責務: [render_panel: generate and rank one panel's alternatives]
    # 処理: [delegate per-panel image generation and validation]
    # 引数: [panel_id: selected panel, candidate_count: alternatives 1..8, seed: optional base seed]
    # 戻り値: [tuple[MangaProject, PanelEvaluation]: updated project and score report]
    # }
    def render_panel(
        self, panel_id: str, candidate_count: int = 1, seed: int | None = None
    ) -> tuple[MangaProject, PanelEvaluation]:
        return self._processor.render_panel(panel_id, candidate_count, seed)

    # {
    # 責務: [repair_panel: apply a local correction to one selected panel]
    # 処理: [delegate only the targeted image region to an optional repair adapter]
    # 引数: [panel_id: selected panel, instruction: correction, region: optional normalized area, seed: optional seed]
    # 戻り値: [tuple[MangaProject, PanelEvaluation]: updated project and report]
    # }
    def repair_panel(
        self,
        panel_id: str,
        instruction: str,
        region: tuple[float, float, float, float] | None = None,
        seed: int | None = None,
    ) -> tuple[MangaProject, PanelEvaluation]:
        return self._processor.repair_panel(panel_id, instruction, region, seed)

    # {
    # 責務: [render_all_panels: build all panels in reading order]
    # 処理: [delegate the resumable batch workflow]
    # 引数: [candidate_count: alternatives per panel, seed: optional base seed]
    # 戻り値: [MangaProject: project with panel renders]
    # }
    def render_all_panels(self, candidate_count: int = 1, seed: int | None = None) -> MangaProject:
        return self._processor.render_all_panels(candidate_count, seed)

    # {
    # 責務: [select_candidate: choose one stored panel alternative]
    # 処理: [delegate choice while preserving other panel renders]
    # 引数: [panel_id: target panel, candidate_index: alternative index]
    # 戻り値: [MangaProject: updated project]
    # }
    def select_candidate(self, panel_id: str, candidate_index: int) -> MangaProject:
        return self._processor.select_candidate(panel_id, candidate_index)

    # {
    # 責務: [compose_page: create one page artifact from generated panels]
    # 処理: [delegate page layout and separate lettering composition]
    # 引数: [page_id: target page, page_size: output pixels]
    # 戻り値: [tuple[MangaProject, tuple[str, ...]]: updated project and warnings]
    # }
    def compose_page(
        self, page_id: str, page_size: tuple[int, int] = (1600, 2200)
    ) -> tuple[MangaProject, tuple[str, ...]]:
        return self._processor.compose_page(page_id, page_size)

    # {
    # 責務: [load_panel_preview: load one panel image for editor display]
    # 処理: [delegate safe project-relative asset loading]
    # 引数: [relative_path: panel artifact path]
    # 戻り値: [bytes: encoded preview image]
    # }
    def load_panel_preview(self, relative_path: str) -> bytes:
        return self._processor.load_panel_preview(relative_path)
