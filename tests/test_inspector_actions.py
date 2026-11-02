import base64
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
from threading import Event
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from PIL import Image
from comfyui_support_tools.shared.contracts.media_item import MediaItem
from comfyui_support_tools.shared.contracts.inspector_contracts import ActionEvent, MediaNotes, ScoredLabel, TaggerSettings
from comfyui_support_tools.applications.main_gui.process.processing.inspector_state import InspectorState
from comfyui_support_tools.applications.main_gui.process.processing.media_actions import validate_settings
from comfyui_support_tools.applications.main_gui.process.processing.tag_result import parse_tags
from comfyui_support_tools.applications.main_gui.data.processing.tagger_transport import TaggerTransport
from comfyui_support_tools.applications.main_gui.data.processing.action_io import ActionIO
from comfyui_support_tools.entrypoints.inspector import create_inspector
from tests.inspector_http_fixture import TaggerFixture


# {
#   責務: [sample: creates and indexes a deterministic image fixture]
#   処理: [1: write a small deterministic PNG under the fixture root, 2: return media metadata for the created sample]
#   引数: [root: temporary fixture root (unspecified), name: fixture item name (unspecified)]
#   戻り値: [result: MediaItem built or selected by this helper]
#   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
# }
def sample(root, name="画像 sample.png"):
    path = root/name
    Image.new("RGB", (40, 30), "blue").save(path)
    stat = path.stat()
    return MediaItem(name, str(path), name, "image", "library", stat.st_size, stat.st_mtime_ns)


# {
#   責務: [drain: polls the commander until queued events are collected or timeout occurs]
#   処理: [1: poll commander messages until its queue is empty, 2: fail if polling exceeds the timeout]
#   引数: [commander: commander passed to this helper (unspecified), timeout: maximum wait duration (unspecified)]
#   戻り値: [result: messages value built or selected by this helper]
# }
def drain(commander, timeout=5):
    messages = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages.extend(commander.poll())
        if not commander.status().busy:
            return messages
        time.sleep(.01)
    raise AssertionError("Action timed out")


