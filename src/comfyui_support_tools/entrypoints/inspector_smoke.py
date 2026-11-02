"""Offline frozen Inspector probe. Loopback fake Tagger; never real AI inference."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread

from PIL import Image
from comfyui_support_tools.shared.contracts.inspector_contracts import (
    ExportSettings,
    MediaNotes,
    TaggerSettings,
)
from comfyui_support_tools.entrypoints.media_smoke import wait_until


# {
#   責務: [exercise_inspector: temporary loopback Taggerを使ってInspectorのprobe/tag/exportを検証する]
#   処理: [synthetic imagesを開き、fake HTTP応答の分離、batch処理、sidecar出力を検査する]
#   引数: [window: 起動済みInspectorを含むMain GUI window]
#   戻り値: [なし。失敗時はRuntimeErrorを送出]
#   副作用: [loopback HTTP server、temporary files、GUI操作を実行する]
# }
def exercise_inspector(window):
    posted = []

    # {
    # 責務: [Handler: smoke testに限ってTagger HTTP responseを返すloopback handler]
    # フィールド: [posted: exercise_inspector closureが受け取ったrequest payloadを記録]
    # }
    class Handler(BaseHTTPRequestHandler):
        # {
        #   責務: [log_message: fixture serverのHTTP log出力を抑止する]
        #   処理: [BaseHTTPRequestHandler logger callbackを何もせず終了する]
        #   引数: [args: handlerが渡すlog message parts]
        #   戻り値: [なし]
        # }
        def log_message(self, *args):
            pass

        # {
        #   責務: [reply: fixture payloadをJSON HTTP 200 responseとして返す]
        #   処理: [payloadをUTF-8 JSON化してcontent type/length付きで送信する]
        #   引数: [payload: JSON-compatible response object]
        #   戻り値: [なし]
        #   副作用: [HTTP response headers/bodyをsocketへ書き込む]
        # }
        def reply(self, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # {
        #   責務: [do_GET: fixture用model list endpointへの問い合わせに応答する]
        #   処理: [PixAI interrogators pathにはfixture modelを返し、他pathは404にする]
        #   引数: [なし。BaseHTTPRequestHandler request stateを読む]
        #   戻り値: [なし]
        #   副作用: [HTTP responseを送信する]
        # }
        def do_GET(self):
            if self.path != "/pixai/v1/interrogators":
                self.send_error(404)
                return
            self.reply({"models": ["smoke-fixture"]})

        # {
        #   責務: [do_POST: Tagger requestを記録し、カテゴリ分離を検査できる固定応答を返す]
        #   処理: [content-length分のJSON requestを読みclosure listへ記録し、synthetic tag payloadを応答する]
        #   引数: [なし。BaseHTTPRequestHandler request stateを読む]
        #   戻り値: [なし]
        #   副作用: [posted listを更新しHTTP responseを送信する]
        # }
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            posted.append(payload)
            self.reply(
                {
                    "general": {"synthetic_fixture": 0.99, "below_threshold": 0.1},
                    "character": {"fixture_character": 0.95},
                    "rating": {"safe": 0.8, "questionable": 0.2},
                    "caption": "synthetic caption",
                    "style": {"must_not_mix_into_content": 0.99},
                }
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryDirectory(prefix="inspector_smoke_") as temp:
            root = Path(temp) / "日本語 action"
            root.mkdir()
            for name in ("one.png", "two.png"):
                Image.new("RGB", (40, 30), "blue").save(root / name)
            window.select_section("all")
            browser = window.workspace.media
            browser.load_folder(str(root))
            wait_until(window, lambda: not browser.commander.view()[1]["loading"])
            wait_until(window, lambda: len(browser.grid_view.images) == 2)
            items, _ = browser.commander.view()
            browser.select((items[0].id,))
            wait_until(window, lambda: window.media_preview.photo is not None)
            panel = window.action_panel
            panel.commander.save_notes(
                MediaNotes(
                    style_tags=("manual-style",),
                    prompt="manual-prompt",
                )
            )
            panel.commander.configure(
                TaggerSettings(
                    f"http://127.0.0.1:{server.server_port}/pixai/v1/interrogate",
                    "smoke-fixture",
                    backend="pixai_http",
                )
            )
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
            if (
                notes.content_tags != ("synthetic_fixture",)
                or notes.character_tags != ("fixture_character",)
                or notes.rating != "safe"
                or notes.caption != "synthetic caption"
                or notes.style_tags != ("manual-style",)
                or notes.prompt != "manual-prompt"
                or "must_not_mix_into_content" in notes.content_tags
            ):
                raise RuntimeError("Normalized Tag fields were not kept separate")
            if "safe" not in panel.fields["rating"].get("1.0", "end"):
                raise RuntimeError("Frozen Inspector did not display rating")

            batch = root / "batch.txt"
            panel.commander.export(
                ExportSettings(
                    caption_sidecar=True,
                    metadata_sidecar=True,
                    batch_txt_path=str(batch),
                )
            )
            wait_until(window, lambda: not panel.commander.status().busy)
            caption = Path(items[0].path).with_suffix(".txt")
            metadata = Path(items[0].path).with_suffix(Path(items[0].path).suffix + ".kadoka.json")
            if not caption.is_file() or not metadata.is_file() or not batch.is_file():
                raise RuntimeError("Frozen analysis export did not create expected files")
            if "synthetic caption" not in caption.read_text(encoding="utf-8"):
                raise RuntimeError("Frozen caption export content is wrong")
            structured = json.loads(metadata.read_text(encoding="utf-8"))
            if structured["analysis"]["rating"] != "safe" or structured["analysis"][
                "style_tags"
            ] != ["manual-style"]:
                raise RuntimeError("Frozen metadata export lost separated fields")
            wait_until(window, lambda: window.media_preview.photo is not None)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(3)
    print(
        "KadokaTools Inspector normalized Tag + export smoke test: OK (loopback fixture, not AI inference)"
    )
