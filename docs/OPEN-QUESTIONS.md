---
name: open-questions
description: What still needs Mark's input before or during the build
type: project
updated: 2026-08-16
---

# Open Questions

## Answered by the first real build, 2026-08-16

Twenty-six routes, all GPX, all Garmin course exports named `COURSE_<id>.gpx` before renaming. Well under the scale at which the map needs clustering or vector tiles, so the simple approach stands. No FIT files supplied, so the FIT decoder is present but untested against real data.

Two of the twenty-six are the same route saved twice: '3 hour 20 loop' and 'Rhiwderin look - 3.5 hours', now named 'Gravel - Bedwas and Machen Loop' and 'Gravel - Rhiwderin and Machen Loop', are both 57.4 km and 389 m from the same start. The build now flags near-identical routes as a warning. Decide whether to delete one in Garmin or keep both.

Still open: whether any completed activity files exist to validate the duration model against real elapsed times.

## Needed before publishing

Repository visibility and whether any route starts at a home address. See decision log open items.

Whether the group should be able to suggest or add routes, or whether this stays a published library that Mark curates.

## Nice to have, decide later

Surface classification. OpenStreetMap carries `surface` tags on most ways, so it is possible to snap route geometry to OSM and report a gravel versus tarmac split per route. This is the single most useful filter for gravel riding and also the most work. Worth scoping properly once the basic map is proven.

Weather and seasonality. Some of these routes are unrideable in winter. A simple manual tag may be worth more than anything clever.


## The three open routes, 2026-08-16

Three routes start exactly at the meeting point but finish 3.9 km away, at 51.61722, -3.17515 near Cwmfelinfach in the Sirhowy valley. All three finish within 30 m of each other, so it is clearly a deliberate end point rather than an accident.

Gravel - New Tredegar to Tredegar, Gravel - Pontsticill and Trefil, and Gravel - Pant, Pontsticill and Torpantau.

They cannot be closed losslessly. Rotation only works on a route that already returns to the point, and none of these do. No other route in the library rides between those two locations either, so there is no existing recorded geometry to borrow.

The fix needs about 4 km of real road, drawn once. Plan it in Garmin or Komoot from 51.61722, -3.17515 back to 51.647080, -3.205153, export it as GPX, and run:

    python scripts\align_starts.py --at 51.647080,-3.205153 --connector <that file>.gpx --apply

One connector file fixes all three, because they finish in the same place. The script orients it automatically, so it does not matter which way round it was drawn, and it refuses to splice anything whose ends do not actually meet.
