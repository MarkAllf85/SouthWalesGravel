#!/usr/bin/env python3
"""
Turn a recorded Garmin activity GPX into a clean course file.

Activity exports carry a timestamp on every point plus heart rate, cadence and
temperature in <extensions>. None of that belongs in a published route: the
timestamps say when you leave the house and the heart rate is health data.
This keeps latitude, longitude and elevation only, drops points closer than
3 m to the previous one (stationary GPS jitter at cafe stops), rounds to six
decimal places (about 0.1 m) and writes a plain GPX 1.1 track. A 4 MB activity
comes out around 0.5 MB.

It edits nothing else. Run it before clip_to_point.py, on the raw activity,
into a staging folder, never over the original.

Usage:
    python scripts/sanitise_activity.py IN.gpx OUT.gpx "Gravel - working name"
"""
import math
import sys
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

NS = "{http://www.topografix.com/GPX/1/1}"
MIN_STEP_M = 3.0


def hv(a, b):
    r = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def main(src, dst, name):
    pts = []
    for tp in ET.parse(src).getroot().iter(NS + "trkpt"):
        e = tp.find(NS + "ele")
        pts.append((float(tp.get("lat")), float(tp.get("lon")), float(e.text) if e is not None else None))
    if not pts:
        sys.exit(f"{src}: no track points")
    kept = [pts[0]]
    for p in pts[1:]:
        if hv(p, kept[-1]) >= MIN_STEP_M:
            kept.append(p)
    if kept[-1] is not pts[-1]:
        kept.append(pts[-1])
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" creator="South Wales Gravel Routes">',
           f"  <metadata><name>{escape(name)}</name></metadata>",
           f"  <trk><name>{escape(name)}</name><trkseg>"]
    for la, lo, e in kept:
        ele = f"<ele>{e:.1f}</ele>" if e is not None else ""
        out.append(f'    <trkpt lat="{la:.6f}" lon="{lo:.6f}">{ele}</trkpt>')
    out += ["  </trkseg></trk>", "</gpx>", ""]
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"{src}: {len(pts)} -> {len(kept)} points")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
