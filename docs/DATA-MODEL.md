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
      "id": "example-loop",
      "name": "Example Loop",
      "source_files": { "gpx": "routes/gpx/example-loop.gpx", "fit": "routes/fit/example-loop.fit" },
      "distance_km": 48.2,
      "ascent_m": 912,
      "descent_m": 908,
      "max_elevation_m": 476,
      "min_elevation_m": 42,
      "is_loop": true,
      "start": [51.1234, -3.5678],
      "end": [51.1234, -3.5678],
      "bbox": [51.1000, -3.6000, 51.2000, -3.4000],
      "geometry": "encoded polyline, simplified",
      "profile": [[0.0, 40], [0.5, 60], "distance_km / elevation_m pairs, resampled"],
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

Three viewer controls drive it, but power is not one of them directly. The primary control is typical average speed. The page bisects on power until the whole library, distance-weighted, averages that speed, then applies the resulting power per gradient segment. Mass and surface remain as controls; with the target speed pinned they do not change the library average, they redistribute time between hilly and flat routes, which is the honest behaviour. Presets map friendly labels to watt values so nobody needs to know their FTP to use the page. The model is deliberately transparent and documented here so its numbers can be sanity-checked against real ride data.

### Checked against real rides, 2026-10-29

Twenty-four recorded Garmin activities (10.9 to 104.2 km, 2.6 to 18.7 m/km of climbing, valleys, Forest of Dean and North Wales) were run through the same profile pipeline and compared against moving time, counting only intervals at 2.5 km/h or above. Results:

At the page defaults (20 km/h, 88 kg, Crr 0.018) the library-solved power is 197 W and estimates land 2.7% long against moving time on average, 8.6% RMS per ride. Against elapsed time they run 11.7% short; elapsed was 16% over moving across the set, which the 1.06 stoppage factor does not try to cover, and should not.

Best single-power fit per Crr: 0.010 to 0.024 all give 7.9 to 8.4% RMS, so the data cannot tell the surface presets apart and the default stays at 0.018. Residuals correlate only weakly with climbing (-0.21 at 0.018), so the hill response is not visibly wrong. At the defaults the median absolute miss is 6% and 16 of 24 rides are within 10%. The two worst are the terrain extremes: a 10.9 km steep Forest of Dean loop ran 17% slower than modelled and a 2.6 m/km railway-path ride 16% faster. No parameter was changed. The FAQ now says the figure is moving time.

Raw activities carry timestamps and heart rate and are never committed; the check is repeatable from `GPX Files/` with any similar script.

## Region

`region` is one of `south-wales`, `wye-dean` or `north-wales`, assigned in `build.py` by where the majority of a route's points lie (north of 52.3, or east of -2.80). The list of regions and their labels travels in `routes.json` as `regions`, so the page builds its chips from data. `meeting_point` also travels in the payload; the "Start within" filter measures from it unless the viewer asks for their own location.

## Route identity

The `id` is a slug derived from the course name and must stay stable, because it will appear in shareable deep links to individual routes. If a route is renamed in Garmin, the slug should be pinned rather than regenerated.
