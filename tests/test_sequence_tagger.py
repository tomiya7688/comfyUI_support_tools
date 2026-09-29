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

    def do_POST(self) -> None:
        type(self).request_payload = json.loads(
            self.rfile.read(int(self.headers["Content-Length"]))
        )
        type(self).image_bytes = base64.b64decode(type(self).request_payload["image"])
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(type(self).response_payload).encode("utf-8"))

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class TaggerCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _TaggerHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = (
            f"http://127.0.0.1:{cls.server.server_address[1]}"
            "/pixai/v1/interrogate"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        _TaggerHandler.request_payload = {}
        _TaggerHandler.image_bytes = b""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.image_path = Path(self.temp.name) / "input.png"
        Image.new("RGB", (16, 16), "blue").save(self.image_path)
        self.command = TaggerCommand(timeout=2)

    def test_result_is_normalized_and_available_to_next_sequence_step(self) -> None:
        observed: list[tuple[list[str], str]] = []

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
