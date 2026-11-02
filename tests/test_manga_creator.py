"""End-to-end checks for the storyboard-first Manga Creator pipeline."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from comfyui_support_tools.applications.manga_creator.data.messenger.project_messenger import (
    MangaProjectMessenger as DataMessenger,
)
from comfyui_support_tools.applications.manga_creator.data.processing.comfyui_backend import (
    ComfyUIPanelBackend,
)
from comfyui_support_tools.applications.manga_creator.data.processing.project_store import (
    MangaProjectStore,
    project_from_json,
    project_to_json,
)
from comfyui_support_tools.applications.manga_creator.process.messenger.project_messenger import (
    MangaProjectMessenger as ProcessMessenger,
)
from comfyui_support_tools.applications.manga_creator.process.processing.continuity import (
    continuity_context,
    record_continuity,
)
from comfyui_support_tools.applications.manga_creator.process.processing.production import (
    MangaProductionProcessor,
)
from comfyui_support_tools.applications.manga_creator.process.processing.story_planner import (
    plan_story,
)
from comfyui_support_tools.applications.manga_creator.process.processing.storyboard_backend import (
    StoryboardRenderBackend,
)
from comfyui_support_tools.shared.contracts.manga_creator import (
    CharacterSpec,
    LocationSpec,
    MangaLayoutMode,
    MangaProject,
    MangaStyleMode,
    PanelRenderRequest,
    PanelRenderResult,
    PropSpec,
    ReadingDirection,
)


# {
# 責務: [_project: create a reusable two-character manga fixture]
# 処理: [build a validated story with dialogue, a location, and a prop]
# 引数: [なし: fixed test data]
# 戻り値: [MangaProject: validated project]
# }
def _project() -> MangaProject:
    """Build a compact two-character story fixture."""
    return MangaProject(
        id="demo",
        title="Rainy meeting",
        premise="Two travelers meet near a station.",
        genre="slice_of_life",
        target_page_count=2,
        reading_direction=ReadingDirection.RIGHT_TO_LEFT,
        style=MangaStyleMode.STORYBOARD,
        layout_mode=MangaLayoutMode.FOUR_KOMA,
        story_script="Aki: Where is the train?\nMio: It is late.\nAki finds an umbrella.\nThey walk home together.",
        characters=(
            CharacterSpec("aki", "Aki", ("short dark hair",), default_costume="school uniform"),
            CharacterSpec("mio", "Mio", ("long hair",), default_costume="rain coat"),
        ),
        locations=(LocationSpec("station", "Station", "Small rural station"),),
        props=(PropSpec("umbrella", "umbrella", "Blue umbrella", owner_character_id="aki"),),
    )


# {
# 責務: [MangaCreatorTests: verify story planning, rendering, persistence, and adapters]
# フィールド: [unittest assertion helpers and temporary directories]
# 処理: [exercise project schemas, continuity, panel generation, and resume]
# }
class MangaCreatorTests(unittest.TestCase):
    """Verify the structured story, render, lettering, and resume workflow."""

    # {
    # 責務: [test_project_json_round_trip_and_untrusted_schema_checks: validate project interchange]
    # 処理: [roundtrip project schema and reject unknown fields and duplicate keys]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_project_json_round_trip_and_untrusted_schema_checks(self) -> None:
        project = _project()
        self.assertEqual(project_from_json(project_to_json(project)), project)
        encoded = project_to_json(project)
        with self.assertRaises(ValueError):
            project_from_json(
                encoded.replace('"title": "Rainy meeting"', '"title": "Rainy meeting", "hidden": 1')
            )
        with self.assertRaises(ValueError):
            project_from_json('{"id":"demo","id":"other"}')

    # {
    # 責務: [test_story_planner_creates_editable_right_to_left_four_koma_panels: verify decomposition]
    # 処理: [plan pages and check four-koma geometry, reading order, and dialogue speakers]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_story_planner_creates_editable_right_to_left_four_koma_panels(self) -> None:
        planned = plan_story(_project())
        self.assertEqual(len(planned.pages), 2)
        self.assertTrue(all(len(page.panels) == 4 for page in planned.pages))
        first_row = planned.pages[0].panels
        self.assertLess(first_row[0].bbox[1], first_row[1].bbox[1])
        self.assertTrue(
            any(
                line.speaker_character_id == "aki" for panel in first_row for line in panel.dialogue
            )
        )
        self.assertTrue(
            all(
                set(panel.character_ids) <= {"aki", "mio"}
                for page in planned.pages
                for panel in page.panels
            )
        )

    # {
    # 責務: [test_continuity_memory_only_applies_after_its_source_panel: verify memory chronology]
    # 処理: [record a state event and check that it applies only to following panels]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_continuity_memory_only_applies_after_its_source_panel(self) -> None:
        planned = plan_story(_project())
        first = planned.pages[0].panels[0]
        second = planned.pages[0].panels[1]
        updated = record_continuity(planned, "aki", "held_prop", "umbrella", first.id)
        self.assertEqual(continuity_context(updated, first.id), ())
        self.assertEqual(continuity_context(updated, second.id)[0].value, "umbrella")

    # {
    # 責務: [test_workspace_renders_candidates_regenerates_one_panel_and_resumes: verify production lifecycle]
    # 処理: [render, replace one panel, compose a page, save and restore the project]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_workspace_renders_candidates_regenerates_one_panel_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "demo.manga.json"
            processor = MangaProductionProcessor(ProcessMessenger(DataMessenger()))
            processor.create_project(
                project_path,
                "Rainy meeting",
                _project().story_script,
                page_count=1,
                layout_mode=MangaLayoutMode.FOUR_KOMA,
                characters=_project().characters,
                locations=_project().locations,
                props=_project().props,
            )
            project = processor.plan()
            first_page = project.pages[0]
            target_panel = first_page.panels[0]
            project, evaluation = processor.render_panel(target_panel.id, candidate_count=2, seed=7)
            rendered = next(
                panel for panel in project.pages[0].panels if panel.id == target_panel.id
            )
            self.assertEqual(len(rendered.candidate_image_paths), 2)
            self.assertEqual(rendered.status.value, "storyboard")
            self.assertTrue(evaluation.limitations)
            selected_path = rendered.image_path
            other_path = (
                processor.render_panel(first_page.panels[1].id)[0].pages[0].panels[1].image_path
            )
            updated, _notes = processor.render_panel(target_panel.id, seed=11)
            rerendered = next(
                panel for panel in updated.pages[0].panels if panel.id == target_panel.id
            )
            self.assertNotEqual(rerendered.image_path, selected_path)
            self.assertEqual(
                next(
                    panel
                    for panel in updated.pages[0].panels
                    if panel.id == first_page.panels[1].id
                ).image_path,
                other_path,
            )
            processor.render_all_panels(seed=40)
            for panel in processor.project.pages[0].panels:
                processor.edit_dialogue(panel.id, panel.dialogue)
            final_project, warnings = processor.compose_page(first_page.id, (800, 1100))
            self.assertTrue(final_project.pages[0].rendered_path)
            page_path = project_path.parent / final_project.pages[0].rendered_path
            self.assertTrue(page_path.is_file())
            with Image.open(page_path) as image:
                self.assertEqual(image.size, (800, 1100))
            self.assertIsInstance(warnings, tuple)
            restored = MangaProjectStore().load(project_path)
            self.assertEqual(restored, final_project)

    # {
    # 責務: [test_panel_geometry_rejects_character_positions_outside_panel: validate nested geometry]
    # 処理: [place one character outside its panel and require contract rejection]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_panel_geometry_rejects_character_positions_outside_panel(self) -> None:
        project = _project()
        planned = plan_story(project)
        panel = planned.pages[0].panels[0]
        with self.assertRaises(ValueError):
            replace(panel, character_positions=(("aki", (0.0, 0.0, 0.2, 0.2)),))

    # {
    # 責務: [test_named_backend_routing_and_local_repair_only_replace_selected_panel: verify isolated routing]
    # 処理: [use one named generator and one repair adapter without changing neighboring panels]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_named_backend_routing_and_local_repair_only_replace_selected_panel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = StoryboardRenderBackend()
            backend = SimpleNamespace(
                render_panel=lambda request: replace(
                    base.render_panel(request), backend_id="test_image_model"
                )
            )
            repair = SimpleNamespace(
                repair_panel=lambda request: PanelRenderResult(
                    request.original_image, "test_local_repair", request.seed
                )
            )
            processor = MangaProductionProcessor(
                ProcessMessenger(DataMessenger()), backend=backend, repair_backend=repair
            )
            processor.create_project(
                Path(directory) / "route.manga.json",
                "Routing test",
                "A character enters the station.\nAki: Hello.",
                layout_mode=MangaLayoutMode.FOUR_KOMA,
                characters=_project().characters,
            )
            project = processor.plan()
            first, second = project.pages[0].panels[:2]
            processor.edit_panel(replace(first, backend_id="injected"))
            routed, _evaluation = processor.render_panel(first.id)
            routed_first = routed.pages[0].panels[0]
            self.assertEqual(routed_first.status.value, "rendered")
            untouched_before = routed.pages[0].panels[1].image_path
            repaired, _repair_evaluation = processor.repair_panel(
                first.id, "adjust only the expression", (0.1, 0.1, 0.4, 0.4)
            )
            self.assertEqual(len(repaired.pages[0].panels[0].candidate_image_paths), 2)
            self.assertEqual(repaired.pages[0].panels[1].image_path, untouched_before)
            self.assertEqual(repaired.pages[0].panels[1].id, second.id)

    # {
    # 責務: [test_comfyui_backend_builds_grounded_prompt_and_validates_output: verify ComfyUI adapter contract]
    # 処理: [run a fake command, check bible grounding and seed override, reject unknown sampler nodes]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_comfyui_backend_builds_grounded_prompt_and_validates_output(self) -> None:
        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "2": {"class_type": "KSampler", "inputs": {"seed": 4}},
        }
        observed = {}

        # {
        # 責務: [command: stand in for one ComfyUI API generation call]
        # 処理: [capture request values and create a valid temporary PNG]
        # 引数: [inputs: adapter payload, _context: command context]
        # 戻り値: [Mapping: generated image path]
        # }
        def command(inputs, _context):
            observed.update(inputs)
            output = Path(inputs["output_dir"]) / "generated.png"
            Image.new("RGB", (16, 16), "white").save(output)
            return {"image": str(output)}

        backend = ComfyUIPanelBackend(
            workflow, prompt_node_ids=("1",), seed_node_ids=("2",), command=command
        )
        planned = plan_story(_project())
        page = planned.pages[0]
        result = backend.render_panel(PanelRenderRequest(planned, page, page.panels[0], seed=92))
        self.assertEqual(result.backend_id, "comfyui")
        self.assertEqual(result.seed, 92)
        self.assertIn("short dark hair", observed["prompt"])
        self.assertEqual(observed["overrides"], {"2": {"seed": 92}})
        self.assertGreater(len(result.image_bytes), 0)
        with self.assertRaises(ValueError):
            ComfyUIPanelBackend(workflow, seed_node_ids=("missing",), command=command)


if __name__ == "__main__":
    unittest.main()
