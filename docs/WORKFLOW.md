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

## The two maintenance scripts

`scripts/name_routes.py` proposes geographic names from the gazetteer in `scripts/data/gb_places.csv`. Run it bare to see proposals with the evidence behind each one, `--csv out.csv` to get them in a file, and `--apply approved.csv` to rewrite the GPX names and filenames from a csv with `id` and `approved_name` columns. It never invents a place; anything it cannot resolve is reported as needing local knowledge.

`scripts/align_starts.py --at 51.647080,-3.205153` reports which routes can be rotated to start and finish at the meeting point, and `--apply` rewrites them. Originals are copied to `data/raw/_pre_alignment/` first. Point-to-point routes are never touched, and neither is anything that does not pass within the tolerance, because connecting to a point a route never reaches means inventing road.

`align_starts.py` also takes `--connector <file>.gpx`, for routes that start at the meeting point but finish somewhere else. The connector must be real ground you have planned or ridden; the script generates nothing. It orients the file automatically and refuses to splice anything whose ends do not meet, so a wrong file is a no-op rather than a corrupted route.

`scripts/clip_to_point.py` is the privacy step and must run first:

    python scripts\clip_to_point.py --at 51.647080,-3.205153 --avoid <address lat,lon> --avoid 51.617153,-3.175053 --radius 200 --apply
    python scripts\align_starts.py --at 51.647080,-3.205153 --apply
    python scripts\name_routes.py --apply approved.csv
    python scripts\build.py

`--avoid` repeats, once per zone. Clip first, then align, then name, then build. Both editing scripts are idempotent and back up to `data/raw/_pre_clip/` and `data/raw/_pre_alignment/` before touching anything. The clip script reports, and refuses to edit, any route that enters the exclusion zone in the middle of a ride and is not a closed loop, because cutting a route in half to dodge a circle produces two broken files rather than one fixed one.

Run all of them before `build.py`, not after.
