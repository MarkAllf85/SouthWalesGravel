---
name: concept
description: What Bike Route Explorer is, why it exists, and what "done" looks like
type: project
updated: 2026-08-16
---

# South Wales Gravel Routes — Concept

## The problem

Garmin Connect holds the routes and works well enough as a store, but it presents courses one at a time. There is no way to see the whole library laid over a single map, no meaningful filtering by duration or distance, and sharing with a group means sending individual course links. Choosing a gravel route with friends currently means someone scrolling their own Garmin account and describing options out loud.

## What we are building

A static, shareable web map that renders every saved route at once, with client-side filtering and a per-route download of the original course file so anyone can push it straight to their own head unit.

The build is deliberately static. Route data changes rarely, the audience is a handful of people, and a static site means no server, no database, no running cost and no authentication to maintain. The whole thing is a folder of files behind a public URL.

## Core capability

Every route renders on one interactive map, colour-coded and individually toggleable. Filters narrow the visible set by distance, total ascent, estimated duration, start location and route type (loop or point to point). Selecting a route opens a detail panel with the elevation profile, key statistics and download links for both GPX and FIT where available.

Estimated duration is computed per viewer rather than baked in. Garmin's estimate reflects Mark's fitness profile and is useless to anyone else in the group, so the map computes time from the route's own gradient profile against a rider power setting the viewer controls. Move the slider, every duration on the page updates.

## Success criteria

The project is working when a group can open one link on a phone, filter to "under three hours, under 800 metres of climbing, starting within 20 km of Caerphilly", see the surviving candidates side by side on a map, agree on one, and each download the file to their own device without further help.

## Non-goals

Route creation and editing stay in Garmin or Komoot. This tool reads and presents, it does not author. There is no user accounts layer, no comments, no ride logging and no live tracking. Automatic sync from Garmin is explicitly deferred, not designed out.

## Constraints worth remembering

Route files are the source of truth and they live in this folder. The site is generated from them, never edited by hand. Anything the map shows must be derivable from a course file or from a lookup the build script performs, so that a rebuild is always reproducible.
