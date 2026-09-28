from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from comfyui_support_tools.applications.sequence.data.processing.comfyui_generate_command import (
    ComfyUIGenerateCommand,
)
from comfyui_support_tools.applications.sequence.process.processing.sequence_runner import SequenceRunner
from comfyui_support_tools.shared.contracts.sequence_contracts import SequenceDefinition, SequenceStep


class _ComfyHandler(BaseHTTPRequestHandler):
    prompt_payload: dict[str, Any] = {}
    image_bytes = b"test-png-data"

    def do_POST(self) -> None:
        type(self).prompt_payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._json({"prompt_id": "fixture-prompt"})

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/history/fixture-prompt":
            self._json({
                "fixture-prompt": {
                    "status": {"status_str": "success"},
                    "outputs": {"9": {"images": [
                        {"filename": "generated.png", "subfolder": "", "type": "output"}
                    ]}},
                }
            })
        elif parsed.path == "/view":
            self.assert_view_query(parse_qs(parsed.query))
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(type(self).image_bytes)
        else:
            self.send_error(404)

    def _json(self, payload: Any) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def assert_view_query(query: dict[str, list[str]]) -> None:
        if query != {"filename": ["generated.png"], "type": ["output"]}:
            raise AssertionError(f"unexpected image query: {query}")

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class ComfyUIGenerateCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _ComfyHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        _ComfyHandler.prompt_payload = {}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.command = ComfyUIGenerateCommand(timeout=3, poll_interval=0.01)
        self.workflow = {
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "old positive"}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "old negative"},
                  "_meta": {"title": "Negative Prompt"}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "test"}},
        }

    def test_generation_output_is_available_to_next_step(self) -> None:
        observed: list[bytes] = []

        def next_step(inputs, _context):
            observed.append(Path(inputs["image"]).read_bytes())
            return {"received": True}

        definition = SequenceDefinition("generate-then-inspect", (
            SequenceStep("generate", "comfyui_generate", {
                "api_url": self.url,
                "workflow": self.workflow,
                "prompt": "corrected prompt",
                "negative_prompt": "unwanted",
                "overrides": {"9": {"filename_prefix": "sequence"}},
                "output_dir": str(Path(self.temp.name)),
            }),
            SequenceStep("inspect", "inspect", {
                "image": {"$ref": "context.generate.image"},
            }),
        ))
        result = SequenceRunner({
            "comfyui_generate": self.command,
            "inspect": next_step,
        }).run(definition)

        self.assertEqual(result.state, "done", result.steps)
        self.assertEqual(observed, [_ComfyHandler.image_bytes])
        self.assertEqual(_ComfyHandler.prompt_payload["prompt"]["6"]["inputs"]["text"], "corrected prompt")
        self.assertEqual(_ComfyHandler.prompt_payload["prompt"]["7"]["inputs"]["text"], "unwanted")
        self.assertEqual(_ComfyHandler.prompt_payload["prompt"]["9"]["inputs"]["filename_prefix"], "sequence")
        self.assertEqual(self.workflow["6"]["inputs"]["text"], "old positive")
        self.assertEqual(result.context["generate"]["prompt_id"], "fixture-prompt")

    def test_rejects_non_loopback_url_and_invalid_workflow(self) -> None:
        with self.assertRaisesRegex(ValueError, "localhost/loopback"):
            self.command({
                "api_url": "https://example.com",
                "workflow": self.workflow,
                "prompt": "test",
                "output_dir": str(Path(self.temp.name)),
            }, {})
        with self.assertRaisesRegex(ValueError, "API-format nodes"):
            self.command({
                "api_url": self.url,
                "workflow": {"nodes": []},
                "prompt": "test",
                "output_dir": str(Path(self.temp.name)),
            }, {})


if __name__ == "__main__":
    unittest.main()
