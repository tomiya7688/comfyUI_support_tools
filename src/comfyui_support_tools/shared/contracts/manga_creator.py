"""Editable manga project, panel, continuity, and backend contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

NormalizedBox = tuple[float, float, float, float]


# {
# 責務: [ReadingDirection: define manga page panel-reading order]
# フィールド: [RIGHT_TO_LEFT, LEFT_TO_RIGHT, TOP_TO_BOTTOM]
# 処理: [keep reading direction explicit across layout and lettering]
# }
class ReadingDirection(str, Enum):
    RIGHT_TO_LEFT = "right_to_left"
    LEFT_TO_RIGHT = "left_to_right"
    TOP_TO_BOTTOM = "top_to_bottom"


# {
# 責務: [MangaLayoutMode: select a page layout family]
# フィールド: [MANGA_PAGE, FOUR_KOMA, WEBTOON, SPLASH]
# 処理: [make page geometry editable and backend-independent]
# }
class MangaLayoutMode(str, Enum):
    MANGA_PAGE = "manga_page"
    FOUR_KOMA = "four_koma"
    WEBTOON = "webtoon"
    SPLASH = "splash"


# {
# 責務: [MangaStyleMode: select an output rendering target]
# フィールド: [BLACK_AND_WHITE, COLOR, STORYBOARD]
# 処理: [describe line/screentone or rough storyboard intent]
# }
class MangaStyleMode(str, Enum):
    BLACK_AND_WHITE = "black_and_white"
    COLOR = "color"
    STORYBOARD = "storyboard"


# {
# 責務: [BalloonKind: define editable dialogue container shape]
# フィールド: [SPEECH, THOUGHT, SHOUT, WHISPER, NARRATION, SFX]
# 処理: [separate dialogue lettering from panel image generation]
# }
class BalloonKind(str, Enum):
    SPEECH = "speech"
    THOUGHT = "thought"
    SHOUT = "shout"
    WHISPER = "whisper"
    NARRATION = "narration"
    SFX = "sfx"


# {
# 責務: [PanelStatus: track the staged panel production state]
# フィールド: [PLANNED, STORYBOARD, RENDERED, REVIEWED, ERROR]
# 処理: [allow one panel to be regenerated without invalidating other panels]
# }
class PanelStatus(str, Enum):
    PLANNED = "planned"
    STORYBOARD = "storyboard"
    RENDERED = "rendered"
    REVIEWED = "reviewed"
    ERROR = "error"


# {
# 責務: [CharacterSpec: hold reusable fixed identity and variable character state]
# フィールド: [id, name, fixed traits, face/body, costumes, palette, speech, references, model hints]
# 処理: [share one editable character bible entry across all pages and panels]
# }
@dataclass(frozen=True)
class CharacterSpec:
    id: str
    name: str
    fixed_visual_attributes: tuple[str, ...] = ()
    variable_state: tuple[str, ...] = ()
    default_costume: str = ""
    alternate_costumes: tuple[str, ...] = ()
    accessories: tuple[str, ...] = ()
    color_palette: tuple[str, ...] = ()
    personality: str = ""
    speech_style: str = ""
    reference_images: tuple[str, ...] = ()
    model_hints: tuple[str, ...] = ()

    # {
    # 責務: [CharacterSpec.__post_init__: validate one character bible entry]
    # 処理: [require a stable ID and nonempty display name]
    # 引数: [self: character definition]
    # 戻り値: [None: valid character or ValueError]
    # }
    def __post_init__(self) -> None:
        _validate_identifier(self.id, "character")
        if not self.name.strip():
            raise ValueError("character name is required")


# {
# 責務: [LocationSpec: define a reusable scene/location bible entry]
# フィールド: [id, name, description, references, layout, objects, lighting, time, palette, style]
# 処理: [preserve recurring environment details between panels]
# }
@dataclass(frozen=True)
class LocationSpec:
    id: str
    name: str
    description: str = ""
    reference_images: tuple[str, ...] = ()
    layout: str = ""
    major_objects: tuple[str, ...] = ()
    lighting: str = ""
    time_of_day: str = ""
    palette: tuple[str, ...] = ()
    style: str = ""

    # {
    # 責務: [LocationSpec.__post_init__: validate one location bible entry]
    # 処理: [require a stable ID and nonempty display name]
    # 引数: [self: location definition]
    # 戻り値: [None: valid location or ValueError]
    # }
    def __post_init__(self) -> None:
        _validate_identifier(self.id, "location")
        if not self.name.strip():
            raise ValueError("location name is required")


# {
# 責務: [PropSpec: track a recurring story object]
# フィールド: [id, name, description, reference image, owner, continuity state]
# 処理: [retain visible object ownership and changes across pages]
# }
@dataclass(frozen=True)
class PropSpec:
    id: str
    name: str
    description: str = ""
    reference_image: str | None = None
    owner_character_id: str | None = None
    continuity_state: str = ""

    # {
    # 責務: [PropSpec.__post_init__: validate one recurring prop]
    # 処理: [require a stable ID and nonempty name]
    # 引数: [self: prop definition]
    # 戻り値: [None: valid prop or ValueError]
    # }
    def __post_init__(self) -> None:
        _validate_identifier(self.id, "prop")
        if not self.name.strip():
            raise ValueError("prop name is required")


# {
# 責務: [DialogueLine: store a speaker-attributed editable lettering line]
# フィールド: [id, text, speaker, kind, language, balloon placement and tail]
# 処理: [keep exact text separate from generated panel pixels]
# }
@dataclass(frozen=True)
class DialogueLine:
    id: str
    text: str
    speaker_character_id: str | None = None
    kind: BalloonKind = BalloonKind.SPEECH
    language: str = "ja"
    region: NormalizedBox = (0.66, 0.05, 0.28, 0.25)
    tail_target: tuple[float, float] | None = None
    vertical: bool = False

    # {
    # 責務: [DialogueLine.__post_init__: validate dialogue and normalized balloon geometry]
    # 処理: [bound text length and check the balloon rectangle and tail point]
    # 引数: [self: dialogue line]
    # 戻り値: [None: valid editable lettering or ValueError]
    # }
    def __post_init__(self) -> None:
        _validate_identifier(self.id, "dialogue")
        if not self.text.strip() or len(self.text) > 2000:
            raise ValueError("dialogue text must contain 1..2000 characters")
        _validate_box(self.region)
        if self.tail_target is not None:
            _validate_point(self.tail_target)


# {
# 責務: [PanelSpec: represent one editable story and visual panel]
# フィールド: [identity, page/order, narrative, participants, composition, dialogue, image, status]
# 処理: [preserve generation intent, rendering result, and dialogue per panel]
# }
@dataclass(frozen=True)
class PanelSpec:
    id: str
    page_id: str
    order: int
    bbox: NormalizedBox
    narrative_purpose: str = ""
    beat: str = ""
    character_ids: tuple[str, ...] = ()
    character_positions: tuple[tuple[str, NormalizedBox], ...] = ()
    poses: tuple[str, ...] = ()
    expressions: tuple[str, ...] = ()
    gaze: str = ""
    camera: str = ""
    shot: str = "medium"
    background_location_id: str | None = None
    prop_ids: tuple[str, ...] = ()
    action: str = ""
    emotion: str = ""
    dialogue: tuple[DialogueLine, ...] = ()
    sound_effects: tuple[str, ...] = ()
    prompt: str = ""
    reference_ids: tuple[str, ...] = ()
    backend_id: str | None = None
    preserve_constraints: tuple[str, ...] = ()
    status: PanelStatus = PanelStatus.PLANNED
    image_path: str | None = None
    candidate_image_paths: tuple[str, ...] = ()
    selected_candidate: int = 0
    seed: int | None = None
    evaluation_notes: tuple[str, ...] = ()

    # {
    # 責務: [PanelSpec.__post_init__: validate one panel plan]
    # 処理: [require stable identifiers, nonnegative order, and normalized page geometry]
    # 引数: [self: panel specification]
    # 戻り値: [None: valid panel or ValueError]
    # }
    def __post_init__(self) -> None:
        _validate_identifier(self.id, "panel")
        _validate_identifier(self.page_id, "page")
        if self.order < 0:
            raise ValueError("panel order must be nonnegative")
        _validate_box(self.bbox)
        for _character_id, box in self.character_positions:
            _validate_box(box)
            if (
                box[0] < self.bbox[0]
                or box[1] < self.bbox[1]
                or box[0] + box[2] > self.bbox[0] + self.bbox[2]
                or box[1] + box[3] > self.bbox[1] + self.bbox[3]
            ):
                raise ValueError("character positions must be contained within their panel")
        if self.candidate_image_paths and not 0 <= self.selected_candidate < len(
            self.candidate_image_paths
        ):
            raise ValueError("selected panel candidate index is outside the available candidates")


# {
# 責務: [MangaPage: group ordered panels and page-level layout policy]
# フィールド: [id, page number, layout mode, panels, page note, rendered page]
# 処理: [keep panel order and page editing independent from flattened output image]
# }
@dataclass(frozen=True)
class MangaPage:
    id: str
    page_number: int
    layout_mode: MangaLayoutMode
    panels: tuple[PanelSpec, ...]
    page_note: str = ""
    rendered_path: str | None = None

    # {
    # 責務: [MangaPage.__post_init__: validate page membership and panel layout]
    # 処理: [require positive page number, matching parent IDs, unique panel IDs and order]
    # 引数: [self: manga page]
    # 戻り値: [None: valid page or ValueError]
    # }
    def __post_init__(self) -> None:
        _validate_identifier(self.id, "page")
        if self.page_number < 1:
            raise ValueError("page numbers start at 1")
        if any(panel.page_id != self.id for panel in self.panels):
            raise ValueError("panel page IDs must match their containing page")
        if len({panel.id for panel in self.panels}) != len(self.panels):
            raise ValueError("panel IDs must be unique within a page")
        if len({panel.order for panel in self.panels}) != len(self.panels):
            raise ValueError("panel reading order must be unique within a page")


# {
# 責務: [ContinuityEvent: store a durable state change in long-form story memory]
# フィールド: [event id, sequence, entity, field, value, source panel]
# 処理: [apply accepted prop/costume/location changes to later panels]
# }
@dataclass(frozen=True)
class ContinuityEvent:
    id: str
    sequence: int
    entity_id: str
    field: str
    value: str
    source_panel_id: str

    # {
    # 責務: [ContinuityEvent.__post_init__: validate one ordered memory event]
    # 処理: [require stable IDs and a nonnegative story sequence]
    # 引数: [self: continuity event]
    # 戻り値: [None: valid event or ValueError]
    # }
    def __post_init__(self) -> None:
        _validate_identifier(self.id, "continuity event")
        if self.sequence < 0 or not self.entity_id.strip() or not self.field.strip():
            raise ValueError("continuity event sequence, entity, and field are required")


# {
# 責務: [StorySection: preserve a named ordered narrative memory segment]
# フィールド: [id, title, summary, page range, continuity snapshot]
# 処理: [split long stories into resumable sections]
# }
@dataclass(frozen=True)
class StorySection:
    id: str
    title: str
    summary: str
    start_page: int
    end_page: int
    active_character_ids: tuple[str, ...] = ()
    active_location_id: str | None = None
    memory_notes: tuple[str, ...] = ()

    # {
    # 責務: [StorySection.__post_init__: validate one story memory range]
    # 処理: [require a nonempty title and a valid positive page interval]
    # 引数: [self: story section]
    # 戻り値: [None: valid story section or ValueError]
    # }
    def __post_init__(self) -> None:
        _validate_identifier(self.id, "story section")
        if not self.title.strip() or self.start_page < 1 or self.end_page < self.start_page:
            raise ValueError("story section title and page range are invalid")


# {
# 責務: [MangaProject: own the editable long-form story production state]
# フィールド: [metadata, bibles, sections, pages, continuity, generation policies]
# 処理: [store project data as the source of truth for storyboard and final rendering]
# }
@dataclass(frozen=True)
class MangaProject:
    id: str
    title: str
    premise: str
    genre: str
    target_page_count: int
    reading_direction: ReadingDirection
    style: MangaStyleMode
    layout_mode: MangaLayoutMode
    story_script: str
    characters: tuple[CharacterSpec, ...] = ()
    locations: tuple[LocationSpec, ...] = ()
    props: tuple[PropSpec, ...] = ()
    story_sections: tuple[StorySection, ...] = ()
    pages: tuple[MangaPage, ...] = ()
    continuity_memory: tuple[ContinuityEvent, ...] = ()
    generation_settings: tuple[tuple[str, str], ...] = ()
    backend_policy: str = "storyboard"
    schema_version: int = 1

    # {
    # 責務: [MangaProject.__post_init__: validate project-level entity references]
    # 処理: [check unique IDs, target page bounds, and all panel bible references]
    # 引数: [self: manga project]
    # 戻り値: [None: valid editable project or ValueError]
    # }
    def __post_init__(self) -> None:
        _validate_identifier(self.id, "project")
        if not self.title.strip() or not 1 <= self.target_page_count <= 500:
            raise ValueError("project title and target page count 1..500 are required")
        if len(self.story_script) > 2_000_000:
            raise ValueError("story script exceeds the 2 MiB project limit")
        if self.schema_version != 1:
            raise ValueError("unsupported manga project schema version")
        entities = (self.characters, self.locations, self.props, self.story_sections, self.pages)
        for collection in entities:
            identifiers = [item.id for item in collection]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError("project entity identifiers must be unique within each collection")
        known_characters = {item.id for item in self.characters}
        known_locations = {item.id for item in self.locations}
        known_props = {item.id for item in self.props}
        page_numbers = [page.page_number for page in self.pages]
        if len(page_numbers) != len(set(page_numbers)) or any(
            number > self.target_page_count for number in page_numbers
        ):
            raise ValueError("page numbers must be unique and within target page count")
        panel_ids = [panel.id for page in self.pages for panel in page.panels]
        dialogue_ids = [
            line.id for page in self.pages for panel in page.panels for line in panel.dialogue
        ]
        if len(panel_ids) != len(set(panel_ids)) or len(dialogue_ids) != len(set(dialogue_ids)):
            raise ValueError("panel and dialogue identifiers must be unique across the project")
        for page in self.pages:
            for panel in page.panels:
                if not set(panel.character_ids) <= known_characters:
                    raise ValueError(f"panel {panel.id} references an unknown character")
                positioned_character_ids = [
                    character_id for character_id, _box in panel.character_positions
                ]
                if (
                    len(positioned_character_ids) != len(set(positioned_character_ids))
                    or not set(positioned_character_ids) <= known_characters
                ):
                    raise ValueError(f"panel {panel.id} has invalid character positions")
                if (
                    panel.background_location_id
                    and panel.background_location_id not in known_locations
                ):
                    raise ValueError(f"panel {panel.id} references an unknown location")
                if not set(panel.prop_ids) <= known_props:
                    raise ValueError(f"panel {panel.id} references an unknown prop")
                for line in panel.dialogue:
                    if (
                        line.speaker_character_id
                        and line.speaker_character_id not in known_characters
                    ):
                        raise ValueError(f"dialogue {line.id} references an unknown speaker")
        for prop in self.props:
            if prop.owner_character_id and prop.owner_character_id not in known_characters:
                raise ValueError(f"prop {prop.id} references an unknown owner")
        for section in self.story_sections:
            if not set(section.active_character_ids) <= known_characters:
                raise ValueError(f"story section {section.id} references an unknown character")
            if section.active_location_id and section.active_location_id not in known_locations:
                raise ValueError(f"story section {section.id} references an unknown location")
        event_sequences = [event.sequence for event in self.continuity_memory]
        if len(event_sequences) != len(set(event_sequences)):
            raise ValueError("continuity event sequence numbers must be unique")
        for event in self.continuity_memory:
            if event.source_panel_id not in set(panel_ids):
                raise ValueError("continuity events must reference an existing panel")
            if event.entity_id not in known_characters | known_locations | known_props:
                raise ValueError(
                    "continuity events must reference a known character, location, or prop"
                )
        if any(section.end_page > self.target_page_count for section in self.story_sections):
            raise ValueError("story section exceeds target page count")


# {
# 責務: [PanelRenderRequest: package one panel and its continuity/quality constraints]
# フィールド: [project, page, panel, character/location/prop bibles, seed, references]
# 処理: [give image backends sufficient context without coupling to a model family]
# }
@dataclass(frozen=True)
class PanelRenderRequest:
    project: MangaProject
    page: MangaPage
    panel: PanelSpec
    seed: int | None = None
    reference_paths: tuple[str, ...] = ()
    continuity_context: tuple[ContinuityEvent, ...] = ()
    attempt: int = 1


# {
# 責務: [PanelRenderResult: report one rendered panel artifact]
# フィールド: [image bytes, backend id, seed, warnings]
# 処理: [make generated content reproducible and auditable]
# }
@dataclass(frozen=True)
class PanelRenderResult:
    image_bytes: bytes
    backend_id: str
    seed: int | None = None
    warnings: tuple[str, ...] = ()


# {
# 責務: [PanelRepairRequest: package one selected local image repair]
# フィールド: [project, page, panel, original image, instruction, local region, preservation constraints]
# 処理: [allow expression, face, text, or composition repair without replacing other page panels]
# }
@dataclass(frozen=True)
class PanelRepairRequest:
    project: MangaProject
    page: MangaPage
    panel: PanelSpec
    original_image: bytes
    instruction: str
    region: NormalizedBox | None = None
    seed: int | None = None

    # {
    # 責務: [PanelRepairRequest.__post_init__: validate a targeted panel repair]
    # 処理: [require a bounded instruction and optional normalized local area]
    # 引数: [self: panel repair request]
    # 戻り値: [None: valid request or ValueError]
    # }
    def __post_init__(self) -> None:
        if not self.instruction.strip() or len(self.instruction) > 2000:
            raise ValueError("panel repair instruction must contain 1..2000 characters")
        if self.region is not None:
            _validate_box(self.region)


# {
# 責務: [PanelRepairBackend: define an optional local image repair adapter]
# フィールド: [repair_panel callable]
# 処理: [adapt Expression Retouch, inpaint, or other local repair tools]
# 引数: [request: targeted panel edit and preservation constraints]
# 戻り値: [PanelRenderResult: repaired panel image]
# }
class PanelRepairBackend(Protocol):
    # {
    # 責務: [repair_panel: modify a bounded panel region]
    # 処理: [preserve all content outside the requested local edit when supported]
    # 引数: [request: panel repair context]
    # 戻り値: [PanelRenderResult: repaired panel candidate]
    # }
    def repair_panel(self, request: PanelRepairRequest) -> PanelRenderResult: ...


# {
# 責務: [PanelGenerationBackend: define a replaceable panel image generator]
# フィールド: [render_panel callable]
# 処理: [allow a ComfyUI/model adapter or offline storyboard renderer]
# 引数: [request: panel and project context]
# 戻り値: [PanelRenderResult: generated panel image]
# }
class PanelGenerationBackend(Protocol):
    # {
    # 責務: [render_panel: generate a panel image from structured visual intent]
    # 処理: [respect references, pose, layout, identity and prompt constraints where supported]
    # 引数: [request: complete panel generation context]
    # 戻り値: [PanelRenderResult: encoded image and provenance]
    # }
    def render_panel(self, request: PanelRenderRequest) -> PanelRenderResult: ...


# {
# 責務: [PanelEvaluation: report independent visual and continuity signals]
# フィールド: [panel ID, score tuples, issues, limitations]
# 処理: [keep proxy checks separate from human-reviewed quality claims]
# }
@dataclass(frozen=True)
class PanelEvaluation:
    panel_id: str
    scores: tuple[tuple[str, float], ...]
    issues: tuple[str, ...]
    limitations: tuple[str, ...] = ()

    # {
    # 責務: [PanelEvaluation.__post_init__: validate bounded panel scores]
    # 処理: [require finite scores within the unit interval]
    # 引数: [self: panel evaluation]
    # 戻り値: [None: valid evaluation or ValueError]
    # }
    def __post_init__(self) -> None:
        _validate_identifier(self.panel_id, "panel evaluation")
        if any(not math.isfinite(score) or not 0 <= score <= 1 for _name, score in self.scores):
            raise ValueError("panel scores must be finite values within 0..1")


# {
# 責務: [_validate_identifier: enforce portable stable IDs]
# 処理: [require nonempty bounded identifiers without path separators]
# 引数: [identifier: candidate ID, entity: entity kind]
# 戻り値: [None: valid identifier or ValueError]
# }
def _validate_identifier(identifier: str, entity: str) -> None:
    if (
        not identifier
        or len(identifier) > 128
        or identifier in {".", ".."}
        or "/" in identifier
        or "\\" in identifier
    ):
        raise ValueError(f"{entity} ID must be a safe nonempty identifier")


# {
# 責務: [_validate_point: validate a normalized page coordinate]
# 処理: [require finite coordinates inside 0..1]
# 引数: [point: normalized x/y point]
# 戻り値: [None: valid point or ValueError]
# }
def _validate_point(point: tuple[float, float]) -> None:
    if len(point) != 2 or any(not math.isfinite(value) or not 0 <= value <= 1 for value in point):
        raise ValueError("manga geometry must use finite normalized coordinates")


# {
# 責務: [_validate_box: validate one normalized page rectangle]
# 処理: [require positive width/height wholly within page bounds]
# 引数: [box: x/y/width/height rectangle]
# 戻り値: [None: valid normalized box or ValueError]
# }
def _validate_box(box: NormalizedBox) -> None:
    if len(box) != 4 or any(not math.isfinite(value) for value in box):
        raise ValueError("manga panel geometry must contain four finite values")
    x, y, width, height = box
    if width <= 0 or height <= 0 or x < 0 or y < 0 or x + width > 1 or y + height > 1:
        raise ValueError("manga panel boxes must be positive and within normalized page bounds")
