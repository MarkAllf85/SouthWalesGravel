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

## For riders

The site has an FAQ at `site/faq.html`, linked from the map, covering how to get a route onto a Garmin on iPhone, Android and desktop, why there is no one-tap button for it, and how the ride times are calculated.

## Quick start

Open `site/index.html` in a browser. It works straight off disk, no server needed.

After adding or removing course files, run `python scripts\\build.py` and reload.

## Status

Live at https://markallf85.github.io/SouthWalesGravel/

Sixty-two routes, 4,329 km and 57,279 m of climbing. Fifty-three loops and nine point-to-point. Shortest is 10.9 km, longest 181.7 km. Coverage reaches west to Glyncorrwg and the Afan valley, north over the Merthyr and Talybont uplands, and east across the Wye into the Forest of Dean. Seven routes sit outside South Wales: five around Barmouth, Dolgellau and Trawsfynydd, and two at Llyn Brenig.

Twenty-nine routes start and finish at the public meeting point. Three 200 m exclusion zones are enforced across every published file; nothing comes within 203 m of any of them. See `docs/DECISIONS.md` entries 13 and 14, and re-run the audit in `docs/WORKFLOW.md` after any change to the route files.

# Deployment

See `docs/DEPLOY.md` for the one-time GitHub Pages setup and the ongoing publish loop.
