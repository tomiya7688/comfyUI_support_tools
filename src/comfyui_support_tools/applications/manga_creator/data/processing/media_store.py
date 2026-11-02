"""Safe panel artifact storage, lettering, and page composition."""

from __future__ import annotations

import io
import os
import re
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from comfyui_support_tools.shared.contracts.manga_creator import (
    BalloonKind,
    MangaPage,
    MangaProject,
    MangaStyleMode,
)

MAX_PANEL_IMAGE_BYTES = 64 * 1024 * 1024
MAX_PANEL_PIXELS = 80_000_000
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_CJK_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
)


# {
# 責務: [_atomic_write: safely replace one generated image artifact]
# 処理: [write through a same-directory temporary file and atomically publish it]
# 引数: [path: destination artifact path, content: encoded image bytes]
# 戻り値: [Path: published artifact path]
# }
def _atomic_write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return path


# {
# 責務: [_create_new: create a new artifact without replacing an existing revision]
# 処理: [reserve with exclusive file creation, then write and fsync the bytes]
# 引数: [path: unique destination path, content: encoded image bytes]
# 戻り値: [Path: newly created artifact]
# }
def _create_new(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


# {
# 責務: [_open_panel_image: decode one bounded image artifact]
# 処理: [reject oversized or malformed images and return a detached RGB copy]
# 引数: [source: image bytes or local image path]
# 戻り値: [Image.Image: verified RGB panel pixels]
# }
def _open_panel_image(source: bytes | str | Path) -> Image.Image:
    if isinstance(source, bytes):
        if not 1 <= len(source) <= MAX_PANEL_IMAGE_BYTES:
            raise ValueError("panel image bytes exceed the 64 MiB limit")
        stream: io.BytesIO | Path = io.BytesIO(source)
    else:
        path = Path(source)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PANEL_IMAGE_BYTES:
            raise ValueError("panel image path is missing, linked, or oversized")
        stream = path
    try:
        with Image.open(stream) as image:
            if image.width < 1 or image.height < 1 or image.width * image.height > MAX_PANEL_PIXELS:
                raise ValueError("panel image dimensions exceed safe limits")
            image.verify()
        with Image.open(stream) as image:
            return ImageOps.exif_transpose(image).convert("RGB")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("panel image is malformed or unsafe") from error


# {
# 責務: [store_panel_image: persist one immutable panel render candidate]
# 処理: [validate PNG bytes and write a versioned artifact without overwriting prior attempts]
# 引数: [project_dir: project artifact directory, panel_id: stable panel ID, revision: render attempt, image_bytes: candidate PNG]
# 戻り値: [Path: saved panel artifact]
# }
def store_panel_image(
    project_dir: str | Path, panel_id: str, revision: int, image_bytes: bytes
) -> Path:
    if not _SAFE_ID.fullmatch(panel_id) or revision < 1:
        raise ValueError("panel artifact identifier or revision is invalid")
    image = _open_panel_image(image_bytes)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    path = Path(project_dir) / "panels" / f"{panel_id}-v{revision:03d}.png"
    return _create_new(path, output.getvalue())


# {
# 責務: [store_panel_candidate: reserve a new image revision for a panel]
# 処理: [find the next free monotonically increasing revision and store the image]
# 引数: [project_dir: artifact directory, panel_id: stable panel ID, image_bytes: candidate image]
# 戻り値: [Path: unique candidate image path]
# }
def store_panel_candidate(project_dir: str | Path, panel_id: str, image_bytes: bytes) -> Path:
    panel_directory = Path(project_dir) / "panels"
    if not _SAFE_ID.fullmatch(panel_id):
        raise ValueError("panel artifact identifier is invalid")
    for revision in range(1, 1_000_001):
        candidate = panel_directory / f"{panel_id}-v{revision:03d}.png"
        if candidate.exists() or candidate.is_symlink():
            continue
        try:
            return store_panel_image(project_dir, panel_id, revision, image_bytes)
        except FileExistsError:
            continue
    raise RuntimeError("panel revision limit reached")


# {
# 責務: [inspect_panel_image: validate a generated panel and return its dimensions]
# 処理: [decode the bounded image without persisting the candidate]
# 引数: [image_bytes: candidate encoded image]
# 戻り値: [tuple[int, int]: width and height]
# }
def inspect_panel_image(image_bytes: bytes) -> tuple[int, int]:
    return _open_panel_image(image_bytes).size


# {
# 責務: [read_project_asset: read one bounded image inside the project asset root]
# 処理: [resolve a relative path and reject traversal, links, and oversized files]
# 引数: [project_dir: trusted project root, relative_path: stored project asset path]
# 戻り値: [bytes: encoded asset data]
# }
def read_project_asset(project_dir: str | Path, relative_path: str) -> bytes:
    root = Path(project_dir).resolve(strict=True)
    source = Path(relative_path)
    if source.is_absolute():
        raise ValueError("project asset path must be relative")
    resolved = (root / source).resolve(strict=True)
    unresolved = root / source
    if not resolved.is_relative_to(root) or unresolved.is_symlink() or not resolved.is_file():
        raise ValueError("project asset path is outside the project or unsafe")
    if resolved.stat().st_size > MAX_PANEL_IMAGE_BYTES:
        raise ValueError("project asset exceeds the 64 MiB limit")
    return resolved.read_bytes()


# {
# 責務: [_font: select a font capable of rendering Japanese dialogue where available]
# 処理: [prefer project-configured font, then known CJK font paths, then a safe fallback]
# 引数: [project: manga project font settings, size: desired render size]
# 戻り値: [ImageFont.ImageFont: selected font]
# }
def _font(project: MangaProject, size: int) -> ImageFont.ImageFont:
    configured = dict(project.generation_settings).get("font_path")
    candidates = ((configured,) if configured else ()) + _CJK_FONT_CANDIDATES
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


# {
# 責務: [_draw_dialogue: draw one editable balloon and exact script text]
# 処理: [draw balloon type, optional tail, and horizontal or vertical text into the page overlay]
# 引数: [draw: page drawing surface, line: dialogue, panel_rect: panel pixels, project: font/style context]
# 戻り値: [str | None: missing font warning when Japanese glyph support is unavailable]
# }
def _draw_dialogue(
    draw: ImageDraw.ImageDraw,
    line: object,
    panel_rect: tuple[int, int, int, int],
    project: MangaProject,
) -> str | None:
    left, top, right, bottom = panel_rect
    x, y, width, height = line.region
    balloon = (
        left + int(x * (right - left)),
        top + int(y * (bottom - top)),
        left + int((x + width) * (right - left)),
        top + int((y + height) * (bottom - top)),
    )
    fill = "white" if project.style != MangaStyleMode.COLOR else "#fffefb"
    outline = "black" if line.kind != BalloonKind.WHISPER else "#777777"
    if line.kind == BalloonKind.NARRATION:
        draw.rounded_rectangle(balloon, radius=5, fill=fill, outline=outline, width=2)
    elif line.kind != BalloonKind.SFX:
        draw.ellipse(balloon, fill=fill, outline=outline, width=2)
        if line.kind == BalloonKind.THOUGHT:
            center_x = (balloon[0] + balloon[2]) // 2
            draw.ellipse(
                (center_x - 4, balloon[3] + 5, center_x + 4, balloon[3] + 13),
                fill=fill,
                outline=outline,
            )
        elif line.tail_target:
            tail_x = left + int(line.tail_target[0] * (right - left))
            tail_y = top + int(line.tail_target[1] * (bottom - top))
            origin_x = min(balloon[2] - 8, max(balloon[0] + 8, tail_x))
            draw.polygon(
                ((origin_x - 7, balloon[3] - 2), (origin_x + 7, balloon[3] - 2), (tail_x, tail_y)),
                fill=fill,
            )
            draw.line(
                ((origin_x - 7, balloon[3] - 2), (tail_x, tail_y), (origin_x + 7, balloon[3] - 2)),
                fill=outline,
                width=2,
            )
    font_size = max(
        10, min(42, (balloon[3] - balloon[1]) // max(2, min(6, len(line.text) // 4 + 1)))
    )
    font = _font(project, font_size)
    text_box = (balloon[0] + 8, balloon[1] + 5, balloon[2] - 8, balloon[3] - 5)
    try:
        if line.vertical:
            cursor_x = text_box[2] - font_size
            for character in line.text:
                if character in "\n\r":
                    cursor_x -= font_size
                    continue
                draw.text((cursor_x, text_box[1]), character, font=font, fill="black")
                text_box = (text_box[0], text_box[1] + font_size, text_box[2], text_box[3])
        else:
            draw.multiline_text(
                (text_box[0], text_box[1]),
                line.text,
                font=font,
                fill="black",
                spacing=2,
                align="center",
            )
    except UnicodeEncodeError:
        draw.text(
            (text_box[0], text_box[1]),
            "[font unavailable]",
            font=ImageFont.load_default(),
            fill="black",
        )
        if any(ord(character) > 127 for character in line.text):
            return "Japanese glyphs were replaced in the preview because no CJK font was available."
    return None


# {
# 責務: [compose_page_image: assemble panel images and separately rendered dialogue]
# 処理: [place panels in page order, preserve aspect ratio, draw gutters and letter overlays]
# 引数: [project: manga project, page: selected page, project_dir: asset path root, page_size: output pixel dimensions]
# 戻り値: [tuple[bytes, tuple[str, ...]]: composed PNG bytes and rendering warnings]
# }
def compose_page_image(
    project: MangaProject,
    page: MangaPage,
    project_dir: str | Path,
    page_size: tuple[int, int] = (1600, 2200),
) -> tuple[bytes, tuple[str, ...]]:
    if page_size[0] < 64 or page_size[1] < 64 or page_size[0] * page_size[1] > MAX_PANEL_PIXELS:
        raise ValueError("page output dimensions are outside safe limits")
    background = "white" if project.style == MangaStyleMode.BLACK_AND_WHITE else "#faf8f4"
    page_image = Image.new("RGB", page_size, background)
    draw = ImageDraw.Draw(page_image)
    warnings = []
    for panel in sorted(page.panels, key=lambda item: item.order):
        if not panel.image_path:
            continue
        source = Path(panel.image_path)
        if not source.is_absolute():
            source = Path(project_dir) / source
        panel_image = _open_panel_image(source)
        x, y, width, height = panel.bbox
        rect = (
            round(x * page_size[0]),
            round(y * page_size[1]),
            round((x + width) * page_size[0]),
            round((y + height) * page_size[1]),
        )
        panel_width, panel_height = rect[2] - rect[0], rect[3] - rect[1]
        fitted = ImageOps.fit(
            panel_image, (panel_width, panel_height), method=Image.Resampling.LANCZOS
        )
        page_image.paste(fitted, (rect[0], rect[1]))
        draw.rectangle(rect, outline="black", width=max(2, page_size[0] // 800))
        for line in panel.dialogue:
            warning = _draw_dialogue(draw, line, rect, project)
            if warning:
                warnings.append(warning)
    output = io.BytesIO()
    page_image.save(output, format="PNG", optimize=True)
    return output.getvalue(), tuple(dict.fromkeys(warnings))


# {
# 責務: [store_page_image: atomically persist one composed page image]
# 処理: [write the PNG artifact using a safe stable page identifier]
# 引数: [project_dir: artifact root, page_id: page identifier, image_bytes: composed PNG]
# 戻り値: [Path: saved page path]
# }
def store_page_image(project_dir: str | Path, page_id: str, image_bytes: bytes) -> Path:
    if not _SAFE_ID.fullmatch(page_id):
        raise ValueError("page artifact identifier is invalid")
    image = _open_panel_image(image_bytes)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return _atomic_write(Path(project_dir) / "pages" / f"{page_id}.png", output.getvalue())
