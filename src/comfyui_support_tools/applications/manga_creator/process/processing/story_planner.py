"""Deterministic text-to-page/panel storyboard planner baseline."""

from __future__ import annotations

import re
from dataclasses import replace

from comfyui_support_tools.shared.contracts.manga_creator import (
    BalloonKind,
    CharacterSpec,
    DialogueLine,
    MangaLayoutMode,
    MangaPage,
    MangaProject,
    PanelSpec,
    ReadingDirection,
    StorySection,
)

_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？.!?])\s*|\n+")


# {
# 責務: [_story_units: split a screenplay or prose draft into compact planning beats]
# 処理: [preserve nonempty lines and divide long paragraphs at sentence punctuation]
# 引数: [script: user-authored story draft]
# 戻り値: [tuple[str, ...]: ordered narrative units]
# }
def _story_units(script: str) -> tuple[str, ...]:
    units = []
    for line in script.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if not cleaned:
            continue
        split_units = [part.strip() for part in _SENTENCE_BOUNDARY.split(cleaned) if part.strip()]
        units.extend(split_units or (cleaned,))
    return tuple(units)


# {
# 責務: [_partition: divide ordered story units into page/panel groups]
# 処理: [allocate contiguous units with a bounded number per group]
# 引数: [units: story beats, group_count: destination count]
# 戻り値: [tuple[tuple[str, ...], ...]: contiguous content groups]
# }
def _partition(units: tuple[str, ...], group_count: int) -> tuple[tuple[str, ...], ...]:
    if group_count <= 0:
        return ()
    groups = [[] for _ in range(group_count)]
    for index, unit in enumerate(units):
        bucket = min(group_count - 1, index * group_count // max(1, len(units)))
        groups[bucket].append(unit)
    return tuple(tuple(group) for group in groups)


# {
# 責務: [_panel_count: choose a baseline panel count for one page]
# 処理: [honor layout modes and use a restrained count for unread drafts]
# 引数: [mode: selected page family, available_units: allocated story beats]
# 戻り値: [int: panel count from 1 to 6]
# }
def _panel_count(mode: MangaLayoutMode, available_units: int) -> int:
    if mode == MangaLayoutMode.SPLASH:
        return 1
    if mode == MangaLayoutMode.FOUR_KOMA:
        return 4
    if mode == MangaLayoutMode.WEBTOON:
        return max(1, min(4, available_units or 2))
    return max(2, min(6, available_units or 4))


# {
# 責務: [_layout_boxes: return panel boxes in declared reading order]
# 処理: [apply page-family geometry and reverse each manga row for right-to-left reading]
# 引数: [mode: layout family, count: panel count, direction: reading direction]
# 戻り値: [tuple[tuple[float, float, float, float], ...]: normalized page boxes]
# }
def _layout_boxes(
    mode: MangaLayoutMode, count: int, direction: ReadingDirection
) -> tuple[tuple[float, float, float, float], ...]:
    if mode == MangaLayoutMode.SPLASH:
        return ((0.035, 0.025, 0.93, 0.95),)
    if mode == MangaLayoutMode.FOUR_KOMA:
        height, gap = 0.225, 0.018
        return tuple((0.12, 0.03 + index * (height + gap), 0.76, height) for index in range(4))
    if mode == MangaLayoutMode.WEBTOON:
        height, gap = (0.94 - 0.04 * (count - 1)) / count, 0.04
        return tuple((0.04, 0.02 + index * (height + gap), 0.92, height) for index in range(count))
    rows = (count + 1) // 2
    height = (0.94 - 0.018 * (rows - 1)) / rows
    cells = []
    for row in range(rows):
        row_count = min(2, count - row * 2)
        columns = (
            [0, 1] if row_count == 2 else [1 if direction == ReadingDirection.RIGHT_TO_LEFT else 0]
        )
        if row_count == 2 and direction == ReadingDirection.RIGHT_TO_LEFT:
            columns.reverse()
        for column in columns:
            cells.append((0.04 + column * 0.47, 0.03 + row * (height + 0.018), 0.45, height))
    return tuple(cells)


# {
# 責務: [_characters_in: resolve explicit character mentions in one story unit]
# 処理: [match longest character names first and preserve bible order]
# 引数: [text: narrative unit, characters: character bible]
# 戻り値: [tuple[CharacterSpec, ...]: mentioned character records]
# }
def _characters_in(text: str, characters: tuple[CharacterSpec, ...]) -> tuple[CharacterSpec, ...]:
    return tuple(
        character
        for character in sorted(characters, key=lambda item: len(item.name), reverse=True)
        if character.name and character.name.casefold() in text.casefold()
    )


# {
# 責務: [_dialogue_lines: parse explicit speaker-prefixed script lines]
# 処理: [match 'Name: text' lines to Character Bible entries and preserve exact text]
# 引数: [text: panel story text, characters: character bible, panel_id: stable panel ID]
# 戻り値: [tuple[DialogueLine, ...]: speaker-attributed editable dialogue]
# }
def _dialogue_lines(
    text: str, characters: tuple[CharacterSpec, ...], panel_id: str
) -> tuple[DialogueLine, ...]:
    character_names = {character.name: character for character in characters}
    lines = []
    for line_index, line in enumerate(text.splitlines()):
        match = re.match(r"^\s*([^:：]{1,80})\s*[:：]\s*(.+?)\s*$", line)
        if not match:
            continue
        speaker = character_names.get(match.group(1))
        lines.append(
            DialogueLine(
                id=f"{panel_id}-dialogue-{line_index + 1}",
                text=match.group(2),
                speaker_character_id=speaker.id if speaker else None,
                kind=BalloonKind.SPEECH if speaker else BalloonKind.NARRATION,
            )
        )
    return tuple(lines)


# {
# 責務: [plan_story: create editable pages and panels from a project script]
# 処理: [split story units, choose a layout template, create panel plans and page memory snapshots]
# 引数: [project: project with story bible and script, page_count: optional output page count]
# 戻り値: [MangaProject: immutable project with planned sections and pages]
# }
def plan_story(project: MangaProject, page_count: int | None = None) -> MangaProject:
    count = page_count if page_count is not None else project.target_page_count
    if not 1 <= count <= 500:
        raise ValueError("page_count must be within 1..500")
    units = _story_units(project.story_script)
    if not units:
        raise ValueError("add a story or script before creating a plan")
    page_units = _partition(units, count)
    pages = []
    sections = []
    for page_index, assigned_units in enumerate(page_units, start=1):
        page_id = f"page-{page_index:03d}"
        panel_count = _panel_count(project.layout_mode, len(assigned_units))
        panel_units = _partition(assigned_units, panel_count)
        boxes = _layout_boxes(project.layout_mode, panel_count, project.reading_direction)
        panels = []
        for panel_index, (content, box) in enumerate(zip(panel_units, boxes, strict=True), start=1):
            panel_id = f"{page_id}-panel-{panel_index:02d}"
            panel_text = "\n".join(content)
            mentioned = _characters_in(panel_text, project.characters)
            if not mentioned and len(project.characters) == 1:
                mentioned = project.characters
            character_ids = tuple(character.id for character in mentioned)
            char_positions = tuple(
                (
                    character.id,
                    (
                        box[0] + box[2] * (0.08 + index * 0.28),
                        box[1] + box[3] * 0.12,
                        box[2] * 0.22,
                        box[3] * 0.7,
                    ),
                )
                for index, character in enumerate(mentioned[:3])
            )
            matched_location = next(
                (
                    location
                    for location in project.locations
                    if location.name.casefold() in panel_text.casefold()
                ),
                project.locations[0] if len(project.locations) == 1 else None,
            )
            matched_props = tuple(
                prop.id for prop in project.props if prop.name.casefold() in panel_text.casefold()
            )
            purpose = (
                "setup"
                if panel_index == 1
                else "reveal"
                if panel_index == panel_count
                else "reaction"
                if panel_index % 2 == 0
                else "action"
            )
            panels.append(
                PanelSpec(
                    id=panel_id,
                    page_id=page_id,
                    order=panel_index - 1,
                    bbox=box,
                    narrative_purpose=purpose,
                    beat=purpose,
                    character_ids=character_ids,
                    character_positions=char_positions,
                    camera="reader-facing composition; vary shot across adjacent panels",
                    shot=("close_up" if panel_index % 3 == 0 else "medium"),
                    background_location_id=matched_location.id if matched_location else None,
                    prop_ids=matched_props,
                    action=panel_text,
                    dialogue=_dialogue_lines(panel_text, project.characters, panel_id),
                    prompt=panel_text,
                    preserve_constraints=tuple(
                        f"preserve character identity: {item.name}" for item in mentioned
                    ),
                )
            )
        pages.append(MangaPage(page_id, page_index, project.layout_mode, tuple(panels)))
        active_characters = tuple(
            dict.fromkeys(character_id for panel in panels for character_id in panel.character_ids)
        )
        sections.append(
            StorySection(
                id=f"section-{page_index:03d}",
                title=f"Page {page_index} story beats",
                summary=" ".join(assigned_units),
                start_page=page_index,
                end_page=page_index,
                active_character_ids=active_characters,
                active_location_id=panels[0].background_location_id if panels else None,
                memory_notes=(
                    "Storyboard planner baseline; review panel causality, camera, pose, and dialogue.",
                ),
            )
        )
    planned = replace(
        project, target_page_count=count, pages=tuple(pages), story_sections=tuple(sections)
    )
    return planned
