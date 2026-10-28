"""Draw AirFare's icon: the launcher .ico, the notification picture and the Chrome extension icons.

Developer tool, needs Pillow (pip install pillow). Run from the project folder:  python tools/make_icons.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SKY_TOP, SKY_BOTTOM = (18, 163, 159), (10, 92, 94)       # the teal of brand.py's logo gradient
WHITE, RED = (255, 255, 255), (229, 72, 77)

# A top-down airliner, nose up, in units of half its length (right half; the left half is mirrored).
HALF_PLANE = [(0, -1.0), (0.07, -0.93), (0.095, -0.80), (0.095, -0.24), (0.96, 0.17), (0.96, 0.31),
              (0.095, 0.09), (0.095, 0.60), (0.39, 0.84), (0.39, 0.95), (0.075, 0.86), (0, 0.90)]


def plane(cx: float, cy: float, half_len: float, heading_deg: float) -> list[tuple[float, float]]:
    pts = HALF_PLANE + [(-x, y) for x, y in reversed(HALF_PLANE[1:-1])]
    a = math.radians(heading_deg)
    return [(cx + half_len * (x * math.cos(a) - y * math.sin(a)), cy + half_len * (x * math.sin(a) + y * math.cos(a)))
            for x, y in pts]


def bezier(p0, p1, p2, t):
    return tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * b + t ** 2 * c for a, b, c in zip(p0, p1, p2))


def render(size: int, detail: bool) -> Image.Image:
    s = 4 * max(size, 64)                       # draw large, then shrink for smooth edges
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sky = Image.new("RGBA", (s, s))
    d = ImageDraw.Draw(sky)
    for y in range(s):
        t = y / (s - 1)
        d.line([(0, y), (s, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(SKY_TOP, SKY_BOTTOM)) + (255,))
    mask = Image.new("L", (s, s), 0)
    m = round(s * 0.03)
    ImageDraw.Draw(mask).rounded_rectangle([m, m, s - m, s - m], radius=round(s * 0.22), fill=255)
    img.paste(sky, (0, 0), mask)
    d = ImageDraw.Draw(img)
    if detail:
        # Dashed flight path from a red origin dot up to the plane.
        start, ctrl, end = (s * 0.21, s * 0.79), (s * 0.25, s * 0.56), (s * 0.43, s * 0.585)
        steps, dash = 11, s * 0.017
        for i in range(2, steps, 2):
            a, b = bezier(start, ctrl, end, i / steps), bezier(start, ctrl, end, (i + 1) / steps)
            d.line([a, b], fill=WHITE + (225,), width=round(dash * 2))
            for p in (a, b):
                d.ellipse([p[0] - dash, p[1] - dash, p[0] + dash, p[1] + dash], fill=WHITE + (225,))
        r = s * 0.05
        d.ellipse([start[0] - r * 1.45, start[1] - r * 1.45, start[0] + r * 1.45, start[1] + r * 1.45], fill=WHITE)
        d.ellipse([start[0] - r, start[1] - r, start[0] + r, start[1] + r], fill=RED)
        d.polygon(plane(s * 0.64, s * 0.38, s * 0.27, 45), fill=WHITE)
    else:
        d.polygon(plane(s * 0.5, s * 0.5, s * 0.40, 45), fill=WHITE)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
    frames = [render(n, detail=n >= 40) for n in sizes]
    frames[-1].save(assets / "airfare.ico", sizes=[(n, n) for n in sizes], append_images=frames[:-1])
    render(256, True).save(assets / "airfare-256.png")
    icons = ROOT / "extension" / "icons"
    icons.mkdir(exist_ok=True)
    for n in (16, 32, 48, 128):
        render(n, detail=n >= 48).save(icons / f"icon{n}.png")
    print("icons written to", assets, "and", icons)


if __name__ == "__main__":
    main()
