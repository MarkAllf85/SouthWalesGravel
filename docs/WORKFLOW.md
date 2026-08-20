---
name: workflow
description: How to add routes and rebuild and publish the map
type: reference
updated: 2026-08-16
---

# Workflow

## Adding routes

Export the course from Garmin Connect. On a course page the export menu offers GPX and, on newer accounts, the FIT course file. Save both where both are offered. Drop GPX files into `data\raw\gpx` and FIT files into `data\raw\fit`, matching the filenames so the pipeline can pair them.

Garmin has no bulk course export in the web UI, so the first load is a manual grind proportional to the number of routes. This is the friction that decides whether the automated sync in decision 5 is worth building.

## Rebuilding

Run the build script in `scripts/`. It reparses everything in `data/raw`, regenerates `site/data/routes.json`, refreshes the copies in `site/routes/` and reports any file it could not parse. The build is idempotent, so running it repeatedly is safe.

## Publishing

`site/` is the GitHub Pages root. Commit and push, and Pages serves the updated map within a minute or so. There is no build step on the GitHub side, which keeps the deployment path short enough to debug from a phone.

## Sharing

One URL covers the whole library. Individual routes get deep links of the form `?route=<id>` so a specific suggestion can be sent into a group chat and opens with that route selected and zoomed.

## Things that will break

Renaming a course in Garmin changes the exported filename and therefore the generated slug, which breaks any deep link already shared. Pin slugs in the build script when this starts to matter.

Tile providers are free but rate limited and rely on their operators' goodwill. If CyclOSM or OpenTopoMap start refusing requests, the fix is a Thunderforest or MapTiler key on a free tier rather than abandoning the layer.

## Where the zone coordinates live

Nowhere in this repository. They sit in `zones.local.txt`, which `.gitignore` excludes, and are passed on the command line. Publishing the exclusion zones alongside the routes would tell a reader exactly which gap in the data to look at, which defeats the purpose of clipping in the first place. The meeting point is a different matter: every published route starts and finishes there, so it is public whether the docs mention it or not.

## The two maintenance scripts

`scripts/name_routes.py` proposes geographic names from the gazetteer in `scripts/data/gb_places.csv`. Run it bare to see proposals with the evidence behind each one, `--csv out.csv` to get them in a file, and `--apply approved.csv` to rewrite the GPX names and filenames from a csv with `id` and `approved_name` columns. It never invents a place; anything it cannot resolve is reported as needing local knowledge.

`scripts/align_starts.py --at 51.647080,-3.205153` reports which routes can be rotated to start and finish at the meeting point, and `--apply` rewrites them. Originals are copied to `data/raw/_pre_alignment/` first. Point-to-point routes are never touched, and neither is anything that does not pass within the tolerance, because connecting to a point a route never reaches means inventing road.

`align_starts.py` also takes `--connector <file>.gpx`, for routes that start at the meeting point but finish somewhere else. The connector must be real ground you have planned or ridden; the script generates nothing. It orients the file automatically and refuses to splice anything whose ends do not meet, so a wrong file is a no-op rather than a corrupted route.

`scripts/clip_to_point.py` is the privacy step and must run first:

    python scripts\clip_to_point.py --at 51.647080,-3.205153 --avoid LAT,LON --avoid LAT,LON --radius 200 --apply
    python scripts\align_starts.py --at 51.647080,-3.205153 --apply
    python scripts\name_routes.py --apply approved.csv
    python scripts\build.py

`--avoid` repeats, once per zone. Clip first, then align, then name, then build. Both editing scripts are idempotent and back up to `data/raw/_pre_clip/` and `data/raw/_pre_alignment/` before touching anything. The clip script reports, and refuses to edit, any route that enters the exclusion zone in the middle of a ride and is not a closed loop, because cutting a route in half to dodge a circle produces two broken files rather than one fixed one.

Run all of them before `build.py`, not after.

## The audit, which runs last

`scripts/audit_routes.py` checks the whole library after a build and exits non-zero if anything is wrong, so it can gate a push:

    python scripts\audit_routes.py --avoid LAT,LON --avoid LAT,LON --radius 200

It exists because two faults reached the published map unnoticed. One route was named after Rhiwderin but never went near it, and was a byte-identical copy of another route under a different name. Two others differed only by "Cross Keys" versus "Crosskeys", which nobody reads as a difference, and the wrong one got opened and compared against a fresh Garmin course. Neither was something `build.py` or `privacy_audit.py` was looking for.

Hard failures are defects and stop the push: a name claiming a gazetteer place the line does not pass within 3 km of, raw and published copies out of step, orphans, slug collisions, `routes.js` drifting from `routes.json`, a GPX that will not parse, a name element disagreeing with itself inside one file, a `route_type` that contradicts the measured start-to-finish gap, and anything inside an exclusion zone.

Advisories never fail. Riding the same valleys means routes genuinely share towns and corridors, so names sharing most of their place words, and routes lying largely on top of one another, are printed to be read rather than fixed. Use `--quiet` to suppress them.

The audit can only check names it can look up. Words the gazetteer lacks, Trefil, Ynysybwl, Rhigos, Garwnant, Pontsticill, Torpantau, Llanwonno, Manmole, Dowlais Top, Mumbles, Wyllie, are listed separately as unverifiable rather than passed silently. Those still need an eye on them.

`privacy-check.ps1` runs `privacy_audit.py` and then this, reading the zones from `zones.local.txt`, so the whole gate is one command.
