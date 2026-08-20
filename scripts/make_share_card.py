#!/usr/bin/env python3
"""
Draw the link preview card, site/assets/share-card.png.

When the site URL is pasted into WhatsApp, Signal or Slack, the scraper reads
the Open Graph tags in site/index.html and fetches whatever og:image points at.
Without one you get a grey rectangle and a bare URL, which is a poor showing for
a link whose entire purpose is being sent to a group.

The card is drawn from the route geometry rather than screenshotted from the
live map, for two reasons. Map tiles carry attribution requirements that a
standalone image shared into a chat cannot satisfy, and the bare lines on the
brand's near-black read better at preview size than a tile background does.

Route colours match the site because the assignment algorithm is the same one
index.html runs: least-used hue and dash first, ties broken by whichever
combination's existing owners lie furthest away. Only the hue is used here,
since dash patterns disappear at this scale.

Regenerate after any change that adds or removes routes. Needs Pillow:

    pip install pillow
    python scripts/make_share_card.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("This needs Pillow.  pip install pillow")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import name_routes as N  # noqa: E402

ROUTES_JSON = ROOT / "site" / "data" / "routes.json"
OUT = ROOT / "site" / "assets" / "share-card.png"

W, H = 1200, 630                  # the size every scraper expects
SS = 2                            # supersample, then downscale, for clean lines
BG = (10, 10, 11)
INDIGO = (68, 133, 203)
WHITE = (255, 255, 255)
MUTED = (138, 143, 155)
HUES = ["#3987e5", "#c98500", "#199e70", "#9085e9", "#e66767", "#008300"]
DASHES = 6                        # must match DASHES.length in index.html
EARTH_R = 6371.0

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FONTS = {
    "bold": FONT_DIR / "DejaVuSans-Bold.ttf",
    "regular": FONT_DIR / "DejaVuSans.ttf",
}


def font(kind, size):
    p = FONTS[kind]
    return ImageFont.truetype(str(p), size) if p.exists() else ImageFont.load_default()


def hv(a, b):
    t = math.pi / 180
    x = (math.sin((b[0] - a[0]) * t / 2) ** 2 +
         math.cos(a[0] * t) * math.cos(b[0] * t) * math.sin((b[1] - a[1]) * t / 2) ** 2)
    return 2 * EARTH_R * math.asin(math.sqrt(x))


def assign_hues(routes):
    """The same greedy assignment index.html uses, so the card matches the map."""
    combos = [{"hue": h, "dash": d, "owners": []}
              for h in range(len(HUES)) for d in range(DASHES)]

    def foot(r):
        c = ((r["bbox"][0] + r["bbox"][2]) / 2, (r["bbox"][1] + r["bbox"][3]) / 2)
        rad = hv((r["bbox"][0], r["bbox"][1]), (r["bbox"][2], r["bbox"][3])) / 2
        return {"c": c, "rad": rad}

    out = {}
    for r in sorted(routes, key=lambda r: r["id"]):
        f = foot(r)
        best, best_key = None, None
        for k in combos:
            far = min((hv(f["c"], o["c"]) - f["rad"] - o["rad"] for o in k["owners"]),
                      default=float("inf"))
            key = (len(k["owners"]), -far)
            if best is None or key < best_key:
                best, best_key = k, key
        best["owners"].append(f)
        out[r["id"]] = best["hue"]
    return out


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def main():
    if not ROUTES_JSON.exists():
        sys.exit("site/data/routes.json is missing. Run scripts/build.py first.")
    data = json.loads(ROUTES_JSON.read_text(encoding="utf-8"))
    routes = data["routes"]
    hue_of = assign_hues(routes)
    tracks = {r["id"]: N.decode(r["geometry"]) for r in routes}

    img = Image.new("RGB", (W * SS, H * SS), BG)
    d = ImageDraw.Draw(img)

    # Map panel: right of the wordmark block, inset from the edges. Deliberately
    # not full-bleed, because previews get cropped to different aspect ratios and
    # a line touching the edge is the first thing to get sliced off.
    pad = 28 * SS
    panel = (int(W * 0.27) * SS, pad + 20 * SS, W * SS - pad, H * SS - pad)

    lats = [p[0] for t in tracks.values() for p in t]
    lons = [p[1] for t in tracks.values() for p in t]
    lat0 = (min(lats) + max(lats)) / 2
    kx = math.cos(math.radians(lat0))           # crude equirectangular is fine at this span
    spanx = (max(lons) - min(lons)) * kx
    spany = max(lats) - min(lats)
    pw, ph = panel[2] - panel[0], panel[3] - panel[1]
    scale = min(pw / spanx, ph / spany) * 0.99
    cx, cy = (min(lons) + max(lons)) / 2, lat0
    ox = (panel[0] + panel[2]) / 2
    oy = (panel[1] + panel[3]) / 2

    def xy(p):
        return (ox + (p[1] - cx) * kx * scale, oy - (p[0] - cy) * scale)

    # Longest first so the big routes sit behind the short ones rather than
    # drawing over them.
    for r in sorted(routes, key=lambda r: -r["distance_km"]):
        pts = [xy(p) for p in tracks[r["id"]]]
        d.line(pts, fill=rgb(HUES[hue_of[r["id"]]]), width=3 * SS, joint="curve")

    d.rectangle([0, 0, W * SS, 5 * SS], fill=INDIGO)   # the site's top rule

    x = pad + 8 * SS
    d.text((x, 150 * SS), "S O U T H   W A L E S", font=font("bold", 19 * SS), fill=INDIGO)
    d.text((x, 180 * SS), "GRAVEL", font=font("bold", 54 * SS), fill=WHITE)
    d.text((x, 240 * SS), "ROUTES", font=font("bold", 54 * SS), fill=WHITE)

    km = sum(r["distance_km"] for r in routes)
    asc = sum(r["ascent_m"] for r in routes)
    f18 = font("regular", 18 * SS)
    d.text((x, 330 * SS), f"{len(routes)} routes", font=font("bold", 22 * SS), fill=WHITE)
    d.text((x, 366 * SS), f"{km:,.0f} km", font=f18, fill=MUTED)
    d.text((x, 394 * SS), f"{asc:,.0f} m of climbing", font=f18, fill=MUTED)
    d.text((x, 448 * SS), "Filter by distance, climbing", font=f18, fill=MUTED)
    d.text((x, 476 * SS), "and how long it will take you.", font=f18, fill=MUTED)

    img.resize((W, H), Image.LANCZOS).save(OUT, "PNG", optimize=True)
    print(f"Wrote {OUT.relative_to(ROOT)}  {W}x{H}  {OUT.stat().st_size / 1024:.0f} KB  "
          f"from {len(routes)} routes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
