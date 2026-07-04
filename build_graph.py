#!/usr/bin/env python3
"""
build_graph.py — produce graph.json for the client-side bike-preference router.

WHY osmnx and not your GeoJSON directly:
Your GeoJSON is OSM-derived so geometry lines up, but raw OSM *ways* aren't
guaranteed to be split at every intersection. osmnx pulls the full rideable
network with correct topology (ways split at shared nodes, oneways encoded),
which is what a router needs. We then paint YOUR three classes onto those
edges — by OSM way id when your file carries one (exact), otherwise by a small
spatial nearest-join (reliable because the geometry is OSM-derived).

KEY DESIGN CHOICE:
We ship the WHOLE rideable network, not just the nice roads. Your classes are
*cost discounts*; hostile big roads get a *penalty* but stay in the graph.
If you routed only on bike infrastructure you'd get disconnected islands and
impossible A-to-B routes.

Usage:
    pip install osmnx geopandas shapely
    python build_graph.py your_bike_classes.geojson -o graph.json

Your GeoJSON needs LineString features each with a class property in
{dedicated, lane, friendly}. An OSM id property (osm_id / @id / "way/123")
makes the join exact but is optional.
"""

import argparse
import json
from pathlib import Path

import geopandas as gpd
import osmnx as ox
from shapely.geometry import box

# ---- cost model — these are your aggression knobs -------------------------
# Multiplier on segment length (metres). Lower = more attractive to the router.
CLASS_MULT = {
    "dedicated": 0.35,   # separated bike road / protected path
    "lane":      0.55,   # painted lane on a normal road
    "friendly":  0.60,   # normal road that's simply nice to ride
    "other":     1.00,   # baseline: everything else rideable
}
# Big roads with no bike class: discouraged hard but NOT removed (keeps graph
# connected so you can still cross one when there's no alternative).
HOSTILE_HIGHWAYS = {
    "primary", "primary_link", "trunk", "trunk_link",
    "secondary", "secondary_link",
}
HOSTILE_MULT = 4.0

# Specific roads to avoid, matched by OSM street name (substring). These are
# forced hostile regardless of highway type or any class in roads.geojson.
DANGEROUS_NAMES = {
    "מטודלה",            # Metudela St, Jerusalem
}

# Colour codes consumed by the frontend legend.
CODE = {"dedicated": 0, "lane": 1, "friendly": 2, "other": 3, "hostile": 4}
# ---------------------------------------------------------------------------

ID_COLS = ("osm_way_id", "osm_id", "osmid", "@id", "way_id", "id")
CLASS_COLS = ("class", "klass", "category", "type", "bike_class")

# Your file's category vocabulary -> internal class names. Add rows here if you
# ever introduce new categories. Internal names pass through unchanged.
CATEGORY_MAP = {
    "bike_road":     "dedicated",
    "bike_lane":     "lane",
    "bike_friendly": "friendly",
}


def parse_osmid(v):
    """12345 / '12345' / 'way/12345' -> 12345 (or None)."""
    try:
        return int(str(v).split("/")[-1])
    except (ValueError, TypeError):
        return None


