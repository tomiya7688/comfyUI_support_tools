"""Offline frozen-executable acceptance probe using temporary synthetic media."""

from pathlib import Path
import tempfile
import time
import threading


# {
#   責務: [create_samples: media browser acceptance probe用のsynthetic image/video/broken fileを作る]
#   処理: [出力directoryを作成し、日本語名画像2枚、壊れた画像、MJPG videoを保存する]
#   引数: [root: fixture filesを書き出すdirectory]
#   戻り値: [なし]
#   副作用: [root配下へtemporary fixture filesを作成する]
#   エラー: [OpenCV video writerを開けない場合RuntimeError]
# }
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


# {
#   責務: [wait_until: GUI updateを回しながら非同期smoke conditionを待つ]
#   処理: [monotonic deadlineまでwindow.updateとpredicate確認を繰り返す]
#   引数: [window: update可能なTk window, predicate: 完了条件, timeout: 待機秒数]
#   戻り値: [なし。condition成立時にreturn]
#   エラー: [RuntimeError: timeout内にconditionが成立しない]
#   副作用: [window event loopを逐次更新し、短時間sleepする]
# }
def wait_until(window, predicate, timeout=12.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        window.update()
        if predicate():
            return
        time.sleep(0.01)
    raise RuntimeError("Media browser probe timed out")


# {
#   責務: [exercise_media: synthetic mediaを使ってbrowser scan/filter/preview/list selectionを検証する]
#   処理: [一時directoryを作り、画像/動画、複数選択、Unicode検索、list表示とworker終了を確認する]
#   引数: [window: 起動済みMain GUI window]
#   戻り値: [なし。検証失敗時RuntimeError]
#   副作用: [GUI stateとtemporary filesを操作し、decoder worker終了を待つ]
# }
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
        wait_until(
            window,
            lambda: (
                not any(
                    t.is_alive()
                    for t in threading.enumerate()
                    if t.name in ("media-scan", "media-preview")
                )
            ),
        )
    print("KadokaTools media browser smoke test: OK")
