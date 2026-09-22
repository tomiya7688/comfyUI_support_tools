"""Offline frozen Action probe. Fake loopback Tagger; never real AI inference."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread

from PIL import Image
from comfyui_support_tools.shared.contracts.inspector_contracts import MediaNotes, TaggerSettings
from comfyui_support_tools.entrypoints.media_smoke import wait_until


def exercise_inspector(window):
    posted = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/pixai/v1/interrogators":
                self.send_error(404)
                return
            self.reply({"models": ["smoke-fixture"]})

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            posted.append(payload)
            self.reply({"tags": {"synthetic_fixture": 0.99}})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryDirectory(prefix="inspector_smoke_") as temp:
            root = Path(temp)/"日本語 action"
            root.mkdir()
            for name in ("one.png", "two.png"):
                Image.new("RGB", (40, 30), "blue").save(root/name)
            window.select_section("all")
            browser = window.workspace.media
            browser.load_folder(str(root))
            wait_until(window, lambda: not browser.commander.view()[1]["loading"])
            wait_until(window, lambda: len(browser.grid_view.images) == 2)
            items, _ = browser.commander.view()
            browser.select((items[0].id,))
            wait_until(window, lambda: window.media_preview.photo is not None)
            panel = window.action_panel
            panel.commander.save_notes(MediaNotes(style_tags=("manual-style",), prompt="manual-prompt"))
            panel.commander.configure(TaggerSettings(
                f"http://127.0.0.1:{server.server_port}/pixai/v1/interrogate", "smoke-fixture"))
            panel.commander.start("probe")
            wait_until(window, lambda: not panel.commander.status().busy)
            if not panel.commander.status().ready:
                raise RuntimeError("Inspector fixture probe failed")
            browser.select(tuple(item.id for item in items))
            panel.commander.start("tag")
            wait_until(window, lambda: not panel.commander.status().busy)
            if len(posted) != 2 or "成功2" not in panel.commander.status().message:
                raise RuntimeError("Frozen Tag batch did not finish")
            browser.select((items[0].id,))
            notes = panel.commander.notes()
            if (notes.content_tags != ("synthetic_fixture",) or notes.style_tags != ("manual-style",)
                    or notes.prompt != "manual-prompt"):
                raise RuntimeError("Inspector fields were not kept separate")
            if "synthetic_fixture" not in panel.fields["content_tags"].get("1.0", "end"):
                raise RuntimeError("Frozen Inspector did not display Tag result")
            wait_until(window, lambda: window.media_preview.photo is not None)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(3)
    print("KadokaTools Inspector Tag Action smoke test: OK (loopback fixture, not AI inference)")
