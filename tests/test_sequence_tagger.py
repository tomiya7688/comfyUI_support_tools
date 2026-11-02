from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from PIL import Image

from comfyui_support_tools.applications.sequence.data.processing.tagger_command import TaggerCommand
from comfyui_support_tools.applications.sequence.process.processing.sequence_runner import SequenceRunner
from comfyui_support_tools.shared.contracts.sequence_contracts import SequenceDefinition, SequenceStep


# {
#   責務: [_TaggerHandler: loopback HTTP fixture that captures tagger requests and returns controlled tags]
#   処理: [1: provide the configured fields and methods used by the surrounding cases]
#   フィールド: [
#     request_payload: request body captured by the local endpoint (dict[str, Any]),
#     image_bytes: image bytes fixture state used by the test cases,
#     response_payload: response body served by the local endpoint,
#   ],
#   引数: []
# }
class _TaggerHandler(BaseHTTPRequestHandler):
    request_payload: dict[str, Any] = {}
    image_bytes = b""
    response_payload = {
        "general": {"blue sky": 0.95, "low confidence": 0.1},
        "character": {"sample character": 0.9},
        "copyright": {"sample series": 0.8},
        "rating": {"safe": 0.99},
        "caption": "A character beneath a blue sky.",
    }

    # {
    #   責務: [do_POST: records a local fixture POST request and returns its response]
    #   処理: [1: read and decode the posted JSON body, 2: record the request and send the configured response payload]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def do_POST(self) -> None:
        type(self).request_payload = json.loads(
            self.rfile.read(int(self.headers["Content-Length"]))
        )
        type(self).image_bytes = base64.b64decode(type(self).request_payload["image"])
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(type(self).response_payload).encode("utf-8"))

    # {
    #   責務: [log_message: suppresses default request logging from the local fixture server]
    #   処理: [1: suppress the HTTP server's default request log output]
    #   引数: [
    #     _format:  format passed to this helper (str),
    #     *_args: additional logging arguments intentionally ignored (Any),
    #   ],
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def log_message(self, _format: str, *_args: Any) -> None:
        return


