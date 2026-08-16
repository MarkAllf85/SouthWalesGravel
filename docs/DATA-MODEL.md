---
name: data-model
description: routes.json schema, file format notes and the duration model
type: reference
updated: 2026-08-16
---

# Data Model

## Pipeline shape

Course files land in `data/raw/gpx` and `data/raw/fit`. The build script parses them, computes statistics, writes `site/data/routes.json`, and copies the untouched originals into `site/routes/` so the map can link to them. Nothing in `site/` is edited by hand.

## routes.json

```json
{
  "generated": "2026-08-16T14:00:00Z",
  "routes": [
    {
      "id": "cwmcarn-twrch-loop",
      "name": "Cwmcarn and Twrch Loop",
      "source_files": { "gpx": "routes/gpx/cwmcarn-twrch-loop.gpx", "fit": "routes/fit/cwmcarn-twrch-loop.fit" },
      "distance_km": 48.2,
      "ascent_m": 912,
      "descent_m": 908,
      "max_elevation_m": 476,
      "min_elevation_m": 42,
      "is_loop": true,
      "start": [51.6489, -3.2201],
      "end": [51.6491, -3.2198],
      "bbox": [51.6012, -3.3104, 51.7220, -3.1188],
      "geometry": "encoded polyline, simplified",
      "profile": [[0.0, 42], [0.5, 61], "distance_km / elevation_m pairs, resampled"],
      "gradient_bands": { "flat_km": 18.4, "climb_km": 14.9, "descent_km": 14.9 },
      "estimated_hours_ref": 2.6,
      "tags": ["gravel", "forestry"],
      "notes": ""
    }
  ]
}
```

`estimated_hours_ref` is a reference figure at the default power setting. The live number shown on the page is recomputed in the browser from `profile` whenever the viewer changes their settings.

## GPX versus FIT

GPX courses from Garmin Connect are track-based XML with latitude, longitude and elevation per point. Everything the map needs is present. Elevation in a Garmin GPX export is usually already corrected against Garmin's DEM rather than raw barometric data, which is what we want.

FIT courses are binary and require `fitdecode` or the Garmin FIT SDK to read. They carry course points (turn cues, named waypoints) and are the file a Garmin device handles best. The pipeline will read FIT where GPX is absent, and will always offer the FIT for download when present.

TCX is a third possible export. It parses like GPX and can be supported cheaply if any routes only exist in that format.

## Duration model

Per-segment speed is solved from a standard cycling power balance:

```
P = (Crr * m * g * cos(theta) + m * g * sin(theta)) * v + 0.5 * rho * CdA * v^3
```

with gravel-appropriate defaults: CdA 0.40 for hoods position on a gravel bike with a bar bag, combined rider and bike mass supplied by the viewer, and air density 1.225. Rolling resistance is the coefficient that matters most and it is exposed as a surface control rather than fixed, because 0.014 hardpack, 0.018 mixed and 0.024 rough and loose produce meaningfully different days out. A road-bike value near 0.010 was the initial default and was wrong: it modelled 28 kph on the flat at 180 W, which is a tarmac number, not a gravel one. The cubic is solved numerically for `v` on each segment of the resampled profile, descents are capped at a sensible braking limit rather than allowed to run away, and a stoppage factor is added for gates, junctions and regrouping.

Three viewer controls drive it, but power is not one of them directly. The primary control is typical average speed. The page bisects on power until the whole library, distance-weighted, averages that speed, then applies the resulting power per gradient segment. Mass and surface remain as controls; with the target speed pinned they do not change the library average, they redistribute time between hilly and flat routes, which is the honest behaviour. Presets map friendly labels to watt values so nobody needs to know their FTP to use the page. The model is deliberately transparent and documented here so its numbers can be sanity-checked against real ride data later.

## Route identity

The `id` is a slug derived from the course name and must stay stable, because it will appear in shareable deep links to individual routes. If a route is renamed in Garmin, the slug should be pinned rather than regenerated.
