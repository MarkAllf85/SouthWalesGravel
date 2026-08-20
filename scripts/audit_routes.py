#!/usr/bin/env python3
"""
Whole-library audit. Run this before every push, after build.py.

privacy_audit.py answers one question: does anything publishable enter an
exclusion zone. This answers the rest of them. It exists because two separate
faults reached the published map without anyone noticing: a route named after
Rhiwderin that never goes near Rhiwderin and was a byte-identical copy of
another route, and two routes whose names differed only by "Cross Keys" versus
"Crosskeys", which is not a difference a person reads at a glance.

Checks are in two tiers.

HARD FAILURES exit non-zero. These are defects:
  - a name claiming a gazetteer place the line does not pass within 3 km of
  - raw and published copies out of step, orphans, slug collisions
  - routes.js out of step with routes.json
  - a name element disagreeing with itself inside one GPX
  - route_type disagreeing with the measured start-to-finish gap
  - anything inside an exclusion zone

ADVISORIES never fail the build. Riding the same valleys repeatedly means
routes genuinely share towns and corridors, so these are for reading, not for
fixing:
  - names sharing most of their place words with another name
  - one route lying largely on top of another

Usage:
    python scripts/audit_routes.py --avoid LAT,LON --avoid LAT,LON --radius 200
    python scripts/audit_routes.py            # skips the privacy section
"""

from __future__ import annotations

import argparse
import difflib
import glob
import hashlib
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import name_routes as N  # noqa: E402

RAW_GPX = ROOT / "data" / "raw" / "gpx"
SITE_GPX = ROOT / "site" / "routes" / "gpx"
ROUTES_JSON = ROOT / "site" / "data" / "routes.json"
ROUTES_JS = ROOT / "site" / "data" / "routes.js"

NEAR_KM = N.NEAR_KM          # a claimed place must be at least this close
OVERLAP_TOL_M = 60.0         # two lines this close count as the same ground
OVERLAP_REPORT = 0.80        # advise above this fraction
SLUG_SIMILARITY = 0.80       # advise above this
EARTH_R = 6371000.0

hard: list[str] = []
soft: list[str] = []


def hv(a, b):
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((la2 - la1) / 2) ** 2 +
         math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def tokens(name):
    """The place words a route name claims, in order."""
    s = re.sub(r"^Gravel\s*-\s*", "", name)
    s = re.sub(r"\s*\(\d+\s*km\)$", "", s)          # the distance disambiguator
    s = re.sub(r"\s+(Loop|Out and Back)$", "", s)
    out = []
    for chunk in s.split(" and "):
        out.extend(p.strip() for p in chunk.split(","))
    return [p for p in out if p]


def track(path):
    """Returns (points, root, prefix), or (None, None, error string) if unreadable.

    A corrupt file must be reported, not raised. Half-written exports and
    partially synced OneDrive files both land here, and a stack trace at the
    point of the privacy check would look like the audit itself was broken.
    """
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return None, None, str(exc)
    p = "{" + root.tag.split("}")[0].strip("{") + "}" if "}" in root.tag else ""
    return [(float(e.get("lat")), float(e.get("lon"))) for e in root.findall(f".//{p}trkpt")], root, p


def header(t):
    print("\n" + "=" * 74 + f"\n{t}\n" + "=" * 74)


