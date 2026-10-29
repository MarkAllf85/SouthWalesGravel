#!/usr/bin/env python3
"""
Pull dangling route ends back from home.

clip_to_point.py guarantees nothing lies inside the 200 m exclusion radius. That
is enough for a loop that closes on the meeting point. It is not enough for a
ride that left home by a different road and never passed the meeting point on
the way out: clipping leaves that end sitting 200 m from the door, and several
routes ending on the same street at 200 m triangulate it.

The rule here: a route end may sit at the meeting point; anywhere else it must
be at least --min-m (default 1000 m) from the zone. The meeting point is about
750 m from zone A, so no end ever points at home more closely than the public
meeting point already does. Deletes leading and trailing points only.

Run after clip_to_point.py and align_starts.py, over the new files only.

Usage:
    python scripts/trim_open_ends.py --at 51.647080,-3.205153 --avoid LAT,LON [--apply]
"""
import argparse
import math
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "http://www.topografix.com/GPX/1/1"
ROOT = Path(__file__).resolve().parent.parent
RAW_GPX = ROOT / "data" / "raw" / "gpx"


def hv(a, b):
    r = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def ll(s):
    a, b = s.split(",")
    return float(a), float(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", required=True, type=ll)
    ap.add_argument("--avoid", required=True, type=ll)
    ap.add_argument("--min-m", type=float, default=1000.0)
    ap.add_argument("--at-tolerance", type=float, default=300.0)
    ap.add_argument("--dir", default=str(RAW_GPX))
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ET.register_namespace("", NS)

    def bad(p):
        return hv(p, a.avoid) < a.min_m and hv(p, a.at) > a.at_tolerance

    for f in sorted(Path(a.dir).glob("*.gpx")):
        tree = ET.parse(f)
        seg = tree.getroot().find(f".//{{{NS}}}trkseg")
        if seg is None:
            continue
        pts = list(seg)
        q = [(float(p.get("lat")), float(p.get("lon"))) for p in pts]
        i, j = 0, len(q) - 1
        while i < j and bad(q[i]):
            i += 1
        while j > i and bad(q[j]):
            j -= 1
        if (i, j) == (0, len(q) - 1):
            continue
        print(f"{f.name}: drop {i} leading, {len(q) - 1 - j} trailing points")
        if a.apply:
            for p in pts[:i] + pts[j + 1:]:
                seg.remove(p)
            tree.write(f, encoding="utf-8", xml_declaration=True)
    if not a.apply:
        print("Dry run. Add --apply to write the changes.")


if __name__ == "__main__":
    main()