def edge_osmids(v):
    """osmnx stores osmid as an int or a list (merged ways)."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def load_classes(path):
    gdf = gpd.read_file(path).to_crs(4326)
    ccol = next((c for c in CLASS_COLS if c in gdf.columns), None)
    if ccol is None:
        raise SystemExit(
            f"No class column found. Columns present: {list(gdf.columns)}\n"
            "Add a property like  class = dedicated|lane|friendly"
        )
    gdf = gdf.rename(columns={ccol: "klass"})
    gdf["klass"] = gdf["klass"].astype(str).str.strip().str.lower()
    gdf["klass"] = gdf["klass"].map(lambda v: CATEGORY_MAP.get(v, v))
    gdf = gdf[gdf.klass.isin(CLASS_MULT.keys())].copy()
    return gdf


def fetch_network(class_gdf, pad_deg):
    minx, miny, maxx, maxy = class_gdf.total_bounds
    poly = box(minx, miny, maxx, maxy).buffer(pad_deg)  # ~pad in degrees
    print(f"Fetching rideable OSM network for bbox padded by {pad_deg}deg ...")
    # retain_all=False keeps the largest connected component (drops stubs)
    return ox.graph_from_polygon(poly, network_type="bike", simplify=True,
                                 retain_all=False)


def classify(G, class_gdf, buffer_m):
    """Return {(u, v, key): klass} for edges we could match to your data."""
    edges = ox.graph_to_gdfs(G, nodes=False).reset_index()  # u, v, key, osmid, geometry...
    out = {}

    # 1) exact join on OSM way id, if your file has one
    idcol = next((c for c in ID_COLS if c in class_gdf.columns), None)
    if idcol:
        by_oid = {}
        for _, r in class_gdf.iterrows():
            oid = parse_osmid(r[idcol])
            if oid is not None:
                by_oid[oid] = r["klass"]
        for _, e in edges.iterrows():
            for oid in edge_osmids(e["osmid"]):
                if oid in by_oid:
                    out[(e["u"], e["v"], e["key"])] = by_oid[oid]
                    break
        print(f"  osmid-matched edges: {len(out)}")

    # 2) spatial nearest-join for whatever's left
    matched = set(out.keys())
    rest = edges[[(r.u, r.v, r.key) not in matched
                  for r in edges.itertuples(index=False)]]
    if len(rest):
        crs_m = edges.estimate_utm_crs()
        rm = rest.to_crs(crs_m)
        cm = class_gdf.to_crs(crs_m)[["klass", "geometry"]]
        joined = gpd.sjoin_nearest(rm, cm, max_distance=buffer_m, how="left")
        joined = joined[~joined.index.duplicated(keep="first")]  # drop tie dupes
        n_spatial = 0
        for idx, row in joined.iterrows():
            if isinstance(row.get("klass"), str):
                e = rest.loc[idx]
                out[(e["u"], e["v"], e["key"])] = row["klass"]
                n_spatial += 1
        print(f"  spatially-matched edges: {n_spatial}")
    return out


def is_dangerous(d):
    """True if the edge's OSM name matches DANGEROUS_NAMES (substring)."""
    nm = d.get("name")
    for n in (nm if isinstance(nm, list) else [nm]):
        if isinstance(n, str) and any(t in n for t in DANGEROUS_NAMES):
            return True
    return False


def build_export(G, klass_by_key):
    node_ids = list(G.nodes)
    idx = {n: i for i, n in enumerate(node_ids)}
    nodes = [[round(G.nodes[n]["y"], 6), round(G.nodes[n]["x"], 6)]
             for n in node_ids]

    edges_out, dist = [], {c: 0.0 for c in list(CLASS_MULT) + ["hostile"]}
    n_dangerous = 0
    # osmnx edges are directed: a two-way street is two reciprocal edges, a
    # oneway is one. Emitting them as-is encodes legal direction for free.
    for u, v, k, d in G.edges(keys=True, data=True):
        a, b = idx[u], idx[v]
        length = float(d.get("length", 0.0) or 0.0)
        if is_dangerous(d):
            klass = "hostile"
            n_dangerous += 1
        else:
            klass = klass_by_key.get((u, v, k))
        if klass is None:
            hw = d.get("highway")
            hw = hw[0] if isinstance(hw, list) else hw
            klass = "hostile" if hw in HOSTILE_HIGHWAYS else "other"
        mult = HOSTILE_MULT if klass == "hostile" else CLASS_MULT[klass]
        cost = round(length * mult, 2)
        dist[klass] += length

        geom = d.get("geometry")
        if geom is not None:
            coords = [[round(y, 6), round(x, 6)] for x, y in geom.coords]
        else:
            coords = [nodes[a], nodes[b]]
        edges_out.append([a, b, cost, CODE[klass], coords])

    if DANGEROUS_NAMES:
        print(f"  dangerous-name edges forced hostile: {n_dangerous}")
    return {"nodes": nodes, "edges": edges_out}, dist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("geojson", help="your bike-class GeoJSON")
    ap.add_argument("-o", "--out", default="graph.json")
    ap.add_argument("--pad", type=float, default=0.01,
                    help="degrees to pad the fetch bbox (~1km). Bigger = more "
                         "connective road around your area.")
    ap.add_argument("--buffer", type=float, default=8.0,
                    help="metres for the spatial nearest-join fallback")
    args = ap.parse_args()

    cls = load_classes(args.geojson)
    print(f"Loaded {len(cls)} classified segments: "
          f"{cls.klass.value_counts().to_dict()}")
    G = fetch_network(cls, args.pad)
    print(f"Network: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    kbk = classify(G, cls, args.buffer)
    export, dist = build_export(G, kbk)

    Path(args.out).write_text(json.dumps(export, separators=(",", ":")))
    km = {k: round(v / 1000, 1) for k, v in dist.items()}
    size_mb = Path(args.out).stat().st_size / 1e6
    print(f"\nWrote {args.out}  ({size_mb:.1f} MB, {len(export['edges'])} edges)")
    print(f"Length by class (km): {km}")
    print("Tip: gzip is applied automatically by GitHub Pages for .json.")


if __name__ == "__main__":
    main()
