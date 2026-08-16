#!/usr/bin/env python3
"""
Propose geographic names for routes, inferred from where the line actually goes.

Nothing here is guessed. Every place name comes from `scripts/data/gb_places.csv`,
a GeoNames cities1000 extract clipped to south east Wales and the Marches, and a
place is only attributed to a route when the route passes within a set distance
of it. Where no gazetteer entry is close enough, the route is reported as
unresolved rather than given an invented name.

The gazetteer's floor is roughly 1000 inhabitants, so valley towns are covered
well and small villages, forestry car parks and reservoirs are not. Unresolved
routes need local knowledge, not more computation.

Usage:
    python scripts/name_routes.py                 # print proposals
    python scripts/name_routes.py --apply names.csv   # rename from an approved csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACES = Path(__file__).resolve().parent / "data" / "gb_places.csv"
ROUTES_JSON = ROOT / "site" / "data" / "routes.json"
RAW_GPX = ROOT / "data" / "raw" / "gpx"

SAMPLE_KM = 1.0        # walk the line this often
NEAR_KM = 3.0          # a place must be at least this close to count at all
THROUGH_KM = 1.6       # this close means the route genuinely goes through it
MIN_SAMPLES = 2        # or it must be nearest for this many samples
PREFIX = "Gravel - "

# Almost every route leaves from the same place, so the start carries no
# information in a name. Places inside this radius of home are excluded from
# name candidates and the route is named for where it actually goes.
HOME = (51.647080, -3.205153)
HOME_EXCLUDE_KM = 5.0
LONG_ROUTE_KM = 70.0   # above this a third place earns its keep

EARTH_R = 6371.0


def haversine(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def decode(s, precision=5):
    factor = 10 ** precision
    index = lat = lng = 0
    out = []
    while index < len(s):
        shift = result = 0
        while True:
            b = ord(s[index]) - 63; index += 1
            result |= (b & 0x1F) << shift; shift += 5
            if b < 0x20: break
        lat += ~(result >> 1) if result & 1 else (result >> 1)
        shift = result = 0
        while True:
            b = ord(s[index]) - 63; index += 1
            result |= (b & 0x1F) << shift; shift += 5
            if b < 0x20: break
        lng += ~(result >> 1) if result & 1 else (result >> 1)
        out.append((lat / factor, lng / factor))
    return out


def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[\s_-]+", "-", s) or "route"


def load_places():
    with open(PLACES, encoding="utf-8") as f:
        return [(float(r["lat"]), float(r["lon"]), r["name"]) for r in csv.DictReader(f)]


def resample(points, step_km):
    """Yield (cumulative_km, point) at roughly even spacing along the line."""
    out = [(0.0, points[0])]
    acc = 0.0
    target = step_km
    for a, b in zip(points, points[1:]):
        d = haversine(a, b)
        if d <= 0:
            continue
        while acc + d >= target:
            t = (target - acc) / d
            out.append((target, (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))))
            target += step_km
        acc += d
    out.append((acc, points[-1]))
    return out


def places_along(points, places):
    """Return ordered place hits with coverage and closest approach."""
    hits = {}
    for km, p in resample(points, SAMPLE_KM):
        best = None
        for lat, lon, name in places:
            # cheap box reject before the trig
            if abs(lat - p[0]) > 0.06 or abs(lon - p[1]) > 0.10:
                continue
            d = haversine(p, (lat, lon))
            if best is None or d < best[0]:
                best = (d, name)
        if best is None or best[0] > NEAR_KM:
            continue
        d, name = best
        h = hits.setdefault(name, {"name": name, "first_km": km, "count": 0, "min_km": d})
        h["count"] += 1
        h["min_km"] = min(h["min_km"], d)
    kept = [h for h in hits.values() if h["min_km"] <= THROUGH_KM or h["count"] >= MIN_SAMPLES]
    kept.sort(key=lambda h: h["first_km"])
    return kept


def nearest_place(point, places, limit_km=4.0):
    best = None
    for lat, lon, name in places:
        d = haversine(point, (lat, lon))
        if best is None or d < best[0]:
            best = (d, name)
    return best[1] if best and best[0] <= limit_km else None


def propose(route, places):
    pts = decode(route["geometry"])
    hits = places_along(pts, places)
    coords = {n: (lat, lon) for lat, lon, n in places}

    for h in hits:
        h["from_home"] = haversine(HOME, coords[h["name"]])

    # Drop the home cluster. Naming a route after the village you always leave
    # from tells nobody anything, which is why the existing good names describe
    # the destinations instead.
    far = [h for h in hits if h["from_home"] > HOME_EXCLUDE_KM]
    far.sort(key=lambda h: h["first_km"])

    tail = {"loop": " Loop", "out-and-back": " Out and Back", "point-to-point": ""}[route["route_type"]]
    want = 3 if route["distance_km"] >= LONG_ROUTE_KM else 2

    picks = []
    if far:
        # The apex is the far end of the ride, but "furthest" alone picks
        # suburbs over the town beside them. Among everything within 85% of the
        # maximum reach, prefer the place the route actually spends time in.
        reach = max(h["from_home"] for h in far)
        contenders = [h for h in far if h["from_home"] >= 0.85 * reach]
        apex = max(contenders, key=lambda h: (h["count"], h["from_home"]))
        picks = [apex]
        # Fill the remaining slots with the best-covered places that are a real
        # distance from what we already have, so the name spans the ride rather
        # than listing three neighbouring villages.
        for cand in sorted(far, key=lambda h: (-h["count"], -h["from_home"])):
            if len(picks) >= want:
                break
            if all(haversine(coords[cand["name"]], coords[p["name"]]) > 3.0 for p in picks):
                picks.append(cand)
        picks.sort(key=lambda h: h["first_km"])

    primary = None
    if len(picks) >= 2:
        names = [p["name"] for p in picks]
        joined = ", ".join(names[:-1]) + " and " + names[-1]
        primary = PREFIX + joined + tail
    elif len(picks) == 1:
        primary = PREFIX + picks[0]["name"] + tail

    # For a route that never leaves the home cluster, fall back to whatever it
    # did pass through, minus the immediate home villages.
    if not primary and hits:
        names = [h["name"] for h in hits if h["from_home"] > 2.5][:2]
        if names:
            primary = PREFIX + " and ".join(names) + tail

    alt = None
    if len(picks) >= 2 and want == 2 and len(far) > len(picks):
        extra = [h for h in far if h not in picks]
        if extra:
            third = max(extra, key=lambda h: h["count"])
            three = sorted(picks + [third], key=lambda h: h["first_km"])
            ns = [p["name"] for p in three]
            alt = PREFIX + ", ".join(ns[:-1]) + " and " + ns[-1] + tail

    return {
        "id": route["id"],
        "current": route["name"],
        "type": route["route_type"],
        "km": route["distance_km"],
        "primary": primary,
        "alt": alt,
        "evidence": [h["name"] for h in hits],
        "start": nearest_place(route["start"], places),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", metavar="CSV", help="apply approved names from a csv of id,new_name")
    ap.add_argument("--csv", metavar="OUT", help="write proposals to a csv for review")
    args = ap.parse_args()

    data = json.loads(ROUTES_JSON.read_text(encoding="utf-8"))
    places = load_places()

    if args.apply:
        apply_names(args.apply, data)
        return

    props = [propose(r, places) for r in data["routes"]]
    props.sort(key=lambda p: p["km"])

    named = [p for p in props if p["primary"]]
    unresolved = [p for p in props if not p["primary"]]

    for p in props:
        flag = "  " if p["primary"] else "??"
        print(f"{flag} {p['km']:>6.1f} km  {p['type']:<14} {p['current']}")
        print(f"      -> {p['primary'] or 'NO GAZETTEER MATCH, needs local knowledge'}")
        if p["alt"]:
            print(f"      or {p['alt']}")
        print(f"      via: {', '.join(p['evidence']) if p['evidence'] else '(nothing within 3 km)'}")
        print()

    print(f"{len(named)} of {len(props)} resolved, {len(unresolved)} need local knowledge")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "current_name", "proposed_name", "alternative", "type",
                        "distance_km", "places_passed"])
            for p in props:
                w.writerow([p["id"], p["current"], p["primary"] or "", p["alt"] or "",
                            p["type"], p["km"], "; ".join(p["evidence"])])
        print(f"wrote {args.csv}")


def apply_names(csv_path, data):
    """Rewrite the <name> element in each GPX and rename the file to match."""
    by_id = {r["id"]: r for r in data["routes"]}
    done = skipped = 0
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rid, new = row["id"].strip(), row.get("approved_name", "").strip()
            if not new or rid not in by_id:
                skipped += 1
                continue
            src = ROOT / by_id[rid]["source_files"]["gpx"].replace("routes/gpx/", "")
            # the original lives in data/raw/gpx under its Garmin filename
            original = find_original(by_id[rid])
            if not original:
                print(f"  ! {rid}: original GPX not found, skipped")
                skipped += 1
                continue
            text = original.read_text(encoding="utf-8")
            text = re.sub(r"<name>.*?</name>", "<name>" + escape(new) + "</name>", text, count=1,
                          flags=re.S)
            # trk/name too, if the file carries both
            text = re.sub(r"(<trk>\s*)<name>.*?</name>", r"\1<name>" + escape(new) + "</name>",
                          text, count=1, flags=re.S)
            target = original.parent / (slugify(new) + ".gpx")
            target.write_text(text, encoding="utf-8")
            if target.resolve() != original.resolve():
                shutil.move(str(original), str(original.parent / ("_superseded_" + original.name)))
            print(f"  renamed {original.name} -> {target.name}")
            done += 1
    print(f"{done} renamed, {skipped} skipped. Run scripts/build.py to rebuild.")


def escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def find_original(route):
    """Match a built route back to its file in data/raw/gpx by name or slug."""
    for p in RAW_GPX.glob("*.gpx"):
        try:
            head = p.read_text(encoding="utf-8", errors="ignore")[:4000]
        except OSError:
            continue
        m = re.search(r"<name>(.*?)</name>", head, re.S)
        if m and slugify(m.group(1).strip()) == route["id"]:
            return p
    cand = RAW_GPX / (route["id"] + ".gpx")
    return cand if cand.exists() else None


if __name__ == "__main__":
    sys.exit(main())
