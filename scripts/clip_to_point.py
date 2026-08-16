#!/usr/bin/env python3
"""
Clip routes so they begin and end at a chosen public meeting point.

This is the privacy tool, and it is a different operation from rotating.
Rotating a loop changes only where the point list begins; the geometry is
untouched, so a route that ran up a residential street still runs up that
street. Clipping removes that ground from the file entirely.

For each route it finds every visit to the meeting point, then keeps only the
span between the first visit and the last, discarding whatever came before and
after. On a ride that left home, rode down to the meeting point, went round and
came back the same way, that discards the home spur at both ends and leaves a
clean loop starting and finishing at the point.

Nothing is invented. This only ever deletes leading and trailing points. The
one exception is the closing snap: when the clipped ends are both inside the
tolerance but not identical, the final point is set equal to the first so the
loop closes exactly. That moves one point by less than the tolerance and is
reported per route.

Routes that never come within tolerance of the point are left alone, and so are
routes that only touch it once and would need road invented to close.

Usage:
    python scripts/clip_to_point.py --at 51.647080,-3.205153
    python scripts/clip_to_point.py --at 51.647080,-3.205153 --apply
    python scripts/clip_to_point.py --at ... --tolerance 80 --apply
"""

from __future__ import annotations

import argparse
import copy
import math
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_GPX = ROOT / "data" / "raw" / "gpx"
BACKUP = ROOT / "data" / "raw" / "_pre_clip"

DEFAULT_TOLERANCE_M = 60.0
MIN_KEEP_FRACTION = 0.5    # refuse to throw away more than half a route
MAX_SPUR_KM = 4.0          # a lead-in longer than this is the ride, not a spur
MAX_SPUR_FRACTION = 0.2
EARTH_R = 6371000.0
GPX_NS = "http://www.topografix.com/GPX/1/1"


