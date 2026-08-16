# About

## What this is

Twenty-six gravel routes across the South Wales valleys, on one interactive map, filterable by the things that actually decide whether a ride happens: how far, how much climbing, and how long it will take you.

1,817 km and 23,013 m of ascent in total. The shortest is 20.5 km, the longest 160.5 km. Twenty-one are loops and five are point-to-point.

## Why it exists

Garmin Connect stores routes perfectly well but shows them one at a time. There is no way to see the whole library laid over a single map, no useful filtering, and sharing with a group means sending individual course links and describing them out loud. Choosing a route with friends was the bit that didn't work.

The aim is that a group can open one link on a phone, filter to something like "under three hours, under 800 metres of climbing", see the surviving candidates side by side, agree on one, and each download the file to their own head unit without further help.

## How the ride time is worked out

Most route tools give you a single duration, and it is either meaningless or it reflects the fitness of whoever planned the route. This one computes time per viewer.

Each route's gradient profile is resampled, and speed is solved segment by segment from the standard cycling power balance, accounting for rolling resistance, gradient, air resistance and combined mass. Descents are capped at a realistic braking speed and a stoppage allowance is added for gates, junctions and regrouping.

Rather than asking for a power figure almost nobody knows, the page asks for your typical average speed, then back-solves the power that makes the whole library average that figure and applies it per segment. Move the slider and every estimate on the page updates for you. Hilly routes come out slower than your average and flat ones faster, which is the point of doing it properly rather than dividing distance by a constant.

Two further controls matter. Total mass, because it changes what the climbs cost you rather than the flat. And surface, because rolling resistance is the single most influential variable on gravel and it genuinely differs between hardpack forest road and loose stone.

## Start and finish points

Every route that can do so begins and ends at the same public meeting point, so a group knows where to gather without reading the file first. This is done by clipping, not by reordering: the residential approach at either end is removed from the file entirely rather than merely moved to the middle.

Nothing is invented. Routes are only ever shortened, never extended toward a point they never reached, because connecting to somewhere a route does not go means fabricating road. Routes that genuinely start elsewhere, the ones you would drive to, keep their own start points.

Exclusion zones are enforced across every published file and verified by an audit that runs before each publish.

## Using the map

Click a duration band to isolate it, click another to add it. Filters narrow by distance, ascent, modelled duration, route type and proximity to the centre of the map. Selecting a route opens its elevation profile, with a crosshair that mirrors your position onto the line on the map, and a download link for the original GPX.

Routes are coloured one per route by default, using six hues crossed with four line styles so that no two are easily confused. Colouring by duration band is available as a switch and reads better when everything is shown at once. There is a dark and a light theme, and four base layers: CyclOSM, OpenTopoMap, standard OSM and satellite imagery.

Individual routes have their own links, so a specific suggestion can be dropped into a group chat and opens with that route selected.

## How it is built

A static site with no server, no database, no accounts and no running cost. The whole thing is a folder of files behind a URL.

The ingest pipeline is Python using only the standard library for GPX, so it runs anywhere without installing anything. It parses each course, computes distance and ascent with hysteresis so GPS noise does not inflate the climbing, detects loops and out-and-backs, simplifies geometry for rendering while keeping the originals intact for download, and derives route names from a gazetteer rather than guesswork.

The map is Leaflet, vendored rather than loaded from a CDN, so there is nothing to break and no key to leak. Deliberately not Google Maps: it needs a billing-enabled API key, and its cartography hides the unsurfaced tracks that are the entire point of gravel.

## Credits

Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors. Tiles by [CyclOSM](https://www.cyclosm.org/) and [OpenTopoMap](https://opentopomap.org/), satellite imagery © Esri. Place names from [GeoNames](https://www.geonames.org/). Built with [Leaflet](https://leafletjs.com/).

Routes are shared for planning. Check conditions, access and the weather before you ride, and remember that a line on a map is not a guarantee of a right of way.
