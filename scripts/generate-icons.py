"""Regenerate site icons from the signpost motif (requires Pillow)."""
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'cyoa-game-server/static/icons'
source = Image.open(ROOT / 'frontend/src/media/signpost-icon.png').convert('RGBA')
source = source.crop(source.getbbox())


def icon(size, fraction=0.92, background=(0, 0, 0, 0)):
    canvas = Image.new('RGBA', (size, size), background)
    artwork = ImageOps.contain(source, (round(size * fraction), round(size * fraction)), Image.Resampling.LANCZOS)
    canvas.alpha_composite(artwork, ((size - artwork.width) // 2, (size - artwork.height) // 2))
    return canvas


icon(256).save(OUTPUT / 'favicon.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
icon(96).save(OUTPUT / 'favicon-96x96.png')
icon(180, 0.82, '#172c33').convert('RGB').save(OUTPUT / 'apple-touch-icon.png')
for size in (192, 512):
    icon(size).save(OUTPUT / f'icon-{size}.png')
    # Keep the entire motif inside the central 80%-diameter safe circle.
    icon(size, 0.56, '#172c33').convert('RGB').save(OUTPUT / f'icon-maskable-{size}.png')
