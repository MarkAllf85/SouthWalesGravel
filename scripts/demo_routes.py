#!/usr/bin/env python3
"""
Synthetic demo routes so the map can be built and reviewed before real Garmin
exports exist. These are PLAUSIBLE, NOT REAL. They trace invented lines around
the South Wales valleys purely to exercise the pipeline and the UI.

Delete everything in data/raw/gpx before the first real build.
"""

import math
import random
from pathlib import Path

DEMO = [
    # name, centre lat, centre lon, radius km, ascent scale, loop?, seed
    ("DEMO Cwmcarn Forest Loop",        51.6470, -3.1330, 3.2, 1.15, True,  11),
    ("DEMO Machen Ridge Circuit",       51.5910, -3.1290, 2.1, 0.95, True,  22),
    ("DEMO Sirhowy Valley Out and Back",51.6300, -3.1900, 5.6, 0.55, False, 33),
    ("DEMO Gelligaer Common Gravel",    51.6800, -3.2600, 4.4, 1.05, True,  44),
    ("DEMO Bargoed to Rhymney Ramble",  51.7050, -3.2350, 3.0, 0.80, False, 55),
    ("DEMO Wentwood Big Day",           51.6300, -2.8500, 8.5, 1.30, True,  66),
    ("DEMO Caerphilly Mountain Short",  51.5820, -3.2200, 1.6, 1.20, True,  77),
]


def terrain(lat, lon, seed):
    """A smooth pseudo-terrain in metres. Valleys and ridges, nothing real."""
    rnd = random.Random(seed)
    if not hasattr(terrain, "_cache"):
        terrain._cache = {}
    if seed not in terrain._cache:
        terrain._cache[seed] = [(rnd.uniform(0.008, 0.05), rnd.uniform(0, 6.28),
                                 rnd.uniform(40, 190)) for _ in range(4)]
    h = 120.0
    for scale, phase, amp in terrain._cache[seed]:
        h += amp * math.sin((lat - 51.6) / scale + phase) * math.cos((lon + 3.1) / scale - phase)
    return max(20.0, h)


def build_track(name, clat, clon, radius_km, ascent_scale, is_loop, seed):
    rnd = random.Random(seed)
    n = 900
    lobes = rnd.choice([2, 3, 4])
    wobble = [rnd.uniform(0.75, 1.25) for _ in range(6)]
    pts = []
    span = 2 * math.pi if is_loop else math.pi
    for i in range(n):
        t = span * i / (n - 1)
        r = radius_km * (1 + 0.28 * math.sin(lobes * t + wobble[0]))
        r *= 1 + 0.10 * math.sin(7 * t + wobble[1])
        if not is_loop:
            r *= 0.55 + 0.9 * math.sin(t) ** 0.5 if math.sin(t) > 0 else 0.55
        dlat = (r / 111.0) * math.sin(t)
        dlon = (r / (111.0 * math.cos(math.radians(clat)))) * math.cos(t)
        lat = clat + dlat + 0.0004 * math.sin(23 * t + wobble[2])
        lon = clon + dlon + 0.0004 * math.cos(19 * t + wobble[3])
        ele = terrain(lat, lon, seed) * ascent_scale
        ele += 6 * math.sin(31 * t + wobble[4])
        pts.append((lat, lon, ele))
    if is_loop:
        pts.append(pts[0])
    else:
        # Out and back: retrace the outward leg so start and end differ slightly.
        pts = pts + [(la, lo, el) for la, lo, el in reversed(pts[:-1])]
        pts[-1] = (pts[-1][0] + 0.0009, pts[-1][1] + 0.0011, pts[-1][2])
    return pts


def to_gpx(name, pts):
    head = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="Bike Route Explorer demo generator" '
        'xmlns="http://www.topografix.com/GPX/1/1">\n'
        f"  <metadata><name>{name}</name></metadata>\n"
        f"  <trk><name>{name}</name><trkseg>\n"
    )
    body = "".join(
        f'    <trkpt lat="{la:.6f}" lon="{lo:.6f}"><ele>{el:.1f}</ele></trkpt>\n'
        for la, lo, el in pts
    )
    return head + body + "  </trkseg></trk>\n</gpx>\n"


def write_demo_routes(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, clat, clon, radius, ascent, loop, seed in DEMO:
        pts = build_track(name, clat, clon, radius, ascent, loop, seed)
        fname = name.lower().replace(" ", "-").replace(",", "") + ".gpx"
        (out_dir / fname).write_text(to_gpx(name, pts), encoding="utf-8")
    print(f"Wrote {len(DEMO)} demo GPX files to {out_dir}")


if __name__ == "__main__":
    write_demo_routes(Path(__file__).resolve().parent.parent / "data" / "raw" / "gpx")
