"""Transcript mora alignment and optional audio prosody measurement."""

from __future__ import annotations

import math
import wave
from pathlib import Path

from .contracts import PhonemeEvent

MAX_AUDIO_BYTES = 512 * 1024 * 1024
MORA_VOWELS = {
    **dict.fromkeys("あかさたなはまやらわがざだばぱぁゃゎ", "a"),
    **dict.fromkeys("いきしちにひみりぎじぢびぴぃ", "i"),
    **dict.fromkeys("うくすつぬふむゆるぐずづぶぷぅゅ", "u"),
    **dict.fromkeys("えけせてねへめれげぜでべぺぇ", "e"),
    **dict.fromkeys("おこそとのほもよろをごぞどぼぽぉょ", "o"),
}


# {
# 責務: [read_wav_duration: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [path: 処理入力]
# 戻り値: [float: 処理結果]
# }
def read_wav_duration(path: str | Path) -> float:
    source = Path(path)
    if source.stat().st_size <= 0 or source.stat().st_size > MAX_AUDIO_BYTES:
        raise ValueError("audio file size is outside the supported range")
    try:
        with wave.open(str(source), "rb") as audio:
            if audio.getcomptype() != "NONE" or audio.getnchannels() not in (1, 2):
                raise ValueError(
                    "only uncompressed mono/stereo PCM WAV is supported without a speech adapter"
                )
            rate = audio.getframerate()
            if rate <= 0:
                raise ValueError("WAV sample rate must be positive")
            return audio.getnframes() / rate
    except (wave.Error, EOFError, OSError) as error:
        raise ValueError(f"cannot read WAV duration: {error}") from error


# {
# 責務: [transcript_to_events: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [transcript, duration_seconds: 処理入力]
# 戻り値: [tuple[PhonemeEvent, ...]: 処理結果]
# }
def transcript_to_events(transcript: str, duration_seconds: float) -> tuple[PhonemeEvent, ...]:
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("transcript alignment requires positive finite audio duration")
    tokens = _mora_tokens(transcript)
    if not tokens:
        return ()
    total_weight = sum(weight for _symbol, weight in tokens)
    cursor = 0.0
    events = []
    for symbol, weight in tokens:
        length = duration_seconds * weight / total_weight
        events.append(PhonemeEvent(symbol, cursor, cursor + length, 0.25))
        cursor += length
    last = events[-1]
    events[-1] = PhonemeEvent(last.symbol, last.start_seconds, duration_seconds, last.confidence)
    return tuple(events)


# {
# 責務: [_mora_tokens: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [text: 処理入力]
# 戻り値: [list[tuple[str, float]]: 処理結果]
# }
def _mora_tokens(text: str) -> list[tuple[str, float]]:
    normalized = "".join(
        chr(ord(character) - 0x60) if "ァ" <= character <= "ヶ" else character for character in text
    )
    small_kana = set("ゃゅょぁぃぅぇぉゎ")
    tokens = []
    index = 0
    while index < len(normalized):
        character = normalized[index].lower()
        if character.isspace() or character in ",.!?。、！？・\n\r":
            index += 1
            continue
        if character == "ー":
            previous_vowel = next(
                (vowel for symbol, _weight in reversed(tokens) if (vowel := _mora_vowel(symbol))),
                None,
            )
            if previous_vowel:
                tokens.append((previous_vowel, 1.4))
            index += 1
            continue
        if character in small_kana and tokens:
            previous = tokens.pop()
            merged = previous[0] + character
            tokens.append((merged, previous[1]))
            index += 1
            continue
        if "a" <= character <= "z":
            vowel = next((item for item in reversed(normalized[index:]) if item in "aeiou"), "")
            if vowel:
                tokens.append((vowel, 1.0))
            while index < len(normalized) and normalized[index].isalpha():
                index += 1
            continue
        if character in MORA_VOWELS:
            tokens.append((character, 1.0))
        elif character in "んっ":
            tokens.append((character, 0.6))
        index += 1
    return tokens


# {
# 責務: [_mora_vowel: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [symbol: 処理入力]
# 戻り値: [str | None: 処理結果]
# }
def _mora_vowel(symbol: str) -> str | None:
    for character in reversed(symbol):
        if character in MORA_VOWELS:
            return MORA_VOWELS[character]
        if character in "aeiou":
            return character
    return None