# {
#   責務: [InspectorStateTests: related test fixtures and cases for InspectorState behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: [state: application state object under test, a: first selected media item, b: second selected media item]
#   引数: []
# }
class InspectorStateTests(unittest.TestCase):
    # {
    #   責務: [setUp: initializes per-test fixture state for InspectorStateTests]
    #   処理: [
    #     1: create the per-test inputs and fixture resources required by the scenario,
    #     2: register cleanup for resources owned by the fixture,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def setUp(self):
        self.state = InspectorState()
        self.a = MediaItem("a", "/a.png", "a.png", "image", "library", 1, 1)
        self.b = replace(self.a, id="b", path="/b.png", name="b.png")
        self.state.configure(TaggerSettings("http://localhost:7861/pixai/v1/interrogate", "test"))
        self.state.models, self.state.ready = ("test",), True
        self.state.select((self.a,))

    # {
    #   責務: [
    #     test_all_expected_actions_exist_and_placeholders_explain_why: verifies the behavior described by "all expected actions exist and placeholders explain why",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for all expected actions exist and placeholders explain why,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_all_expected_actions_exist_and_placeholders_explain_why(self):
        options = self.state.options()
        self.assertEqual({o.definition.id for o in options}, {"tag", "style", "img2img", "dataset", "character", "variations", "video"})
        self.assertTrue(options[0].enabled)
        self.assertTrue(all(not o.enabled and "未実装" in o.reason for o in options[1:]))

    # {
    #   責務: [
    #     test_no_selection_mixed_video_and_unknown_action_blocked: verifies the behavior described by "no selection mixed video and unknown action blocked",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for no selection mixed video and unknown action blocked,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_no_selection_mixed_video_and_unknown_action_blocked(self):
        for items in ((), (replace(self.a, kind="video"),), (self.a, replace(self.b, kind="video"))):
            self.state.select(items)
            with self.assertRaises(ValueError):
                self.state.begin("tag")
        with self.assertRaises(ValueError):
            self.state.begin("unknown")

    # {
    #   責務: [
    #     test_selection_cannot_exceed_sixty_or_duplicate_ids: verifies the behavior described by "selection cannot exceed sixty or duplicate ids",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for selection cannot exceed sixty or duplicate ids,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_selection_cannot_exceed_sixty_or_duplicate_ids(self):
        for items in ((self.a, self.a), tuple(replace(self.a, id=str(i)) for i in range(61))):
            with self.assertRaises(ValueError):
                self.state.select(items)

    # {
    #   責務: [
    #     test_notes_are_separate_and_tag_result_preserves_other_fields: verifies the behavior described by "notes are separate and tag result preserves other fields",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for notes are separate and tag result preserves other fields,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_notes_are_separate_and_tag_result_preserves_other_fields(self):
        notes = MediaNotes(("old",), ("watercolor",), "prompt", "negative", "character", "dataset")
        self.state.save_notes(notes)
        request = self.state.begin("tag")
        self.state.accept((ActionEvent(request.token, "result", self.a, message='{"tags":{"sky":0.9}}'),
                           ActionEvent(request.token, "done")))
        self.assertEqual(
            self.state.current_notes(),
            replace(
                notes,
                content_tags=("sky",),
                tagger_backend="pixai_http",
                tagger_model="test",
                content_scores=(ScoredLabel("sky", 0.9),),
            ),
        )

    # {
    #   責務: [
    #     test_immutable_batch_snapshot_and_results_do_not_follow_new_selection: verifies the behavior described by "immutable batch snapshot and results do not follow new selection",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for immutable batch snapshot and results do not follow new selection,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_immutable_batch_snapshot_and_results_do_not_follow_new_selection(self):
        self.state.select((self.a, self.b))
        request = self.state.begin("tag")
        self.state.select((self.b,))
        self.assertEqual(request.items, (self.a, self.b))
        self.state.accept((ActionEvent(request.token, "result", self.a, message='{"tags":"landscape"}'),))
        self.assertEqual(self.state.current_notes(), MediaNotes())
        self.state.select((self.a,))
        self.assertEqual(self.state.current_notes().content_tags, ("landscape",))

    # {
    #   責務: [
    #     test_pending_actions_cannot_be_double_submitted_or_edit_notes: verifies the behavior described by "pending actions cannot be double submitted or edit notes",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for pending actions cannot be double submitted or edit notes,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_pending_actions_cannot_be_double_submitted_or_edit_notes(self):
        self.state.begin("tag")
        for call in (lambda: self.state.begin("tag"), lambda: self.state.save_notes(MediaNotes()),
                     lambda: self.state.configure(self.state.settings)):
            with self.assertRaises(ValueError):
                call()

    # {
    #   責務: [
    #     test_failed_and_stale_duplicate_results_do_not_corrupt_notes: verifies the behavior described by "failed and stale duplicate results do not corrupt notes",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for failed and stale duplicate results do not corrupt notes,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_failed_and_stale_duplicate_results_do_not_corrupt_notes(self):
        request = self.state.begin("tag")
        self.state.accept((ActionEvent(request.token-1, "result", self.a, message='{"tags":"stale"}'),))
        self.assertEqual(self.state.current_notes(), MediaNotes())
        bad = ActionEvent(request.token, "result", self.a, message='{"error":"server secret"}')
        messages = self.state.accept((bad, bad, ActionEvent(request.token, "done")))
        self.assertEqual(self.state.failures, 1)
        self.assertNotIn("server secret", str(messages))
        self.assertFalse(self.state.busy)

    # {
    #   責務: [
    #     test_url_change_invalidates_probe_model_change_requires_supported_model: verifies the behavior described by "url change invalidates probe model change requires supported model",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for url change invalidates probe model change requires supported model,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_url_change_invalidates_probe_model_change_requires_supported_model(self):
        self.state.configure(replace(self.state.settings, model="missing"))
        self.assertFalse(self.state.ready)
        self.state.configure(replace(self.state.settings, model="test"))
        self.assertTrue(self.state.ready)
        self.state.configure(replace(self.state.settings, url="http://localhost:9999/tagger/v1/interrogate"))
        self.assertEqual(self.state.models, ())
        self.assertFalse(self.state.ready)

    # {
    #   責務: [
    #     test_probe_auto_selects_first_model_and_failure_disables_action: verifies the behavior described by "probe auto selects first model and failure disables action",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for probe auto selects first model and failure disables action,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_probe_auto_selects_first_model_and_failure_disables_action(self):
        self.state.configure(replace(self.state.settings, model=""))
        req = self.state.begin("probe")
        self.state.accept((ActionEvent(req.token, "models", models=("first",)), ActionEvent(req.token, "done", message="完了")))
        self.assertEqual(self.state.settings.model, "first")
        self.assertTrue(self.state.ready)
        req = self.state.begin("probe")
        self.state.accept((ActionEvent(req.token, "error", message="not installed"), ActionEvent(req.token, "done", message="完了")))
        self.assertFalse(self.state.ready)
        self.assertIn("not installed", self.state.message)

    # {
    #   責務: [
    #     test_modified_file_invalidates_notes_and_rejects_old_tag_result: verifies the behavior described by "modified file invalidates notes and rejects old tag result",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for modified file invalidates notes and rejects old tag result,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_modified_file_invalidates_notes_and_rejects_old_tag_result(self):
        self.state.save_notes(MediaNotes(content_tags=("old",)))
        request = self.state.begin("tag")
        updated = replace(self.a, modified_ns=2)
        self.state.select((updated,))
        self.assertEqual(self.state.current_notes(), MediaNotes())
        self.state.accept((ActionEvent(request.token, "result", self.a, message='{"tags":"stale"}'),))
        self.assertEqual(self.state.current_notes(), MediaNotes())
        self.assertEqual(self.state.failures, 1)

    # {
    #   責務: [
    #     test_session_notes_limit_and_validation: verifies the behavior described by "session notes limit and validation",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for session notes limit and validation,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_session_notes_limit_and_validation(self):
        with self.assertRaises(ValueError):
            self.state.save_notes(MediaNotes(prompt="x"*8193))
        self.state.notes = {str(i): MediaNotes() for i in range(4096)}
        with self.assertRaises(ValueError):
            self.state.save_notes(MediaNotes())


