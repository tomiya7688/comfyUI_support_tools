"""Offline frozen-executable acceptance probe using temporary synthetic media."""
from pathlib import Path
import tempfile
import time
import threading


def create_samples(root: Path) -> None:
    from PIL import Image, ImageDraw
    import cv2
    import numpy as np

    root.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (160, 100), (38, 80, 140))
    ImageDraw.Draw(image).rectangle((20, 20, 110, 70), fill=(220, 150, 70))
    image.save(root / "画像 sample.png")
    image.save(root / "second.JPG")
    (root / "broken.png").write_bytes(b"not an image")
    video = cv2.VideoWriter(str(root / "clip.avi"), cv2.VideoWriter_fourcc(*"MJPG"), 5, (64, 48))
    try:
        if not video.isOpened():
            raise RuntimeError("Bundled OpenCV cannot write the MJPG test fixture")
        for value in (20, 70, 120, 170, 220):
            video.write(np.full((48, 64, 3), value, dtype=np.uint8))
    finally:
        video.release()


def wait_until(window, predicate, timeout=12.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        window.update()
        if predicate():
            return
        time.sleep(0.01)
    raise RuntimeError("Media browser probe timed out")


def exercise_media(window) -> None:
    with tempfile.TemporaryDirectory(prefix="kadoka_media_") as temporary:
        root = Path(temporary) / "日本語 media"
        create_samples(root)
        window.select_section("all")
        browser = window.workspace.media
        browser.load_folder(str(root), "generated")
        wait_until(window, lambda: not browser.commander.view()[1]["loading"])
        items, info = browser.commander.view()
        if info["loaded"] != 4:
            raise RuntimeError("Media folder did not load all fixtures")
        browser.select(tuple(item.id for item in items[:2]))
        if len(window.media_selection) != 2:
            raise RuntimeError("Multi-selection did not reach Inspector")
        image = next(item for item in items if item.name == "画像 sample.png")
        browser.select((image.id,))
        wait_until(window, lambda: window.media_preview.photo is not None)
        window.select_section("videos")
        videos, _ = browser.commander.view()
        if len(videos) != 1 or videos[0].kind != "video":
            raise RuntimeError("Media filter did not isolate the video")
        browser.select((videos[0].id,))
        wait_until(window, lambda: window.media_preview.photo is not None)
        # Basic preview is a decoded still frame, not real-time/audio playback.
        browser.mode.set("リスト")
        browser._render()
        if browser.table.get_children() != (videos[0].id,):
            raise RuntimeError("List view did not render the video record")
        window.select_section("all")
        browser.query.set("画像")
        browser.apply_query()
        if browser.commander.view()[1]["total"] != 1:
            raise RuntimeError("Unicode media search failed")
        browser.select((image.id,))
        wait_until(window, lambda: window.media_preview.photo is not None)
        # Finish all decoding before temporary files are deleted (Windows locks).
        browser.close()
        wait_until(window, lambda: not any(t.is_alive() for t in threading.enumerate()
                                           if t.name in ("media-scan", "media-preview")))
    print("KadokaTools media browser smoke test: OK")
