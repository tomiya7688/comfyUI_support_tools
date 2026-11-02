"""Long-form story memory and immutable project-edit helpers."""

from __future__ import annotations

from dataclasses import replace

from comfyui_support_tools.shared.contracts.manga_creator import (
    ContinuityEvent,
    MangaProject,
    PanelSpec,
)


# {
# 責務: [panel_position: locate a panel in project reading order]
# 処理: [map panel IDs to page/panel sequence positions]
# 引数: [project: manga project, panel_id: target panel ID]
# 戻り値: [tuple[int, int]: page number and panel order]
# }
def panel_position(project: MangaProject, panel_id: str) -> tuple[int, int]:
    for page in project.pages:
        for panel in page.panels:
            if panel.id == panel_id:
                return page.page_number, panel.order
    raise KeyError(panel_id)


# {
# 責務: [continuity_context: resolve active long-form state before one panel]
# 処理: [apply only prior events and retain the latest state for each entity field]
# 引数: [project: manga project, panel_id: target panel ID]
# 戻り値: [tuple[ContinuityEvent, ...]: effective entity state records]
# }
def continuity_context(project: MangaProject, panel_id: str) -> tuple[ContinuityEvent, ...]:
    target_position = panel_position(project, panel_id)
    previous_panel_ids = {
        panel.id
        for page in project.pages
        for panel in page.panels
        if (page.page_number, panel.order) < target_position
    }
    latest: dict[tuple[str, str], ContinuityEvent] = {}
    for event in sorted(project.continuity_memory, key=lambda item: item.sequence):
        if event.source_panel_id in previous_panel_ids:
            latest[(event.entity_id, event.field)] = event
    return tuple(sorted(latest.values(), key=lambda item: item.sequence))


# {
# 責務: [record_continuity: append a state event from an accepted panel]
# 処理: [assign the next stable sequence number and replace immutable project memory]
# 引数: [project: current state, entity_id: changed character/location/prop, field: state name, value: new state, source_panel_id: accepted panel]
# 戻り値: [MangaProject: updated memory]
# }
def record_continuity(
    project: MangaProject,
    entity_id: str,
    field: str,
    value: str,
    source_panel_id: str,
) -> MangaProject:
    panel_position(project, source_panel_id)
    event = ContinuityEvent(
        id=f"memory-{len(project.continuity_memory) + 1:06d}",
        sequence=max((item.sequence for item in project.continuity_memory), default=-1) + 1,
        entity_id=entity_id,
        field=field,
        value=value,
        source_panel_id=source_panel_id,
    )
    return replace(project, continuity_memory=project.continuity_memory + (event,))


# {
# 責務: [replace_panel: immutably replace one planned or rendered panel]
# 処理: [replace one panel and invalidate only its page composition path]
# 引数: [project: current project, updated_panel: replacement panel]
# 戻り値: [MangaProject: updated project with other panels preserved]
# }
def replace_panel(project: MangaProject, updated_panel: PanelSpec) -> MangaProject:
    matched = False
    pages = []
    for page in project.pages:
        panels = []
        for panel in page.panels:
            if panel.id == updated_panel.id:
                if panel.page_id != updated_panel.page_id:
                    raise ValueError("panel page identity cannot change during edit")
                panels.append(updated_panel)
                matched = True
            else:
                panels.append(panel)
        pages.append(
            replace(page, panels=tuple(panels), rendered_path=None)
            if any(panel.id == updated_panel.id for panel in page.panels)
            else page
        )
    if not matched:
        raise KeyError(updated_panel.id)
    return replace(project, pages=tuple(pages))
