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


# {
#   責務: [_OllamaHandler: loopback HTTP fixture that captures Ollama prompt requests and returns a canned response]
#   処理: [1: provide the configured fields and methods used by the surrounding cases]
#   フィールド: [
#     request_payload: request body captured by the local endpoint (dict[str, Any]),
#     generated_prompt: generated prompt fixture state used by the test cases,
#   ],
#   引数: []
# }
class _OllamaHandler(BaseHTTPRequestHandler):
    request_payload: dict[str, Any] = {}
    generated_prompt = "corrected prompt"

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
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"response": type(self).generated_prompt}).encode("utf-8"))

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
#   責務: [OllamaPromptCommandTests: related test fixtures and cases for OllamaPromptCommand behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class OllamaPromptCommandTests(unittest.TestCase):
    # {
    #   責務: [setUpClass: initializes class-wide fixture state for OllamaPromptCommandTests]
    #   処理: [1: create class-wide fixture resources shared by related cases, 2: register cleanup for owned resources]
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [test専用のloopback HTTP fixture serverを起動・停止する]
    # }
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.api_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    # {
    #   責務: [tearDownClass: releases class-wide resources created by OllamaPromptCommandTests]
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
    #   責務: [setUp: initializes per-test fixture state for OllamaPromptCommandTests]
    #   処理: [
    #     1: create the per-test inputs and fixture resources required by the scenario,
    #     2: register cleanup for resources owned by the fixture,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def setUp(self) -> None:
        _OllamaHandler.request_payload = {}
        _OllamaHandler.generated_prompt = "corrected prompt"

    # {
    #   責務: [
    #     test_returns_before_and_after_and_uses_non_streaming_api: verifies the behavior described by "returns before and after and uses non streaming api",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for returns before and after and uses non streaming api,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
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

    # {
    #   責務: [
    #     test_corrected_prompt_flows_directly_into_next_command: verifies the behavior described by "corrected prompt flows directly into next command",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for corrected prompt flows directly into next command,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
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

        # {
        #   責務: [generate: returns a deterministic image payload for the supplied generation request]
        #   処理: [
        #     1: record or derive the generation output from the supplied sequence inputs,
        #     2: return the deterministic output payload,
        #   ],
        #   引数: [
        #     inputs: input mapping from the previous workflow step (unspecified),
        #     _context: execution context passed through the workflow (unspecified),
        #   ],
        #   戻り値: [result: mapping built or selected by this helper]
        # }
        def generate(inputs, _context):
            generated_prompts.append(inputs["prompt"])
            return {"submitted_prompt": inputs["prompt"]}

        result = SequenceRunner(
            {"ollama.correct": OllamaPromptCommand(timeout=2), "generate": generate}
        ).run(definition)

        self.assertEqual(result.state, "done")
        self.assertEqual(generated_prompts, ["corrected prompt"])

    # {
    #   責務: [
    #     test_rejects_missing_model_and_non_base_api_url: verifies the behavior described by "rejects missing model and non base api url",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for rejects missing model and non base api url,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
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
