"""Small honest panel quality proxies for candidate ranking and review."""

from __future__ import annotations

import math

from comfyui_support_tools.shared.contracts.manga_creator import (
    MangaPage,
    MangaProject,
    PanelEvaluation,
    PanelSpec,
)


# {
# 責務: [evaluate_panel_dimensions: score one valid rendered candidate using measurable proxies]
# 処理: [compare generated aspect and resolution with panel requirements and report unmeasured semantics]
# 引数: [project: manga project, page: containing page, panel: target panel, dimensions: rendered width and height]
# 戻り値: [PanelEvaluation: dimension proxy scores and explicit limitations]
# }
def evaluate_panel_dimensions(
    project: MangaProject,
    page: MangaPage,
    panel: PanelSpec,
    dimensions: tuple[int, int],
) -> PanelEvaluation:
    del page
    width, height = dimensions
    expected_ratio = panel.bbox[2] * 0.73 / panel.bbox[3]
    actual_ratio = width / height
    aspect_score = max(0.0, min(1.0, math.exp(-abs(math.log(actual_ratio / expected_ratio)))))
    resolution_score = max(0.0, min(1.0, min(width, height) / 640))
    text_size = sum(len(line.text) for line in panel.dialogue)
    text_fit_score = 1.0 if text_size <= 100 else max(0.0, 1 - (text_size - 100) / 500)
    scores = (
        ("panel_aspect_proxy", aspect_score),
        ("minimum_resolution_proxy", resolution_score),
        ("dialogue_density_proxy", text_fit_score),
    )
    notes = list(panel.evaluation_notes)
    if not project.characters and panel.character_ids:
        notes.append("panel references characters but the project Character Bible is empty")
    return PanelEvaluation(
        panel.id,
        scores,
        tuple(notes),
        (
            "character identity, anatomy, pose accuracy, OCR and story semantics were not measured",
            "image-model quality requires a configured model backend and human review",
        ),
    )
