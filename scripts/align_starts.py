#!/usr/bin/env python3
"""
Rotate closed routes so they start and finish at a common point.

For a loop, "starting somewhere else" is purely a property of where the point
list begins. Rotating the list to begin at the track point nearest a chosen
coordinate is therefore lossless: no geometry is added, removed or moved, the
line on the ground is identical, and the distance and ascent are unchanged. The
file simply now begins and ends where you actually set off from.

What this deliberately does NOT do is connect a route to a point it never
touches. That means inventing road, which needs a routing engine and can put a
straight line across a hillside. Routes whose closest approach exceeds the
tolerance are reported and left alone.

Point-to-point routes are never rotated. Reversing or re-anchoring one changes
what the ride is.

Usage:
    python scripts/align_starts.py --at 51.647080,-3.205153            # report
    python scripts/align_starts.py --at 51.647080,-3.205153 --apply    # rewrite
    python scripts/align_starts.py --at ... --tolerance 600 --apply
"""

from __future__ import annotations

import argparse
import math
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_GPX = ROOT / "data" / "raw" / "gpx"
BACKUP = ROOT / "data" / "raw" / "_pre_alignment"

DEFAULT_TOLERANCE_M = 300.0
CLOSED_GAP_M = 1000.0     # start and end closer than this means the route is closed
EARTH_R = 6371000.0

GPX_NS = "http://www.topografix.com/GPX/1/1"