# {
#   責務: [TagProtocolTests: related test fixtures and cases for TagProtocol behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class TagProtocolTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_settings_reject_wrong_schemes_credentials_queries_and_bad_numbers: verifies the behavior described by "settings reject wrong schemes credentials queries and bad numbers",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for settings reject wrong schemes credentials queries and bad numbers,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_settings_reject_wrong_schemes_credentials_queries_and_bad_numbers(self):
        for url in ("", "file:///tmp/image", "http://u:p@localhost/pixai/v1/interrogate",
                    "http://localhost/pixai/v1/interrogate?token=secret", "http://localhost/wrong", "http://localhost:99999/pixai/v1/interrogate"):
            with self.assertRaises(ValueError):
                validate_settings(TaggerSettings(url))
        valid = TaggerSettings("https://example.org/pixai/v1/interrogate", "test")
        validate_settings(valid)
        for settings in (replace(valid, threshold=float("nan")), replace(valid, timeout=0), replace(valid, character_threshold=2)):
            with self.assertRaises(ValueError):
                validate_settings(settings)

    # {
    #   責務: [
    #     test_tag_shapes_and_confidence_filter: verifies the behavior described by "tag shapes and confidence filter",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for tag shapes and confidence filter,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_tag_shapes_and_confidence_filter(self):
        for response in ({"tag": {"sky": .9, "low": .1}}, {"tags": [{"name": "sky", "confidence": .9}]},
                         {"caption": "sky, sky"}, ["sky"]):
            self.assertEqual(parse_tags(response, .35), ("sky",))
        self.assertEqual(parse_tags({"tags": [], "style": ["not content"]}, .35), ())
        for response in ({"error":"bad"}, {"sky": float("nan")}, {"sky":True}, {"sky":2}, {"unknown": {"nested":5}}, [42]):
            with self.assertRaises(ValueError):
                parse_tags(response, .35)


