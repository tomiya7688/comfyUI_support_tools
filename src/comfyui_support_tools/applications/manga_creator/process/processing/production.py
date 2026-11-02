"""Storyboard-first production state machine for manga projects."""

from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path

from comfyui_support_tools.applications.manga_creator.process.messenger.project_messenger import (
    MangaProjectMessenger,
)
from comfyui_support_tools.applications.manga_creator.process.processing.backend_registry import (
    PanelBackendRegistry,
)
from comfyui_support_tools.applications.manga_creator.process.processing.continuity import (
    continuity_context,
    record_continuity,
    replace_panel,
)
from comfyui_support_tools.applications.manga_creator.process.processing.evaluation import (
    evaluate_panel_dimensions,
)
from comfyui_support_tools.applications.manga_creator.process.processing.story_planner import (
    plan_story,
)
from comfyui_support_tools.applications.manga_creator.process.processing.storyboard_backend import (
    StoryboardRenderBackend,
)
from comfyui_support_tools.shared.contracts.manga_creator import (
    CharacterSpec,
    DialogueLine,
    LocationSpec,
    MangaLayoutMode,
    MangaPage,
    MangaProject,
    MangaStyleMode,
    PanelEvaluation,
    PanelGenerationBackend,
    PanelRenderRequest,
    PanelRepairBackend,
    PanelRepairRequest,
    PanelSpec,
    PanelStatus,
    PropSpec,
    ReadingDirection,
)


