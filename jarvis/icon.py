"""The orb icon, drawn with your agent's letter and color (JARVIS: cyan "J"; FRIDAY: orange "F"...).

  python -m jarvis.icon   writes data/orb.ico (e.g. for the desktop shortcut)
"""
from __future__ import annotations

import io
from functools import lru_cache

from . import settings

BG = (11, 18, 32)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else (56, 225, 255)


@lru_cache(maxsize=8)
def draw(letter: str, color: str, size: int = 512, maskable: bool = False) -> bytes:
    """PNG of the orb: three rings, a glowing core and the letter."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    S, c, accent = 2048, 1024, _rgb(color)
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(base).ellipse((0, 0, S - 1, S - 1), fill=BG + (255,))
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((c - 430, c - 430, c + 430, c + 430), fill=accent + (150,))
    base = Image.alpha_composite(base, glow.filter(ImageFilter.GaussianBlur(170)))
    rings = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    for r, w, a in ((900, 26, 90), (760, 34, 150), (620, 52, 255)):
        ImageDraw.Draw(rings).ellipse((c - r, c - r, c + r, c + r), outline=accent + (a,), width=w)
    base = Image.alpha_composite(base, rings.filter(ImageFilter.GaussianBlur(3)))
    d = ImageDraw.Draw(base)
    d.ellipse((c - 430, c - 430, c + 430, c + 430), fill=BG + (255,), outline=accent + (255,), width=40)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/seguisb.ttf", 620)
    except OSError:
        font = ImageFont.load_default(620)
    d.text((c, c + 10), (letter or "J")[:1].upper(), font=font, fill=accent + (255,), anchor="mm")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, S - 1, S - 1), fill=255)
    base.putalpha(Image.composite(base.getchannel("A"), Image.new("L", (S, S), 0), mask))
    if maskable:  # some launchers crop icons: orb in the middle 80 % on a solid background
        canvas = Image.new("RGBA", (S, S), BG + (255,))
        small = base.resize((int(S * .8),) * 2, Image.LANCZOS)
        canvas.alpha_composite(small, ((S - small.width) // 2,) * 2)
        base = canvas
    out = io.BytesIO()
    base.resize((size, size), Image.LANCZOS).save(out, "PNG")
    return out.getvalue()


def ico(letter: str, color: str) -> bytes:
    from PIL import Image
    out = io.BytesIO()
    Image.open(io.BytesIO(draw(letter, color, 256))).save(out, "ICO", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    return out.getvalue()


if __name__ == "__main__":  # writes data/orb.ico with the current identity (for a desktop shortcut)
    ident = settings.identity()
    settings.DATA.mkdir(exist_ok=True)
    (settings.DATA / "orb.ico").write_bytes(ico(ident["letter"], ident["color"]))
    print("icon:", settings.DATA / "orb.ico", ident["short"], ident["color"])
