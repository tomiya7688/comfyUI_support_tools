from __future__ import annotations

import json
from hashlib import sha256
from io import BytesIO
import ssl
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

from comfyui_support_tools.applications.sequence.data.processing.ollama_prompt_command import (
    OllamaPromptCommand,
)
from tools.security.check_python_ca import AFFECTED_CERTIFICATES
from comfyui_support_tools.applications.sequence.process.processing.sequence_runner import (
    SequenceRunner,
)
from comfyui_support_tools.shared.contracts.sequence_contracts import (
    SequenceDefinition,
    SequenceStep,
)


class _OllamaHandler(BaseHTTPRequestHandler):
    request_payload: dict[str, Any] = {}
    generated_prompt = "corrected prompt"

    def do_POST(self) -> None:
        type(self).request_payload = json.loads(
            self.rfile.read(int(self.headers["Content-Length"]))
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"response": type(self).generated_prompt}).encode("utf-8"))

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class OllamaPromptCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.api_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        _OllamaHandler.request_payload = {}
        _OllamaHandler.generated_prompt = "corrected prompt"

    def test_returns_before_and_after_and_uses_non_streaming_api(self) -> None:
        command = OllamaPromptCommand(timeout=2)
        result = command(
            {"prompt": "  original request  ", "model": "model:latest", "api_url": self.api_url},
            {},
        )

        self.assertEqual(result["prompt_before"], "original request")
        self.assertEqual(result["prompt_after"], "corrected prompt")
        self.assertEqual(_OllamaHandler.request_payload["model"], "model:latest")
        self.assertFalse(_OllamaHandler.request_payload["stream"])

    def test_corrected_prompt_flows_directly_into_next_command(self) -> None:
        generated_prompts: list[str] = []
        definition = SequenceDefinition(
            "ollama-to-generation",
            (
                SequenceStep(
                    "correct",
                    "ollama.correct",
                    {
                        "prompt": "sunset city",
                        "model": "model:latest",
                        "api_url": self.api_url,
                    },
                ),
                SequenceStep(
                    "generate",
                    "generate",
                    {"prompt": {"$ref": "context.correct.prompt_after"}},
                ),
            ),
        )

        def generate(inputs, _context):
            generated_prompts.append(inputs["prompt"])
            return {"submitted_prompt": inputs["prompt"]}

        result = SequenceRunner(
            {"ollama.correct": OllamaPromptCommand(timeout=2), "generate": generate}
        ).run(definition)

        self.assertEqual(result.state, "done")
        self.assertEqual(generated_prompts, ["corrected prompt"])

    def test_rejects_missing_model_and_non_base_api_url(self) -> None:
        command = OllamaPromptCommand(timeout=2)
        with self.assertRaisesRegex(ValueError, "model"):
            command({"prompt": "request"}, {})
        with self.assertRaisesRegex(ValueError, "base URL"):
            command(
                {
                    "prompt": "request",
                    "model": "m",
                    "api_url": self.api_url + "/custom",
                },
                {},
            )

    # {
    #   責務: [test_https_uses_managed_ca_bundle: HTTPS通信で管理対象CA bundleのcontextを使う]
    #   処理: [1: HTTPS応答を模擬する, 2: urlopenへ渡されたcontextから問題CAがないことを確認する]
    #   引数: [self: テストインスタンス]
    #   戻り値: []
    # }
    def test_https_uses_managed_ca_bundle(self) -> None:
        with patch(
            "comfyui_support_tools.applications.sequence.data.processing.ollama_prompt_command.urlopen",
            return_value=BytesIO(b'{"response":"ok"}'),
        ) as urlopen:
            OllamaPromptCommand(timeout=2)._post_json("https://example.com", {})

        context = urlopen.call_args.kwargs["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        fingerprints = {
            sha256(certificate).hexdigest()
            for certificate in context.get_ca_certs(binary_form=True)
        }
        self.assertTrue(fingerprints)
        self.assertFalse(fingerprints & set(AFFECTED_CERTIFICATES))


if __name__ == "__main__":
    unittest.main()