def haversine(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def parse(path):
    """Return (tree, root, seg_element, [trkpt elements], name)."""
    ET.register_namespace("", GPX_NS)
    tree = ET.parse(path)
    root = tree.getroot()
    prefix = "{" + root.tag.split("}")[0].strip("{") + "}" if "}" in root.tag else ""
    seg = root.find(f".//{prefix}trkseg")
    if seg is None:
        return tree, root, None, [], path.stem
    pts = list(seg.findall(f"{prefix}trkpt"))
    nm = root.find(f"{prefix}trk/{prefix}name")
    name = nm.text.strip() if nm is not None and nm.text else path.stem
    return tree, root, seg, pts, name


def coords(el, prefix):
    return (float(el.get("lat")), float(el.get("lon")))


def analyse(path, target, tolerance):
    tree, root, seg, pts, name = parse(path)
    if seg is None or len(pts) < 10:
        return {"file": path, "name": name, "status": "no usable track", "tree": None}

    ll = [coords(p, None) for p in pts]
    gap = haversine(ll[0], ll[-1])
    closed = gap < CLOSED_GAP_M

    best_i, best_d = 0, float("inf")
    for i, p in enumerate(ll):
        d = haversine(target, p)
        if d < best_d:
            best_i, best_d = i, d

    start_d = haversine(target, ll[0])

    if not closed:
        status = "point to point, left alone"
    elif best_d > tolerance:
        status = f"closest approach {best_d:.0f} m, beyond tolerance"
    elif best_i == 0 or start_d <= 25:
        status = "already starts there"
    else:
        status = f"rotate by {best_i} points"

    return {"file": path, "name": name, "tree": tree, "seg": seg, "pts": pts,
            "index": best_i, "closest_m": best_d, "start_m": start_d,
            "closed": closed, "status": status,
            "rotatable": closed and best_d <= tolerance and best_i != 0 and start_d > 25}


def rotate(info):
    """Rewrite the trkseg so the point list begins at the chosen index."""
    seg, pts, i = info["seg"], info["pts"], info["index"]
    # A closed loop repeats its first point at the end. Drop that duplicate
    # before rotating or it lands in the middle of the new track.
    body = pts[:-1] if haversine(
        (float(pts[0].get("lat")), float(pts[0].get("lon"))),
        (float(pts[-1].get("lat")), float(pts[-1].get("lon")))) < 15 else pts[:]

    n = len(body)
    idx = i % n
    new = body[idx:] + body[:idx]
    # Close the loop again on the new start point.
    import copy
    new.append(copy.deepcopy(new[0]))

    # Timestamps would now run backwards across the seam, and they mean nothing
    # in a course file anyway, so strip them rather than ship something that
    # looks like a corrupt activity.
    for el in new:
        for child in list(el):
            if child.tag.endswith("}time") or child.tag == "time":
                el.remove(child)

    for el in list(seg):
        seg.remove(el)
    for el in new:
        seg.append(el)
    return len(new)


def read_points(path):
    tree, root, seg, pts, name = parse(path)
    return [(float(p.get("lat")), float(p.get("lon"))) for p in pts]


def splice(connector_path, target, tolerance, do_apply):
    """
    Append a short real connector to routes that start at the meeting point but
    finish somewhere else.

    The connector must be a GPX of ground that has actually been ridden or
    planned; nothing is generated here. It is oriented automatically, so it does
    not matter which way round it was drawn, and it is only used when one of its
    ends sits near the route's finish and the other near the meeting point.
    """
    import copy
    cpts = read_points(connector_path)
    if len(cpts) < 2:
        print(f"Connector {connector_path.name} has no usable track")
        return

    ends = [(haversine(target, cpts[0]), haversine(target, cpts[-1]))]
    print(f"\nConnector {connector_path.name}: {len(cpts)} points, "
          f"{sum(haversine(a, b) for a, b in zip(cpts, cpts[1:])) / 1000:.2f} km")

    for path in sorted(RAW_GPX.glob("*.gpx")):
        tree, root, seg, pts, name = parse(path)
        if seg is None or len(pts) < 10:
            continue
        first = (float(pts[0].get("lat")), float(pts[0].get("lon")))
        last = (float(pts[-1].get("lat")), float(pts[-1].get("lon")))
        if haversine(target, first) > tolerance or haversine(target, last) <= tolerance:
            continue  # not an open route that starts at the meeting point

        # Orient the connector so it runs from the route's finish to the point.
        if haversine(last, cpts[0]) <= tolerance and haversine(target, cpts[-1]) <= tolerance:
            run = cpts
        elif haversine(last, cpts[-1]) <= tolerance and haversine(target, cpts[0]) <= tolerance:
            run = list(reversed(cpts))
        else:
            print(f"  {name[:50]}: connector does not meet this finish, left alone")
            continue

        added = sum(haversine(a, b) for a, b in zip(run, run[1:])) / 1000
        print(f"  {name[:50]}: splice {added:.2f} km, becomes a closed loop")
        if not do_apply:
            continue

        BACKUP.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, BACKUP / path.name)
        template = pts[-1]
        for lat, lon in run[1:]:
            el = copy.deepcopy(template)
            el.set("lat", f"{lat:.7f}")
            el.set("lon", f"{lon:.7f}")
            for child in list(el):
                if child.tag.endswith("}time") or child.tag == "time":
                    el.remove(child)
            seg.append(el)
        tree.write(path, encoding="utf-8", xml_declaration=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", required=True, help="lat,lon to start and finish at")
    ap.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_M,
                    help="metres; a route must pass this close to be rotated")
    ap.add_argument("--apply", action="store_true", help="write the changes")
    ap.add_argument("--connector", metavar="GPX",
                    help="a short GPX linking an open route's finish back to the meeting point; "
                         "spliced onto every route whose finish it matches, either way round")
    args = ap.parse_args()

    lat, lon = [float(x) for x in args.at.split(",")]
    target = (lat, lon)

    files = sorted(RAW_GPX.glob("*.gpx"))
    if not files:
        print("No GPX files in data/raw/gpx")
        return 1

    results = [analyse(f, target, args.tolerance) for f in files]
    results.sort(key=lambda r: r.get("closest_m", 9e9))

    todo = [r for r in results if r.get("rotatable")]
    print(f"Target {lat:.6f}, {lon:.6f} with a {args.tolerance:.0f} m tolerance\n")
    for r in results:
        mark = "->" if r.get("rotatable") else "  "
        cd = f"{r['closest_m']:6.0f} m" if r.get("closest_m") is not None else "      -"
        print(f"{mark} {r['name'][:52]:<54} closest {cd}   {r['status']}")
    print(f"\n{len(todo)} of {len(results)} to rotate")

    if args.connector:
        splice(Path(args.connector), target, args.tolerance, args.apply)

    if not args.apply:
        print("\nDry run. Add --apply to write the changes.")
        return 0

    BACKUP.mkdir(parents=True, exist_ok=True)
    for r in todo:
        shutil.copy2(r["file"], BACKUP / r["file"].name)
        n = rotate(r)
        r["tree"].write(r["file"], encoding="utf-8", xml_declaration=True)
        print(f"  rotated {r['name'][:50]} ({n} points)")
    print(f"\n{len(todo)} rewritten. Originals copied to data/raw/_pre_alignment/.")
    print("Run scripts/build.py to rebuild.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
