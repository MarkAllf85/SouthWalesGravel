# South Wales Gravel Routes

An interactive, shareable map of every saved gravel route, with filtering by distance, ascent and estimated duration, and per-route GPX and FIT download.

Built because Garmin Connect stores routes well but shows them one at a time.

## Folder layout

```
data/raw/gpx     drop GPX course exports here
data/raw/fit     drop FIT course exports here
data/processed   build intermediates, safe to delete
scripts/         the build pipeline
site/            the generated static site, GitHub Pages root
docs/            project context, decisions and open questions
```

## Documentation

Read `docs/CONCEPT.md` first for what this is and what done looks like. `docs/DECISIONS.md` records what was chosen and why. `docs/DATA-MODEL.md` covers the routes.json schema and the duration model. `docs/WORKFLOW.md` is the add-a-route-and-publish loop. `docs/OPEN-QUESTIONS.md` tracks what still needs deciding.

## Quick start

Open `site/index.html` in a browser. It works straight off disk, no server needed.

After adding or removing course files, run `python scripts\\build.py` and reload.

## Status

Live at https://markallf85.github.io/SouthWalesGravel/

Twenty-six routes, 1,817 km and 23,013 m of climbing. Twenty-one loops and five point-to-point. Shortest is 20.5 km, longest 160.5 km.

Fifteen routes start and finish at the public meeting point. Two 200 m exclusion zones are enforced across every published file; nothing comes within 203 m of either. See `docs/DECISIONS.md` entries 13 and 14, and re-run the audit in `docs/WORKFLOW.md` after any change to the route files.

# Deployment

See `docs/DEPLOY.md` for the one-time GitHub Pages setup and the ongoing publish loop.