# {
#   責務: [TaggerCommandTests: related test fixtures and cases for TaggerCommand behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: [
#     temp: temporary root containing fixture files,
#     image_path: path to the generated media fixture,
#     command: command fixture state used by the test cases,
#   ],
#   引数: []
# }
class TaggerCommandTests(unittest.TestCase):
    # {
    #   責務: [setUpClass: initializes class-wide fixture state for TaggerCommandTests]
    #   処理: [1: create class-wide fixture resources shared by related cases, 2: register cleanup for owned resources]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [test専用のloopback HTTP fixture serverを起動・停止する]
    # }
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _TaggerHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = (
            f"http://127.0.0.1:{cls.server.server_address[1]}"
            "/pixai/v1/interrogate"
        )

    # {
    #   責務: [tearDownClass: releases class-wide resources created by TaggerCommandTests]
    #   処理: [1: stop owned workers/servers and release temporary files or UI resources]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    # {
    #   責務: [setUp: initializes per-test fixture state for TaggerCommandTests]
    #   処理: [
    #     1: create the per-test inputs and fixture resources required by the scenario,
    #     2: register cleanup for resources owned by the fixture,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def setUp(self) -> None:
        _TaggerHandler.request_payload = {}
        _TaggerHandler.image_bytes = b""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.image_path = Path(self.temp.name) / "input.png"
        Image.new("RGB", (16, 16), "blue").save(self.image_path)
        self.command = TaggerCommand(timeout=2)

    # {
    #   責務: [
    #     test_result_is_normalized_and_available_to_next_sequence_step: verifies the behavior described by "result is normalized and available to next sequence step",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for result is normalized and available to next sequence step,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def test_result_is_normalized_and_available_to_next_sequence_step(self) -> None:
        observed: list[tuple[list[str], str]] = []

        # {
        #   責務: [consume: records normalized tags/caption from prior sequence output and returns an acknowledgement]
        #   処理: [1: record normalized tags and caption, 2: return an acknowledgement to the sequence runner]
        #   引数: [
        #     inputs: input mapping from the previous workflow step (unspecified),
        #     _context: execution context passed through the workflow (unspecified),
        #   ],
        #   戻り値: [result: mapping built or selected by this helper]
        # }
        def consume(inputs, _context):
            observed.append((inputs["tags"], inputs["caption"]))
            return {"seen": True}

        definition = SequenceDefinition(
            "tagger-to-next-step",
            (
                SequenceStep(
                    "tag",
                    "tagger",
                    {
                        "image": str(self.image_path),
                        "url": self.url,
                        "backend": "pixai_http",
                        "model": "fixture-model",
                        "threshold": 0.35,
                        "character_threshold": 0.85,
                    },
                ),
                SequenceStep(
                    "consume",
                    "consume",
                    {
                        "tags": {"$ref": "context.tag.tags"},
                        "caption": {"$ref": "context.tag.caption_text"},
                    },
                ),
            ),
        )


        result = SequenceRunner({"tagger": self.command, "consume": consume}).run(definition)

        self.assertEqual(result.state, "done", result.steps)
        self.assertEqual(observed, [
            (["blue sky", "sample character", "sample series"], "A character beneath a blue sky.")
        ])
        self.assertEqual(result.context["tag"]["metadata"]["rating"], "safe")
        self.assertEqual(_TaggerHandler.request_payload["model"], "fixture-model")
        self.assertEqual(_TaggerHandler.request_payload["threshold"], 0.35)
        self.assertEqual(_TaggerHandler.request_payload["character_threshold"], 0.85)
        with Image.open(self.image_path) as image:
            self.assertEqual(image.format, "PNG")
        self.assertTrue(_TaggerHandler.image_bytes.startswith(b"\x89PNG"))

    # {
    #   責務: [
    #     test_explicit_txt_and_metadata_paths_write_sidecar_files: verifies the behavior described by "explicit txt and metadata paths write sidecar files",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for explicit txt and metadata paths write sidecar files,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def test_explicit_txt_and_metadata_paths_write_sidecar_files(self) -> None:
        output_directory = Path(self.temp.name) / "results"
        txt_path = output_directory / "tags.txt"
        metadata_path = output_directory / "metadata.json"

        result = self.command(
            {
                "image": str(self.image_path),
                "url": self.url,
                "backend": "pixai_http",
                "model": "fixture-model",
                "txt_output": str(txt_path),
                "metadata_output": str(metadata_path),
            },
            {},
        )

        self.assertEqual(
            txt_path.read_text(encoding="utf-8"),
            "blue sky, sample character, sample series\n",
        )
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["caption"], "A character beneath a blue sky.")
        self.assertEqual(metadata["rating"], "safe")
        self.assertEqual(result["txt_path"], str(txt_path))
        self.assertEqual(result["metadata_path"], str(metadata_path))

    # {
    #   責務: [
    #     test_non_loopback_url_is_rejected_before_any_request: verifies the behavior described by "non loopback url is rejected before any request",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for non loopback url is rejected before any request,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def test_non_loopback_url_is_rejected_before_any_request(self) -> None:
        with self.assertRaisesRegex(ValueError, "localhost/loopback"):
            self.command(
                {
                    "image": str(self.image_path),
                    "url": "https://example.com/pixai/v1/interrogate",
                    "backend": "pixai_http",
                    "model": "fixture-model",
                },
                {},
            )

    # {
    #   責務: [
    #     test_bad_threshold_and_missing_image_are_rejected: verifies the behavior described by "bad threshold and missing image are rejected",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for bad threshold and missing image are rejected,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def test_bad_threshold_and_missing_image_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "threshold"):
            self.command(
                {
                    "image": str(self.image_path),
                    "url": self.url,
                    "backend": "pixai_http",
                    "model": "fixture-model",
                    "threshold": 1.1,
                },
                {},
            )
        with self.assertRaisesRegex(ValueError, "absolute file"):
            self.command(
                {
                    "image": str(self.image_path.with_name("missing.png")),
                    "url": self.url,
                    "backend": "pixai_http",
                    "model": "fixture-model",
                },
                {},
            )


if __name__ == "__main__":
    unittest.main()
