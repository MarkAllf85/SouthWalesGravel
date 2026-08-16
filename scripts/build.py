#!/usr/bin/env python3
"""
Bike Route Explorer - build pipeline.

Reads course files from data/raw/{gpx,fit}, computes statistics, and writes
the static site data into site/data/ plus downloadable copies into site/routes/.

GPX parsing is stdlib only, so no pip install is needed for the common case.
FIT parsing requires `pip install fitdecode` and is skipped with a warning if
the module is missing.

Usage:
    python scripts/build.py
    python scripts/build.py --demo      # also generate synthetic demo routes
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_GPX = ROOT / "data" / "raw" / "gpx"
RAW_FIT = ROOT / "data" / "raw" / "fit"
SITE = ROOT / "site"
SITE_DATA = SITE / "data"
SITE_GPX = SITE / "routes" / "gpx"
SITE_FIT = SITE / "routes" / "fit"

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

ASCENT_THRESHOLD_M = 3.0      # hysteresis, stops GPS noise inflating total ascent
ELEV_SMOOTH_WINDOW = 5        # points, centred rolling mean before ascent maths
SIMPLIFY_TOLERANCE_M = 12.0   # Douglas-Peucker tolerance for map geometry
PROFILE_POINTS = 240          # resampled elevation profile resolution
LOOP_MAX_GAP_KM = 1.0         # start/end closer than this counts as a loop

# Reference rider used only for the pre-computed sort key. The live figure the
# page shows is recomputed in the browser from the viewer's own settings.
REF_POWER_W = 180.0
REF_MASS_KG = 88.0

# Gravel, not road. Crr 0.010 would model a road bike on tarmac and produces
# fantasy speeds. Surface presets exposed in the UI: 0.014 hardpack and forest
# road, 0.018 mixed, 0.024 rough and loose.
CRR = 0.018        # mixed gravel, the default
CDA = 0.40         # hoods position, gravel bike with a bar bag
RHO = 1.225        # air density at sea level, 15C
DRIVETRAIN_EFF = 0.97
G = 9.80665
MAX_DESCENT_KPH = 55.0
STOPPAGE_FACTOR = 1.06   # gates, junctions, regrouping

EARTH_R = 6371000.0


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def haversine(a, b) -> float:
    """Distance in metres between two (lat, lon) pairs."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def perpendicular_distance_m(pt, start, end) -> float:
    """Approximate point-to-segment distance in metres using a local planar projection."""
    lat0 = math.radians(start[0])
    mx = EARTH_R * math.cos(lat0)

    def proj(p):
        return (math.radians(p[1]) * mx, math.radians(p[0]) * EARTH_R)

    px, py = proj(pt)
    ax, ay = proj(start)
    bx, by = proj(end)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def douglas_peucker(points, tolerance_m):
    """Iterative Douglas-Peucker so long tracks cannot blow the recursion limit."""
    n = len(points)
    if n < 3:
        return list(points)
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        worst_d, worst_i = 0.0, -1
        for i in range(first + 1, last):
            d = perpendicular_distance_m(points[i], points[first], points[last])
            if d > worst_d:
                worst_d, worst_i = d, i
        if worst_d > tolerance_m and worst_i != -1:
            keep[worst_i] = True
            stack.append((first, worst_i))
            stack.append((worst_i, last))
    return [p for p, k in zip(points, keep) if k]


def encode_polyline(points, precision=5):
    """Google encoded polyline, latitude then longitude."""
    factor = 10 ** precision
    out = []
    prev_lat = prev_lon = 0

    def encode_value(v):
        v = v << 1 if v >= 0 else ~(v << 1)
        chunks = []
        while v >= 0x20:
            chunks.append((0x20 | (v & 0x1F)) + 63)
            v >>= 5
        chunks.append(v + 63)
        return "".join(chr(c) for c in chunks)

    for lat, lon in points:
        ilat, ilon = int(round(lat * factor)), int(round(lon * factor))
        out.append(encode_value(ilat - prev_lat))
        out.append(encode_value(ilon - prev_lon))
        prev_lat, prev_lon = ilat, ilon
    return "".join(out)


# ---------------------------------------------------------------------------
# Physics
# ---------------------------------------------------------------------------