# {
#   責務: [TagTransportTests: related test fixtures and cases for TagTransport behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: [
#     fixture: local service fixture used by the test,
#     tmp: temporary root containing fixture files,
#     item: media item fixture passed to the action under test,
#     settings: validated request settings for the fixture backend,
#     transport: local/fake transport object under test,
#   ],
#   引数: []
# }
class TagTransportTests(unittest.TestCase):
    # {
    #   責務: [setUp: initializes per-test fixture state for TagTransportTests]
    #   処理: [
    #     1: create the per-test inputs and fixture resources required by the scenario,
    #     2: register cleanup for resources owned by the fixture,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def setUp(self):
        self.fixture = TaggerFixture()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.fixture.close)
        self.addCleanup(self.tmp.cleanup)
        self.item = sample(Path(self.tmp.name))
        self.settings = TaggerSettings(self.fixture.url, "fixture-model")
        self.transport = TaggerTransport()

    # {
    #   責務: [
    #     test_real_http_payload_and_models_match_existing_folder_tagger_contract: verifies the behavior described by "real http payload and models match existing folder tagger contract",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for real http payload and models match existing folder tagger contract,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_real_http_payload_and_models_match_existing_folder_tagger_contract(self):
        self.assertEqual(self.transport.probe(self.settings), ("fixture-model",))
        self.transport.tag(self.item, self.settings)
        verb, path, payload = self.fixture.requests[-1]
        self.assertEqual((verb,path), ("POST", "/pixai/v1/interrogate"))
        self.assertEqual(base64.b64decode(payload["image"]), Path(self.item.path).read_bytes())
        self.assertEqual(payload["character_threshold"], .85)
        self.assertEqual(payload["model"], "fixture-model")

    # {
    #   責務: [
    #     test_generic_tagger_payload_omits_pixai_only_field: verifies the behavior described by "generic tagger payload omits pixai only field",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for generic tagger payload omits pixai only field,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_generic_tagger_payload_omits_pixai_only_field(self):
        self.transport.tag(self.item, replace(self.settings, url=self.fixture.url.replace("pixai", "tagger")))
        self.assertNotIn("character_threshold", self.fixture.requests[-1][2])

    # {
    #   責務: [
    #     test_redirect_never_forwards_image_to_another_target: verifies the behavior described by "redirect never forwards image to another target",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for redirect never forwards image to another target,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_redirect_never_forwards_image_to_another_target(self):
        self.fixture.code, self.fixture.redirect = 302, self.fixture.url+"/leak"
        with self.assertRaises(ValueError):
            self.transport.tag(self.item, self.settings)
        self.assertEqual(len(self.fixture.requests), 1)

    # {
    #   責務: [
    #     test_missing_changed_corrupt_and_oversized_images_never_post: verifies the behavior described by "missing changed corrupt and oversized images never post",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for missing changed corrupt and oversized images never post,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_missing_changed_corrupt_and_oversized_images_never_post(self):
        path=Path(self.item.path)
        path.write_bytes(b"invalid")
        with self.assertRaises(ValueError):
            self.transport.tag(self.item,self.settings)
        stat=path.stat()
        broken=replace(self.item,size=stat.st_size,modified_ns=stat.st_mtime_ns)
        with self.assertRaises(ValueError):
            self.transport.tag(broken,self.settings)
        path.unlink()
        with self.assertRaises(ValueError):
            self.transport.tag(self.item,self.settings)
        item=sample(Path(self.tmp.name))
        from comfyui_support_tools.applications.main_gui.data.processing import tagger_transport
        with mock.patch.object(tagger_transport,"MAX_IMAGE_BYTES",1), self.assertRaises(ValueError):
            self.transport.tag(item,self.settings)
        self.assertEqual(self.fixture.requests, [])

    # {
    #   責務: [test_bad_or_empty_models_fail: verifies the behavior described by "bad or empty models fail"]
    #   処理: [
    #     1: arrange case data and fixture state for bad or empty models fail,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_bad_or_empty_models_fail(self):
        for response in ({"models":[]}, {"models":[42]}, {"error":"oops"}):
            self.fixture.models=response
            with self.assertRaises(ValueError):
                self.transport.probe(self.settings)

    # {
    #   責務: [
    #     test_disconnected_backend_returns_explicit_error: verifies the behavior described by "disconnected backend returns explicit error",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for disconnected backend returns explicit error,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_disconnected_backend_returns_explicit_error(self):
        with mock.patch.object(self.transport._opener,"open",side_effect=TimeoutError):
            with self.assertRaisesRegex(ValueError,"timeout"):
                self.transport.probe(self.settings)

    # {
    #   責務: [test_response_limit: verifies the behavior described by "response limit"]
    #   処理: [
    #     1: arrange case data and fixture state for response limit,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_response_limit(self):
        self.fixture.models={"models":["x"*(1024*1024)]}
        with self.assertRaisesRegex(ValueError,"上限"):
            self.transport.probe(self.settings)

    # {
    #   責務: [
    #     test_gui_free_facade_runs_real_batch_and_keeps_partial_failures: verifies the behavior described by "gui free facade runs real batch and keeps partial failures",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for gui free facade runs real batch and keeps partial failures,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_gui_free_facade_runs_real_batch_and_keeps_partial_failures(self):
        controller=create_inspector()
        self.addCleanup(controller.close)
        controller.configure(self.settings)
        controller.start("probe")
        drain(controller)
        second=sample(Path(self.tmp.name), "second.png")
        bad=replace(self.item,id="missing",path=self.item.path+".missing")
        controller.select((self.item,second,bad))
        controller.start("tag")
        messages=drain(controller)
        self.assertIn("成功2 / 失敗1",controller.status().message)
        controller.select((second,))
        self.assertEqual(controller.notes().content_tags,("landscape","sky"))
        self.assertTrue(any("missing" in text or "ありません" in text for text in messages))

    # {
    #   責務: [
    #     test_cancellation_prevents_later_batch_items_and_close_is_nonblocking: verifies the behavior described by "cancellation prevents later batch items and close is nonblocking",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for cancellation prevents later batch items and close is nonblocking,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: mapping built or selected by this helper]
    # }
    def test_cancellation_prevents_later_batch_items_and_close_is_nonblocking(self):
        entered,release=Event(),Event()
        transport=mock.Mock()
        # {
        #   責務: [slow: blocks on a test event to simulate in-flight work during cancellation]
        #   処理: [
        #     1: signal that the fake operation has started,
        #     2: wait for release and return its deterministic partial result,
        #   ],
        #   引数: [*args: positional HTTP handler arguments forwarded to the base class (unspecified)]
        #   戻り値: [result: mapping built or selected by this helper]
        # }
        def slow(*args):
            entered.set(); release.wait(3); return {"tags":["sky"]}
        transport.tag.side_effect=slow
        io=ActionIO(transport)
        state=InspectorState();state.configure(self.settings);state.ready=True
        state.select((self.item,replace(self.item,id="second")))
        try:
            io.start(state.begin("tag"))
            self.assertTrue(entered.wait(2))
            io.cancel();release.set()
            io._thread.join(3)
            self.assertFalse(io._thread.is_alive())
            self.assertEqual(transport.tag.call_count,1)
            events=io.poll()
            self.assertEqual(events[-1].kind,"done")
            self.assertIn("停止",events[-1].message)
        finally:
            release.set();io.close()
        self.assertEqual(io._events.maxsize,64)
        with self.assertRaises(ValueError):
            io.start(state.request)


if __name__ == "__main__":
    unittest.main()