def check(label, ok, detail=""):
    print(f"  {'ok' if ok else 'FAIL':<5}{label}" + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        hard.append(f"{label} {detail}".strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--avoid", metavar="LAT,LON", action="append", default=[])
    ap.add_argument("--radius", type=float, default=200.0)
    ap.add_argument("--quiet", action="store_true", help="suppress the advisory sections")
    args = ap.parse_args()

    if not ROUTES_JSON.exists():
        print("site/data/routes.json is missing. Run scripts/build.py first.")
        return 2
    data = json.loads(ROUTES_JSON.read_text(encoding="utf-8"))
    routes = data["routes"]
    places = {n: (la, lo) for la, lo, n in N.load_places()}
    geom = {r["id"]: N.decode(r["geometry"]) for r in routes}

    # ---------------------------------------------------------------- names
    header("NAME vs GEOMETRY")
    checked = 0
    unverifiable = []
    for r in sorted(routes, key=lambda r: r["name"]):
        for t in tokens(r["name"]):
            if t not in places:
                unverifiable.append((r["name"], t))
                continue
            checked += 1
            km = min(hv(places[t], p) for p in geom[r["id"]]) / 1000
            if km > NEAR_KM:
                hard.append(f'"{r["name"]}" claims {t}, closest approach {km:.1f} km')
                print(f"  FAIL {r['name'][:56]:<58}{t:<16} closest {km:.2f} km")
    print(f"  {checked} gazetteer-backed place claim(s) checked, "
          f"{sum(1 for h in hard if ' claims ' in h)} failure(s)")
    if unverifiable and not args.quiet:
        print("\n  Not in the gazetteer, so neither confirmed nor denied. These are the")
        print("  landmark words kept deliberately; check them by eye, not by script:")
        for nm, t in unverifiable:
            print(f"    {nm[:56]:<58}{t}")

    # ------------------------------------------------------------ integrity
    header("DATA INTEGRITY")
    ids = [r["id"] for r in routes]
    check("slug uniqueness", len(ids) == len(set(ids)))
    dupe_suffixed = [i for i in ids if re.search(r"-\d+$", i) and not i.endswith("-km")]
    check("no collision-suffixed ids from build.py", not dupe_suffixed, str(dupe_suffixed))
    raw = sorted(os.path.basename(f) for f in glob.glob(str(RAW_GPX / "*.gpx")))
    site = sorted(os.path.basename(f) for f in glob.glob(str(SITE_GPX / "*.gpx")))
    check("raw and published file sets match", raw == site, str(set(raw) ^ set(site)))
    check("every id has a published GPX",
          all((SITE_GPX / f"{i}.gpx").exists() for i in ids))

    def md5(f):
        return hashlib.md5(Path(f).read_bytes()).hexdigest()

    drift = [i for i in ids
             if (RAW_GPX / f"{i}.gpx").exists() and (SITE_GPX / f"{i}.gpx").exists()
             and md5(RAW_GPX / f"{i}.gpx") != md5(SITE_GPX / f"{i}.gpx")]
    check("published copies byte-identical to raw", not drift, str(drift))
    expected = "window.ROUTE_DATA = " + ROUTES_JSON.read_text(encoding="utf-8").strip() + ";"
    check("routes.js payload matches routes.json",
          ROUTES_JS.read_text(encoding="utf-8").strip() == expected)
    strays = glob.glob(str(RAW_GPX / "_superseded*")) + glob.glob(str(RAW_GPX / "COURSE_*"))
    check("no superseded or unrenamed Garmin exports left in raw", not strays,
          str([os.path.basename(s) for s in strays]))
    check("no pre-edit backup folders inside the repository",
          not ((RAW_GPX.parent / "_pre_clip").is_dir() or (RAW_GPX.parent / "_pre_alignment").is_dir()),
          "these hold unclipped originals and must never be committed")

    unreadable = []
    for f in glob.glob(str(RAW_GPX / "*.gpx")) + glob.glob(str(SITE_GPX / "*.gpx")):
        pts, root, p = track(f)
        if pts is None:
            unreadable.append(f"{os.path.basename(f)}: {p}")
        elif len(pts) < 2:
            unreadable.append(f"{os.path.basename(f)}: fewer than two track points")
    check("every GPX parses and holds a track", not unreadable, "; ".join(unreadable))

    mismatch = []
    for i in ids:
        _, root, p = track(RAW_GPX / f"{i}.gpx")
        if root is None:
            continue
        m = root.find(f"{p}metadata/{p}name")
        t = root.find(f"{p}trk/{p}name")
        mt = m.text.strip() if m is not None and m.text else None
        tt = t.text.strip() if t is not None and t.text else None
        if mt != tt:
            mismatch.append((i, mt, tt))
    check("metadata name matches trk name in every GPX", not mismatch, str(mismatch))

    bad = [r["id"] for r in routes if r["ascent_m"] <= 0 or r["distance_km"] <= 0]
    check("no route with zero distance or ascent", not bad, str(bad))
    flat = [r["id"] for r in routes if r["max_elevation_m"] == r["min_elevation_m"]]
    check("every route carries an elevation profile", not flat, str(flat))
    typed = []
    for r in routes:
        gap = hv(r["start"], r["end"]) / 1000
        closed = gap < 1.0
        if closed != (r["route_type"] != "point-to-point"):
            typed.append((r["id"], r["route_type"], round(gap, 2)))
    check("route_type agrees with the measured start-to-finish gap", not typed, str(typed))

    # -------------------------------------------------------------- privacy
    if args.avoid:
        header("PRIVACY")
        zones = [tuple(float(x) for x in a.split(",")) for a in args.avoid]
        files = glob.glob(str(SITE_GPX / "*.gpx")) + glob.glob(str(RAW_GPX / "*.gpx"))
        for n, z in enumerate(zones, 1):
            worst, who = 9e9, None
            for f in files:
                pts, _, _ = track(f)
                if not pts:
                    continue          # already reported as a hard failure above
                m = min(hv(z, q) for q in pts)
                if m < worst:
                    worst, who = m, os.path.basename(f)
            ok = worst >= args.radius
            print(f"  {'ok' if ok else 'FAIL':<5}zone {n}: closest approach {worst:.0f} m  ({who})")
            if not ok:
                hard.append(f"zone {n} breached at {worst:.0f} m by {who}")

    # ------------------------------------------------------------ advisories
    if not args.quiet:
        header("ADVISORY: names that share most of their place words")
        any_ = False
        for i, a in enumerate(routes):
            for b in routes[i + 1:]:
                ta, tb = set(tokens(a["name"])), set(tokens(b["name"]))
                shared = ta & tb
                ratio = difflib.SequenceMatcher(None, a["id"], b["id"]).ratio()
                if (shared and len(shared) >= min(len(ta), len(tb))) or ratio > SLUG_SIMILARITY:
                    any_ = True
                    soft.append(f'"{a["name"]}" / "{b["name"]}"')
                    print(f"  {a['name'][:52]:<54}{a['distance_km']:6.1f} km")
                    print(f"  {b['name'][:52]:<54}{b['distance_km']:6.1f} km   "
                          f"shared {sorted(shared)}, slug similarity {ratio:.2f}\n")
        if not any_:
            print("  none")

        header("ADVISORY: routes lying on top of one another")

        def cover(A, B):
            step = max(1, len(A) // 250)
            s = A[::step]
            return sum(1 for a in s if min(hv(a, b) for b in B) <= OVERLAP_TOL_M) / len(s)

        any_ = False
        for i, a in enumerate(routes):
            for b in routes[i + 1:]:
                ca = cover(geom[a["id"]], geom[b["id"]])
                cb = cover(geom[b["id"]], geom[a["id"]])
                if max(ca, cb) >= OVERLAP_REPORT:
                    any_ = True
                    soft.append(f'{a["name"]} / {b["name"]} ({ca:.0%}/{cb:.0%})')
                    print(f"  {ca:.0%} of \"{a['name'][:42]}\" ({a['distance_km']:.1f} km) lies on")
                    print(f"        \"{b['name'][:42]}\" ({b['distance_km']:.1f} km); reverse {cb:.0%}")
        if not any_:
            print("  none")

    header("RESULT")
    print(f"  {len(routes)} route(s), {len(hard)} hard failure(s), {len(soft)} advisory note(s)")
    for h in hard:
        print(f"  FAIL  {h}")
    if not hard:
        print("\n  PASS. Nothing here blocks a push.")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
