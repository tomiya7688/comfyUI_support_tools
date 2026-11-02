"""半透明素材を画像へ重ねる合成処理。"""

from __future__ import annotations

import math
from random import Random

from PIL import Image, ImageDraw, ImageFilter


# {
#   責務: [surface_color: Randomから半透明surface用の中間輝度RGB colorを作る]
#   処理: [80..210 baseにchannel別-38..38 jitterを加え0..255へclipする]
#   引数: [randomizer: caller seeded Random]
#   戻り値: [tuple[int,int,int]: RGB surface color]
# }
def surface_color(randomizer: Random) -> tuple[int, int, int]:
    base = randomizer.randint(80, 210)
    return tuple(max(0, min(255, base + randomizer.randint(-38, 38))) for _ in range(3))


# {
#   責務: [alpha_map: 幅方向の斜めwaveをblurし半透明合成用grayscale opacity mapを作る]
#   処理: [randomized low/high/angle/periodでper-pixel alphaを計算しGaussian blurを適用する]
#   引数: [size: width/height, randomizer: deterministic variation source]
#   戻り値: [Pillow L image: opacity map]
# }
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


# {
#   責務: [surface_shape: inset rectangleまたはellipseをblurしてsurface placement maskを作る]
#   処理: [randomized inset/shapeを白maskへdraw後、edgeをGaussian blurする]
#   引数: [size: target dimensions, randomizer: shape/blur variation source]
#   戻り値: [Pillow L image: surface shape mask]
# }
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


# {
#   責務: [apply_translucent_surface: imageへsynthetic thin fabric/film colorとsoft blurを合成する]
#   処理: [RGB化しalpha mapをshape mask内へcompositeして低強度Gaussian blurする]
#   引数: [image: source Pillow image, randomizer: deterministic augmentation RNG]
#   戻り値: [Pillow RGB image: augmented copy]
# }
def apply_translucent_surface(image: Image.Image, randomizer: Random) -> Image.Image:
    """薄布・フィルム越しに見える入力画像を合成する。"""
    original = image.convert("RGB")
    alpha = Image.composite(
        alpha_map(original.size, randomizer),
        Image.new("L", original.size, 0),
        surface_shape(original.size, randomizer),
    )
    surface = Image.new("RGB", original.size, surface_color(randomizer))
    result = Image.composite(surface, original, alpha)
    return result.filter(ImageFilter.GaussianBlur(randomizer.uniform(0.0, 0.65)))