# {
# 責務: [MangaProductionProcessor: coordinate resumable panel-based manga production]
# フィールド: [Data messenger, pluggable panel backend, current project and project file]
# 処理: [plan, edit, render, evaluate, locally regenerate and compose pages]
# }
class MangaProductionProcessor:
    # {
    # 責務: [__init__: configure an offline storyboard-first production processor]
    # 処理: [bind the Data messenger and injectable panel image backend]
    # 引数: [self: processor, data: Process-to-Data messenger, backend: optional image backend]
    # 戻り値: [None: processor initialized]
    # }
    def __init__(
        self,
        data: MangaProjectMessenger,
        backend: PanelGenerationBackend | None = None,
        repair_backend: PanelRepairBackend | None = None,
    ) -> None:
        self._data = data
        self._backends = PanelBackendRegistry()
        self._backends.register("storyboard", StoryboardRenderBackend())
        if backend is not None:
            self._backends.register("injected", backend)
        self._repair_backend = repair_backend
        self._project: MangaProject | None = None
        self._project_file: Path | None = None

    # {
    # 責務: [project: expose the current immutable project state]
    # 処理: [return the loaded project or fail explicitly]
    # 引数: [self: processor]
    # 戻り値: [MangaProject: current project]
    # }
    @property
    def project(self) -> MangaProject:
        if self._project is None:
            raise RuntimeError("create or open a manga project first")
        return self._project

    # {
    # 責務: [_persist: atomically store project state when a project file is bound]
    # 処理: [save the current project after completed editing/generation operations]
    # 引数: [self: processor]
    # 戻り値: [Path | None: project path when persisted]
    # }
    def _persist(self) -> Path | None:
        if self._project is None or self._project_file is None:
            return None
        return self._data.save(self._project, self._project_file)

    # {
    # 責務: [create_project: start an editable manga workspace]
    # 処理: [initialize project schema and bind its resumable JSON file]
    # 引数: [path: project JSON path, title: project title, story_script: draft, page_count: target pages, genre: genre, layout_mode: page layout, reading_direction: panel reading, style: rendering target, characters/locations/props: optional bibles]
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
        project = MangaProject(
            id=uuid.uuid4().hex,
            title=title,
            premise=story_script[:300],
            genre=genre,
            target_page_count=page_count,
            reading_direction=reading_direction,
            style=style,
            layout_mode=layout_mode,
            story_script=story_script,
            characters=characters,
            locations=locations,
            props=props,
            backend_policy=backend_policy,
        )
        self._project = project
        self._project_file = Path(path).expanduser().resolve()
        self._persist()
        return project

    # {
    # 責務: [open_project: resume a saved manga project]
    # 処理: [load validated project state and bind its artifact directory]
    # 引数: [path: project JSON path]
    # 戻り値: [MangaProject: restored project]
    # }
    def open_project(self, path: str | Path) -> MangaProject:
        self._project_file = Path(path).expanduser().resolve(strict=True)
        self._project = self._data.load(self._project_file)
        return self._project

    # {
    # 責務: [register_backend: expose one external panel model to the project]
    # 処理: [register a unique backend name for panel-level generation routing]
    # 引数: [name: adapter ID, backend: image generation implementation]
    # 戻り値: [None: backend registered]
    # }
    def register_backend(self, name: str, backend: PanelGenerationBackend) -> None:
        self._backends.register(name, backend)

    # {
    # 責務: [available_backends: list configured image generators]
    # 処理: [expose stable IDs for editor selection]
    # 引数: [self: processor]
    # 戻り値: [tuple[str, ...]: available backend IDs]
    # }
    @property
    def available_backends(self) -> tuple[str, ...]:
        return self._backends.names

    # {
    # 責務: [save_project: persist the current editable state]
    # 処理: [save to the active project path or a newly selected path]
    # 引数: [path: optional replacement project path]
    # 戻り値: [Path: saved project JSON]
    # }
    def save_project(self, path: str | Path | None = None) -> Path:
        if self._project is None:
            raise RuntimeError("create or open a manga project first")
        if path is not None:
            self._project_file = Path(path).expanduser().resolve()
        if self._project_file is None:
            raise RuntimeError("a project file path is required")
        return self._data.save(self._project, self._project_file)

    # {
    # 責務: [plan: create an editable storyboard from the project script]
    # 処理: [delegate deterministic story decomposition and persist its plan]
    # 引数: [page_count: optional replacement page count]
    # 戻り値: [MangaProject: planned pages, panels and section summaries]
    # }
    def plan(self, page_count: int | None = None) -> MangaProject:
        self._project = plan_story(self.project, page_count)
        self._persist()
        return self.project

    # {
    # 責務: [edit_project: replace project story metadata or settings]
    # 処理: [replace allowed project-level user fields and persist]
    # 引数: [updates: named MangaProject fields]
    # 戻り値: [MangaProject: updated project]
    # }
    def edit_project(self, **updates: object) -> MangaProject:
        allowed = {
            "title",
            "premise",
            "genre",
            "target_page_count",
            "reading_direction",
            "style",
            "layout_mode",
            "story_script",
            "generation_settings",
            "backend_policy",
        }
        if not updates or not set(updates) <= allowed:
            raise ValueError("unsupported project fields in edit request")
        self._project = replace(self.project, **updates)
        self._persist()
        return self.project

    # {
    # 責務: [upsert_character: add or revise a reusable character bible]
    # 処理: [replace a character with the same ID or append a new entry]
    # 引数: [character: immutable CharacterSpec]
    # 戻り値: [MangaProject: updated project bible]
    # }
    def upsert_character(self, character: CharacterSpec) -> MangaProject:
        values = tuple(item for item in self.project.characters if item.id != character.id) + (
            character,
        )
        self._project = replace(self.project, characters=values)
        self._persist()
        return self.project

    # {
    # 責務: [upsert_location: add or revise a reusable location bible]
    # 処理: [replace a location with the same ID or append a new entry]
    # 引数: [location: immutable LocationSpec]
    # 戻り値: [MangaProject: updated project bible]
    # }
    def upsert_location(self, location: LocationSpec) -> MangaProject:
        values = tuple(item for item in self.project.locations if item.id != location.id) + (
            location,
        )
        self._project = replace(self.project, locations=values)
        self._persist()
        return self.project

    # {
    # 責務: [upsert_prop: add or revise one tracked prop]
    # 処理: [replace a prop with the same ID or append a new entry]
    # 引数: [prop: immutable PropSpec]
    # 戻り値: [MangaProject: updated project bible]
    # }
    def upsert_prop(self, prop: PropSpec) -> MangaProject:
        values = tuple(item for item in self.project.props if item.id != prop.id) + (prop,)
        self._project = replace(self.project, props=values)
        self._persist()
        return self.project

    # {
    # 責務: [edit_panel: update one panel's structured visual intent]
    # 処理: [replace one panel and invalidate its page composite while preserving other panels]
    # 引数: [panel: edited PanelSpec]
    # 戻り値: [MangaProject: updated project]
    # }
    def edit_panel(self, panel: PanelSpec) -> MangaProject:
        self._project = replace_panel(self.project, panel)
        self._persist()
        return self.project

    # {
    # 責務: [edit_dialogue: update one panel's separate editable lettering]
    # 処理: [replace the dialogue list without changing panel rendering or neighbor panels]
    # 引数: [panel_id: panel identifier, dialogue: replacement lines]
    # 戻り値: [MangaProject: updated project]
    # }
    def edit_dialogue(self, panel_id: str, dialogue: tuple[DialogueLine, ...]) -> MangaProject:
        _page, panel = self._find_panel(panel_id)
        updated = replace(panel, dialogue=dialogue)
        self._project = replace_panel(self.project, updated)
        self._persist()
        return self.project

    # {
    # 責務: [record_continuity_event: update story-section memory after an accepted panel]
    # 処理: [append an ordered character/costume/prop/location state event]
    # 引数: [entity_id: tracked entity, field: state field, value: new value, panel_id: source panel]
    # 戻り値: [MangaProject: updated continuity memory]
    # }
    def record_continuity_event(
        self, entity_id: str, field: str, value: str, panel_id: str
    ) -> MangaProject:
        self._project = record_continuity(self.project, entity_id, field, value, panel_id)
        self._persist()
        return self.project

    # {
    # 責務: [_find_panel: resolve one page/panel pair]
    # 処理: [scan the bounded project plan and raise when the panel is absent]
    # 引数: [self: processor, panel_id: selected panel ID]
    # 戻り値: [tuple[MangaPage, PanelSpec]: owning page and panel]
    # }
    def _find_panel(self, panel_id: str) -> tuple[MangaPage, PanelSpec]:
        for page in self.project.pages:
            for panel in page.panels:
                if panel.id == panel_id:
                    return page, panel
        raise KeyError(panel_id)

    # {
    # 責務: [load_panel_preview: retrieve a rendered image for the editor]
    # 処理: [read a panel asset through the Process-to-Data messenger]
    # 引数: [relative_path: project-relative image path]
    # 戻り値: [bytes: encoded preview]
    # }
    def load_panel_preview(self, relative_path: str) -> bytes:
        if self._project_file is None:
            raise RuntimeError("open or create a project before loading assets")
        return self._data.read_asset(self._project_file.parent, relative_path)

    # {
    # 責務: [_references_for: collect project reference images for one panel request]
    # 処理: [resolve character, location, and prop reference paths in stable order]
    # 引数: [panel: selected panel]
    # 戻り値: [tuple[str, ...]: backend reference image paths]
    # }
    def _references_for(self, panel: PanelSpec) -> tuple[str, ...]:
        project = self.project
        references = []
        for character in project.characters:
            if character.id in panel.character_ids:
                references.extend(character.reference_images)
        for location in project.locations:
            if location.id == panel.background_location_id:
                references.extend(location.reference_images)
        for prop in project.props:
            if prop.id in panel.prop_ids and prop.reference_image:
                references.append(prop.reference_image)
        return tuple(dict.fromkeys(references))

    # {
    # 責務: [render_panel: generate, rank and retain candidates for one panel]
    # 処理: [request independent panel renders, validate outputs, save all candidates and select the strongest measurable proxy]
    # 引数: [panel_id: selected panel, candidate_count: bounded candidate number, seed: optional base seed]
    # 戻り値: [tuple[MangaProject, PanelEvaluation]: updated project and chosen candidate evaluation]
    # }
    def render_panel(
        self, panel_id: str, candidate_count: int = 1, seed: int | None = None
    ) -> tuple[MangaProject, PanelEvaluation]:
        if not 1 <= candidate_count <= 8:
            raise ValueError("candidate_count must be within 1..8")
        page, panel = self._find_panel(panel_id)
        if self._project_file is None:
            raise RuntimeError("save the project before rendering panel assets")
        project_dir = self._project_file.parent
        candidates = []
        for attempt_index in range(candidate_count):
            try:
                candidate_seed = None if seed is None else seed + attempt_index
                request = PanelRenderRequest(
                    self.project,
                    page,
                    panel,
                    candidate_seed,
                    self._references_for(panel),
                    continuity_context(self.project, panel.id),
                    attempt_index + 1,
                )
                backend_name = panel.backend_id or self.project.backend_policy
                result = self._backends.resolve(backend_name).render_panel(request)
                dimensions = self._data.inspect_panel(result.image_bytes)
                evaluation = evaluate_panel_dimensions(self.project, page, panel, dimensions)
                score = sum(value for _name, value in evaluation.scores) / len(evaluation.scores)
                path = self._data.store_panel(project_dir, panel.id, result.image_bytes)
                candidates.append((score, path, result, evaluation))
            except Exception as error:
                self._mark_panel_error(panel, error)
                raise RuntimeError(
                    f"panel {panel.id} render attempt {attempt_index + 1} failed: {error}"
                ) from error
        winner_index = max(range(len(candidates)), key=lambda index: candidates[index][0])
        winner_score, _winner_path, winner_result, evaluation = candidates[winner_index]
        prior_paths = panel.candidate_image_paths
        new_paths = tuple(str(item[1].relative_to(project_dir)) for item in candidates)
        selected_index = len(prior_paths) + winner_index
        status = (
            PanelStatus.STORYBOARD
            if "storyboard" in winner_result.backend_id
            else PanelStatus.RENDERED
        )
        notes = tuple(
            dict.fromkeys(
                panel.evaluation_notes
                + winner_result.warnings
                + (f"best_of_n_proxy_score={winner_score:.3f}",)
                + evaluation.limitations
            )
        )
        updated = replace(
            panel,
            candidate_image_paths=prior_paths + new_paths,
            selected_candidate=selected_index,
            image_path=new_paths[winner_index],
            seed=winner_result.seed,
            status=status,
            evaluation_notes=notes,
        )
        self._project = replace_panel(self.project, updated)
        self._persist()
        return self.project, evaluation

    # {
    # 責務: [_mark_panel_error: persist one failed panel attempt for later retry]
    # 処理: [retain prior image candidates while marking the selected panel error]
    # 引数: [panel: failed panel, error: renderer or validation failure]
    # 戻り値: [None: project state saved]
    # }
    def _mark_panel_error(self, panel: PanelSpec, error: Exception) -> None:
        updated = replace(
            panel,
            status=PanelStatus.ERROR,
            evaluation_notes=panel.evaluation_notes
            + (f"render error: {type(error).__name__}: {error}",),
        )
        self._project = replace_panel(self.project, updated)
        self._persist()

    # {
    # 責務: [repair_panel: apply one injected local correction to an existing panel]
    # 処理: [send only the selected panel, original pixels and optional region to a repair adapter]
    # 引数: [panel_id: target panel, instruction: local correction, region: optional normalized area, seed: optional seed]
    # 戻り値: [tuple[MangaProject, PanelEvaluation]: updated project and quality proxies]
    # }
    def repair_panel(
        self,
        panel_id: str,
        instruction: str,
        region: tuple[float, float, float, float] | None = None,
        seed: int | None = None,
    ) -> tuple[MangaProject, PanelEvaluation]:
        if self._repair_backend is None:
            raise RuntimeError(
                "no panel repair adapter is configured; inject an inpaint or Expression Retouch adapter"
            )
        if self._project_file is None:
            raise RuntimeError("save the project before repairing panel assets")
        page, panel = self._find_panel(panel_id)
        if not panel.image_path:
            raise ValueError("render the panel before requesting a local repair")
        original = self._data.read_asset(self._project_file.parent, panel.image_path)
        request = PanelRepairRequest(self.project, page, panel, original, instruction, region, seed)
        result = self._repair_backend.repair_panel(request)
        dimensions = self._data.inspect_panel(result.image_bytes)
        evaluation = evaluate_panel_dimensions(self.project, page, panel, dimensions)
        path = self._data.store_panel(self._project_file.parent, panel.id, result.image_bytes)
        candidates = panel.candidate_image_paths + (
            str(path.relative_to(self._project_file.parent)),
        )
        notes = tuple(
            dict.fromkeys(
                panel.evaluation_notes
                + result.warnings
                + evaluation.limitations
                + (f"local repair instruction: {instruction}",)
            )
        )
        updated = replace(
            panel,
            candidate_image_paths=candidates,
            selected_candidate=len(candidates) - 1,
            image_path=candidates[-1],
            status=PanelStatus.RENDERED,
            seed=result.seed,
            evaluation_notes=notes,
        )
        self._project = replace_panel(self.project, updated)
        self._persist()
        return self.project, evaluation

    # {
    # 責務: [render_all_panels: build all planned panel artifacts]
    # 処理: [visit panels in page reading order and persist progress after each render]
    # 引数: [candidate_count: alternatives per panel, seed: optional reproducibility seed]
    # 戻り値: [MangaProject: project with all panel artifacts]
    # }
    def render_all_panels(self, candidate_count: int = 1, seed: int | None = None) -> MangaProject:
        panel_ids = tuple(
            panel.id
            for page in self.project.pages
            for panel in page.panels
            if panel.image_path is None
        )
        for index, panel_id in enumerate(panel_ids):
            self.render_panel(
                panel_id, candidate_count, None if seed is None else seed + index * candidate_count
            )
        return self.project

    # {
    # 責務: [select_candidate: select one stored alternative for a panel]
    # 処理: [change the chosen image path and invalidate only its page composite]
    # 引数: [panel_id: selected panel, candidate_index: zero-based alternative index]
    # 戻り値: [MangaProject: updated project]
    # }
    def select_candidate(self, panel_id: str, candidate_index: int) -> MangaProject:
        _page, panel = self._find_panel(panel_id)
        if not 0 <= candidate_index < len(panel.candidate_image_paths):
            raise IndexError("candidate index is outside available alternatives")
        updated = replace(
            panel,
            selected_candidate=candidate_index,
            image_path=panel.candidate_image_paths[candidate_index],
        )
        self._project = replace_panel(self.project, updated)
        self._persist()
        return self.project

    # {
    # 責務: [compose_page: create one final page image with separate text overlays]
    # 処理: [require each page panel to have a selected render, then compose and persist the page]
    # 引数: [page_id: selected page, page_size: optional output dimensions]
    # 戻り値: [tuple[MangaProject, tuple[str, ...]]: updated project and font/render warnings]
    # }
    def compose_page(
        self, page_id: str, page_size: tuple[int, int] = (1600, 2200)
    ) -> tuple[MangaProject, tuple[str, ...]]:
        if self._project_file is None:
            raise RuntimeError("save the project before composing pages")
        page = next((item for item in self.project.pages if item.id == page_id), None)
        if page is None:
            raise KeyError(page_id)
        if any(not panel.image_path for panel in page.panels):
            raise ValueError("render every panel before composing the page")
        path, warnings = self._data.compose_page(
            self.project, page, self._project_file.parent, page_size
        )
        relative_path = str(path.relative_to(self._project_file.parent))
        pages = tuple(
            replace(item, rendered_path=relative_path) if item.id == page_id else item
            for item in self.project.pages
        )
        self._project = replace(self.project, pages=pages)
        self._persist()
        return self.project, warnings
