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


class _OllamaHandler(BaseHTTPRequestHandler):
    payload: dict[str, Any] = {}

    def do_POST(self) -> None:
        type(self).payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._json({"response": "corrected image prompt"})

    def _json(self, payload: Any) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class _ComfyHandler(BaseHTTPRequestHandler):
    payload: dict[str, Any] = {}
    image_data = b""

    def do_POST(self) -> None:
        type(self).payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._json({"prompt_id": "sequence-e2e"})

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

    def _json(self, payload: Any) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class _TaggerHandler(BaseHTTPRequestHandler):
    payload: dict[str, Any] = {}
    image_data = b""

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

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class _A1111Handler(BaseHTTPRequestHandler):
    payload: dict[str, Any] = {}
    image_data = b""

    def do_POST(self) -> None:
        type(self).payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        encoded = base64.b64encode(type(self).image_data).decode("ascii")
        data = json.dumps({"images": [encoded]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class SequenceEndToEndTests(unittest.TestCase):
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

    @classmethod
    def tearDownClass(cls) -> None:
        for server in cls.servers:
            server.shutdown()
            server.server_close()
        for thread in cls.threads:
            thread.join(timeout=2)

    @staticmethod
    def _base_url(server: ThreadingHTTPServer) -> str:
        return f"http://127.0.0.1:{server.server_address[1]}"

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
