"""半透明素材を画像へ重ねる合成処理。"""

from __future__ import annotations

import math
from random import Random

from PIL import Image, ImageDraw, ImageFilter


def surface_color(randomizer: Random) -> tuple[int, int, int]:
    base = randomizer.randint(80, 210)
    return tuple(max(0, min(255, base + randomizer.randint(-38, 38))) for _ in range(3))


def alpha_map(size: tuple[int, int], randomizer: Random) -> Image.Image:
    width, height = size
    low = randomizer.randint(45, 95)
    high = randomizer.randint(low + 20, min(190, low + 95))
    image = Image.new("L", size, low)
    pixels = image.load()
    angle = randomizer.uniform(-0.9, 0.9)
    period = randomizer.uniform(9.0, 32.0)
    for y in range(height):
        for x in range(width):
            phase = (x * math.cos(angle) + y * math.sin(angle)) / period
            wave = (math.sin(phase) + 1.0) * 0.5
            pixels[x, y] = int(low + (high - low) * wave)
    return image.filter(ImageFilter.GaussianBlur(randomizer.uniform(0.4, 1.8)))


def surface_shape(size: tuple[int, int], randomizer: Random) -> Image.Image:
    width, height = size
    mask = Image.new("L", size, 0)
    drawer = ImageDraw.Draw(mask)
    inset_x = randomizer.randint(0, max(1, width // 8))
    inset_y = randomizer.randint(0, max(1, height // 8))
    if randomizer.random() < 0.5:
        drawer.rectangle((inset_x, inset_y, width - inset_x, height - inset_y), fill=255)
    else:
        drawer.ellipse((inset_x, inset_y, width - inset_x, height - inset_y), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(randomizer.uniform(4.0, 18.0)))


def apply_translucent_surface(image: Image.Image, randomizer: Random) -> Image.Image:
    """薄布・フィルム越しに見える入力画像を合成する。"""
    original = image.convert("RGB")
    alpha = Image.composite(alpha_map(original.size, randomizer), Image.new("L", original.size, 0), surface_shape(original.size, randomizer))
    surface = Image.new("RGB", original.size, surface_color(randomizer))
    result = Image.composite(surface, original, alpha)
    return result.filter(ImageFilter.GaussianBlur(randomizer.uniform(0.0, 0.65)))
