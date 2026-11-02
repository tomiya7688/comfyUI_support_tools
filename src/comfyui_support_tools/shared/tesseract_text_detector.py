"""Optional local OCR adapter for low-information frame analysis."""

from __future__ import annotations

import csv
import io
import math
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from comfyui_support_tools.shared.contracts.frame_filter import FrameTextBox

DEFAULT_TIMEOUT_SECONDS = 20.0


# {
#   責務: [default_tesseract_text_detector: PATH上のTesseract adapterをprocess内で再利用する]
#   処理: [1: executable/version/languagesを初回だけ検査する 2: cached detectorを返す]
#   引数: []
#   戻り値: [detector: local OCR adapter]
# }
@lru_cache(maxsize=1)
def default_tesseract_text_detector() -> TesseractTextDetector:
    return TesseractTextDetector()


# {
#   責務: [TesseractTextDetector: ローカルTesseractをnormalized text-box providerとして公開する]
#   フィールド: [executable、languages、version、timeout]
# }
class TesseractTextDetector:
    # {
    #   責務: [__init__: 実行可能なTesseractと言語データを検査する]
    #   処理: [1: executableを解決する 2: version/langを取得し指定言語を確認する]
    #   引数: [executable: optional binary path, languages: OCR language expression, timeout: command timeout]
    #   戻り値: []
    # }
    def __init__(
        self,
        executable: str | Path | None = None,
        *,
        languages: str = "auto",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        resolved = str(executable) if executable is not None else shutil.which("tesseract")
        if not resolved:
            raise FileNotFoundError("Tesseract is required for text-only/title-card filtering")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("Tesseract timeout must be positive")
        self.executable = resolved
        self.timeout = float(timeout)
        versions = self._command(("--version",)).splitlines()
        if not versions or not versions[0].strip():
            raise RuntimeError("Tesseract did not report its version")
        self.version = versions[0].strip()
        available = self._available_languages()
        if languages == "auto":
            selected = "jpn+eng" if {"jpn", "eng"}.issubset(available) else "eng"
        else:
            selected = languages
        if not isinstance(selected, str):
            raise ValueError("Tesseract languages must be a nonempty string")
        requested = set(selected.split("+"))
        if not selected or not requested.issubset(available):
            missing = ", ".join(sorted(requested - available)) or "a language"
            raise ValueError(f"Tesseract language data is missing: {missing}")
        self.languages = selected

    # {
    #   責務: [__call__: RGB image pixelsをTesseract TSVへ渡し行単位のnormalized OCR boxesを返す]
    #   処理: [1: PNG bytesを作る 2: bounded subprocessを実行する 3: TSV linesをboxへ集約する]
    #   引数: [pixels: RGB uint8 image]
    #   戻り値: [boxes: normalized OCR line boxes]
    # }
    def __call__(self, pixels: np.ndarray) -> tuple[FrameTextBox, ...]:
        if (
            not isinstance(pixels, np.ndarray)
            or pixels.ndim != 3
            or pixels.shape[2] != 3
            or pixels.dtype != np.uint8
        ):
            raise ValueError("Tesseract input must be an RGB uint8 image")
        height, width, _channels = pixels.shape
        if width < 1 or height < 1:
            raise ValueError("Tesseract input image cannot be empty")
        image_buffer = io.BytesIO()
        Image.fromarray(pixels, mode="RGB").save(image_buffer, format="PNG")
        output = self._command(
            ("stdin", "stdout", "-l", self.languages, "--psm", "11", "tsv"),
            input_bytes=image_buffer.getvalue(),
        )
        return _parse_tsv_lines(output, width, height)

    # {
    #   責務: [_available_languages: Tesseract language dataを一覧化する]
    #   処理: [1: --list-langsを実行する 2: nonempty language identifiersを返す]
    #   引数: []
    #   戻り値: [languages: installed language codes]
    # }
    def _available_languages(self) -> set[str]:
        output = self._command(("--list-langs",))
        return {line.strip() for line in output.splitlines()[1:] if line.strip()}

    # {
    #   責務: [_command: Tesseract subprocessをtimeoutと明示error付きで実行する]
    #   処理: [1: stdout/stderrを捕捉する 2: timeout/exit errorを検査する]
    #   引数: [arguments: Tesseract args, input_bytes: optional PNG stdin]
    #   戻り値: [stdout: UTF-8 decoded output]
    # }
    def _command(self, arguments: Sequence[str], input_bytes: bytes | None = None) -> str:
        try:
            result = subprocess.run(
                [self.executable, *arguments],
                input=input_bytes,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(f"Tesseract command failed: {type(error).__name__}") from error
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace")[-500:].strip()
            raise RuntimeError(f"Tesseract exited with {result.returncode}: {detail}")
        return result.stdout.decode("utf-8", errors="replace")


# {
#   責務: [_parse_tsv_lines: TSV word rowsをreading-order line boxesへ集約する]
#   処理: [1: valid word rowsをline keyごとにgroupする 2: box/conf/textを正規化する]
#   引数: [content: Tesseract TSV text, width/height: image geometry]
#   戻り値: [boxes: normalized text-line boxes]
# }
def _parse_tsv_lines(content: str, width: int, height: int) -> tuple[FrameTextBox, ...]:
    grouped: dict[tuple[int, int, int, int], list[tuple[int, int, int, int, float, str]]] = (
        defaultdict(list)
    )
    try:
        for row in csv.DictReader(io.StringIO(content), delimiter="\t"):
            text = (row.get("text") or "").strip()
            if not text:
                continue
            confidence = float(row["conf"])
            if not math.isfinite(confidence) or confidence < 0:
                continue
            raw_left, raw_top = int(row["left"]), int(row["top"])
            box_width, box_height = int(row["width"]), int(row["height"])
            left = max(0, min(width, raw_left))
            top = max(0, min(height, raw_top))
            right = max(0, min(width, raw_left + box_width))
            bottom = max(0, min(height, raw_top + box_height))
            if right <= left or bottom <= top:
                continue
            key = tuple(int(row[name]) for name in ("page_num", "block_num", "par_num", "line_num"))
            grouped[key].append((left, top, right, bottom, min(1.0, confidence / 100.0), text))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Tesseract returned malformed TSV data") from error

    boxes = []
    for key in sorted(grouped):
        words = grouped[key]
        left = min(word[0] for word in words)
        top = min(word[1] for word in words)
        right = max(word[2] for word in words)
        bottom = max(word[3] for word in words)
        confidence = round(sum(word[4] for word in words) / len(words), 6)
        text = " ".join(word[5] for word in words)
        boxes.append(
            FrameTextBox(
                left / width,
                top / height,
                (right - left) / width,
                (bottom - top) / height,
                confidence,
                text,
            )
        )
    return tuple(boxes)
