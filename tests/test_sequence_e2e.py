from __future__ import annotations

from io import BytesIO, StringIO
import base64
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from PIL import Image

from comfyui_support_tools.applications.sequence.data.processing.a1111_generate_command import (
    A1111GenerateCommand,
)
from comfyui_support_tools.applications.sequence.data.processing.sequence_store import SequenceStore
from comfyui_support_tools.entrypoints.sequence_cli import main
from comfyui_support_tools.shared.contracts.sequence_contracts import SequenceDefinition, SequenceStep


# {
#   責務: [_OllamaHandler: loopback HTTP fixture that captures Ollama prompt requests and returns a canned response]
#   処理: [1: provide the configured fields and methods used by the surrounding cases]
#   フィールド: [payload: HTTP request/response payload captured by the fixture (dict[str, Any])]
#   引数: []
# }
class _OllamaHandler(BaseHTTPRequestHandler):
    payload: dict[str, Any] = {}

    # {
    #   責務: [do_POST: records a local fixture POST request and returns its response]
    #   処理: [1: read and decode the posted JSON body, 2: record the request and send the configured response payload]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def do_POST(self) -> None:
        type(self).payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._json({"response": "corrected image prompt"})

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
#   責務: [_ComfyHandler: loopback HTTP fixture that captures ComfyUI prompts and serves a generated image]
#   処理: [1: provide the configured fields and methods used by the surrounding cases]
#   フィールド: [
#     payload: HTTP request/response payload captured by the fixture (dict[str, Any]),
#     image_data: image data fixture state used by the test cases,
#   ],
#   引数: []
# }
class _ComfyHandler(BaseHTTPRequestHandler):
    payload: dict[str, Any] = {}
    image_data = b""

    # {
    #   責務: [do_POST: records a local fixture POST request and returns its response]
    #   処理: [1: read and decode the posted JSON body, 2: record the request and send the configured response payload]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def do_POST(self) -> None:
        type(self).payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._json({"prompt_id": "sequence-e2e"})

    # {
    #   責務: [do_GET: records a local fixture GET request and returns its response]
    #   処理: [1: record the request method and path, 2: send the configured model-list response]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/history/sequence-e2e":
            self._json({
                "sequence-e2e": {
                    "status": {"status_str": "success"},
                    "outputs": {"9": {"images": [
                        {"filename": "sequence.png", "subfolder": "", "type": "output"}
                    ]}},
                }
            })
        elif path == "/view":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(type(self).image_data)
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
#   責務: [_TaggerHandler: loopback HTTP fixture that captures tagger requests and returns controlled tags]
#   処理: [1: provide the configured fields and methods used by the surrounding cases]
#   フィールド: [
#     payload: HTTP request/response payload captured by the fixture (dict[str, Any]),
#     image_data: image data fixture state used by the test cases,
#   ],
#   引数: []
# }
class _TaggerHandler(BaseHTTPRequestHandler):
    payload: dict[str, Any] = {}
    image_data = b""

    # {
    #   責務: [do_POST: records a local fixture POST request and returns its response]
    #   処理: [1: read and decode the posted JSON body, 2: record the request and send the configured response payload]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def do_POST(self) -> None:
        type(self).payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).image_data = base64.b64decode(type(self).payload["image"])
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "general": {"blue sky": 0.95},
            "character": {"sample character": 0.9},
            "rating": {"safe": 0.99},
            "caption": "tagged generated image",
        }).encode("utf-8"))

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
#   責務: [_A1111Handler: reusable fixture or controlled test double for _A1111Handler behavior]
#   処理: [1: provide the configured fields and methods used by the surrounding cases]
#   フィールド: [
#     payload: HTTP request/response payload captured by the fixture (dict[str, Any]),
#     image_data: image data fixture state used by the test cases,
#   ],
#   引数: []
# }
class _A1111Handler(BaseHTTPRequestHandler):
    payload: dict[str, Any] = {}
    image_data = b""

    # {
    #   責務: [do_POST: records a local fixture POST request and returns its response]
    #   処理: [1: read and decode the posted JSON body, 2: record the request and send the configured response payload]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def do_POST(self) -> None:
        type(self).payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        encoded = base64.b64encode(type(self).image_data).decode("ascii")
        data = json.dumps({"images": [encoded]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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
#   責務: [SequenceEndToEndTests: related test fixtures and cases for SequenceEndToEnd behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class SequenceEndToEndTests(unittest.TestCase):
    # {
    #   責務: [setUpClass: initializes class-wide fixture state for SequenceEndToEndTests]
    #   処理: [1: create class-wide fixture resources shared by related cases, 2: register cleanup for owned resources]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [test専用のloopback HTTP fixture serverを起動・停止する]
    # }
    @classmethod
    def setUpClass(cls) -> None:
        cls.servers = []
        cls.threads = []
        for handler in (_OllamaHandler, _ComfyHandler, _TaggerHandler, _A1111Handler):
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            cls.servers.append(server)
            cls.threads.append(thread)
        cls.ollama_url = cls._base_url(cls.servers[0])
        cls.comfy_url = cls._base_url(cls.servers[1])
        cls.tagger_url = cls._base_url(cls.servers[2]) + "/pixai/v1/interrogate"
        cls.a1111_url = cls._base_url(cls.servers[3])

    # {
    #   責務: [tearDownClass: releases class-wide resources created by SequenceEndToEndTests]
    #   処理: [1: stop owned workers/servers and release temporary files or UI resources]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    @classmethod
    def tearDownClass(cls) -> None:
        for server in cls.servers:
            server.shutdown()
            server.server_close()
        for thread in cls.threads:
            thread.join(timeout=2)

    # {
    #   責務: [_base_url: returns the loopback URL for the local fixture server]
    #   処理: [1: read the ephemeral port from the running HTTP server, 2: return its loopback URL]
    #   引数: [server: running local HTTP server (ThreadingHTTPServer)]
    #   戻り値: [result: str produced for the supplied fixture/input]
    # }
    @staticmethod
    def _base_url(server: ThreadingHTTPServer) -> str:
        return f"http://127.0.0.1:{server.server_address[1]}"

    # {
    #   責務: [
    #     test_saved_sequence_runs_ollama_comfyui_and_tagger_through_cli: verifies the behavior described by "saved sequence runs ollama comfyui and tagger through cli",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for saved sequence runs ollama comfyui and tagger through cli,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_saved_sequence_runs_ollama_comfyui_and_tagger_through_cli(self) -> None:
        image_buffer = BytesIO()
        Image.new("RGB", (24, 16), "blue").save(image_buffer, format="PNG")
        _ComfyHandler.image_data = image_buffer.getvalue()
        _OllamaHandler.payload = {}
        _ComfyHandler.payload = {}
        _TaggerHandler.payload = {}
        _TaggerHandler.image_data = b""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated_dir = root / "generated"
            workflow = {
                "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "unmodified"}},
                "7": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"text": "unmodified negative"},
                    "_meta": {"title": "Negative Prompt"},
                },
                "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "e2e"}},
            }
            definition = SequenceDefinition(
                "ollama-comfy-tagger",
                (
                    SequenceStep("correct", "ollama_prompt", {
                        "prompt": "a request in natural language",
                        "model": "fixture-ollama",
                        "api_url": self.ollama_url,
                    }),
                    SequenceStep("generate", "comfyui_generate", {
                        "prompt": {"$ref": "context.correct.prompt_after"},
                        "negative_prompt": "blurry",
                        "workflow": workflow,
                        "api_url": self.comfy_url,
                        "output_dir": str(generated_dir),
                    }),
                    SequenceStep("tag", "tagger", {
                        "image": {"$ref": "context.generate.image"},
                        "url": self.tagger_url,
                        "backend": "pixai_http",
                        "model": "fixture-tagger",
                        "threshold": 0.35,
                    }),
                ),
            )
            SequenceStore(root).save(definition)
            output = StringIO()

            status = main(
                ["--directory", str(root), "run", definition.name],
                stdout=output,
            )

            result = json.loads(output.getvalue())

        self.assertEqual(status, 0, result)
        self.assertEqual(result["state"], "done")
        self.assertEqual(
            [step["state"] for step in result["steps"]],
            ["done", "done", "done"],
        )
        self.assertEqual(result["steps"][0]["outputs"]["prompt_after"], "corrected image prompt")
        submitted_workflow = _ComfyHandler.payload["prompt"]
        self.assertEqual(submitted_workflow["6"]["inputs"]["text"], "corrected image prompt")
        self.assertEqual(submitted_workflow["7"]["inputs"]["text"], "blurry")
        self.assertEqual(result["steps"][2]["inputs"]["image"], result["steps"][1]["outputs"]["image"])
        self.assertEqual(result["steps"][2]["outputs"]["tags"], ["blue sky", "sample character"])
        self.assertEqual(result["steps"][2]["outputs"]["caption_text"], "tagged generated image")
        self.assertTrue(_TaggerHandler.image_data.startswith(b"\x89PNG"))
        self.assertEqual(_OllamaHandler.payload["model"], "fixture-ollama")
        self.assertEqual(_TaggerHandler.payload["model"], "fixture-tagger")
        self.assertEqual(workflow["6"]["inputs"]["text"], "unmodified")

    # {
    #   責務: [
    #     test_saved_sequence_runs_ollama_a1111_and_tagger_through_cli: verifies the behavior described by "saved sequence runs ollama a1111 and tagger through cli",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for saved sequence runs ollama a1111 and tagger through cli,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_saved_sequence_runs_ollama_a1111_and_tagger_through_cli(self) -> None:
        image_buffer = BytesIO()
        Image.new("RGB", (24, 16), "red").save(image_buffer, format="PNG")
        _A1111Handler.image_data = image_buffer.getvalue()
        _OllamaHandler.payload = {}
        _A1111Handler.payload = {}
        _TaggerHandler.payload = {}
        _TaggerHandler.image_data = b""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated_dir = root / "generated"
            definition = SequenceDefinition(
                "ollama-a1111-tagger",
                (
                    SequenceStep("correct", "ollama_prompt", {
                        "prompt": "a natural language request",
                        "model": "fixture-ollama",
                        "api_url": self.ollama_url,
                    }),
                    SequenceStep("generate", "a1111_generate", {
                        "prompt": {"$ref": "context.correct.prompt_after"},
                        "negative_prompt": "blurry",
                        "checkpoint": "fixture.safetensors",
                        "sampler": "Euler a",
                        "steps": 8,
                        "width": 64,
                        "height": 64,
                        "api_url": self.a1111_url,
                        "output_dir": str(generated_dir),
                    }),
                    SequenceStep("tag", "tagger", {
                        "image": {"$ref": "context.generate.image"},
                        "url": self.tagger_url,
                        "backend": "pixai_http",
                        "model": "fixture-tagger",
                        "threshold": 0.35,
                    }),
                ),
            )
            SequenceStore(root).save(definition)
            output = StringIO()

            status = main(
                ["--directory", str(root), "run", definition.name],
                stdout=output,
            )

            result = json.loads(output.getvalue())

        self.assertEqual(status, 0, result)
        self.assertEqual(result["state"], "done")
        self.assertEqual([step["state"] for step in result["steps"]], ["done", "done", "done"])
        self.assertEqual(result["steps"][1]["outputs"]["backend"], "a1111")
        self.assertEqual(result["steps"][2]["inputs"]["image"], result["steps"][1]["outputs"]["image"])
        self.assertEqual(result["steps"][2]["outputs"]["tags"], ["blue sky", "sample character"])
        self.assertEqual(_A1111Handler.payload["prompt"], "corrected image prompt")
        self.assertEqual(_A1111Handler.payload["override_settings"]["sd_model_checkpoint"], "fixture.safetensors")
        self.assertEqual(_A1111Handler.payload["steps"], 8)
        self.assertEqual(_A1111Handler.payload["width"], 64)
        self.assertEqual(_A1111Handler.payload["height"], 64)
        self.assertFalse(_A1111Handler.payload["save_images"])
        self.assertTrue(_TaggerHandler.image_data.startswith(b"\x89PNG"))

    # {
    #   責務: [
    #     test_a1111_command_rejects_remote_api_before_creating_output_directory: verifies the behavior described by "a1111 command rejects remote api before creating output directory",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for a1111 command rejects remote api before creating output directory,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def test_a1111_command_rejects_remote_api_before_creating_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "not-created"
            command = A1111GenerateCommand(request_post=lambda *_args, **_kwargs: self.fail("unexpected API call"))
            with self.assertRaisesRegex(ValueError, "localhost/loopback"):
                command({
                    "api_url": "https://example.com",
                    "prompt": "test",
                    "checkpoint": "fixture.safetensors",
                    "output_dir": str(output_dir),
                }, {})
            self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()
