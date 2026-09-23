import json
from pathlib import Path
import sys
import tempfile
import unittest
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from comfyui_support_tools.shared.contracts.inspector_contracts import (
    ActionEvent,
    ExportSettings,
    MediaExportRecord,
    MediaNotes,
    ScoredLabel,
    TaggerSettings,
)
from comfyui_support_tools.shared.contracts.media_item import MediaItem
from comfyui_support_tools.shared.contracts.tagger_backend import (
    backend_label,
    resolve_backend,
)
from comfyui_support_tools.applications.main_gui.data.processing.result_exporter import export_records
from comfyui_support_tools.applications.main_gui.process.processing.inspector_state import InspectorState
from comfyui_support_tools.applications.main_gui.process.processing.media_actions import validate_settings
from comfyui_support_tools.applications.main_gui.process.processing.tag_result import (
    parse_tag_result,
    parse_tags,
)


def media_item(path: Path):
    stat = path.stat()
    return MediaItem(
        "id-" + path.stem,
        str(path.absolute()),
        path.name,
        "image",
        "library",
        stat.st_size,
        stat.st_mtime_ns,
    )


class NormalizedTagResultTests(unittest.TestCase):
    def test_categories_rating_caption_and_scores_are_separate(self):
        payload = {
            "general": {"1girl": 0.95, "low": 0.1},
            "character": {"alice": 0.91, "maybe": 0.7},
            "copyright": {"series": 0.8},
            "rating": {"safe": 0.2, "explicit": 0.9},
            "caption": "A synthetic caption.",
            "style": {"watercolor": 0.99},
        }
        result = parse_tag_result(
            payload,
            0.35,
            0.85,
            "pixai_http",
            "http://127.0.0.1:7861/pixai/v1/interrogate",
            "fixture-model",
        )
        self.assertEqual(result.content_tags, ("1girl",))
        self.assertEqual(result.character_tags, ("alice",))
        self.assertEqual(result.copyright_tags, ("series",))
        self.assertEqual(result.rating, "explicit")
        self.assertEqual(result.caption, "A synthetic caption.")
        self.assertEqual(result.backend, "pixai_http")
        self.assertEqual(result.model, "fixture-model")
        self.assertEqual(tuple(value.name for value in result.content_scores), ("1girl", "low"))
        self.assertNotIn("watercolor", result.content_tags)

    def test_nested_common_service_and_flat_pixai_compatibility(self):
        nested = {
            "tags": {
                "general": [{"name": "sky", "confidence": 0.9}],
                "character": {"hero": 0.95},
                "rating": {"safe": 1.0},
            },
            "caption": "sky scene",
        }
        result = parse_tag_result(
            nested,
            0.35,
            0.85,
            "tagger_service_http",
            "http://localhost:9000/tagger/v1/interrogate",
            "anime-future",
        )
        self.assertEqual(result.content_tags, ("sky",))
        self.assertEqual(result.character_tags, ("hero",))
        self.assertEqual(result.rating, "safe")
        self.assertEqual(parse_tags({"tag": {"sky": 0.9, "low": 0.1}}, 0.35), ("sky",))
        self.assertEqual(parse_tags({"caption": "sky, clouds"}, 0.35), ("sky", "clouds"))

    def test_freeform_caption_is_not_invented_as_content_tag(self):
        result = parse_tag_result({"caption": "A woman standing under a blue sky."}, 0.35, 0.85)
        self.assertEqual(result.content_tags, ())
        self.assertEqual(result.caption, "A woman standing under a blue sky.")

    def test_unknown_style_only_and_invalid_scores_are_rejected(self):
        for payload in (
            {"style": {"watercolor": 0.9}},
            {"unknown": {"nested": 5}},
            {"general": {"sky": float("nan")}},
            {"rating": {"safe": True}},
        ):
            with self.assertRaises(ValueError):
                parse_tag_result(payload, 0.35, 0.85)


class BackendMigrationTests(unittest.TestCase):
    def test_pixai_and_common_service_are_explicit_and_path_checked(self):
        pixai = TaggerSettings(
            "http://localhost:7861/pixai/v1/interrogate",
            "pixai-model",
            backend="pixai_http",
        )
        common = TaggerSettings(
            "http://localhost:7862/tagger/v1/interrogate",
            "anime-model",
            backend="tagger_service_http",
        )
        validate_settings(pixai)
        validate_settings(common)
        self.assertEqual(resolve_backend("auto_http", pixai.url).id, "pixai_http")
        self.assertEqual(resolve_backend("auto_http", common.url).id, "tagger_service_http")
        self.assertEqual(backend_label("tagger_service_http"), "Tagger Service HTTP")
        with self.assertRaises(ValueError):
            validate_settings(replace(pixai, backend="tagger_service_http"))

    def test_unimplemented_backend_cannot_be_selected_by_id(self):
        with self.assertRaises(ValueError):
            resolve_backend("anime_timm_magic", "http://localhost/tagger/v1/interrogate")


class InspectorNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / "image.png"
        Image.new("RGB", (20, 20), "blue").save(path)
        self.item = media_item(path)
        self.state = InspectorState()
        self.settings = TaggerSettings(
            "http://localhost:7861/pixai/v1/interrogate",
            "fixture-model",
            backend="pixai_http",
        )
        self.state.configure(self.settings)
        self.state.models = ("fixture-model",)
        self.state.ready = True
        self.state.select((self.item,))
        self.state.save_notes(MediaNotes(
            style_tags=("manual-style",),
            prompt="keep prompt",
        ))

    def test_tag_updates_normalized_fields_without_overwriting_style_or_prompt(self):
        request = self.state.begin("tag")
        payload = {
            "general": {"landscape": 0.9},
            "character": {"hero": 0.95},
            "copyright": {"series": 0.8},
            "rating": {"safe": 0.9},
            "caption": "generated caption",
            "style": {"wrong-place": 0.99},
        }
        self.state.accept((
            ActionEvent(request.token, "result", self.item, message=json.dumps(payload)),
            ActionEvent(request.token, "done", message="完了"),
        ))
        notes = self.state.current_notes()
        self.assertEqual(notes.content_tags, ("landscape",))
        self.assertEqual(notes.character_tags, ("hero",))
        self.assertEqual(notes.copyright_tags, ("series",))
        self.assertEqual(notes.rating, "safe")
        self.assertEqual(notes.caption, "generated caption")
        self.assertEqual(notes.style_tags, ("manual-style",))
        self.assertEqual(notes.prompt, "keep prompt")
        self.assertEqual(notes.tagger_backend, "pixai_http")
        self.assertEqual(notes.tagger_model, "fixture-model")

    def test_manual_analysis_edit_clears_stale_confidence_provenance(self):
        previous = MediaNotes(
            content_tags=("old",),
            tagger_backend="pixai_http",
            tagger_model="model",
            content_scores=(ScoredLabel("old", 0.9),),
        )
        self.state._store(self.item, previous)
        self.state.save_notes(replace(previous, content_tags=("edited",)))
        notes = self.state.current_notes()
        self.assertEqual(notes.content_scores, ())
        self.assertEqual(notes.tagger_backend, "manual-edit")
        self.assertEqual(notes.tagger_model, "")

    def test_export_request_does_not_require_live_tagger(self):
        self.state.ready = False
        settings = ExportSettings(caption_sidecar=True, metadata_sidecar=False)
        request = self.state.begin_export(settings)
        self.assertEqual(request.kind, "export")
        self.assertEqual(request.items, (self.item,))
        self.assertEqual(request.export_records[0].notes.style_tags, ("manual-style",))


class ResultExporterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / "画像 sample.png"
        Image.new("RGB", (20, 10), "blue").save(self.image)
        self.item = media_item(self.image)

    def test_caption_metadata_and_batch_export_keep_fields_structured(self):
        notes = MediaNotes(
            content_tags=("1girl", "blue sky"),
            style_tags=("watercolor",),
            character_tags=("hero",),
            copyright_tags=("series",),
            rating="safe",
            prompt="prompt",
            tagger_backend="pixai_http",
            tagger_model="fixture",
            content_scores=(ScoredLabel("1girl", 0.99),),
            rating_scores=(ScoredLabel("safe", 0.9),),
        )
        batch = self.root / "batch.txt"
        paths = export_records(
            (MediaExportRecord(self.item, notes),),
            ExportSettings(
                caption_sidecar=True,
                metadata_sidecar=True,
                batch_txt_path=str(batch),
                include_style_in_caption=True,
            ),
        )
        self.assertEqual(len(paths), 3)
        caption = self.image.with_suffix(".txt").read_text(encoding="utf-8").strip()
        self.assertEqual(caption, "1girl, blue sky, hero, series, watercolor")
        metadata_path = self.image.with_suffix(".png.kadoka.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["analysis"]["content_tags"], ["1girl", "blue sky"])
        self.assertEqual(metadata["analysis"]["style_tags"], ["watercolor"])
        self.assertEqual(metadata["analysis"]["rating"], "safe")
        self.assertEqual(metadata["analysis"]["tagger_backend"], "pixai_http")
        self.assertEqual(metadata["analysis"]["content_scores"][0]["score"], 0.99)
        self.assertIn(str(self.image.absolute()), batch.read_text(encoding="utf-8"))

    def test_image_to_text_caption_has_priority_over_tag_join(self):
        notes = MediaNotes(
            content_tags=("tag",),
            style_tags=("style",),
            caption="A complete caption sentence.",
        )
        export_records(
            (MediaExportRecord(self.item, notes),),
            ExportSettings(metadata_sidecar=False, include_style_in_caption=True),
        )
        self.assertEqual(
            self.image.with_suffix(".txt").read_text(encoding="utf-8").strip(),
            "A complete caption sentence.",
        )

    def test_existing_file_requires_explicit_overwrite(self):
        target = self.image.with_suffix(".txt")
        target.write_text("original", encoding="utf-8")
        record = MediaExportRecord(self.item, MediaNotes(content_tags=("new",)))
        with self.assertRaises(FileExistsError):
            export_records((record,), ExportSettings(metadata_sidecar=False))
        self.assertEqual(target.read_text(encoding="utf-8"), "original")
        export_records((record,), ExportSettings(metadata_sidecar=False, overwrite=True))
        self.assertEqual(target.read_text(encoding="utf-8").strip(), "new")

    def test_changed_source_and_bad_batch_target_are_rejected_before_writing(self):
        record = MediaExportRecord(self.item, MediaNotes(content_tags=("tag",)))
        self.image.write_bytes(self.image.read_bytes() + b"x")
        with self.assertRaises(ValueError):
            export_records((record,), ExportSettings(metadata_sidecar=False))
        self.assertFalse(self.image.with_suffix(".txt").exists())

        Image.new("RGB", (20, 10), "blue").save(self.image)
        fresh = MediaExportRecord(media_item(self.image), MediaNotes(content_tags=("tag",)))
        with self.assertRaises(ValueError):
            export_records(
                (fresh,),
                ExportSettings(
                    caption_sidecar=False,
                    metadata_sidecar=False,
                    batch_txt_path=str(self.root / "batch.json"),
                ),
            )


if __name__ == "__main__":
    unittest.main()
