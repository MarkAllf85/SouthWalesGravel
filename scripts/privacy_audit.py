#!/usr/bin/env python3
"""
Fail loudly if anything publishable comes too close to a private location.

Run this before every push. It exists because a rebuild is not the risky
moment: the risky moment is a backup folder, a stray export or a forgotten
working copy getting swept up by `git add -A`. So this does not just check the
built site, it walks every GPX anywhere under the project, plus routes.json,
and reports what git would actually publish.

Exit code is 1 if any tracked or untracked-but-unignored file breaches a zone,
which makes it usable as a pre-push hook.

Usage:
    python scripts/privacy_audit.py --avoid 51.6,-3.2 --avoid 51.61,-3.17 --radius 200
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EARTH_R = 6371000.0


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


def gpx_points(path):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return []
    pre = "{" + root.tag.split("}")[0].strip("{") + "}" if "}" in root.tag else ""
    pts = []
    for tag in (f".//{pre}trkpt", f".//{pre}rtept", f".//{pre}wpt"):
        for el in root.findall(tag):
            try:
                pts.append((float(el.get("lat")), float(el.get("lon"))))
            except (TypeError, ValueError):
                continue
    return pts


def git_available():
    """
    Ignore rules can only be evaluated inside a repository. Outside one,
    `git check-ignore` exits 128 for every path, which would otherwise be
    misread as "not ignored" and flag the whole tree.
    """
    try:
        r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT,
                           capture_output=True, text=True)
    except FileNotFoundError:
        return False, "git is not installed"
    if r.returncode != 0:
        return False, "this folder is not a git repository yet"
    return True, ""


def git_would_publish(path, have_git):
    """True if git would add the file under `git add -A`. None if unknowable."""
    if not have_git:
        return None
    rel = path.relative_to(ROOT).as_posix()
    rc = subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT,
                        capture_output=True).returncode
    if rc == 0:
        return False   # ignored
    if rc == 1:
        return True    # would be added
    return None        # git could not decide


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--avoid", metavar="LAT,LON", action="append", required=True,
                    help="a private location; repeat for more than one")
    ap.add_argument("--radius", type=float, default=200.0)
    ap.add_argument("--all", action="store_true",
                    help="also report files git would not publish")
    args = ap.parse_args()

    zones = [tuple(float(x) for x in a.split(",")) for a in args.avoid]
    have_git, why = git_available()
    breaches, checked, skipped = [], 0, 0

    if not have_git:
        print(f"WARNING: {why}, so .gitignore cannot be evaluated.")
        print("         Every file is reported as unknown rather than safe.")
        print("         Run `git init` first, then re-run this audit for a real answer.\n")

    for path in sorted(ROOT.rglob("*.gpx")):
        publish = git_would_publish(path, have_git)
        if publish is False and not args.all:
            skipped += 1
            continue
        pts = gpx_points(path)
        if not pts:
            continue
        checked += 1
        for zi, z in enumerate(zones):
            d = min(haversine(z, p) for p in pts)
            if d < args.radius:
                breaches.append((d, zi, path.relative_to(ROOT).as_posix(), publish))

    rj = ROOT / "site" / "data" / "routes.json"
    if rj.exists():
        data = json.loads(rj.read_text(encoding="utf-8"))
        for r in data.get("routes", []):
            pts = decode(r["geometry"])
            checked += 1
            for zi, z in enumerate(zones):
                d = min(haversine(z, p) for p in pts)
                if d < args.radius:
                    breaches.append((d, zi, f"routes.json :: {r['id']}", True))

    print(f"Privacy audit: {len(zones)} zone(s) at {args.radius:.0f} m, "
          f"{checked} file(s) checked, {skipped} ignored by git")

    real = [b for b in breaches if b[3] is True]
    unknown = [b for b in breaches if b[3] is None]

    if not breaches:
        print("\nPASS. Nothing publishable enters any exclusion zone.")
        return 0

    breaches.sort(key=lambda b: (b[3] is not True, b[0]))
    print(f"\n{len(real)} breach(es) that would be published"
          + (f", {len(unknown)} unknown" if unknown else "") + ":\n")
    for d, zi, name, publish in breaches:
        tag = {True: "WOULD BE PUBLISHED", False: "ignored by git",
               None: "unknown, no repo"}[publish]
        print(f"  {d:6.0f} m from zone {zi + 1}   {name}   [{tag}]")

    if real:
        print("\nFAIL. Add these paths to .gitignore, or re-run scripts/clip_to_point.py.")
        return 1
    if unknown and not have_git:
        print("\nINCONCLUSIVE. Run `git init` first, then re-run.")
        return 2
    print("\nPASS. Every breach is in a path git will not publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
