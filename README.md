# Bike Router

A static, client-side bike-routing PWA. It routes A-to-B **anywhere on the
rideable OSM network**, treating my classified roads as preferences — dedicated
bike roads first, then bike lanes, then bike-friendly streets; ordinary roads
are fine and hostile big roads are heavily penalized but never removed. It runs
entirely in the browser (in-browser A\*), so it hosts on GitHub Pages with no
server and no API keys, and installs to an Android home screen.

Type start/destination addresses (autocomplete via Photon, Nominatim fallback),
tap the map, or use GPS. **▶ Navigate** follows you live with remaining
distance/ETA and re-routes automatically when you leave the line; **GPX**
exports the route to OsmAnd for voice turn-by-turn.

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

## The routing graph

The committed `graph.json` is the **full rideable OSM network** for the area,
with my classes welded on by `osm_way_id` as cost preferences. Why the full
network and not just the bike roads: you sometimes must cross an ordinary road
to connect two nice segments — big roads stay in the graph but at a heavy cost
penalty, so they're used only when unavoidable.

It's rebuilt automatically by CI (`.github/workflows/build-graph.yml`) whenever
`roads.geojson`, `build_graph.py` or `requirements.txt` change — the workflow
runs `make graph` on a GitHub runner, commits the result, and redeploys Pages.
You can also trigger it manually from the Actions tab, or build locally:

1. **Build the routable graph** (needs internet — pulls OSM data):
   ```
   pip install -r requirements.txt
   make graph          # == python build_graph.py roads.geojson -o graph.json
   ```

   > Note for Claude Code: `make graph` reaches out to OSM's Overpass servers.
   > If the sandbox has no outbound network to those hosts the build fails —
   > that's expected; use the CI workflow instead.

2. **Run locally** (serve over HTTP — `file://` breaks the service worker):
   ```
   make serve          # http://localhost:8000
   ```

## Deploy to GitHub Pages

Deploys automatically via `.github/workflows/pages.yml` on every push (Pages
source must be set once to "GitHub Actions" in Settings -> Pages). Open the
Pages URL in Chrome on Android and "Add to Home Screen". Type addresses or tap
a start then a destination to route; the 📍 button starts from GPS.

## Tuning

Cost multipliers live at the top of `build_graph.py` (`CLASS_MULT`,
`HOSTILE_MULT`). Lower = more attractive. Re-run `make graph` after changes.
The frontend heuristic constant `MIN_MULT` in `index.html` must equal the
smallest multiplier you use (keeps A\* optimal — it must never overestimate).
If you add categories to `roads.geojson`, extend `CATEGORY_MAP` in
`build_graph.py`.

## Navigation

**▶ Navigate** live-follows your GPS along the planned line: remaining
distance and ETA update as you ride, the map tracks you (drag to look around,
⌖ to re-center), and drifting >60 m off the line for two fixes re-routes from
where you are. There's no spoken guidance in-app — for voice turn-by-turn,
export **GPX** and import it into OsmAnd.

## How routing works

`graph.json` is `{ nodes: [[lat,lon],...], edges: [[a,b,cost,classCode,[[lat,lon],...]],...] }`.
Edges are directed (oneways encoded). `cost = length_m * class_multiplier`, so a
route over a dedicated path is "shorter" in cost-space and A\* prefers it.
Everything is same-origin except the Leaflet CDN, OSM map tiles, and the
Photon/Nominatim geocoders (all free, no keys).