def haversine(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def parse(path):
    ET.register_namespace("", GPX_NS)
    tree = ET.parse(path)
    root = tree.getroot()
    pre = "{" + root.tag.split("}")[0].strip("{") + "}" if "}" in root.tag else ""
    seg = root.find(f".//{pre}trkseg")
    pts = list(seg.findall(f"{pre}trkpt")) if seg is not None else []
    nm = root.find(f"{pre}trk/{pre}name")
    name = nm.text.strip() if nm is not None and nm.text else path.stem
    return tree, seg, pts, name, pre


def latlon(el):
    return (float(el.get("lat")), float(el.get("lon")))


def length_km(ll):
    return sum(haversine(a, b) for a, b in zip(ll, ll[1:])) / 1000


def find_visits(ll, target, tol):
    """Group the indices that sit inside the tolerance into distinct visits."""
    visits, cur = [], None
    for i, p in enumerate(ll):
        if haversine(target, p) <= tol:
            if cur is None:
                cur = [i, i]
            else:
                cur[1] = i
        elif cur is not None:
            visits.append(tuple(cur))
            cur = None
    if cur is not None:
        visits.append(tuple(cur))
    return visits


def plan(path, target, tol):
    tree, seg, pts, name, pre = parse(path)
    if seg is None or len(pts) < 10:
        return {"name": name, "path": path, "action": "no usable track"}

    ll = [latlon(p) for p in pts]
    total = length_km(ll)
    visits = find_visits(ll, target, tol)
    info = {"name": name, "path": path, "tree": tree, "seg": seg, "pts": pts,
            "total_km": total, "visits": len(visits),
            "closest_m": min(haversine(target, p) for p in ll)}

    if not visits:
        info["action"] = f"never within {tol:.0f} m, left alone"
        return info

    if len(visits) == 1:
        # Touches the point once, so only a spur at one end can go. Whichever
        # side is short enough to be an approach rather than the ride itself.
        a, b = visits[0]
        lead_km = length_km(ll[:a + 1])
        tail_km = length_km(ll[b:])
        cand = []
        if lead_km <= min(MAX_SPUR_KM, MAX_SPUR_FRACTION * total) and lead_km > 0.05:
            cand.append(("lead-in", lead_km, b, len(ll) - 1))
        if tail_km <= min(MAX_SPUR_KM, MAX_SPUR_FRACTION * total) and tail_km > 0.05:
            cand.append(("run-out", tail_km, 0, a))
        if not cand:
            info["action"] = ("single visit mid-ride, nothing safe to trim "
                              f"(lead {lead_km:.1f} km, tail {tail_km:.1f} km)")
            return info
        what, km, lo, hi = max(cand, key=lambda c: c[1])
        info.update(action=f"trim {km:.2f} km {what}, still open at the far end",
                    lo=lo, hi=hi, close=False)
        return info

    # Two or more visits: keep the span between a pair of visits, choosing the
    # pair that retains the most riding. First-and-last is usually right, but a
    # route that clips the junction twice in quick succession would otherwise
    # be reduced to nothing.
    best = None
    for i in range(len(visits)):
        for j in range(i + 1, len(visits)):
            lo_, hi_ = visits[i][1], visits[j][0]
            if hi_ <= lo_:
                continue
            k = length_km(ll[lo_:hi_ + 1])
            if best is None or k > best[0]:
                best = (k, lo_, hi_)
    if best is None:
        info["action"] = "visits overlap, nothing to trim"
        return info

    kept, lo, hi = best
    if kept < MIN_KEEP_FRACTION * total:
        info["action"] = (f"would keep only {kept:.1f} of {total:.1f} km, refused "
                          f"(the point is not visited near both ends)")
        return info

    removed = total - kept
    gap = haversine(ll[lo], ll[hi])
    info.update(action=f"clip {removed:.2f} km from the ends, keeps {kept:.1f} km",
                lo=lo, hi=hi, close=gap <= tol, gap_m=gap, removed_km=removed)
    return info


def apply_exclusion(info, avoid, radius):
    """
    Guarantee no geometry inside a radius of a private address.

    Ends are trimmed inward until they clear the radius, which handles the
    normal case of a ride that begins and finishes at the door. A route that
    enters the zone in the middle is reported, not edited: cutting a route in
    half to dodge a circle produces two broken files, not a fixed one.
    """
    if "pts" not in info or "rotate_order" in info:
        return
    ll = [latlon(p) for p in info["pts"]]
    lo = info.get("lo", 0)
    hi = info.get("hi", len(ll) - 1)

    a, b = lo, hi
    while a < b and haversine(avoid, ll[a]) < radius:
        a += 1
    while b > a and haversine(avoid, ll[b]) < radius:
        b -= 1
    if b <= a:
        info["breach"] = min(haversine(avoid, p) for p in ll)
        info["exclusion"] = "entire route sits inside the exclusion zone"
        return

    inner = min(haversine(avoid, p) for p in ll[a:b + 1])
    if inner < radius:
        # A closed loop that clips the zone mid-ride can be rotated so the
        # offending section sits at the seam, then cut off. The loop simply
        # now starts and finishes at the edge of the zone instead of running
        # through it. Nothing is invented and nothing else moves.
        closed = haversine(ll[0], ll[-1]) < 1000.0
        zone = [i for i in range(a, b + 1) if haversine(avoid, ll[i]) < radius]
        if closed and zone:
            dropped = haversine(ll[0], ll[-1]) < 15
            body = ll[:-1] if dropped else ll
            n = len(body)
            after = (zone[-1] + 1) % n
            order = list(range(after, n)) + list(range(0, after))
            rot = [body[i] for i in order]
            x, y = 0, len(rot) - 1
            while x < y and haversine(avoid, rot[x]) < radius:
                x += 1
            while y > x and haversine(avoid, rot[y]) < radius:
                y -= 1
            still = min(haversine(avoid, q) for q in rot[x:y + 1])
            if still >= radius:
                cut = (length_km(ll) - length_km(rot[x:y + 1]))
                info["rotate_order"] = order[x:y + 1]
                info["rot_dropped_last"] = dropped
                info["close"] = haversine(rot[x], rot[y]) <= 1000.0
                info.pop("lo", None); info.pop("hi", None)
                info["action"] = (f"rotate the seam onto the exclusion zone and cut "
                                  f"{cut:.2f} km, keeps {length_km(rot[x:y + 1]):.1f} km")
                return
        info["breach"] = inner
        info["exclusion"] = f"still passes {inner:.0f} m from the address mid-ride"

    if (a, b) != (lo, hi):
        cut = (length_km(ll[lo:a + 1]) + length_km(ll[b:hi + 1]))
        info["lo"], info["hi"] = a, b
        info["close"] = haversine(ll[a], ll[b]) <= max(radius, DEFAULT_TOLERANCE_M)
        prev = info.get("action", "")
        info["action"] = (prev + " | " if prev and "left alone" not in prev else "") + \
                         f"trim {cut:.2f} km to clear the exclusion zone"


def apply_clip(info, target):
    seg, pts = info["seg"], info["pts"]
    if "rotate_order" in info:
        body = pts[:-1] if info.get("rot_dropped_last") else pts
        keep = [body[i] for i in info["rotate_order"]]
    else:
        lo, hi = info["lo"], info["hi"]
        keep = pts[lo:hi + 1]

    if info.get("close"):
        # Close the loop exactly on its own first point.
        end = copy.deepcopy(keep[0])
        keep = keep[:-1] + [end]

    for el in list(seg):
        seg.remove(el)
    for el in keep:
        for child in list(el):
            if child.tag.endswith("}time") or child.tag == "time":
                el.remove(child)
        seg.append(el)
    return len(keep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", required=True, help="lat,lon of the public meeting point")
    ap.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_M)
    ap.add_argument("--avoid", metavar="LAT,LON", action="append", default=[],
                    help="a location to keep out of the published files; repeat for more than one")
    ap.add_argument("--radius", type=float, default=250.0,
                    help="metres around --avoid that must contain no geometry")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    lat, lon = [float(x) for x in args.at.split(",")]
    target = (lat, lon)

    files = sorted(RAW_GPX.glob("*.gpx"))
    if not files:
        print("No GPX files in data/raw/gpx")
        return 1

    avoid = [tuple(float(x) for x in a.split(",")) for a in args.avoid]

    plans = [plan(f, target, args.tolerance) for f in files]
    for zone in avoid:
        for p in plans:
            apply_exclusion(p, zone, args.radius)
    plans.sort(key=lambda p: p.get("closest_m", 9e9))

    todo = [p for p in plans if "lo" in p or "rotate_order" in p]
    print(f"Meeting point {lat:.6f}, {lon:.6f}, tolerance {args.tolerance:.0f} m")
    for z in avoid:
        print(f"Exclusion zone {args.radius:.0f} m around {z[0]:.6f}, {z[1]:.6f}")
    print()
    for p in plans:
        mark = "->" if ("lo" in p or "rotate_order" in p) else "  "
        print(f"{mark} {p['name'][:50]:<52} {p.get('total_km', 0):6.1f} km  {p['action']}")
        if p.get("exclusion"):
            print(f"{'':55}{p['exclusion']}")
    print(f"\n{len(todo)} of {len(plans)} to clip")
    if avoid:
        breached = [p for p in plans if p.get("breach")]  # noqa: E501
        if breached:
            print(f"\n{len(breached)} route(s) still enter an exclusion zone mid-ride and cannot be "
                  f"fixed by trimming ends:")
            for p in breached:
                print(f"  {p['name'][:52]:<54} closest {p['breach']:.0f} m")
            print("  These need the offending section re-planned, or a wider meeting point.")
        else:
            print("\nNo route enters any exclusion zone.")

    if not args.apply:
        print("\nDry run. Add --apply to write the changes.")
        return 0

    BACKUP.mkdir(parents=True, exist_ok=True)
    for p in todo:
        shutil.copy2(p["path"], BACKUP / p["path"].name)
        n = apply_clip(p, target)
        p["tree"].write(p["path"], encoding="utf-8", xml_declaration=True)
        note = "closed on the point" if p.get("close") else "left open at the far end"
        print(f"  {p['name'][:50]:<52} {n} points, {note}")
    print(f"\n{len(todo)} rewritten. Originals copied to data/raw/_pre_clip/.")
    print("Run scripts/build.py to rebuild.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
