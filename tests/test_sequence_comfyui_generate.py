from __future__ import annotations

import json
import ssl
import tempfile
import threading
import unittest
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPSHandler

from comfyui_support_tools.applications.sequence.data.processing.comfyui_generate_command import (
    ComfyUIGenerateCommand,
)
from comfyui_support_tools.applications.sequence.process.processing.sequence_runner import (
    SequenceRunner,
)
from comfyui_support_tools.shared.contracts.sequence_contracts import (
    SequenceDefinition,
    SequenceStep,
)
from tools.security.check_python_ca import AFFECTED_CERTIFICATES


# {
#   責務: [_ComfyHandler: loopback HTTP fixture that captures ComfyUI prompts and serves a generated image]
#   処理: [1: provide the configured fields and methods used by the surrounding cases]
#   フィールド: [
#     prompt_payload: prompt payload fixture state used by the test cases (dict[str, Any]),
#     image_bytes: image bytes fixture state used by the test cases,
#     uploaded_image: uploaded image fixture state used by the test cases (bytes),
#   ],
#   引数: []
# }
class _ComfyHandler(BaseHTTPRequestHandler):
    prompt_payload: dict[str, Any] = {}
    image_bytes = b"test-png-data"
    uploaded_image: bytes = b""

    # {
    #   責務: [do_POST: records a local fixture POST request and returns its response]
    #   処理: [1: read and decode the posted JSON body, 2: record the request and send the configured response payload]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/upload/image":
            boundary = self.headers["Content-Type"].split("boundary=", 1)[1].encode("ascii")
            image_part = next(
                part for part in body.split(b"--" + boundary) if b'name="image"' in part
            )
            type(self).uploaded_image = image_part.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n", 1)[0]
            self._json({"name": "uploaded-input.png", "subfolder": ""})
            return
        type(self).prompt_payload = json.loads(body)
        self._json({"prompt_id": "fixture-prompt"})

    # {
    #   責務: [do_GET: records a local fixture GET request and returns its response]
    #   処理: [1: record the request method and path, 2: send the configured model-list response]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/history/fixture-prompt":
            self._json(
                {
                    "fixture-prompt": {
                        "status": {"status_str": "success"},
                        "outputs": {
                            "9": {
                                "images": [
                                    {"filename": "generated.png", "subfolder": "", "type": "output"}
                                ]
                            }
                        },
                    }
                }
            )
        elif parsed.path == "/view":
            self.assert_view_query(parse_qs(parsed.query))
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(type(self).image_bytes)
        else:
            self.send_error(404)

    # {
    #   責務: [_json: encodes the payload and writes a JSON HTTP response with content headers]
    #   処理: [1: serialize the payload as JSON bytes, 2: write a response with JSON content headers]
    #   引数: [payload: JSON request/response payload (Any)]
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def _json(self, payload: Any) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    # {
    #   責務: [assert_view_query: fails when the request does not target ComfyUI's image-view endpoint]
    #   処理: [
    #     1: validate the endpoint and required view parameters,
    #     2: raise AssertionError when the request is malformed,
    #   ],
    #   引数: [query: query passed to this helper (dict[str, list[str]])]
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    @staticmethod
    def assert_view_query(query: dict[str, list[str]]) -> None:
        if query != {"filename": ["generated.png"], "type": ["output"]}:
            raise AssertionError(f"unexpected image query: {query}")

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
#   責務: [ComfyUIGenerateCommandTests: related test fixtures and cases for ComfyUIGenerateCommand behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: [
#     temp: temporary root containing fixture files,
#     command: command fixture state used by the test cases,
#     workflow: saved workflow fixture under test,
#   ],
#   引数: []
# }
class ComfyUIGenerateCommandTests(unittest.TestCase):
    # {
    #   責務: [setUpClass: initializes class-wide fixture state for ComfyUIGenerateCommandTests]
    #   処理: [1: create class-wide fixture resources shared by related cases, 2: register cleanup for owned resources]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [test専用のloopback HTTP fixture serverを起動・停止する]
    # }
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _ComfyHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    # {
    #   責務: [tearDownClass: releases class-wide resources created by ComfyUIGenerateCommandTests]
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
    #   責務: [setUp: initializes per-test fixture state for ComfyUIGenerateCommandTests]
    #   処理: [
    #     1: create the per-test inputs and fixture resources required by the scenario,
    #     2: register cleanup for resources owned by the fixture,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def setUp(self) -> None:
        _ComfyHandler.prompt_payload = {}
        _ComfyHandler.uploaded_image = b""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.command = ComfyUIGenerateCommand(timeout=3, poll_interval=0.01)
        self.workflow = {
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "old positive"}},
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "old negative"},
                "_meta": {"title": "Negative Prompt"},
            },
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "test"}},
        }

    # {
    #   責務: [test_https_context_uses_managed_ca_bundle: ComfyUI HTTPS contextは管理対象CAだけを信頼する]
    #   処理: [1: opener内のHTTPS contextを取得する, 2: 検証設定と影響証明書の不在を確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: []
    # }
    def test_https_context_uses_managed_ca_bundle(self) -> None:
        context = next(
            handler._context
            for handler in self.command._opener.handlers
            if isinstance(handler, HTTPSHandler)
        )
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        fingerprints = {
            sha256(certificate).hexdigest()
            for certificate in context.get_ca_certs(binary_form=True)
        }
        self.assertTrue(fingerprints)
        self.assertFalse(fingerprints & set(AFFECTED_CERTIFICATES))

    # {
    #   責務: [
    #     test_generation_output_is_available_to_next_step: verifies the behavior described by "generation output is available to next step",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for generation output is available to next step,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def test_generation_output_is_available_to_next_step(self) -> None:
        observed: list[bytes] = []

        # {
        #   責務: [next_step: records sequence inputs and reads the produced image as the next step would]
        #   処理: [1: record the upstream step values, 2: read the image referenced by the previous step]
        #   引数: [
        #     inputs: input mapping from the previous workflow step (unspecified),
        #     _context: execution context passed through the workflow (unspecified),
        #   ],
        #   戻り値: [result: mapping built or selected by this helper]
        # }
        def next_step(inputs, _context):
            observed.append(Path(inputs["image"]).read_bytes())
            return {"received": True}

        definition = SequenceDefinition(
            "generate-then-inspect",
            (
                SequenceStep(
                    "generate",
                    "comfyui_generate",
                    {
                        "api_url": self.url,
                        "workflow": self.workflow,
                        "prompt": "corrected prompt",
                        "negative_prompt": "unwanted",
                        "overrides": {"9": {"filename_prefix": "sequence"}},
                        "output_dir": str(Path(self.temp.name)),
                    },
                ),
                SequenceStep(
                    "inspect",
                    "inspect",
                    {
                        "image": {"$ref": "context.generate.image"},
                    },
                ),
            ),
        )
        result = SequenceRunner(
            {
                "comfyui_generate": self.command,
                "inspect": next_step,
            }
        ).run(definition)

        self.assertEqual(result.state, "done", result.steps)
        self.assertEqual(observed, [_ComfyHandler.image_bytes])
        self.assertEqual(
            _ComfyHandler.prompt_payload["prompt"]["6"]["inputs"]["text"], "corrected prompt"
        )
        self.assertEqual(_ComfyHandler.prompt_payload["prompt"]["7"]["inputs"]["text"], "unwanted")
        self.assertEqual(
            _ComfyHandler.prompt_payload["prompt"]["9"]["inputs"]["filename_prefix"], "sequence"
        )
        self.assertEqual(self.workflow["6"]["inputs"]["text"], "old positive")
        self.assertEqual(result.context["generate"]["prompt_id"], "fixture-prompt")

    # {
    #   責務: [test_input_image_upload_is_bound_to_load_image_node: verify safe workflow image conditioning]
    #   処理: [upload image bytes and confirm the returned ComfyUI input name is assigned before submission]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_input_image_upload_is_bound_to_load_image_node(self) -> None:
        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "2": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "test"}},
        }
        self.command(
            {
                "api_url": self.url,
                "workflow": workflow,
                "prompt": "expression retouch",
                "image_uploads": {"2": ("retouch-source.png", b"source-image")},
                "output_dir": str(Path(self.temp.name)),
            },
            {},
        )
        self.assertEqual(_ComfyHandler.uploaded_image, b"source-image")
        self.assertEqual(
            _ComfyHandler.prompt_payload["prompt"]["2"]["inputs"]["image"],
            "uploaded-input.png",
        )

    # {
    #   責務: [
    #     test_rejects_non_loopback_url_and_invalid_workflow: verifies the behavior described by "rejects non loopback url and invalid workflow",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for rejects non loopback url and invalid workflow,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def test_rejects_non_loopback_url_and_invalid_workflow(self) -> None:
        with self.assertRaisesRegex(ValueError, "localhost/loopback"):
            self.command(
                {
                    "api_url": "https://example.com",
                    "workflow": self.workflow,
                    "prompt": "test",
                    "output_dir": str(Path(self.temp.name)),
                },
                {},
            )
        with self.assertRaisesRegex(ValueError, "API-format nodes"):
            self.command(
                {
                    "api_url": self.url,
                    "workflow": {"nodes": []},
                    "prompt": "test",
                    "output_dir": str(Path(self.temp.name)),
                },
                {},
            )


if __name__ == "__main__":
    unittest.main()
