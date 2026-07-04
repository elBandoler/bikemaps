# Bike Router

A static, client-side bike-routing PWA. It routes on **my** classified roads —
preferring dedicated bike roads, then bike lanes, then bike-friendly streets —
and runs entirely in the browser (in-browser A\*), so it hosts on GitHub Pages
with no server, no API keys, and installs to an Android home screen.

Source data is `roads.geojson`: 274 OSM-derived ways around Jerusalem
(194 dedicated bike roads, 75 bike-friendly, 5 bike lanes), each carrying an
`osm_way_id` for an exact join.

## Layout

```
index.html            the app: Leaflet map + A* router + GPX export (static)
graph.json            the routing graph the app loads (see "Two phases" below)
build_graph.py        pipeline: OSM network + my classes -> graph.json
roads.geojson         my classification (LineStrings w/ category + osm_way_id)
manifest.webmanifest  PWA manifest
sw.js                 service worker (offline app shell)
icon.svg              app icon
requirements.txt      python deps for the build step only
Makefile              `make graph`, `make serve`, `make clean`
```

## Two phases (important)

**The committed `graph.json` is a PREVIEW** built from the bike infrastructure
only. That means it's fragmented into ~53 disconnected components, so routing
works *within* a component (e.g. the HaMesila spine) but not across gaps. It's
enough to load the app and see the network. To get real point-to-point routing,
regenerate it:

1. **Build the routable graph** (needs internet — pulls OSM data):
   ```
   pip install -r requirements.txt
   make graph          # == python build_graph.py roads.geojson -o graph.json
   ```
   This fetches the full *rideable* OSM network for the area via osmnx, welds my
   classes onto the matching edges by `osm_way_id`, and overwrites `graph.json`.
   Now A-to-B works anywhere, preferring my roads. Why the full network and not
   just the bike roads: you sometimes must cross an ordinary road to connect two
   nice segments — big roads stay in the graph but at a heavy cost penalty, so
   they're used only when unavoidable.

   > Note for Claude Code: `make graph` reaches out to OSM's Overpass and
   > Nominatim servers. If this sandbox has no outbound network to those hosts,
   > the build will fail — that's expected; the committed preview `graph.json`
   > still lets `make serve` work. Run the build wherever OSM is reachable.

2. **Run locally** (serve over HTTP — `file://` breaks the service worker):
   ```
   make serve          # http://localhost:8000
   ```

## Deploy to GitHub Pages

Push this repo, then Settings -> Pages -> "Deploy from a branch" -> your branch
/ root. Open the Pages URL in Chrome on Android and "Add to Home Screen".
Tap a start then a destination to route; the 📍 button routes from GPS.

## Tuning

Cost multipliers live at the top of `build_graph.py` (`CLASS_MULT`,
`HOSTILE_MULT`). Lower = more attractive. Re-run `make graph` after changes.
The frontend heuristic constant `MIN_MULT` in `index.html` must equal the
smallest multiplier you use (keeps A\* optimal — it must never overestimate).
If you add categories to `roads.geojson`, extend `CATEGORY_MAP` in
`build_graph.py`.

## Navigation

This plans and draws routes; it isn't turn-by-turn. The **GPX** button exports
the route — import it into OsmAnd on the phone to get spoken navigation of the
exact line.

## How routing works

`graph.json` is `{ nodes: [[lat,lon],...], edges: [[a,b,cost,classCode,[[lat,lon],...]],...] }`.
Edges are directed (oneways encoded). `cost = length_m * class_multiplier`, so a
route over a dedicated path is "shorter" in cost-space and A\* prefers it.
Everything is same-origin except the Leaflet CDN and OSM map tiles.