def speed_for_gradient(power_w, mass_kg, gradient, crr=CRR, cda=CDA):
    """
    Solve P_wheel = (Crr*m*g*cos + m*g*sin) * v + 0.5*rho*CdA*v^3 for v.

    Bisection rather than a closed-form cubic: it is a handful of iterations,
    it never returns a spurious complex root, and it is trivially portable to
    the JavaScript side so both ends of the pipeline agree.
    """
    p = power_w * DRIVETRAIN_EFF
    theta = math.atan(gradient)
    resist = (crr * mass_kg * G * math.cos(theta)) + (mass_kg * G * math.sin(theta))
    lo, hi = 0.05, 30.0

    def net(v):
        return resist * v + 0.5 * RHO * cda * v ** 3 - p

    if net(lo) > 0:
        # Steep enough that even the minimum speed needs more than the rider has.
        # Below roughly 4 kph a rider walks, so floor it there.
        return 4.0 / 3.6
    if net(hi) < 0:
        return hi
    for _ in range(60):
        mid = (lo + hi) / 2
        if net(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def estimate_hours(profile, power_w=REF_POWER_W, mass_kg=REF_MASS_KG):
    """profile is a list of [cumulative_km, elevation_m]."""
    if len(profile) < 2:
        return 0.0
    seconds = 0.0
    cap = MAX_DESCENT_KPH / 3.6
    for (d0, e0), (d1, e1) in zip(profile, profile[1:]):
        dist_m = (d1 - d0) * 1000.0
        if dist_m <= 0:
            continue
        gradient = (e1 - e0) / dist_m
        v = min(speed_for_gradient(power_w, mass_kg, gradient), cap)
        seconds += dist_m / v
    return seconds / 3600.0 * STOPPAGE_FACTOR


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s or "route"


def parse_gpx(path: Path):
    """Return (name, [(lat, lon, ele), ...]). Handles both <trk> and <rte> courses."""
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {"g": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}

    # ElementTree needs the namespace baked into the path, so build it explicitly.
    prefix = "{" + ns["g"] + "}" if ns else ""

    name = None
    for tag in (f"{prefix}metadata/{prefix}name", f"{prefix}trk/{prefix}name", f"{prefix}rte/{prefix}name"):
        el = root.find(tag)
        if el is not None and el.text and el.text.strip():
            name = el.text.strip()
            break
    if not name:
        name = path.stem

    pts = []
    for tag in (f".//{prefix}trkpt", f".//{prefix}rtept"):
        for el in root.findall(tag):
            try:
                lat = float(el.get("lat"))
                lon = float(el.get("lon"))
            except (TypeError, ValueError):
                continue
            ele_el = el.find(f"{prefix}ele")
            ele = 0.0
            if ele_el is not None and ele_el.text:
                try:
                    ele = float(ele_el.text)
                except ValueError:
                    ele = 0.0
            pts.append((lat, lon, ele))
        if pts:
            break
    return name, pts


def parse_fit(path: Path):
    try:
        import fitdecode
    except ImportError:
        return None, None, "fitdecode not installed"

    name = path.stem
    pts = []
    try:
        with fitdecode.FitReader(str(path)) as fit:
            for frame in fit:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                if frame.name == "course" and frame.has_field("name"):
                    v = frame.get_value("name")
                    if v:
                        name = str(v)
                elif frame.name == "record":
                    try:
                        lat = frame.get_value("position_lat")
                        lon = frame.get_value("position_long")
                    except KeyError:
                        continue
                    if lat is None or lon is None:
                        continue
                    # FIT stores position in semicircles
                    lat = lat * (180.0 / 2 ** 31)
                    lon = lon * (180.0 / 2 ** 31)
                    ele = 0.0
                    for f in ("enhanced_altitude", "altitude"):
                        try:
                            v = frame.get_value(f)
                        except KeyError:
                            continue
                        if v is not None:
                            ele = float(v)
                            break
                    pts.append((lat, lon, ele))
    except Exception as exc:  # noqa: BLE001 - report and continue the batch
        return None, None, f"FIT parse failed: {exc}"
    return name, pts, None


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def smooth(values, window):
    if window < 2 or len(values) < window:
        return list(values)
    half = window // 2
    out = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def compute_stats(points):
    """points: [(lat, lon, ele)]. Returns a dict of derived statistics."""
    latlon = [(p[0], p[1]) for p in points]

    cum = [0.0]
    for a, b in zip(latlon, latlon[1:]):
        cum.append(cum[-1] + haversine(a, b))
    total_m = cum[-1]

    # Smooth over a fixed GROUND DISTANCE, not a fixed point count. A sparse
    # route-style export with points hundreds of metres apart would otherwise
    # have its real climbs averaged away by a five-point window.
    spacing = total_m / max(1, len(latlon) - 1)
    window = 1 if spacing >= 30 else min(15, max(1, int(round(ELEV_SMOOTH_WINDOW * 20 / max(spacing, 1)))))
    eles = smooth([p[2] for p in points], window)

    # Hysteresis ascent: only bank a change once it exceeds the threshold.
    ascent = descent = 0.0
    anchor = eles[0]
    direction = 0
    for e in eles[1:]:
        delta = e - anchor
        if direction >= 0 and delta >= ASCENT_THRESHOLD_M:
            ascent += delta
            anchor = e
            direction = 1
        elif direction <= 0 and delta <= -ASCENT_THRESHOLD_M:
            descent += -delta
            anchor = e
            direction = -1
        elif abs(delta) >= ASCENT_THRESHOLD_M:
            if delta > 0:
                ascent += delta
            else:
                descent += -delta
            anchor = e
            direction = 1 if delta > 0 else -1

    # Resample the profile onto an even distance grid.
    profile = []
    if total_m > 0:
        step = total_m / (PROFILE_POINTS - 1)
        j = 0
        for i in range(PROFILE_POINTS):
            target = i * step
            while j < len(cum) - 2 and cum[j + 1] < target:
                j += 1
            span = cum[j + 1] - cum[j]
            t = 0.0 if span <= 0 else (target - cum[j]) / span
            ele = eles[j] + t * (eles[min(j + 1, len(eles) - 1)] - eles[j])
            profile.append([round(target / 1000.0, 4), round(ele, 1)])

    # Gradient bands over the resampled profile.
    flat_km = climb_km = desc_km = 0.0
    for (d0, e0), (d1, e1) in zip(profile, profile[1:]):
        seg = d1 - d0
        if seg <= 0:
            continue
        grade = (e1 - e0) / (seg * 1000.0)
        if grade > 0.02:
            climb_km += seg
        elif grade < -0.02:
            desc_km += seg
        else:
            flat_km += seg

    gap_km = haversine(latlon[0], latlon[-1]) / 1000.0
    closed = gap_km < LOOP_MAX_GAP_KM and total_m > 3000

    # Out and back: the second half retraces the first. Sample the outward leg
    # and check how close each sample sits to the mirrored return leg.
    out_and_back = False
    if closed and len(latlon) >= 40:
        half = len(latlon) // 2
        outward = latlon[:half]
        back = list(reversed(latlon[half:]))
        samples = 40
        close = 0
        for i in range(samples):
            a = outward[int(i * (len(outward) - 1) / (samples - 1))]
            b = back[int(i * (len(back) - 1) / (samples - 1))]
            if haversine(a, b) < 120:
                close += 1
        out_and_back = close / samples > 0.7

    is_loop = closed and not out_and_back
    route_type = "out-and-back" if out_and_back else ("loop" if closed else "point-to-point")

    lats = [p[0] for p in latlon]
    lons = [p[1] for p in latlon]

    simplified = douglas_peucker(latlon, SIMPLIFY_TOLERANCE_M)

    return {
        "distance_km": round(total_m / 1000.0, 2),
        "ascent_m": int(round(ascent)),
        "descent_m": int(round(descent)),
        "max_elevation_m": int(round(max(eles))),
        "min_elevation_m": int(round(min(eles))),
        "is_loop": is_loop,
        "route_type": route_type,
        "start": [round(latlon[0][0], 6), round(latlon[0][1], 6)],
        "end": [round(latlon[-1][0], 6), round(latlon[-1][1], 6)],
        "bbox": [round(min(lats), 6), round(min(lons), 6), round(max(lats), 6), round(max(lons), 6)],
        "geometry": encode_polyline(simplified),
        "point_count": len(latlon),
        "simplified_count": len(simplified),
        "profile": profile,
        "gradient_bands": {
            "flat_km": round(flat_km, 1),
            "climb_km": round(climb_km, 1),
            "descent_km": round(desc_km, 1),
        },
        "estimated_hours_ref": round(estimate_hours(profile), 2),
    }


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(demo=False):
    for d in (RAW_GPX, RAW_FIT, SITE_DATA, SITE_GPX, SITE_FIT):
        d.mkdir(parents=True, exist_ok=True)

    if demo:
        from demo_routes import write_demo_routes
        write_demo_routes(RAW_GPX)

    gpx_files = sorted(RAW_GPX.glob("*.gpx"))
    fit_files = sorted(RAW_FIT.glob("*.fit"))
    fit_by_stem = {f.stem.lower(): f for f in fit_files}

    routes = []
    warnings = []
    seen_slugs = {}

    def register(name, points, gpx_path=None, fit_path=None):
        if not points or len(points) < 2:
            warnings.append(f"{(gpx_path or fit_path).name}: fewer than two usable points, skipped")
            return
        slug = slugify(name)
        if slug in seen_slugs:
            seen_slugs[slug] += 1
            slug = f"{slug}-{seen_slugs[slug]}"
        else:
            seen_slugs[slug] = 1

        stats = compute_stats(points)
        sources = {}
        if gpx_path:
            dest = SITE_GPX / f"{slug}.gpx"
            shutil.copy2(gpx_path, dest)
            sources["gpx"] = f"routes/gpx/{slug}.gpx"
        if fit_path:
            dest = SITE_FIT / f"{slug}.fit"
            shutil.copy2(fit_path, dest)
            sources["fit"] = f"routes/fit/{slug}.fit"

        routes.append({"id": slug, "name": name, "source_files": sources, **stats})

    for gpx_path in gpx_files:
        try:
            name, points = parse_gpx(gpx_path)
        except ET.ParseError as exc:
            warnings.append(f"{gpx_path.name}: invalid XML ({exc})")
            continue
        fit_path = fit_by_stem.pop(gpx_path.stem.lower(), None)
        register(name, points, gpx_path=gpx_path, fit_path=fit_path)

    for fit_path in fit_by_stem.values():
        name, points, err = parse_fit(fit_path)
        if err:
            warnings.append(f"{fit_path.name}: {err}")
            continue
        register(name, points, fit_path=fit_path)

    # Prune orphans from the published folder. Renaming a route changes its
    # slug, and without this the previous file stays in site/routes/ forever.
    # That is a privacy problem, not just untidiness: an orphan can be a copy
    # made before the exclusion zones were applied.
    wanted = {Path(v).name for r in routes for v in r["source_files"].values()}
    for d in (SITE_GPX, SITE_FIT):
        for stale in d.glob("*.*"):
            if stale.name not in wanted:
                stale.unlink()
                warnings.append(f"removed orphaned {d.name}/{stale.name} from the published folder")

    routes.sort(key=lambda r: r["distance_km"])

    # Flag near-identical routes. Garmin accumulates duplicates when a course is
    # copied and renamed, and two of the same line on the map is just noise.
    for i, a in enumerate(routes):
        for b in routes[i + 1:]:
            if abs(a["distance_km"] - b["distance_km"]) < 0.15 and abs(a["ascent_m"] - b["ascent_m"]) <= 5:
                if haversine(a["start"], b["start"]) < 300:
                    warnings.append(f"possible duplicate: '{a['name']}' and '{b['name']}' "
                                    f"({a['distance_km']} km, {a['ascent_m']} m)")

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reference_rider": {"power_w": REF_POWER_W, "mass_kg": REF_MASS_KG},
        "model": {"crr": CRR, "cda": CDA, "rho": RHO, "drivetrain_eff": DRIVETRAIN_EFF,
                  "max_descent_kph": MAX_DESCENT_KPH, "stoppage_factor": STOPPAGE_FACTOR},
        "routes": routes,
    }

    (SITE_DATA / "routes.json").write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    # Also emit a JS shim so index.html works when opened straight off disk,
    # where fetch() against file:// is blocked by the browser.
    (SITE_DATA / "routes.js").write_text(
        "window.ROUTE_DATA = " + json.dumps(payload, separators=(",", ":")) + ";",
        encoding="utf-8",
    )

    print(f"Built {len(routes)} route(s) -> site/data/routes.json")
    for r in routes:
        print(f"  {r['id']:<34} {r['distance_km']:>6.1f} km  {r['ascent_m']:>5} m  "
              f"{r['estimated_hours_ref']:>5.2f} h  {r['route_type']:<14} "
              f"{r['simplified_count']}/{r['point_count']} pts")
    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  ! {w}")
    if not routes:
        print("\nNo routes found. Drop GPX exports into data/raw/gpx and run again.")
    return len(routes)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="generate synthetic demo routes first")
    args = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    build(demo=args.demo)
